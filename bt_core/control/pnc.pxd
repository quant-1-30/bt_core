from libc.stdint cimport int32_t, int64_t
from libcpp.string cimport string as cpp_string


cdef struct CoreData:
    cpp_string sid
    double weight
    bint isbuy
    int32_t size 
    int32_t priority


cdef class TraderPlan:
    
    cdef readonly CoreData core


cdef class Pnc:

    cdef int32_t interval
    cdef double stake
    cdef double dd
    cdef object sizer

    cdef list sells
    cdef list buys
    cdef dict pending_sells
    
    cpdef list check_risk(self, dict current_prices, object snapshot, dict stats)
    
    cpdef dict generate_plan(self, dict topk_info, dict current_prices, object snapshot, dict stats)

    cpdef void on_updt(self, dict sell_trades)

