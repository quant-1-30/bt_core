from libc.stdint cimport int64_t, int32_t
cimport numpy as cnp

from backtest.execution.core.finance.position cimport Position
from backtest.execution.core.finance.order cimport Order


cdef enum CommType:
    COMM_PERC = 0
    COMM_FIXED = 1


cdef class CommInfoBase:
    # 成员变量声明
    cdef double commission
    cdef double creditrate
    cdef int32_t commtype
    cdef bint _stocklike
    
    # cdef 方法声明，子类可以重写 (Virtual-like)
    cdef double calculate(self, Order order)

    cdef double getcommission(self, Order order, int32_t size, double price)

    cdef double get_credit_interest(self, Position pobj, int64_t dt)


cdef class CommInfo_Stocks(CommInfoBase):
    
    cdef double calculate(self, Order order) # virtual


cdef class CommInfo_Futures(CommInfoBase):

    cdef double calculate(self, Order order) # virtual
