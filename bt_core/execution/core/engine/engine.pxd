from libc.stdint cimport int32_t
from bt_core.execution.gateway.interface cimport AsyncGateway, SubTopic  # 导入类型信息
from bt_core.execution.core.finance.simulate cimport Simulator

cpdef enum EngineTopic:
    Register = 0
    SetCash = 1
    Submit = 2
    Tplus1 = 3 
    Snapshot = 4
    Subscribe = 5


cdef class BackEngine:
    cdef AsyncGateway gt
    cdef Simulator simulator  
    # cdef object _loop
    cdef set _active_tasks

    # cpdef void start(self)
    cpdef void start(self, object loop)
    