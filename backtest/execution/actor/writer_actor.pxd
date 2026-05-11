from libc.stdint cimport int32_t
       
cdef _sync_write_file(str path, list data)


cdef class IBatchWriter:
    cpdef void push(self, list data)


cdef class BatchWriterActor(IBatchWriter): 
    cdef int32_t batch_size
    cdef int32_t retries
    cdef bint _running
    cdef public bint remote
    cdef list _buffer
    cdef object _queue
    cdef object _finished_event 
    
    cpdef void push(self, list data)
    
