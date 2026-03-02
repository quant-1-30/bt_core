from libc.stdint cimport int32_t


cdef class BatchWriterActor:
    cdef int32_t batch_size
    cdef bint _running
    cdef object _queue
    cdef list _buffer
    cdef object _finished_event 
    
    cdef void push(self, dict snapshot)

