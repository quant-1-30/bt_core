# cython: boundscheck=False
# cython: wraparound=False
# distutils: language = c++
# cython: language_level=3

import os
import asyncio
import logging
from libc.stdint cimport int32_t

from bt_protocol._protocol import Event
from bt_core.execution.core.finance.function cimport _get_bt_timeout
from bt_core.execution.core.engine.engine cimport BackEngine, EngineTopic

logger = logging.getLogger(__name__)


cdef class TdApi:
    """Single-thread Cerebro execution gateway wrapping BackEngine.

    Direct methods (set_cash, submit, get_snapshot) run synchronously on the
    caller thread; async methods (register, subscribe, on_dt_over, stop)
    dispatch coroutines to the background runner loop with a configurable
    timeout (`BT_TIMEOUT`, default 60s)."""

    def __init__(self, bytes client_id, int32_t q_size, int32_t buffer_size, object actor):
        self.client_id = client_id
        self.engine = BackEngine(q_size, buffer_size, actor)

        self._loop = None

    cpdef start(self, object _loop):
        self._loop = _loop
        self.engine.start(_loop)
    
    def __enter__(self):
        return self 

    # ------------------------------------------------------------------
    # Async Methods
    # ------------------------------------------------------------------

    cpdef object register(self, object body):
        cdef object event = Event(topic=EngineTopic.Register, body=body, experiment_id=b'')
        cdef object coro = self.engine.register(event)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=_get_bt_timeout())

    cpdef object subscribe(self, int topic, bytes experiment_id, object body):
        cdef object event = Event(topic=EngineTopic.Subscribe, body=body, 
                                experiment_id=experiment_id, sub_topic=topic)
        cdef object coro = self.engine.subscribe(event)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=_get_bt_timeout())

    cpdef stop(self):
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.engine.stop(), self._loop)
            future.result(timeout=_get_bt_timeout())

    # ------------------------------------------------------------------
    # Direct Methods
    # ------------------------------------------------------------------
    
    cpdef object set_cash(self, bytes experiment_id, object body):
        cdef object event = Event(
            topic=EngineTopic.SetCash,
            body=body,
            experiment_id=experiment_id
        )
        cdef object result = self.engine.set_cash(event)
        return result

    cpdef object submit(self, bytes experiment_id, object body):
        cdef object event = Event(
            topic=EngineTopic.Submit,
            body=body,
            experiment_id=experiment_id
        ) 
        cdef object result = self.engine.submit(event)
        return result

    cpdef object on_dt_over(self, bytes experiment_id, object body):
        cdef object event = Event(
            topic=EngineTopic.Over,
            body=body,
            experiment_id=experiment_id
        )
        cdef object result = self.engine.on_dt_over(event)
        return result

    cpdef object get_snapshot(self, bytes experiment_id):
        cdef object event = Event(
            topic=EngineTopic.Snapshot,
            experiment_id=experiment_id
        )
        cdef object result = self.engine.get_snapshot(event)
        return result
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error("TdApi error: %s: %s", exc_type, exc_val)
