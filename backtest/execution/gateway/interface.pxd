cdef enum SubTopic:
    Order = 0
    Position = 1
    Account = 2


cdef class AsyncGateway:
    cdef object _mdapi 
