#! /usr/bin/env python3 
# -*- coding: utf-8 -*-

import asyncio
import threading
from typing import Tuple
from concurrent.futures import ThreadPoolExecutor
from libc.stdint cimport int32_t

from bt_sdk.core.protocol import Event
from backtest.execution.core.engine.engine cimport BackEngine, EngineTopic


cdef class AsyncApi:

    def __init__(self, bytes client_id, int32_t q_size, int32_t buffer_size, object actor):
        self.client_id = client_id
        self.engine = BackEngine(q_size, buffer_size, actor)
        self._loop = None

    cdef start(self, object _loop):
        self.engine.start(_loop)
        self._loop = _loop

    async def register_async(self, object body):
        cdef object event = Event(
            topic=EngineTopic.Register,
            body=body,
            experiment_id=b''
        )
        return await self.engine.register(event)

    async def set_cash_async(self, bytes experiment_id, object body):
        cdef object event = Event(
            topic=EngineTopic.SetCash,
            body=body,
            experiment_id=experiment_id
        )
        return await self.engine.set_cash(event)

    async def submit_async(self, bytes experiment_id, object body):
        cdef object event = Event(
            topic=EngineTopic.Submit,
            body=body,
            experiment_id=experiment_id
        )
        return await self.engine.submit(event)

    async def on_dt_over_async(self, bytes experiment_id, object body):
        cdef object event = Event(
            topic=EngineTopic.Tplus1,
            body=body,
            experiment_id=experiment_id
        )
        return await self.engine.on_dt_over(event)

    async def get_snapshot_async(self, bytes experiment_id):
        cdef object event = Event(
            topic=EngineTopic.Snapshot,
            experiment_id=experiment_id
        )
        return await self.engine.get_snapshot(event)

    async def subscribe_async(self, int topic, bytes experiment_id, object body):
        cdef object event = Event(
            topic=EngineTopic.Subscribe,
            body=body,
            experiment_id=experiment_id,
            sub_topic=topic
        )
        # async for item in self.engine.subscribe(event):
        #     yield item
        return await self.engine.subscribe(event)

    async def close(self):
        await self.engine.stop()


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
        self._async_api = AsyncApi(client_id, q_size, buffer_size, actor)
        self._loop = None

    cpdef start(self, object _loop):
        self._loop = _loop
        self._async_api.start(_loop)
    
    def __enter__(self):
        return self 

    # ------------------------------------------------------------------
    # Blocking Methods
    # ------------------------------------------------------------------

    cpdef object register(self, object body):
        cdef object coro = self._async_api.register_async(body)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()
    
    cpdef object set_cash(self, bytes experiment_id, object body):
        cdef object coro = self._async_api.set_cash_async(experiment_id, body)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    cpdef object submit(self, bytes experiment_id, object body):
        # run_coroutine_threadsafe return concurrent.futures.Future 
        cdef object coro = self._async_api.submit_async(experiment_id, body)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result() 
        except Exception as e:
            print(f"Submit failed: {e}")
            raise e

    cpdef object on_dt_over(self, bytes experiment_id, object body):
        cdef object coro = self._async_api.on_dt_over_async(experiment_id, body)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop) # # ensure cross thread safely / fut.set_result(payload)
        return future.result() 

    cpdef object get_snapshot(self, bytes experiment_id):
        cdef object coro = self._async_api.get_snapshot_async(experiment_id)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()
    
    cpdef object subscribe(self, int topic, bytes experiment_id, object body):
        cdef object coro = self._async_api.subscribe_async(topic, experiment_id, body)
        cdef object future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    cpdef stop(self):
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._async_api.close(), self._loop)
            future.result()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            print(f"Error: {exc_type}, {exc_val}, {exc_tb}")
