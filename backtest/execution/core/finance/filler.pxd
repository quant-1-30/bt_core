from libcpp.string cimport string as cpp_string
from libc.math cimport modf as cmodf
from libc.stdint cimport int64_t, int32_t

from backtest.execution.core.finance.order cimport Order
from backtest.execution.core.finance.position cimport Position
from backtest.execution.core.finance.line cimport Lines    
from backtest.execution.core.finance.comminfo cimport CommInfoBase
from backtest.execution.core.finance.slippage cimport Slippage
from backtest.execution.core.finance.asset cimport AssetCore


cdef class PseudoFiller:
    cdef public double impact
    cdef public int32_t batch_size
    cdef Slippage slip
    cdef CommInfoBase comm
    
    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines)

    cdef (int32_t, double) _find_limit_execution(self, int32_t loc, double limit_price, bint is_buy, Lines lines)
    
    cdef void _execute(self, Order order, Position p_obj, double cash, Lines lines)


cdef class OCC(PseudoFiller):
    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines)


cdef class Smooth(PseudoFiller):
    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines)


cdef class Likehood(PseudoFiller):
    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines)
