from libcpp.string cimport string as cpp_string
from libc.math cimport modf as cmodf

from backtest.execution.core.finance.order cimport Order
from backtest.execution.core.finance.position cimport Position
from backtest.execution.core.finance.line cimport Lines    
from backtest.execution.core.finance.comminfo cimport CommInfoBase
from backtest.execution.core.finance.slippage cimport Slippage
from backtest.execution.core.finance.cache cimport AssetInfo


cdef class PseudoFiller:
    cdef public double impact
    cdef public double thres
    cdef public int batch_size
    cdef Slippage slip
    cdef CommInfoBase comm
    
    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines)
    
    cdef void _filler(self, Order order, Position p_obj, double cash, Lines lines)


cdef class OCC(PseudoFiller):
    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines)


cdef class Smooth(PseudoFiller):
    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines)


cdef class Likehood(PseudoFiller):
    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines)
