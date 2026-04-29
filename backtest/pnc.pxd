from libc.stdint cimport int32_t, int64_t


cdef class Pnc:

    cdef int32_t interval
    cdef object sizer
    cdef list sells
    cdef list buys
    cdef dict pending_sells

    cpdef void generate_plan(self, 
                        dict topk_info,
                        object snapshot, 
                        double rish_tl)   

    cpdef void on_filled(self, object sell_trades)

    cpdef dict get_pending_sells(self)

    cpdef dict to_plan(self)
    