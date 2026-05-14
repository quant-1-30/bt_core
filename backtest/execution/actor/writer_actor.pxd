from libc.stdint cimport int32_t


cdef class BatchWriterActor: 
    cdef int32_t batch_size
    cdef int32_t retries
    cdef int32_t timeout
    cdef bint _running
    cdef list _buffer
    cdef object _queue
    cdef object _finished_event 
    
