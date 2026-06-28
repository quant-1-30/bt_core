from libc.stdint cimport int32_t
from bt_core.execution.gateway.interface cimport AsyncGateway, SubTopic  # 导入类型信息
from bt_core.execution.core.finance.simulate cimport Simulator

cpdef enum EngineTopic:
    Register = 0
    SetCash = 1
    Submit = 2
    Over = 3  # T+1
    Subscribe = 4
    Snapshot = 5


cdef class BackEngine:
    cdef AsyncGateway gt
    cdef Simulator simulator  
    # cdef object _loop
    cdef set _active_tasks

    cpdef void start(self, object loop)

    cpdef object set_cash(self, object trade_event)

    cpdef object submit(self, object trade_event)

    cpdef object on_dt_over(self, object trade_event)

    cpdef object get_snapshot(self, object trade_event)# macht case in suited for cython
    