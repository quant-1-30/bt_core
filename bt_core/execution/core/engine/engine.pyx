# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++
# cython: language_level=3

import os
import asyncio
import warnings
import atexit
import weakref
import time
import logging
from itertools import chain
from typing import Dict, Any, AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

from libc.stdint cimport int32_t

from bt_core.execution.core.finance.order cimport Order
from bt_core.execution.core.finance.account cimport Account
from bt_core.execution.core.finance.position cimport Position 
from bt_core.execution.core.finance.simulate cimport Simulator
from bt_core.execution.gateway.interface import async_gt # singleton cast to cdef class type 
from bt_core.execution.actor.writer_actor cimport BatchWriterActor


logger = logging.getLogger(__name__)


cdef class BackEngine:

    def __init__(self, int32_t q_size, int32_t buffer_size, BatchWriterActor actor):
        self.simulator = Simulator(q_size=q_size, buffer_size=buffer_size, actor=actor)
        self.gt = <AsyncGateway>async_gt # cast to cdef class type

    cpdef void start(self, object loop):
         self.simulator.attach(loop)

    # -----------------------------------------------------------
    # async api 
    # -----------------------------------------------------------

    async def register(self, object trade_event):
        cdef object resp

        resp = await async_gt.register(trade_event)
        return resp
    
    async def subscribe(self, object trade_event):
        cdef list resp = []

        async for batch in async_gt.subscribe(trade_event): 
            resp.append(batch)
        
        resp = list(chain(*resp)) # stack
        return resp
    
    # -----------------------------------------------------------
    # direct api via Cython / C
    # -----------------------------------------------------------

    cpdef object set_cash(self, object trade_event):
        cdef object resp

        resp = self.simulator.set_cash(trade_event)
        return resp
    
    cpdef object submit(self, object trade_event):
        cdef object body = trade_event.body 
        cdef bytes experiment_id = trade_event.experiment_id
        cdef Order order_obj
        cdef object resp

        order_obj = Order(experiment_id=experiment_id, 
                          sid=body.sid,
                          order_id=body.order_id, 
                          sizer_ratio=body.sizer_ratio,
                          price=body.price,
                          order_type=body.order_type,
                          exec_type=body.exec_type,
                          created_dt=body.created_dt,
                          filler=body.filler)
        order_obj.submit()
        resp = self.simulator.submit(order_obj)
        return resp

    cpdef object on_dt_over(self, object trade_event):
        cdef object resp

        resp = self.simulator.on_dt_over(trade_event)
        return resp

    cpdef object get_snapshot(self, object trade_event): 
        cdef object resp
 
        resp = self.simulator.get_snapshot(trade_event)
        return resp

    async def stop(self):
        logger.info("Stopping back broker...")
        try:
            await self.simulator.shutdown()
            # if self._active_tasks:
            #     await asyncio.gather(*self._active_tasks, return_exceptions=True)
            logger.info("BackEngine stopped successfully")
            
        except Exception as e:
            logger.exception(f"Error stopping back broker: {e}")
