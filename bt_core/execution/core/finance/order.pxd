# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++

from libc.stdint cimport int32_t, int64_t
from libcpp.string cimport string as cpp_string

from bt_core.execution.core.finance.trade cimport OrderExecutionBit, OrderExbitData
from bt_core.execution.core.finance.asset cimport Asset, AssetCore

cpdef enum ExecType:
    Open = 0 # suited for backtest
    Market = 1 
    Close = 2 # suited for backtest 
    Limit = 3
    Stop = 4
    StopLimit = 5
    StopTrail = 6
    StopTrailLimit = 7


cpdef enum OrderType:
    Buy = 0
    Sell = 1
    Unkown = 2


cdef enum OrderStatus:
    Created = 0
    Submitted = 1
    Accepted = 2
    Partial = 3
    Completed = 4
    Canceled = 5
    Expired = 6
    Rejected = 7


cdef struct OrderCoreData:
     cpp_string experiment_id # bytes in python
     cpp_string sid
     cpp_string order_id
     int32_t size
     double sizer_ratio
     double price
     int32_t order_type
     int32_t exec_type
     int32_t created_dt


cdef class Order:
    cdef readonly OrderCoreData core
    cdef readonly bytes filler

    cdef AssetCore info
    cdef int32_t status
    cdef int32_t _exchange

    cdef object _exbits
    cdef object _exbits_schema
    cdef object cached_uuid

    cdef void addinfo(self, Asset asset)
    
    cdef void execute(self, int32_t size, OrderExecutionBit order_bit, double order_price)
    
    cdef void submit(self)

    cdef void accept(self)

    cdef void reject(self)

    cdef void partial(self)

    cdef void expire(self)

    cdef void completed(self)

    cdef void cancel(self)

    cdef Order clone(self)
    
    cdef object serialize(self)
    
    cdef object to_schema(self)
    
    cdef OrderCoreData get_snapshot(self)
