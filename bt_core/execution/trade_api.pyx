# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++
# cython: language_level=3

import asyncio
import threading
from typing import Tuple
from concurrent.futures import ThreadPoolExecutor
from libc.stdint cimport int32_t

from bt_protocol._protocol import Event
from bt_core.execution.core.engine.engine cimport BackEngine, EngineTopic


cdef class TdApi:
    """
    # How to implement a tradeApi:
    ---
    ## Basics
    A tradeApi should satisfies:
    * this class should be thread-safe:
        * all methods should be thread-safe
        * no mutable shared properties between objects.
    * all methods should be non-blocked
    * satisfies all requirements written in docstring for every method and callbacks.
    * automatically reconnect if connection lost.

    All the XxxData passed to callback should be constant, which means that
        the object should not be modified after passing to on_xxxx.
    So if you use a cache to store reference of data, use copy.copy to create a new object
    before passing that data into on_xxxx
    """

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

    cpdef object register(self, object body): # run_coroutine_threadsafe return concurrent.futures.Future
        cdef object event = Event(topic=EngineTopic.Register, body=body, experiment_id=b'')
        cdef object coro = self.engine.register(event)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        return future.result()

    cpdef object subscribe(self, int topic, bytes experiment_id, object body):
        cdef object event = Event(topic=EngineTopic.Subscribe, body=body, 
                                experiment_id=experiment_id, sub_topic=topic)

        cdef object coro = self.engine.subscribe(event)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    cpdef stop(self):
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.engine.stop(), self._loop)
            future.result()

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
            print(f"Error: {exc_type}, {exc_val}, {exc_tb}")
