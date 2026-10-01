# distutils: language = c++
# cython: profile=False
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True

import asyncio
import logging
import numpy as np
import polars as pl

from libc.stdint cimport int32_t, int64_t

from bt_core.execution.gateway.interface import async_gt
from bt_core.utils.dateintern cimport ts2intdt, elapse_seconds
from bt_core.execution.core.finance.order cimport OrderCoreData, ExecType, Order
from bt_core.execution.core.finance.position cimport Position
from bt_core.execution.core.finance.slippage import _slip
from bt_core.execution.core.finance.comminfo cimport CommInfo_Stocks, CommInfoBase
from bt_core.execution.core.finance.trade cimport OrderExecutionBit

from bt_protocol._protocol import QueryBody
from bt_protocol.constant import RpcTopic

cimport numpy as cnp
cnp.import_array()

logger = logging.getLogger(__name__)


# =====================================================================
# Module-level helpers
# =====================================================================

cdef inline int32_t _round_share_lot(int32_t chunk_size, 
                                      int32_t remains,
                                      int32_t tick_size, 
                                      bint is_buy) noexcept nogil:
    """A Stock Principle
    - buy: multiply tick_size
    - sell:
      1. chunk_size >= remains sell all
      2. remains < tick_size sell all
      3. step sell multipy tick_size
    """
    if chunk_size <= 0 or remains <= 0:
        return 0
    if tick_size <= 1:
        return chunk_size if chunk_size < remains else remains

    if is_buy:
        return (chunk_size // tick_size) * tick_size
    else:
        if chunk_size >= remains or remains < tick_size:
            return remains
        return (chunk_size // tick_size) * tick_size


cdef const double PRICE_TICK = 0.01


cdef inline int32_t calculate(Order order, Position p_obj, 
                              double cash, double price,
                              Slippage slip, CommInfoBase comm):
    cdef AssetCore info = order.info
    cdef OrderCoreData core = order.core
    cdef bint is_buy = order.isbuy
    cdef int32_t tick_sz = info.tick_size if info.tick_size > 0 else 100

    cdef int32_t avail, want_sell
    cdef double budget, total

    if core.sizer_ratio <= 0.0:
        return 0

    if not is_buy:
        # sizer_ratio (0, 1.0)
        avail = p_obj.get_available()
        if avail <= 0:
            return 0
        want_sell = <int32_t>(avail * core.sizer_ratio)
        return _round_share_lot(min(want_sell, avail), avail, tick_sz, False)

    if cash <= 0.0:
        return 0

    cdef double slip_price = slip.get_slip_price(price, price, price, price, price, True)
    if slip_price <= 0.0:
        slip_price = price

    cdef double cost_per_lot = slip_price * tick_sz * (1.0 + comm.get_comm_rate(order))
    if cost_per_lot <= 0.0:
        return 0

    # sizer_ratio (<1.0) x cash
    budget = core.sizer_ratio * cash
    if budget < cost_per_lot:
        return 0

    total = budget / cost_per_lot # avoid exceed 1e7              
    return <int32_t>total * tick_sz


cdef inline bint _limit_fillable(double bar_open,
                                 double bar_high,
                                 double bar_low,
                                 double bar_close,
                                 double limit_ratio,
                                 bint is_buy) noexcept nogil:
    if bar_low <= 0.0 or bar_high <= 0.0:
        return False

    if limit_ratio >= 1.0:
        return True

    cdef double spread = bar_high - bar_low

    if spread <= 1.5 * PRICE_TICK:
        if is_buy and (bar_close >= bar_high - 1 * PRICE_TICK):
            return False

        if (not is_buy) and (bar_close <= bar_low + 1 * PRICE_TICK):
            return False

    return True


# =====================================================================
# PseudoFiller
# =====================================================================

cdef class PseudoFiller:

    def __init__(self, 
                    double impact=0.05, 
                    double slip_perc=0.005, 
                    str slip_name="default"):
        self.impact = impact
        self.slip = _slip[slip_name](slip_perc=slip_perc)
        self.comm = CommInfo_Stocks()
        self._lines_cache = {}
        self._current_cache_dt = 0

    cdef Lines _preload(self, Order ord, object loop):
        cdef OrderCoreData core = ord.core
        cdef int32_t int_dt = ts2intdt(core.created_dt)
        cdef tuple cache_key = (core.sid, int_dt)
        cdef Lines lines

        if self._current_cache_dt != int_dt:
            self._lines_cache.clear()
            self._current_cache_dt = int_dt

        if cache_key in self._lines_cache:
            return <Lines>self._lines_cache[cache_key]

        lines = Lines()
        cdef object request = QueryBody(int_dt, int_dt, [core.sid])

        async def loader(object req):
            cdef double[:, ::1] np_view
            cdef list cols = ["tick", "open", "high", "low", "close", "volume", "amount"]
            cdef object df, cast_df, np_arr
            try:
                data = await async_gt.rpc(req, RpcTopic.Tick)
                df = data[req.sid[0]]
                cast_df = df.select(pl.col(cols).cast(pl.Float64))
                np_arr = np.ascontiguousarray(cast_df.to_numpy())
                np_view = np_arr
                lines.batch_load(np_view)
            except GeneratorExit:
                pass
            except Exception:
                logger.exception("tick loader failed for sid %s", core.sid)

        asyncio.run_coroutine_threadsafe(loader(request), loop).result(timeout=30)
        self._lines_cache[cache_key] = lines
        return lines

    cdef (int32_t, double) _find_limit_execution(self, int32_t loc, double limit_price,
                                                 bint is_buy, Lines lines):
        cdef int32_t n = len(lines)
        cdef int32_t i
        cdef double open_i
        for i in range(loc, n):
            if is_buy and lines.low[i] <= limit_price:
                open_i = lines.open[i]
                return i, limit_price if open_i > limit_price else open_i
            elif not is_buy and lines.high[i] >= limit_price:
                open_i = lines.open[i]
                return i, limit_price if open_i < limit_price else open_i
        return -1, 0.0

    cdef double _get_exec_price(self, Order order, Lines lines, int32_t loc):
        cdef OrderCoreData core = order.core
        if core.exec_type == ExecType.Limit:
            return core.price
        elif core.exec_type == ExecType.Close:
            return lines.close[loc]
        return lines.open[loc]

    cdef (int32_t, double) _fill(self, Order order, int32_t total_size, int32_t exec_loc,
                                 int32_t req_size, bint is_buy, double order_price, Lines lines,
                                 double cash):
        if req_size <= 0:
            return 0, 0.0

        cdef OrderCoreData core = order.core
        cdef AssetCore info = order.info
        cdef int32_t fill_size = req_size
        cdef double unit_cost, comm_rate
        cdef int32_t max_by_cash

        cdef int32_t tick_sz = info.tick_size if info.tick_size > 0 else 100

        cdef double slip_price = self.slip.get_slip_price(
            order_price, lines.open[exec_loc], lines.high[exec_loc],
            lines.low[exec_loc], lines.close[exec_loc], is_buy)

        comm_rate = self.comm.get_comm_rate(order)
   
        if is_buy:
            if cash <= 0.0 or slip_price <= 0.0:
                return 0, 0.0

            unit_cost = slip_price * (1.0 + comm_rate)
            max_by_cash = (<int32_t>(cash / (unit_cost * tick_sz))) * tick_sz
            if fill_size > max_by_cash:
                fill_size = max_by_cash

        cdef double comm = slip_price * fill_size * comm_rate

        cdef double cash_change
        if is_buy:
            cash_change = slip_price * fill_size + comm  
        else:
            cash_change = slip_price * fill_size - comm  

        cdef OrderExecutionBit order_bit = OrderExecutionBit(
            order_id=core.order_id,
            executed_dt=lines.tick[exec_loc],
            executed_size=fill_size,
            executed_price=slip_price,
            comm=comm,
            isbuy=is_buy)

        order.execute(total_size, order_bit, order_price)
        return fill_size, cash_change

    cdef (int32_t, double, int32_t) _prepare_execute(self, Order order, Position p_obj,
                                                     double cash, Lines lines):
        cdef OrderCoreData core = order.core
        cdef AssetCore info = order.info
        cdef bint is_buy = order.isbuy

        if core.created_dt <= 0:
            order.reject()   
            return -1, 0.0, 0

        cdef int32_t n = len(lines)
        if n <= 0:
            order.expire()   
            return -1, 0.0, 0

        cdef int32_t start_loc = lines.get_loc(core.created_dt)
        if start_loc < 0 or start_loc >= n:
            order.expire()   
            return -1, 0.0, 0

        cdef double target_price = self._get_exec_price(order, lines, start_loc)
        if target_price <= 0.0:
            return -1, 0.0, 0

        cdef int32_t total_size = core.size if core.size > 0 else calculate(order, p_obj, cash, target_price, self.slip, self.comm)

        if total_size <= 0:
            order.reject()
            return -1, 0.0, 0
        
        if not is_buy:
            totol_size = min(p_obj.get_available(), total_size)

        return start_loc, target_price, total_size

    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines):
        cdef AssetCore info = order.info
        cdef bint is_buy = order.isbuy
        cdef bint is_limit = (order.core.exec_type == ExecType.Limit)
        cdef int32_t tick_sz = info.tick_size if info.tick_size > 0 else 100
        cdef int32_t n = len(lines)

        cdef int32_t start_loc, total_size
        cdef double target_price
        start_loc, target_price, total_size = self._prepare_execute(order, p_obj, cash, lines)
        if start_loc < 0:
            return

        cdef int32_t remains = total_size

        cdef double limit_ratio = order.core.limit_ratio
        cdef int32_t exec_loc, filler_size, filled
        cdef double order_price, cost

        while remains > 0 and start_loc < n:
            if is_limit:
                exec_loc, order_price = self._find_limit_execution(
                    start_loc, target_price, is_buy, lines)
            else:
                exec_loc = start_loc
                order_price = self._get_exec_price(order, lines, exec_loc)

            if exec_loc < 0:
                break

            if not _limit_fillable(
                    lines.open[exec_loc], lines.high[exec_loc], lines.low[exec_loc], lines.close[exec_loc],
                    limit_ratio, is_buy):
                start_loc = exec_loc + 1
                continue

            filler_size = min(remains, <int32_t>(lines.volume[exec_loc] * self.impact))
            filler_size = _round_share_lot(filler_size, remains, tick_sz, is_buy)
            if filler_size <= 0:
                start_loc = exec_loc + 1
                continue

            filled, cost = self._fill(order, total_size, exec_loc, filler_size, is_buy,
                                       order_price, lines, cash)
            if filled <= 0:
                if is_buy and cash <= 0.0:
                    break
                start_loc = exec_loc + 1
                continue

            if is_buy:
                cash -= cost
            remains -= filled
            start_loc = exec_loc + 1

        if remains > 0:
            order.expire()

    def __call__(self, Order order, double cash, Position p_obj, object loop):
        if order.core.created_dt <= 0:
            order.reject()
            return

        cdef Lines lines
        try:
            lines = self._preload(order, loop)
            if lines is not None and len(lines) > 0:
                self._execute(order, p_obj, cash, lines)
            else:
                order.expire()
        except Exception:
            logger.exception(
                "filler execution failed for order %s sid %s",
                order.core.order_id, order.core.sid)
            order.reject()


# =====================================================================
# AlgoFiller (VWAP / TWAP) 
# =====================================================================


cdef inline double _get_algo_price(
    OrderCoreData core,
    const double* p_open,
    const double* p_high,
    const double* p_low,
    const double* p_close,
    const double* p_volume,
    const double* p_amount,
    int32_t exec_loc,
    double target_price,
    bint is_limit,
    bint is_buy,
    bint is_vwap
) nogil:
    cdef double bar_vol, bar_amt

    if is_limit:
        if is_buy:
            return p_open[exec_loc] if p_open[exec_loc] < target_price else target_price
        else:
            return p_open[exec_loc] if p_open[exec_loc] > target_price else target_price

    if core.exec_type == ExecType.Open:
        return p_open[exec_loc]
    elif core.exec_type == ExecType.Close:
        return p_close[exec_loc]

    if is_vwap:
        bar_vol = p_volume[exec_loc]
        bar_amt = p_amount[exec_loc]
        if bar_vol > 0.0 and bar_amt > 0.0:
            return bar_amt / bar_vol
        elif p_high[exec_loc] > 0.0 and p_low[exec_loc] > 0.0:
            return (p_high[exec_loc] + p_low[exec_loc] + p_close[exec_loc]) / 3.0
        return p_open[exec_loc]
    else:
        if p_high[exec_loc] > 0.0 and p_low[exec_loc] > 0.0:
            return (p_open[exec_loc] + p_high[exec_loc] + p_low[exec_loc] + p_close[exec_loc]) * 0.25
        return p_open[exec_loc]


cdef class AlgoFiller(PseudoFiller):
    # TWAP: = total x (k+1)/ bars
    # VWAP: = total x accumlated_vol / v_hat

    def __init__(self, 
                    double impact=0.05,
                    double slip_perc=0.005,
                    str slip_name="default", 
                    int32_t lookback_days=5, 
                    bint is_vwap=True, 
                    **kwargs):
        super().__init__(impact=impact, slip_perc=slip_perc, slip_name=slip_name)
        self.is_vwap = is_vwap
        self.lookback_days = lookback_days if lookback_days > 0 else 5
        self._vhat_cache = {}

    cdef Lines _preload(self, Order ord, object loop):
        cdef OrderCoreData core = ord.core
        cdef int32_t int_dt = ts2intdt(core.created_dt)
        
        if self._current_cache_dt != int_dt:
            self._vhat_cache.clear()

        cdef Lines lines = PseudoFiller._preload(self, ord, loop)
        if self.is_vwap:
            self._ensure_window_volume(core, int_dt, loop)
        return lines

    cdef void _ensure_window_volume(self, OrderCoreData core, int32_t int_dt, object loop):
        """v_hat: [T-lookback, T-1]
        """
        cdef int64_t created = <int64_t>core.created_dt

        cdef tuple key = (core.sid, ts2intdt(<double>created))  # same with _execute key
        if key in self._vhat_cache:
            return

        cdef int64_t start_sec = elapse_seconds(created)

        cdef object request = QueryBody(
            ts2intdt(<double>(created - <int64_t>self.lookback_days * 86400)),
            ts2intdt(<double>(created - 86400)),
            [core.sid])

        async def hist_loader(object req, bytes sid, int64_t start_sec):
            cdef double v = 0.0
            cdef object df, bj_expr, per_day
            try:
                data = await async_gt.rpc(req, RpcTopic.Tick)
                df = data.get(sid)
                if df is not None and df.height > 0:
                    bj_expr = pl.col("tick").cast(pl.Int64) + 28800
                    df = df.select(
                        (bj_expr // 86400).alias("day"),
                        (bj_expr % 86400).alias("sec"),
                        pl.col("volume").cast(pl.Float64))
                    df = df.filter((pl.col("sec") >= start_sec) & (pl.col("sec") < 54000)) # 15:00
                    per_day = df.group_by("day").agg(pl.col("volume").sum().alias("v"))
                    per_day = per_day.filter(pl.col("v") > 0.0)
                    if per_day.height > 0:
                        v = per_day["v"].mean()
                return v
            except GeneratorExit:
                raise
            except Exception:
                logger.exception("volume history loader failed for sid %s", sid)
                return 0.0

        cdef double v_hat = 0.0
        try:
            v_hat = asyncio.run_coroutine_threadsafe(
                hist_loader(request, core.sid, start_sec),
                loop).result(timeout=3)
        except Exception:
            logger.warning(
                "window-volume backfill failed for sid %s; vwap degrades to twap",
                core.sid)
            v_hat = 0.0

        self._vhat_cache[key] = v_hat

    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines):
        cdef OrderCoreData core = order.core
        cdef AssetCore info = order.info
        cdef bint is_buy = order.isbuy
        cdef bint is_limit = (core.exec_type == ExecType.Limit)
        cdef int32_t tick_sz = info.tick_size if info.tick_size > 0 else 100

        cdef int32_t n = len(lines)
        cdef int32_t start_loc, total_size
        cdef double target_price
        start_loc, target_price, total_size = self._prepare_execute(order, p_obj, cash, lines)
        if start_loc < 0:
            return

        cdef int32_t end_loc = n                  # 执行窗口 = 当日剩余全部 bar
        cdef int32_t total_bars = n - start_loc

        cdef int32_t remains = total_size

        cdef double limit_ratio = order.core.limit_ratio

        # VWAP
        cdef double v_hat = 0.0
        if self.is_vwap:
            v_hat = self._vhat_cache.get((core.sid, ts2intdt(core.created_dt)), 0.0)

        cdef const double* p_open = lines.open
        cdef const double* p_high = lines.high
        cdef const double* p_low = lines.low
        cdef const double* p_close = lines.close
        cdef const double* p_volume = lines.volume
        cdef const double* p_amount = lines.amount

        cdef int32_t filled_so_far = 0
        cdef double s_exec = 0.0
        cdef int32_t exec_loc, target_cum, target_fill, max_liq, chunk_size, filled
        cdef double frac, order_price, cost, bar_vol

        for exec_loc in range(start_loc, end_loc):
            if remains <= 0:
                break

            bar_vol = p_volume[exec_loc]
            if bar_vol != bar_vol: # Nan
                bar_vol = 0.0
            s_exec += bar_vol

            if is_limit:
                if is_buy and p_low[exec_loc] > target_price:
                    continue
                if (not is_buy) and p_high[exec_loc] < target_price:
                    continue

            if not _limit_fillable(
                    p_open[exec_loc], p_high[exec_loc], p_low[exec_loc], p_close[exec_loc],
                    limit_ratio, is_buy):
                continue
            
            twap_frac = <double>(exec_loc - start_loc + 1) / <double>total_bars
            if v_hat > 0.0:
                vwap_frac = s_exec / v_hat
                if vwap_frac > 1.0:
                    vwap_frac = 1.0
                
                # avoid n bar swallow 
                frac = vwap_frac if vwap_frac < (twap_frac * 1.5) else (twap_frac * 1.5)
                if frac > 1.0:
                    frac = 1.0       
            else:
                frac = <double>(exec_loc - start_loc + 1) / <double>total_bars  # TWAP degrade

            target_cum = <int32_t>(<double>total_size * frac + 0.5)
            target_fill = target_cum - filled_so_far

            if target_fill <= 0:
                continue
            if target_fill > remains:
                target_fill = remains

            if self.impact > 0.0:
                max_liq = <int32_t>(bar_vol * self.impact)
                chunk_size = target_fill if target_fill < max_liq else max_liq
            else:
                chunk_size = target_fill

            chunk_size = _round_share_lot(chunk_size, remains, tick_sz, is_buy)
            if chunk_size <= 0:
                continue

            order_price = _get_algo_price(
                core, p_open, p_high, p_low, p_close, p_volume, p_amount,
                exec_loc, target_price, is_limit, is_buy, self.is_vwap)

            filled, cash_change = self._fill(order, total_size, exec_loc, chunk_size, is_buy,
                                    order_price, lines, cash)
            if filled <= 0:
                if is_buy and cash <= 0.0:
                    break
                continue

            if is_buy:
                cash -= cash_change
            else:
                cash += cash_change  

            filled_so_far += filled
            remains -= filled

        if remains > 0:
            order.expire()


cdef class VWAPFiller(AlgoFiller):
    def __init__(self, **kwargs):
        kwargs["is_vwap"] = True
        super().__init__(**kwargs)


cdef class TWAPFiller(AlgoFiller):
    def __init__(self, **kwargs):
        kwargs["is_vwap"] = False
        super().__init__(**kwargs)


_fillers = {
    b"default": PseudoFiller(),
    b"vwap": VWAPFiller(),
    b"twap": TWAPFiller()
}