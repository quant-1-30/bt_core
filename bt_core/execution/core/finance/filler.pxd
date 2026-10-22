from libc.stdint cimport int64_t, int32_t

from bt_core.execution.core.finance.order cimport Order, OrderCoreData
from bt_core.execution.core.finance.position cimport Position
from bt_core.execution.core.finance.line cimport Lines, Bar
from bt_core.execution.core.finance.comminfo cimport CommInfoBase
from bt_core.execution.core.finance.slippage cimport Slippage
from bt_core.execution.core.finance.asset cimport AssetCore
from bt_core.execution.core.finance.common cimport ExecPrep


cdef class PseudoFiller:
    cdef public double impact
    cdef Slippage slip
    cdef CommInfoBase comm

    cdef dict _lines_cache 
    cdef int32_t _current_cache_dt
    
    cdef Lines _preload(self, Order ord, object loop)

    cdef int32_t _calculate(self, Order order, Position p_obj, ExecPrep prep, Bar bar)

    cdef ExecPrep _prepare_execute(self, Order order, Position p_obj, double cash, Lines lines)

    cdef (int32_t, double) _find_limit_execution(self, int32_t loc, double limit_price, bint is_buy, Lines lines)

    cdef double _get_exec_price(self, Order order, Lines lines, int32_t loc)

    cdef int32_t _fill(self, Order order, ExecPrep* prep, Bar bar, int32_t req_size)

    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines)


cdef class AlgoFiller(PseudoFiller):
    cdef public bint is_vwap
    cdef public int32_t lookback_days
    cdef dict _vhat_cache
    cdef int32_t _current_vhat_dt

    cdef void _ensure_window_volume(self, OrderCoreData core, int32_t int_dt, object loop)

    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines)


cdef class VWAPFiller(AlgoFiller):
    pass


cdef class TWAPFiller(AlgoFiller):
    pass