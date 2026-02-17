
from libc.stdint cimport int32_t
from libcpp.vector cimport vector

cdef class Sizer:

    cpdef int32_t getsizing(self, bint is_buy)
    
    cpdef void reset(self)


cdef class Fixed(Sizer):
    cpdef int32_t getsizing(self, bint isbuy)


cdef class Pyramid(Sizer):
    cdef vector[int32_t] ratios 
    cdef int32_t step
    cdef int32_t max_step

    cpdef int32_t getsizing(self, bint is_buy)
