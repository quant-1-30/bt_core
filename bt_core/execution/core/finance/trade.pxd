from libcpp.string cimport string as cpp_string
from libc.stdint cimport int64_t

cdef struct OrderExbitData:
    cpp_string order_id
    int64_t executed_dt
    int64_t executed_size
    double executed_price
    double comm
    bint isbuy

cdef class OrderExecutionBit:
    cdef readonly OrderExbitData core

    cdef OrderExecutionBit clone(self)
    
    cdef object serialize(self)
    
    cdef object to_schema(self)
    
    cdef OrderExbitData get_snapshot(self)