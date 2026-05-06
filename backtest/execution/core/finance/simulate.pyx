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
from bt_sdk.core.client import RpcTopic
from backtest.execution.gateway.interface import async_gt

from libcpp.unordered_map cimport unordered_map
from libcpp.string cimport string as cpp_string
from libcpp.pair cimport pair
from libcpp.vector cimport vector
from cython.operator cimport dereference as deref
from libc.stdint cimport int32_t, int64_t

from backtest.execution.core.finance.position cimport Position, PositionCoreData
from backtest.execution.core.finance.order cimport OrderCoreData, Order
from backtest.execution.core.finance.account cimport Account
from backtest.execution.core.finance.trade cimport OrderExecutionBit
from backtest.execution.core.finance.common cimport EventItem, AdjustmentData, RightData
from backtest.execution.core.finance.filler cimport PseudoFiller, OCC, Smooth, Likehood 
from backtest.execution.core.finance.simulate_types cimport MsgType
from backtest.execution.utils.util cimport ts2intdt
from backtest.execution.actor.writer_actor cimport IBatchWriter


cimport numpy as cnp
cnp.import_array() # initialize numpy C-API

logger = logging.getLogger(__name__)


cdef class ActorMessage:

    def __init__(self, int32_t _type, bytes experiment_id, object payload, object reply_future=None):
        self.actor_id.MsgType = _type
        self.actor_id.experiment_id = experiment_id
        self.payload = payload
        self.reply_future = reply_future


cdef class TrackerActor:

    def __init__(self, IBatchWriter writer, AssetCache asset_cache, int32_t q_size, int32_t buffer_size):
        
        self.positions = {}
        self._put_buffer = [] 
        self.buffer_size = buffer_size
        self._queue = asyncio.Queue(maxsize=q_size)
        self.cash_manager = AsyncCashManager()
        self.asset_cache = asset_cache

        self._writer = writer 

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
    
    cdef tuple set_cash(self, object event):
        """set cash and accout wrt"""
        self.cash_manager.set_cash(event)

    async def run(self):
        cdef ActorMessage msg
        cdef Order order_payload
        cdef object result = None  

        try:
            await self._start()
            logger.info("Actor start ready.")
        except Exception as e:
            logger.critical(f"Actor start failed: {e}", exc_info=True)
            return 

        while True:
            msg = await self._queue.get()
            payload = msg.payload

            try:
                if msg.actor_id.MsgType == MsgType.Sentinel:
                    break 
                
                elif msg.actor_id.MsgType == MsgType.Account:
                    self.set_cash(payload)
                    self._create_and_send_snapshot(reason="account_sync", msg=msg, writer=False)
                
                elif msg.actor_id.MsgType == MsgType.Order:
                    await self.process_order(payload)

                    order_payload = <Order>payload
                    order_schema = order_payload.to_schema() 

                    if order_schema.order_bits:
                        self._put_buffer.append({"order": order_schema})
                
                    self._create_and_send_snapshot(reason="order_sync", msg=msg, writer=False, ord_body=order_payload.serialize())

                elif msg.actor_id.MsgType == MsgType.Tplus1:
                    await self.on_dt_over(payload)

                    self._create_and_send_snapshot(reason="tplus1_eod", msg=msg, writer=True)

                elif msg.actor_id.MsgType == MsgType.Snapshot:

                    self._create_and_send_snapshot(reason="query", msg=msg, writer=False)

                if msg.reply_future and not msg.reply_future.done():
                    result = self.get_snapshot()
                    msg.reply_future.set_result(result)

            except Exception as e:
                logger.error(f"Actor process error: {e}", exc_info=True)
                if msg.reply_future and not msg.reply_future.done():
                    msg.reply_future.set_exception(e)

    async def _fetch_from_rpc(self, object event):

        async def remote(int32_t rpc_type, object body):
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
        
        close_task = remote(RpcTopic.Close, close_body) 
        adj_task = remote(RpcTopic.Adjustment, event_body)
        rgt_task = remote(RpcTopic.Rightment, event_body)
        closes_df, adjs_df, rgts_df = await asyncio.gather(close_task, adj_task, rgt_task) 
        return (closes_df, adjs_df, rgts_df)
    
    async def process_order(self, Order order):
        cdef OrderCoreData core = order.core
        cdef bytes sid = core.sid
        cdef bytes experiment_id = core.experiment_id
        cdef OrderExecutionBit ordbit
        cdef Position p_sid

        asset_info = await self.asset_cache.addinfo(sid)
        # p_objs = self.positions.setdefault(experiment_id, {}) # default value if key not exists
        if sid not in self.positions: 
            self.positions[sid] = Position(sid=sid, experiment_id=experiment_id, asset_info=asset_info)
        p_sid = self.positions[sid]

        acct = self.cash_manager.get_account(experiment_id)
        order.addinfo(asset_info)
        await self._fillers[order.filler](order, acct.core.cash, p_sid)

        if order.exbits:
            for ordbit in order.exbits:
                p_sid.update(ordbit) 
            self.cash_manager.update(experiment_id, order.exbits, p_sid.core.pnl)

    async def on_dt_over(self, object event):
        cdef bytes experiment_id = event.experiment_id
        cdef int64_t sync_tick = event.body.start_date
        cdef list psids = list(self.positions.keys())
        cdef Position p_obj
        
        cdef int32_t close_dt
        cdef double close_price

        if not psids:
            self.cash_manager.sync(experiment_id, sync_tick, {})
            return

        closes_df, adjs_df, rgts_df = await self._fetch_from_rpc(event)

        # for _, close_df in closes_df.items():
        #     if not close_df.is_empty():
        #         for sid, day, close in close_df.select(["sid", "day", "close"]).rows(): # better than iter_rows(named=True)
        #             if sid in self.positions:
        #                 p_obj = self.positions[sid]

        #                 close_dt = int(day)
        #                 close_price = float(close)
        #                 # print("simulate on_dt_over: ", close_dt, close_price)
        #                 print("position on_dt_over")
        #                 p_obj.on_dt_over(close_dt, close_price)
        #                 # print("finish simulate on_dt_over: ", p_obj)
        
        if closes_df:
            for sid_bytes, p_obj in self.positions.items():
                close_df = closes_df.get(sid_bytes, None)
                # if close_df is None:
                #     close_df = closes_df.get(sid_bytes.decode('utf-8'))
                
                if close_df is not None and not close_df.is_empty():
                    for day, close in close_df.select(["day", "close"]).rows():
                        close_dt = int(day)
                        close_price = float(close)
                        print("position on_dt_over")
                        p_obj.on_dt_over(close_dt, close_price)

        self.cash_manager.sync(experiment_id, sync_tick, self.positions)
        self._sync_event(experiment_id, self.positions, adjs_df, rgts_df) 
 
    cdef void _sync_event(self, bytes experiment_id, dict pobjs, dict py_adj_dfs, dict py_rgt_dfs):
        cdef double event_cash = 0.0
        cdef Position pos_obj  
        cdef unordered_map[int32_t, AdjustmentData] cpp_adj_map 
        cdef unordered_map[int32_t, RightData] cpp_rgt_map
        cdef vector[EventItem] v_events
        cdef EventItem temp
        cdef int32_t int_sid

        for sid, py_adj_df in py_adj_dfs.items():
            if not py_adj_df.is_empty():
                for bonus_share, transfer, bonus in py_adj_df.select(["bonus_share", "transfer", "bonus"]).rows():
                    int_sid = int(sid)
                    cpp_adj_map[int_sid] = AdjustmentData(
                        bonus_share=float(bonus_share), 
                        transfer=float(transfer), 
                        bonus=float(bonus)
                    )

        for sid, py_rgt_df in py_rgt_dfs.items():
            if not py_rgt_df.is_empty():
                for ratio, price in py_rgt_df.select(["ratio", "price"]).rows():
                    int_sid = int(sid)
                    cpp_rgt_map[int_sid] = RightData(
                        ratio=float(ratio), 
                        price=float(price)
                    )

        for sid_bytes, pos_obj in pobjs.items():
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

    cdef _flush(self):
        if not self._put_buffer: return

        self._writer.push(self._put_buffer)
        self._put_buffer = []

    # separate order --- event stream  from snapshot
    # 1 position / order and  1 account  daily avoid `UniqueConstraint`
    cdef void _create_and_send_snapshot(self, str reason, ActorMessage msg, bint writer=False, list ord_body=[]):
        cdef bytes experiment_id
        cdef Position p_obj
        cdef Account acct
        
        cdef dict pos_snaps = {}
        cdef list pobj_body =[]
        
        if msg is not None:
            experiment_id = msg.actor_id.experiment_id
        else:
            return 
        
        acct = self.cash_manager.get_account(experiment_id).clone()
            
        for sid, p_obj in self.positions.items():
            if p_obj.closed:
                continue
            
            pos_snaps[sid] = p_obj.to_schema()
            pobj_body.append(p_obj.serialize().body)
            
        self._latest_snapshot = SnapshotBody(
            account=acct.serialize().body, 
            positions=pobj_body,
            order=ord_body
        )

        if writer:
            payload = {
                "positions": pos_snaps,
                "account": acct.to_schema()
            }
            self._put_buffer.append(payload)
            if len(self._put_buffer) >= self.buffer_size:
                self._flush()
    
    cdef object get_snapshot(self):
        return Resp(body=self._latest_snapshot)

    async def shutdown(self):
        self._flush()
        self._writer.push([MsgType.Sentinel])


cdef class Simulator:
    
    def __init__(self, int32_t q_size, int32_t buffer_size, IBatchWriter actor):
        self._loop = None # avoid initialize loop in __init__
        self._actors = {}
        self.q_size = q_size 
        self.buffer_size = buffer_size
        self._asset_cache = AssetCache()

        self._writer = actor

    cdef void attach(self, loop):
        self._loop = loop

    cdef TrackerActor _get_or_create_actor(self, bytes experiment_id):
        cdef TrackerActor actor

        if experiment_id not in self._actors:
            actor = TrackerActor(self._writer, self._asset_cache, self.q_size, self.buffer_size)
            self._actors[experiment_id] = actor
            self._loop.create_task(actor.run())
        return self._actors[experiment_id]
        
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
        
        msg = ActorMessage(MsgType.Tplus1, experiment_id, event, future)
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

    async def shutdown(self):
        cdef ActorMessage msg = ActorMessage(MsgType.Sentinel, b"", None)

        for actor in self._actors.values():
            await actor.push(msg)
            await actor.shutdown()
        # if self._actor_tasks:
        #     await asyncio.gather(*self._actor_tasks, return_exceptions=True)
        logger.info("All TrackerActors stopped.")
        await self._writer.wait_until_finished()
        logger.info("Simulator shutdown complete.")
