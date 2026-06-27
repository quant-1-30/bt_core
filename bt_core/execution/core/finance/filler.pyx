# distutils: language = c++
# cython: profile=False
# cython: language_level=3

import asyncio
import pyarrow as pa
import numpy as np
import polars as pl
from functools import partial

from libc.math cimport floor 

from bt_core.execution.gateway.interface import async_gt # cimport the async wrapper
from bt_core.execution.gateway.interface cimport AsyncGateway  # cimport the enum type

# cdef func differ from cdef class
from bt_core.utils.dateintern cimport ts2intdt
from bt_core.execution.core.finance.order cimport OrderCoreData, ExecType
from bt_core.execution.core.finance.position cimport Position
from bt_core.execution.core.finance.slippage import _slip
from bt_core.execution.core.finance.comminfo cimport CommInfo_Stocks
from bt_core.execution.core.finance.trade cimport OrderExecutionBit

from bt_protocol._protocol import QueryBody
from bt_protocol.constant import RpcTopic

cimport numpy as cnp
cnp.import_array() # initialize numpy C-API

# ---------------------------------------------------------------------
# buy mulitply 100 and sell contain fract
# ---------------------------------------------------------------------

cdef inline int calculate(Order order, Position p_obj, double cash, double price):
    cdef AssetCore info = order.info
    cdef OrderCoreData core = order.core
    cdef double tick_value, sizer_cash
    cdef int32_t sizer_size
    cdef bint is_buy = order.isbuy
    
    tick_value = price * info.tick_size
    sizer_cash = core.sizer_ratio * cash

    if not is_buy:
        size = p_obj.get_available()
        # print("not is_buy filler calculate size :", size)
        sizer_size = <int32_t>(size * core.sizer_ratio) 
        return sizer_size 

    if tick_value > cash:
        return 0

    raw_shares = floor(sizer_cash / tick_value)
    return <int32_t>(raw_shares * info.tick_size)


# ---------------------------------------------------------------------
# execute_ratio base high / low
# ---------------------------------------------------------------------

cdef double _execute_factor(double bar_high, double bar_low, double bar_close, 
                            double p_max, double p_min, bint is_buy) noexcept nogil:
    cdef double bar_amplitude = 0.0
    cdef double rel_eps = 1e-6  
    
    if bar_low <= 0 or p_min <= 0 or p_max <= 0:
        return 0.0

    if (p_max - p_min) / p_min < rel_eps:
        return 0.0

    bar_amplitude = (bar_high - bar_low) / bar_low

    if is_buy and (p_max - bar_close) / p_max < rel_eps:
        if bar_amplitude < rel_eps:
            return 0.0  
        else:
            return min(bar_amplitude / 0.005, 1.0)

    if not is_buy and (bar_close - p_min) / p_min < rel_eps:
        if bar_amplitude < rel_eps:
            return 0.0  
        else:
            return min(bar_amplitude / 0.005, 1.0)

    return 1.0


cdef class PseudoFiller:
    """
        Tradeplan to generate possible orderbody
    """

    def __init__(self, double impact = 0.05, int32_t batch_size = 1000, double slip_perc = 0.005, slip_name="default"):

        self.impact = impact
        self.batch_size = batch_size
        self.slip = _slip[slip_name](slip_perc=slip_perc)
        self.comm = CommInfo_Stocks() 

        self._lines_cache = {}
        self._current_cache_dt = 0

    # ----------------------------------------------------
    # Tick Engine
    # ----------------------------------------------------
    async def _preload(self, Order ord, cache=None):
        """
            [[tick, open, high, low, close, volume, amount]]
        """
        cdef OrderCoreData core = ord.core 
        cdef int32_t int_dt = ts2intdt(core.created_dt)
        cdef tuple cache_key = (core.sid, int_dt)

        if self._current_cache_dt != int_dt:
            self._lines_cache.clear()
            self._current_cache_dt = int_dt

        if cache_key in self._lines_cache:
            return self._lines_cache[cache_key]
        
        # rpc api
        cdef Lines lines = Lines() 
        cdef object request = QueryBody(int_dt, int_dt, [core.sid])

        async def loader(object req):
              cdef double[:, ::1] np_view
              cdef list float_column =["tick", "open", "high", "low", "close", "volume", "amount"]
              cdef object df, cast_df, np_arr

              try:
                  data = await async_gt.rpc(req, RpcTopic.Tick) # sid: pl.DataFrame
                  df = data[req.sid[0]]

                  cast_df = df.select(pl.col(float_column).cast(pl.Float64))
                  # 2D Numpy Array np.ascontiguousarray double[:, ::1] (C-Contiguous)
                  np_arr = np.ascontiguousarray(cast_df.to_numpy())

                  np_view = np_arr # Cython MemoryView
                  lines.batch_load(np_view)
              except GeneratorExit:
                  print("GeneratorExit Error means error during line batch_load")
                  pass
              except Exception as e:
                  print(f"Loader Error: {e}")

        if cache is not None:
            data = await cache.get_or_load(request, loader)
            lines.batch_load(data)
        else:
            await loader(request)

        # cache
        self._lines_cache[cache_key] = lines
        return lines

    # ----------------------------------------------------
    # Execution Price Engine
    # ----------------------------------------------------
    cdef (int32_t, double) _find_limit_execution(self, int32_t loc, double limit_price, bint is_buy, Lines lines):
        """Price Bit Policy """
        cdef int32_t n = len(lines)
        cdef int32_t i
        
        for i in range(loc, n): 
            if is_buy and lines.low[i] <= limit_price:
                open_i = lines.open[i]
                return i, open_i if open_i > limit_price else limit_price
            elif not is_buy and lines.high[i] >= limit_price:
                open_i = lines.open[i]
                return i, open_i if open_i > limit_price else limit_price
        return -1, 0.0

    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines): 
        cdef double p_max = lines.max(), p_min = lines.min()

        if (p_max - p_min) / p_min < 0.01: # filter reach limit  
            return
        
        cdef OrderExecutionBit order_bit
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy
        cdef bint is_limit = (core.exec_type == ExecType.Limit)
        cdef bint is_close = (core.exec_type == ExecType.Close)

        cdef int32_t start_exec_loc = np.searchsorted(lines.tick, core.created_dt) 
        cdef int32_t n = len(lines)

        cdef double order_target_price, order_price, slip_price, comm
        cdef int32_t total_size, filler_size, exec_loc, remains

        # ==========================================
        # 1. calculate price
        # ==========================================
        order_target_price = core.limit_price if is_limit else (lines.close[start_exec_loc] if is_close else lines.open[start_exec_loc]) 

        # ==========================================
        # 2. calculate size
        # ==========================================

        total_size = core.size if core.size > 0 else calculate(order, p_obj, cash, order_target_price) 

        remains = total_size

        # ==========================================
        # 3. Eager Execute 
        # ==========================================
        while remains > 0 and start_exec_loc < n:

            if is_limit:
                exec_loc, order_price = self._find_limit_execution(start_exec_loc, order_target_price, is_buy, lines)
            else:
                exec_loc = start_exec_loc
                order_price = lines.close[exec_loc] if is_close else lines.open[exec_loc] 

            if exec_loc < 0: break 

            fill_factor = _execute_factor( lines.high[exec_loc], lines.low[exec_loc], lines.close[exec_loc], p_max, p_min, is_buy)
            
            if fill_factor <= 0.0:
                start_exec_loc += 1
                continue 
            
            filler_size = min(remains, <int32_t>(lines.volume[exec_loc] * self.impact * fill_factor))
            if filler_size <= 0:
                start_exec_loc = exec_loc + 1
                continue

            # slippage and commission
            slip_price = self.slip.get_slip_price(order_price, lines.open[exec_loc], lines.high[exec_loc], lines.low[exec_loc], lines.close[exec_loc], is_buy)
            comm = self.comm(order, filler_size, slip_price)
            
            order_bit = OrderExecutionBit(
                            order_id = core.order_id,
                            executed_dt = lines.tick[exec_loc],
                            executed_size = filler_size, 
                            executed_price = slip_price, 
                            comm = comm,
                            isbuy = is_buy)
                              
            order.execute(total_size, order_bit, order_price) # update core size / price and append exbit

            remains -= filler_size
            start_exec_loc = exec_loc + 1

    async def __call__(self, Order order, double cash, Position p_obj):
        try:
            lines = await self._preload(order)
            if len(lines) > 0: self._execute(order, p_obj, cash, lines)
        except Exception as e:
            print(f"Error during filler preload: {e}")
            return

# =====================================================================
# AlgoFiller
# =====================================================================
cdef class AlgoFiller(PseudoFiller):

    def __init__(self, bint is_vwap=True, double impact=0.05, int32_t batch_size=1000, double slip_perc=0.005):
        super().__init__(impact=impact, batch_size=batch_size, slip_perc=slip_perc)
        self.is_vwap = is_vwap
     
    # -------------------------------------------------------------
    # VWAP/TWAP
    # -------------------------------------------------------------
    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines): 
            cdef OrderCoreData core = order.core
            cdef OrderExecutionBit order_bit
            cdef int32_t start_exec_loc = np.searchsorted(lines.tick, core.created_dt)
            cdef int32_t n = len(lines)
            
            cdef int32_t total_bars = n - start_exec_loc
            if total_bars <= 0: return
            
            # startswith first open bar
            cdef int32_t total_size = core.size if core.size > 0 else calculate(order, p_obj, cash, lines.open[start_exec_loc])
            if total_size <= 0: return 
                
            cdef int32_t remains = total_size
            cdef int32_t filled_so_far = 0
            cdef int32_t chunk_size = 0
            
            cdef double expected_ratio = 0.0
            cdef double target_fill = 0.0
            
            cdef double order_price, slip_price, comm, fill_factor
            cdef bint is_buy = order.isbuy
            cdef double p_max = lines.max(), p_min = lines.min()
     
            # ==========================================================
            # VWAP / TWAP 
            # ==========================================================
            cdef double total_market_vol = 0.0
            cdef double accum_market_vol = 0.0
            cdef int32_t bars_passed = 0
            
            if self.is_vwap:
                for i in range(start_exec_loc, n): total_market_vol += lines.volume[i]
                if total_market_vol <= 0: return
 
            # ==========================================================
            # Target Tracking
            # ==========================================================
            for exec_loc in range(start_exec_loc, n):
                if remains <= 0: break
               
                # Schedule Ratio
                if self.is_vwap:
                    accum_market_vol += lines.volume[exec_loc]
                    expected_ratio = accum_market_vol / total_market_vol
                else:
                    bars_passed += 1
                    expected_ratio = <double>bars_passed / total_bars
                    
                target_fill = (total_size * expected_ratio) - filled_so_far
                if target_fill <= 0:
                    continue

                # fill size factor  
                fill_factor = _execute_factor(lines.high[exec_loc], lines.low[exec_loc], lines.close[exec_loc], p_max, p_min, is_buy)
                if fill_factor == 0.0: 
                    continue 
               
                chunk_size = <int32_t>(target_fill * fill_factor)
               
                # near end sell fract size
                if exec_loc == n - 1 and not is_buy:
                    pass 
                else:
                    chunk_size = (chunk_size // 100) * 100 # buy must 100 mulitply
                    
                if chunk_size > remains: 
                    chunk_size = remains
                if chunk_size <= 0: 
                    continue
 
                # ==========================================================
                # execute
                # ==========================================================
                order_price = lines.close[exec_loc]
                slip_price = self.slip.get_slip_price(order_price, lines.open[exec_loc], lines.high[exec_loc], lines.low[exec_loc], lines.close[exec_loc], is_buy)
                comm = self.comm(order, chunk_size, slip_price)
            
                order_bit = OrderExecutionBit(
                                order_id = core.order_id,
                                executed_dt = lines.tick[exec_loc],
                                executed_size = chunk_size, 
                                executed_price = slip_price, 
                                comm = comm,
                                isbuy = is_buy)

                order.execute(total_size, order_bit, order_price)
               
                # advance
                filled_so_far += chunk_size
                remains -= chunk_size


cdef class VWAPFiller(AlgoFiller):
    def __init__(self, **kwargs):
        super().__init__(is_vwap=True, **kwargs)


cdef class TWAPFiller(AlgoFiller):
    def __init__(self, **kwargs):
        super().__init__(is_vwap=False, **kwargs)


_fillers = {
    b"default": PseudoFiller(),
    b"vwap": VWAPFiller(), 
    b"twap": TWAPFiller()
}
