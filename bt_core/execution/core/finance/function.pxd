# cython: boundscheck=False
# cython: wraparound=False
# distutils: language = c++

from libc.stdint cimport int32_t, int64_t
from libc.stdlib cimport getenv, atoi
from libc.math cimport floor
from bt_core.execution.core.finance.common cimport AdjustmentData, RightData, EventItem, ExecPrep
from bt_core.execution.core.finance.order cimport OrderCoreData, OrderType, ExecType
from bt_core.execution.core.finance.line cimport Lines, Bar


cdef struct cRatio:
    double sizer_ratio
    double bonus_ratio


cdef inline object _get_bt_timeout():
    """Return RPC/DB wait timeout in seconds from BT_TIMEOUT (default 60s).
    Explicit '0' or negative disables timeout (returns None); non-numeric values fall back to 60s."""
    cdef const char* s = getenv("BT_TIMEOUT")
    if s == NULL or s[0] == 0:
        return 60
    cdef int t = atoi(s)
    if t == 0 and s[0] != b'0':
        return 60
    return t if t > 0 else None


cdef inline bint compare_events(EventItem a, EventItem b) noexcept nogil:
    if a.ex_date != b.ex_date:
        return a.ex_date < b.ex_date
    return a.event_type < b.event_type


cdef inline double round_tick(double px) noexcept nogil:
    return floor(px * 100.0 + 0.5) / 100.0


cdef inline cRatio calc_ratio(AdjustmentData dividend) nogil:
    cdef cRatio cr
    cr.sizer_ratio = (dividend.bonus_share + dividend.transfer) / 10 + 1.0
    cr.bonus_ratio = dividend.bonus / 10
    return cr


cdef inline double _dividend_tax_rate(int32_t days_held, int32_t ex_date) noexcept nogil:
    """A-share tiered dividend tax rate by holding period (trading days):
    <= 20 days (1 month): 20%; 21..240 days (1 year): 10%;
    > 240 days: 0% from 2015-09-08 onwards (5% before 2015-09-08)."""
    if days_held <= 0:
        return 0.0
    if days_held <= 20:
        return 0.20
    if days_held <= 240:
        return 0.10
    return 0.05 if (0 < ex_date < 20150908) else 0.0


cdef inline int32_t _round_share_lot(int32_t chunk_size,
                                     int32_t remains,
                                     int32_t tick_size,
                                     bint is_buy,
                                     bint increment=True) noexcept nogil:
    if chunk_size <= 0 or remains <= 0:
        return 0
    if tick_size <= 1:
        return chunk_size if chunk_size < remains else remains
    if is_buy:
        if chunk_size < tick_size:
            return 0
        if not increment:
            return chunk_size if chunk_size < remains else remains
        return (chunk_size // tick_size) * tick_size
    if chunk_size >= remains or remains < tick_size:
        return remains
    if not increment and chunk_size >= tick_size:
        return chunk_size
    return (chunk_size // tick_size) * tick_size


cdef inline void _resolve_limit_bounds(Lines lines,
                                       OrderCoreData core,
                                       ExecPrep* prep):
    prep.limit_down = 0.0
    prep.limit_up = 0.0
    if core.limit_ratio >= 1.0 or core.created_dt <= 0:
        return

    cdef int32_t n = len(lines)
    if n <= 1:
        return

    cdef int64_t day_start_ts = ((<int64_t>core.created_dt + 28800) // 86400) * 86400 - 28800
    cdef int32_t first_today = lines.get_loc(day_start_ts)
    if first_today <= 0 or first_today >= n:
        return

    cdef double pre_close = lines.close[first_today - 1]
    if pre_close <= 0.0:
        return

    cdef double down = round_tick(pre_close * (1.0 - core.limit_ratio))
    cdef double up = round_tick(pre_close * (1.0 + core.limit_ratio))
    cdef double open_today = lines.open[first_today]
    # Guard against ex-dividend/split days where raw pre_close is unadjusted
    if open_today > 0.0 and (open_today < down - 0.02 or open_today > up + 0.02):
        return
        
    prep.limit_down = down
    prep.limit_up = up


cdef inline bint _limit_fillable(Bar bar,
                                 double limit_ratio,
                                 bint is_buy,
                                 ExecPrep prep) noexcept nogil:
    if bar.low <= 0.0 or bar.high <= 0.0:
        return False
    if limit_ratio >= 1.0:
        return True
    if prep.limit_up > 0.0 and prep.limit_down > 0.0:
        if is_buy and bar.close >= prep.limit_up - 1e-6:
            return False
        if (not is_buy) and bar.close <= prep.limit_down + 1e-6:
            return False
        return True

    # Fallback when previous close is unavailable: reject one-word sealed bars
    if bar.high - bar.low <= 0.015:
        if is_buy and (bar.close >= bar.high - 0.01):
            return False
        if (not is_buy) and (bar.close <= bar.low + 0.01):
            return False
    return True


cdef inline double _get_algo_price(OrderCoreData core,
                                   Bar bar,
                                   double target_price,
                                   bint is_vwap) noexcept nogil:
    cdef bint is_limit = (core.exec_type == ExecType.Limit)
    cdef bint is_buy = (core.order_type == OrderType.Buy)
    if is_limit:
        if is_buy:
            return bar.open if bar.open < target_price else target_price
        return bar.open if bar.open > target_price else target_price

    if core.exec_type == ExecType.Open:
        return bar.open
    elif core.exec_type == ExecType.Close:
        return bar.close

    if is_vwap:
        if bar.volume > 0.0 and bar.amount > 0.0:
            return bar.amount / bar.volume
        elif bar.high > 0.0 and bar.low > 0.0:
            return (bar.high + bar.low + bar.close) / 3.0
        return bar.open
    else:
        if bar.high > 0.0 and bar.low > 0.0:
            return (bar.open + bar.high + bar.low + bar.close) * 0.25
        return bar.open
