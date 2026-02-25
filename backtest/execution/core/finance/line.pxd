
cimport numpy as cnp
from libcpp.vector cimport vector
from libc.stdint cimport int64_t
from libcpp.string cimport string as cpp_string

cnp.import_array() # 必须调用以初始化 numpy C-API


cdef struct Bar:
    int64_t tick
    double open
    double high
    double low
    double close
    double volume
    double amount


cdef class LineAlias:
    cdef str name

    cdef vector[double] _data  # std::vector nogil

    cdef void append(self, double value) 

    cdef void extend(self, double[:] arr) # memoryview

    cdef double[:] get_array(self) 


cdef class Lines:
    cdef int _size

    cdef vector[int64_t] tick
    cdef vector[double] open
    cdef vector[double] high
    cdef vector[double] low
    cdef vector[double] close
    cdef vector[double] volume
    cdef vector[double] amount

    cdef void batch_load(self, double[:, :] arr)

    cdef Bar getvalue(self, int idx)

    cdef double max(self) 

    cdef double min(self)
    
    cdef bint is_in(self, int64_t tick)
