from libc.stdint cimport int32_t

cdef class IBatchWriter:

    cpdef void push(self, list data)


cdef class BatchWriterActor(IBatchWriter): # CPU Intensive
    cdef int32_t batch_size
    cdef bint _running
    cdef public bint remote
    cdef object _queue
    cdef list _buffer
    cdef object _finished_event 
    
    cpdef void push(self, list data)
    
    cdef _sync_write_file(self, str path, list data)


cdef class RayWriterProxy(IBatchWriter):
    cdef object _handle

    cpdef void push(self, list data)
