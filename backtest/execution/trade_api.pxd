
from backtest.execution.core.simulator.engine cimport BackEngine

cdef enum EngineTopic:
    Register = 0
    SetCash = 1
    Submit = 2
    DayOver = 3 
    GetValue = 4
    Subscribe = 5

cpdef enum SubTopic:
    Order = 0
    Position = 1
    Account = 2

cpdef enum OrderType:
    Buy = 0
    Sell = 1
    Unkown = 2

cpdef enum ExecType:
    Open = 0
    Market = 1
    COC = 2
    Limit = 3
    Stop = 4
    StopLimit = 5
    StopTrail = 6
    StopTrailLimit = 7
    Historical = 8


cdef class AsyncApi:
    cdef BackEngine engine
    cdef bytes client_id
    cdef object _loop
    
    cdef start(self, object _loop)


cdef class TdApi:
    cdef AsyncApi _async_api
    cdef object _loop
    
    cpdef start(self, object _loop)
    
    cpdef object register(self, object body)

    cpdef object set_cash(self, bytes experiment_id, object body)

    cpdef object submit(self, bytes experiment_id, object body)

    cpdef object on_dt_over(self, bytes experiment_id, object body)
    
    cpdef object getvalue(self, bytes experiment_id)
    
    cpdef object subscribe(self, int topic, bytes experiment_id, object body)
    
    cpdef stop(self)
