#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
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

from backtest.execution.core.finance.order cimport Order
from backtest.execution.core.finance.account cimport Account
from backtest.execution.core.finance.position cimport Position 
from backtest.execution.core.finance.simulate cimport Simulator
from backtest.execution.gateway.interface import async_gt # singleton cast to cdef class type 
from backtest.execution.actor.writer_actor cimport BatchWriterActor

from libc.stdint cimport int32_t


logger = logging.getLogger(__name__)


cdef class BackEngine:

    # def __init__(self, int32_t max_size, int32_t batch_size):
    def __init__(self, int32_t max_size, BatchWriterActor actor):
        self.simulator = Simulator(max_size=max_size, actor=actor)
        self.gt = <AsyncGateway>async_gt # cast to cdef class type

    async def __aenter__(self):
        self._start()
        return self
        
    cpdef void start(self, object loop):
         # self._loop = asyncio.get_running_loop()
         self.simulator.attach(loop)

    # -----------------------------------------------------------
    # direct API 
    # -----------------------------------------------------------

    async def register(self, object event):
        cdef object resp

        resp = await async_gt.register(event)
        return resp

    async def set_cash(self, object event):
        cdef object resp

        resp = await self.simulator.set_cash(event)
        return resp
    
    async def submit(self, object event):
        cdef object body = event.body 
        cdef bytes experiment_id = event.experiment_id
        cdef Order order_obj
        cdef object resp

        order_obj = Order(experiment_id=experiment_id, 
                          sid=body.sid, 
                          sizer_ratio=body.sizer_ratio,
                          pricelimit=body.pricelimit,
                          order_type=body.order_type,
                          exec_type=body.exec_type,
                          created_dt=body.created_dt,
                          filler=body.filler)
        order_obj.submit()
        resp = await self.simulator.submit(order_obj)
        return resp

    async def on_dt_over(self, object event):
        cdef object resp

        resp = await self.simulator.on_dt_over(event)
        return resp

    async def getvalue(self, object event): # macht case in suited for cython
        cdef Position p_obj
        cdef Account acct_obj
        cdef object resp
        
        resp = await self.simulator.getvalue(event)
        return resp

    async def subscribe(self, object event):
        cdef list resp = []

        async for batch in async_gt.subscribe(event): 
            resp.append(batch)
        
        resp = list(chain(*resp)) # stack
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

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
