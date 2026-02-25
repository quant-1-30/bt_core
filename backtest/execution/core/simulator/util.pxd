cdef class Distributor:
    cdef public object queue
    cdef public object event

    cpdef void put(self, object resp)
    

cdef class AsyncSemaphoreWrapper:
    cdef object _sem
