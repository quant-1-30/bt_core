# distutils: language = c++
# cython: profile=False
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True

import os
import asyncio
import logging
import numpy as np
import polars as pl

from libc.stdint cimport int32_t, int64_t

from bt_core.execution.gateway.interface import async_gt
from bt_core.tradingcal import prev_trading_day
from bt_core.utils.dateintern cimport ts2intdt, elapse_seconds
from bt_core.execution.core.finance.order cimport OrderCoreData, ExecType, Order
from bt_core.execution.core.finance.position cimport Position
from bt_core.execution.core.finance.slippage import _slip
from bt_core.execution.core.finance.comminfo cimport CommInfo_Stocks, CommInfoBase
from bt_core.execution.core.finance.trade cimport OrderExecutionBit
from bt_core.execution.core.finance.common cimport ExecPrep
from bt_core.execution.core.finance.function cimport (
    _get_bt_timeout, _round_share_lot, _resolve_limit_bounds,
    _limit_fillable, _get_algo_price
)

from bt_protocol._protocol import QueryBody
from bt_protocol.constant import RpcTopic

cimport numpy as cnp
cnp.import_array()

logger = logging.getLogger(__name__)


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

    cdef int32_t _calculate(self, Order order, Position p_obj, ExecPrep prep, Bar bar):
        cdef AssetCore info = order.info
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy
        cdef int32_t tick_sz = info.tick_size if info.tick_size > 0 else 100
        cdef int32_t avail, want_sell
        cdef double budget, total, slip_price, cost_per_lot

        if core.sizer_ratio <= 0.0:
            return 0

        if not is_buy:
            avail = p_obj.get_available()
            if avail <= 0:
                return 0
            want_sell = <int32_t>(avail * core.sizer_ratio)
            return _round_share_lot(min(want_sell, avail), avail, tick_sz, False, info.increment)

        if prep.cash <= 0.0:
            return 0

        slip_price = self.slip.get_slip_price(prep.target_price, bar, True)
        if slip_price <= 0.0:
            slip_price = prep.target_price

        cost_per_lot = slip_price * tick_sz + self.comm.getcommission(order, tick_sz, slip_price)
        if cost_per_lot <= 0.0:
            return 0

        budget = core.sizer_ratio * prep.cash
        if budget < cost_per_lot:
            return 0

        if not info.increment:
            return <int32_t>(budget / (cost_per_lot / tick_sz))

        total = budget / cost_per_lot  # avoid exceed 1e7
        return <int32_t>total * tick_sz

    cdef Lines _preload(self, Order ord, object loop):
        cdef OrderCoreData core = ord.core
        cdef int32_t int_dt = ts2intdt(core.created_dt)
        cdef tuple cache_key = (core.sid, int_dt)
        cdef Lines lines
        cdef object cached

        if self._current_cache_dt != int_dt:
            self._lines_cache.clear()
            self._current_cache_dt = int_dt

        cached = self._lines_cache.get(cache_key, None)
        if cached is not None:
            return <Lines>cached

        lines = Lines()
        cdef int32_t pre_dt = prev_trading_day(int_dt)
        cdef object request = QueryBody(pre_dt, int_dt, [core.sid])

        async def loader(object req):
            cdef list cols = ["tick", "open", "high", "low", "close", "volume", "amount"]
            cdef object df, cast_df, np_arr

            try:
                data = await async_gt.rpc(req, RpcTopic.Tick)
                df = data.get(req.sid[0]) if data else None
                if df is not None and df.height > 0:
                    cast_df = df.select(pl.col(cols).cast(pl.Float64))
                    np_arr = np.ascontiguousarray(cast_df.to_numpy())
                    lines.batch_load(np_arr)
            except GeneratorExit:
                pass
            except Exception:
                logger.exception("tick loader failed for sid %s", core.sid)

        asyncio.run_coroutine_threadsafe(loader(request), loop).result(timeout=_get_bt_timeout())
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

    cdef int32_t _fill(self, Order order, ExecPrep* prep, Bar bar, int32_t req_size):
        if req_size <= 0:
            return 0

        cdef OrderCoreData core = order.core
        cdef AssetCore info = order.info
        cdef bint is_buy = order.isbuy
        cdef int32_t fill_size = req_size
        cdef double lot_cost
        cdef int32_t max_by_cash

        cdef int32_t tick_sz = info.tick_size if info.tick_size > 0 else 100

        cdef double slip_price = self.slip.get_slip_price(prep.order_price, bar, is_buy)

        if prep.limit_up > 0.0 and slip_price > prep.limit_up:
            slip_price = prep.limit_up
        elif prep.limit_down > 0.0 and slip_price < prep.limit_down:
            slip_price = prep.limit_down

        if is_buy:
            if prep.cash <= 0.0 or slip_price <= 0.0:
                return 0

            lot_cost = slip_price * tick_sz + self.comm.getcommission(order, tick_sz, slip_price)
            if info.increment:
                # Standard boards (100-share whole lots): floor by whole lot count
                max_by_cash = (<int32_t>(prep.cash / lot_cost)) * tick_sz
            else:
                # STAR board (min 200 shares, 1-share increment above 200): floor by single share
                max_by_cash = <int32_t>(prep.cash / (lot_cost / tick_sz)) if prep.cash >= lot_cost else 0
            if fill_size > max_by_cash:
                fill_size = max_by_cash
            if fill_size <= 0:
                return 0

        cdef double comm = self.comm.getcommission(order, fill_size, slip_price)

        if is_buy:
            prep.cash -= slip_price * fill_size + comm

        cdef OrderExecutionBit order_bit = OrderExecutionBit(
            order_id=core.order_id,
            executed_dt=bar.tick,
            executed_size=fill_size,
            executed_price=slip_price,
            comm=comm,
            isbuy=is_buy)

        order.execute(prep.total_size, order_bit, prep.order_price)
        return fill_size

    cdef ExecPrep _prepare_execute(self, Order order, Position p_obj, double cash, Lines lines):
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy
        cdef int32_t n, avail = 0
        cdef ExecPrep prep
        prep.cash = cash

        prep.start_loc = -1
        prep.total_size = 0
        prep.order_price = 0.0
        prep.limit_down = 0.0
        prep.limit_up = 0.0
        prep.target_price = 0.0

        if core.created_dt <= 0:
            order.reject()   
            return prep

        n = len(lines)
        if n <= 0:
            order.expire()   
            return prep

        prep.start_loc = lines.get_loc(core.created_dt)
        if prep.start_loc >= n and n > 0 and ts2intdt(core.created_dt) == ts2intdt(lines.tick[n - 1]):
            prep.start_loc = n - 1
        if prep.start_loc < 0 or prep.start_loc >= n:
            prep.start_loc = -1
            order.expire()   
            return prep

        prep.target_price = self._get_exec_price(order, lines, prep.start_loc)
        if prep.target_price <= 0.0:
            prep.start_loc = -1
            order.expire()
            return prep

        if core.limit_ratio < 1.0:
            _resolve_limit_bounds(lines, core, &prep)
            if core.exec_type == ExecType.Limit:
                if (prep.limit_up > 0.0 and prep.target_price > prep.limit_up + 1e-6) or (
                    prep.limit_down > 0.0 and prep.target_price < prep.limit_down - 1e-6
                ):
                    prep.start_loc = -1
                    order.reject()
                    return prep

        prep.total_size = (
            core.size if core.size > 0
            else self._calculate(order, p_obj, prep, lines.getvalue(prep.start_loc))
        )

        if prep.total_size <= 0:
            prep.start_loc = -1
            order.reject()
            return prep

        if not is_buy:
            # never sell more than T+1 available shares: Position.update would
            # raise mid-order and leave the tracker in a half-processed state
            avail = p_obj.get_available()
            if prep.total_size > avail:
                prep.total_size = avail
                if prep.total_size <= 0:
                    prep.start_loc = -1
                    order.reject()
                    return prep

        return prep

    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines):
        cdef AssetCore info = order.info
        cdef bint is_buy = order.isbuy
        cdef bint is_limit = (order.core.exec_type == ExecType.Limit)
        cdef int32_t tick_sz = info.tick_size if info.tick_size > 0 else 100
        cdef int32_t n = len(lines)

        cdef ExecPrep prep = self._prepare_execute(order, p_obj, cash, lines)
        if prep.start_loc < 0:
            return

        cdef int32_t start_loc = prep.start_loc
        cdef int32_t remains = prep.total_size
        cdef double limit_ratio = order.core.limit_ratio
        cdef int32_t exec_loc, filler_size, filled
        cdef Bar bar

        while remains > 0 and start_loc < n:
            if is_limit:
                exec_loc, prep.order_price = self._find_limit_execution(
                    start_loc, prep.target_price, is_buy, lines)
            else:
                exec_loc = start_loc
                prep.order_price = self._get_exec_price(order, lines, exec_loc)

            if exec_loc < 0:
                break

            bar = lines.getvalue(exec_loc)
            if not _limit_fillable(bar, limit_ratio, is_buy, prep):
                start_loc = exec_loc + 1
                continue

            filler_size = min(remains, <int32_t>(bar.volume * self.impact))
            filler_size = _round_share_lot(filler_size, remains, tick_sz, is_buy, info.increment)
            if filler_size <= 0:
                start_loc = exec_loc + 1
                continue

            filled = self._fill(order, &prep, bar, filler_size)
            if filled <= 0:
                if is_buy and prep.cash <= 0.0:
                    break
                start_loc = exec_loc + 1
                continue

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
        self._current_vhat_dt = 0

    cdef Lines _preload(self, Order ord, object loop):
        cdef OrderCoreData core = ord.core
        cdef int32_t int_dt = ts2intdt(core.created_dt)
        
        if self._current_vhat_dt != int_dt:
            self._vhat_cache.clear()
            self._current_vhat_dt = int_dt

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
        cdef int32_t start_ymd = prev_trading_day(int_dt, self.lookback_days)
        cdef int32_t end_ymd = prev_trading_day(int_dt, 1)
        cdef object request = QueryBody(start_ymd, end_ymd, [core.sid])

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
                loop).result(timeout=_get_bt_timeout())
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
        cdef ExecPrep prep = self._prepare_execute(order, p_obj, cash, lines)
        if prep.start_loc < 0:
            return

        cdef int32_t start_loc = prep.start_loc
        cdef int32_t end_loc = n                  
        cdef int32_t total_bars = n - start_loc
        cdef int32_t remains = prep.total_size
        cdef double limit_ratio = core.limit_ratio

        # VWAP
        cdef double v_hat = 0.0
        if self.is_vwap:
            v_hat = self._vhat_cache.get((core.sid, ts2intdt(core.created_dt)), 0.0)

        cdef int32_t filled_so_far = 0
        cdef double s_exec = 0.0
        cdef int32_t exec_loc, target_cum, target_fill, max_liq, chunk_size, filled
        cdef double frac, bar_vol, twap_frac, vwap_frac
        cdef Bar bar

        for exec_loc in range(start_loc, end_loc):
            if remains <= 0:
                break

            bar = lines.getvalue(exec_loc)
            bar_vol = bar.volume if bar.volume == bar.volume else 0.0
            s_exec += bar_vol

            if is_limit:
                if is_buy and bar.low > prep.target_price:
                    continue
                if (not is_buy) and bar.high < prep.target_price:
                    continue

            if not _limit_fillable(bar, limit_ratio, is_buy, prep):
                continue
            
            twap_frac = <double>(exec_loc - start_loc + 1) / <double>total_bars
            if exec_loc == end_loc - 1:
                frac = 1.0
            elif v_hat > 0.0:
                vwap_frac = s_exec / v_hat
                if vwap_frac > 1.0:
                    vwap_frac = 1.0
                
                # avoid n bar swallow 
                frac = vwap_frac if vwap_frac < (twap_frac * 1.5) else (twap_frac * 1.5)
                if frac > 1.0:
                    frac = 1.0       
            else:
                frac = twap_frac  # TWAP degrade

            target_cum = <int32_t>(<double>prep.total_size * frac + 0.5)
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

            chunk_size = _round_share_lot(chunk_size, remains, tick_sz, is_buy, info.increment)
            if chunk_size <= 0:
                continue

            prep.order_price = _get_algo_price(core, bar, prep.target_price, self.is_vwap)
            filled = self._fill(order, &prep, bar, chunk_size)
            if filled <= 0:
                if is_buy and prep.cash <= 0.0:
                    break
                continue

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