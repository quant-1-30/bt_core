# distutils: language = c++
# cython: language_level=3

from libc.stdint cimport uint8_t


cdef struct uuid128:
    uint8_t data[16]

cpdef bytes fast_uuid4_bytes()

cpdef str fast_uuid4_str()

cdef uuid128 fast_uuid4_c() nogil
