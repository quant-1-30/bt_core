cdef enum SubTopic:
    Order = 0
    Position = 1
    Account = 2

cdef enum RpcTopic:
    Calendar = 0
    Instrument = 1
    Index = 2
    Tick = 3 
    Close = 4
    Adjustment = 5
    Rightment = 6


cdef class AsyncGateway:
    cdef object mdapi 
