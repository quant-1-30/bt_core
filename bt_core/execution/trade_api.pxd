
from bt_core.execution.core.engine.engine cimport BackEngine

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


cdef class TdApi:
    cdef BackEngine engine
    cdef bytes client_id
    cdef object _loop
    
    cpdef start(self, object _loop)
    
    cpdef object register(self, object body)

    cpdef object set_cash(self, bytes experiment_id, object body)

    cpdef object submit(self, bytes experiment_id, object body)

    cpdef object on_dt_over(self, bytes experiment_id, object body)
    
    cpdef object get_snapshot(self, bytes experiment_id)
    
    cpdef object subscribe(self, int topic, bytes experiment_id, object body)
    
    cpdef stop(self)
