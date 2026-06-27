from libcpp.string cimport string as cpp_string
from libc.math cimport modf as cmodf
from libc.stdint cimport int64_t, int32_t

from bt_core.execution.core.finance.order cimport Order
from bt_core.execution.core.finance.position cimport Position
from bt_core.execution.core.finance.line cimport Lines    
from bt_core.execution.core.finance.comminfo cimport CommInfoBase
from bt_core.execution.core.finance.slippage cimport Slippage
from bt_core.execution.core.finance.asset cimport AssetCore


cdef class PseudoFiller:
    cdef public double impact
    cdef public int32_t batch_size
    cdef Slippage slip
    cdef CommInfoBase comm

    cdef dict _lines_cache 
    cdef int32_t _current_cache_dt
    
    cdef (int32_t, double) _find_limit_execution(self, int32_t loc, double limit_price, bint is_buy, Lines lines)

    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines)


cdef class AlgoFiller(PseudoFiller):
    cdef public bint is_vwap


cdef class VWAPFiller(AlgoFiller):
    pass


cdef class TWAPFiller(AlgoFiller):
    pass
