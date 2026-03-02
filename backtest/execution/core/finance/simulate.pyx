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
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import os
import time
import json

import asyncio
import logging
import numpy as np
import threading
import pyarrow as pa
import pyarrow.compute as pc
from collections import defaultdict
from itertools import chain

from bt_sdk.core.protocol import SnapshotBody, Resp, Event, QueryBody

from libcpp.unordered_map cimport unordered_map
from libcpp.string cimport string as cpp_string
from libcpp.pair cimport pair
from libcpp.vector cimport vector
from cython.operator cimport dereference as deref
from libc.stdint cimport int32_t, int64_t

from backtest.execution.core.finance.position cimport Position, PositionCoreData
from backtest.execution.core.finance.order cimport OrderCoreData
from backtest.execution.core.finance.account cimport Account
from backtest.execution.core.finance.trade cimport OrderExecutionBit
from backtest.execution.core.finance.common cimport EventItem, AdjustmentData, RightData
from backtest.execution.core.finance.filler cimport PseudoFiller, OCC, Smooth, Likehood 
from backtest.execution.core.finance.simulate_types cimport MsgType
from backtest.execution.utils.util cimport ts2intdt
from backtest.execution.gateway.interface cimport RpcTopic
from backtest.execution.gateway.interface import async_gt


cimport numpy as cnp
cnp.import_array() # initialize numpy C-API

logger = logging.getLogger(__name__)


cdef class ActorMessage:

    def __init__(self, int type, bytes experiment_id, object payload, object reply_future=None):
        self.actor_id.MsgType = type
        self.actor_id.experiment_id = experiment_id
        self.payload = payload
        self.reply_future = reply_future


cdef class TrackerActor:

    def __init__(self, bytes experiment_id, BatchWriterActor writer, object asset_cache, int32_t max_size):
        
        self.positions = {}
        self.experiment_id = experiment_id
        self.cash_manager = AsyncCashManager()
        self.asset_cache = asset_cache
        self._writer = writer
        self._queue = asyncio.Queue(maxsize=max_size)

        self._fillers = {
            b"oco": PseudoFiller(),
            b"occ": OCC(),
            b"smooth": Smooth(),
            b"likehood": Likehood()
        }
        self._latest_snapshot = None 

    async def push(self, ActorMessage msg):
        try:
            self._queue.put_nowait(msg) # cause oom
        except asyncio.QueueFull:
            await self._queue.put(msg) # backpressure

    async def _start(self):
        cdef bytes sid, experiment_id
        cdef Position p_obj
        cdef list datas
        cdef object body, row # Resp
        
        try:
            datas = await async_gt.get_position()
            for row in datas:
                body = row.body
                sid = body.sid
                experiment_id = body.experiment_id

                asset_info = await self.asset_cache.addinfo(sid)
                p_obj = Position(experiment_id = experiment_id,
                                sid = sid,
                                asset_info = asset_info,
                                datetime = body.datetime,
                                size = body.size,
                                available = body.available,
                                cost_basis = body.cost_basis,
                                pnl = body.pnl)
                self.positions[sid] = p_obj # setdefault return default object
            # print(f"TrackerActor _start positions: {self.positions}")
            await self.cash_manager._start()
            self._create_and_send_snapshot(reason="_start", msg=None)

        except Exception as e:
            logger.exception(f"Error starting position tracker: {e}")

    async def run(self):
        cdef ActorMessage msg
        cdef object result = None  
        cdef object error = None   

        try:
            await self._start()
            logger.info(f"Actor {self.experiment_id} ready.")
        except Exception as e:
            logger.critical(f"Actor {self.experiment_id} start failed: {e}", exc_info=True)
            await self._fail_pending_messages(e) # avoid dead lock 
            return 

        while True:
            msg = await self._queue.get()
            on_writer = True
            payload = msg.payload

            try:
                if msg.actor_id.MsgType == MsgType.Sentinel:
                    break 
                
                elif msg.actor_id.MsgType == MsgType.Account:
                    self.set_cash(payload)
                
                elif msg.actor_id.MsgType == MsgType.Order:
                    await self.process_order(payload)
                    on_writer = True if len(payload.exbits) else False

                elif msg.actor_id.MsgType == MsgType.Snapshot:
                    on_writer = False
                    
                elif msg.actor_id.MsgType == MsgType.Settlement:
                    await self.on_dt_over(payload)

                self._create_and_send_snapshot(reason="_run", msg=msg, writer=on_writer) 

                if msg.reply_future and not msg.reply_future.done():
                    result = self.get_snapshot()
                    msg.reply_future.set_result(result)

            except Exception as e:
                logger.error(f"Actor {self.experiment_id} process error: {e}", exc_info=True)
                if msg.reply_future and not msg.reply_future.done():
                    msg.reply_future.set_exception(e)

    cdef tuple set_cash(self, object event):
        """set cash and accout wrt"""
        self.cash_manager.set_cash(event)
    
    async def process_order(self, Order order):
        cdef Position p_sid
        cdef OrderCoreData core = order.core
        cdef bytes sid = core.sid
        cdef OrderExecutionBit ordbit

        asset_info = await self.asset_cache.addinfo(sid)
        # p_objs = self.positions.setdefault(experiment_id, {}) # default value if key not exists
        if sid not in self.positions: 
            self.positions[sid] = Position(sid=sid, experiment_id=self.experiment_id, asset_info=asset_info)
        p_sid = self.positions[sid]

        acct = self.cash_manager.get_account(self.experiment_id)
        order.addinfo(asset_info)
        await self._fillers[order.filler](order, acct.core.cash, p_sid)

        if order.exbits:
            for ordbit in order.exbits:
                p_sid.update(ordbit) 
            self.cash_manager.sync(self.experiment_id, self.positions)

    async def on_dt_over(self, object event):
        cdef bytes experiment_id = event.experiment_id
        cdef object close_table, adj_table, rgt_table
        cdef list psids = list(self.positions.keys())
        cdef Position p_obj
        cdef int64_t sync_tick = event.body.start_date

        if not psids: 
            self.cash_manager.sync_no_sids(experiment_id, sync_tick)
            return

        close_table, adj_table, rgt_table = await self._fetch_from_rpc(event)
        if close_table:
            for sid in close_table:
                p_obj = self.positions[sid]
                sid_table = close_table[sid]
                close_dt = sid_table.column("day")[0].as_py()
                close_price = sid_table.column("close")[0].as_py()
                p_obj.on_dt_over(int(close_dt), close_price)

        self.cash_manager.sync(self.experiment_id, self.positions)
        self._sync_event(experiment_id, self.positions, adj_table, rgt_table) # next_day sync event
        
    cdef void _sync_event(self, bytes experiment_id, dict pobjs, dict py_adj_table, dict py_rgt_table):
        cdef double event_cash = 0.0
        cdef Position pos_obj  
        cdef unordered_map[int, AdjustmentData] cpp_adj_map # int as key better than cpp_String c++ stl vector& to deref to access value in cython 
        cdef unordered_map[int , RightData] cpp_rgt_map
        cdef vector[EventItem] v_events
        cdef EventItem temp
        cdef int int_sid
        cdef list psids

        psids = list(pobjs.keys())
        if py_adj_table:
            for adj_sid, v in py_adj_table.items():
                int_sid = int(adj_sid)
                cpp_adj_map[int_sid] = AdjustmentData(bonus_share=v.column("bonus_share")[0].as_py(), 
                                                  transfer=v.column("transfer")[0].as_py(), 
                                                  bonus=v.column("bonus")[0].as_py())
                
        if py_rgt_table:
            for rgt_sid, v in py_rgt_table.items():
                int_sid = int(rgt_sid)
                cpp_rgt_map[int_sid] = RightData(ratio=v.column("ratio")[0].as_py(), 
                                             price=v.column("price")[0].as_py())

        for sid_bytes in psids:
            pos_obj = pobjs[sid_bytes] 
            int_sid = int(sid_bytes)
            v_events.clear() 
            adj_it = cpp_adj_map.find(int_sid) 
            if adj_it != cpp_adj_map.end():
                temp.event_type = 0
                temp.adj = deref(adj_it).second 
                v_events.push_back(temp)

            rgt_it = cpp_rgt_map.find(int_sid)
            if rgt_it != cpp_rgt_map.end():
                temp.event_type = 1
                temp.rgt = deref(rgt_it).second 
                v_events.push_back(temp)
            if not v_events.empty():
                event_cash += pos_obj.process_events(v_events)

        if event_cash != 0:
            self.cash_manager.add_cash(experiment_id, event_cash)

    async def _fetch_from_rpc(self, object event):

        async def remote_wrap(int rpc_type, object body):
            cdef list batches = []
            sorted_batches = await async_gt.remote(rpc_type, body) 
            return sorted_batches# return pa.Table.from_batches(batches) / np.fromiter

        cdef object body = event.body
        cdef list psids = list(self.positions.keys())
        cdef int32_t s_dt, e_dt

        s_dt = ts2intdt(body.start_date)
        e_dt = ts2intdt(body.end_date)

        close_body = QueryBody(start_date=s_dt, end_date=s_dt, sid=psids)
        event_body = QueryBody(start_date=e_dt, end_date=e_dt, sid=psids)
        
        close_task = remote_wrap(RpcTopic.Close, close_body) 
        adj_task = remote_wrap(RpcTopic.Adjustment, event_body)
        rgt_task = remote_wrap(RpcTopic.Rightment, event_body)
        close_table, adj_table, rgt_table = await asyncio.gather(close_task, adj_task, rgt_task) 
        return (close_table, adj_table, rgt_table)

    cdef void _create_and_send_snapshot(self, str reason, ActorMessage msg, bint writer=False):
        cdef Position p_obj
        cdef Account acct_snap
        cdef Order order_snap
        cdef dict pos_snaps = {}
        cdef dict payload = {}
        cdef list posn_body = []
        cdef object snapshot_body
         
        # Deep Copy Positions and Account
        for sid, p_obj in self.positions.items():
            pos_snaps[sid] = p_obj.clone() # C Level clone
            posn_body.append(p_obj.clone().serialize().body)
            
        acct_snap = self.cash_manager.get_account(self.experiment_id).clone()
        payload = {
            "positions": pos_snaps,
            "account": acct_snap
        }

        if msg and msg.actor_id.MsgType == MsgType.Order:
            order_snap = msg.payload
            snapshot_body = SnapshotBody(
                account=acct_snap.serialize().body, 
                positions=posn_body,
                order=[item.body for item in order_snap.clone().serialize()]
            )
            payload["order"] = order_snap.clone()
        else:
            snapshot_body = SnapshotBody(
                account=acct_snap.serialize().body, 
                positions=posn_body,
            )

        self._latest_snapshot = snapshot_body 
        if writer:
            self._writer.push(payload)

    async def _fail_pending_messages(self, Exception e):
        while not self._queue.empty():
            msg = self._queue.get_nowait()
            if msg.reply_future and not msg.reply_future.done():
                msg.reply_future.set_exception(e)

    cdef object get_snapshot(self):
        return Resp(body=self._latest_snapshot)


cdef class Simulator:
    
    def __init__(self, int32_t max_size, BatchWriterActor actor):
        self._loop = None # avoid initialize loop in __init__
        self._actors = {}
        self.max_size = max_size 
        self._asset_cache = AssetCache()
        self._writer = actor

    cdef void attach(self, loop):
        self._loop = loop
        
    async def set_cash(self, object event):
        cdef bytes experiment_id = event.experiment_id
        cdef TrackerActor actor = self._get_or_create_actor(experiment_id)
        cdef object future = self._loop.create_future()
        
        msg = ActorMessage(MsgType.Account, experiment_id, event, future)
        await actor.push(msg)
        
        result = await future
        return result

    async def submit(self, Order order):
        cdef bytes experiment_id = order.core.experiment_id
        cdef TrackerActor actor = self._get_or_create_actor(experiment_id)
        cdef object future = self._loop.create_future()
        
        msg = ActorMessage(MsgType.Order, experiment_id, order, future)
        await actor.push(msg)

        result = await future
        return result

    async def on_dt_over(self, object event): # nonblocking
        cdef bytes experiment_id = event.experiment_id
        cdef TrackerActor actor = self._get_or_create_actor(experiment_id)
        cdef object future = self._loop.create_future()
        
        msg = ActorMessage(MsgType.Settlement, experiment_id, event, future)
        await actor.push(msg)

        result = await future
        return result

    async def getvalue(self, object event):
        cdef bytes experiment_id = event.experiment_id
        cdef TrackerActor actor = self._get_or_create_actor(experiment_id)
        cdef object future = self._loop.create_future()
        
        msg = ActorMessage(MsgType.Snapshot, experiment_id, event, future)
        await actor.push(msg)

        result = await future
        return result

    cdef TrackerActor _get_or_create_actor(self, bytes experiment_id):
        cdef TrackerActor actor

        if experiment_id not in self._actors:
            actor = TrackerActor(experiment_id, self._writer, self._asset_cache, self.max_size)
            self._actors[experiment_id] = actor
            self._loop.create_task(actor.run())
        return self._actors[experiment_id]

    async def shutdown(self):
        cdef ActorMessage msg = ActorMessage(MsgType.Sentinel, b"", None)
        cdef dict _sentinel = {MsgType.Sentinel: 0}

        for actor in self._actors.values():
            await actor.push(msg)
        # if self._actor_tasks:
        #     await asyncio.gather(*self._actor_tasks, return_exceptions=True)
        logger.info("All TrackerActors stopped.")
        self._writer.push(_sentinel)
        await self._writer.wait_until_finished()
        logger.info("Simulator shutdown complete.")
