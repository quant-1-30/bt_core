from libcpp.vector cimport vector
from libcpp.algorithm cimport binary_search, lower_bound
from libc.stdint cimport int32_t, int64_t

import numpy as np
cimport numpy as cnp
cnp.import_array() # 必须调用以初始化 numpy C-API


cdef struct Bar:
    int64_t tick
    double open
    double high
    double low
    double close
    double volume
    double amount


cdef class Lines:
    cdef:
        int32_t _size
        
        vector[int64_t] _v_tick
        vector[double] _v_open
        vector[double] _v_high
        vector[double] _v_low
        vector[double] _v_close
        vector[double] _v_volume
        vector[double] _v_amount

        # C ptr 
        int64_t* tick
        double* open
        double* high
        double* low
        double* close
        double* volume
        double* amount
        
    cdef void batch_load(self, double[:, :] arr)

    cdef double max(self) nogil

    cdef double min(self) nogil
    
    cdef Bar getvalue(self, int32_t idx) nogil

    cdef bint is_in(self, int64_t tick_val) nogil
    
    cdef int32_t get_loc(self, int64_t target_tick) nogil
    
    cpdef clear(self)
