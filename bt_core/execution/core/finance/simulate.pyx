# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++

import os
import time
import json
import uuid
import asyncio
import logging
import numpy as np
import threading
import pyarrow as pa
import pyarrow.compute as pc
from collections import defaultdict
from itertools import chain

from bt_core.execution.gateway.interface import async_gt

from libcpp.unordered_map cimport unordered_map
from libcpp.string cimport string as cpp_string
from libcpp.pair cimport pair
from libcpp.vector cimport vector
from cython.operator cimport dereference as deref
from libc.stdint cimport int32_t, int64_t

from bt_core.execution.core.finance.position cimport Position, PositionCoreData
from bt_core.execution.core.finance.order cimport OrderCoreData, Order
from bt_core.execution.core.finance.account cimport Account
from bt_core.execution.core.finance.trade cimport OrderExecutionBit
from bt_core.execution.core.finance.common cimport EventItem, AdjustmentData, RightData
from bt_core.execution.core.finance.filler cimport PseudoFiller, OCC, Smooth, Likehood 
from bt_core.execution.core.finance.simulate_types cimport MsgType
from bt_core.utils.dateintern cimport ts2intdt
from bt_core.execution.actor.writer_actor cimport BatchWriterActor

from bt_protocol._protocol import SnapshotBody, Resp, Event, QueryBody
from bt_protocol.constant import RpcTopic

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

    def __init__(self, bytes experiment_id, BatchWriterActor writer, AssetCache asset_cache, int32_t q_size, int32_t buffer_size):
        
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
        
        self.cached_uuid = uuid.UUID(bytes=experiment_id)
     
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
                                pnl = body.pnl,
                                created_dt = body.created_dt)
                self.positions[sid] = p_obj # setdefault return default object
            # print(f"TrackerActor _start positions: {self.positions}")
            await self.cash_manager._start()
            self._create_and_send_snapshot(reason="_start", msg=None)

        except Exception as e:
            logger.exception(f"Error starting position tracker: {e}")
     
    async def push(self, ActorMessage msg):
        # self._queue.put_nowait(msg) # cause oom
        await self._queue.put(msg) # backpressure
    
    async def run(self):
        cdef ActorMessage msg
        cdef Order order_obj
        cdef OrderExecutionBit ordbit

        cdef dict order_dict, ordbit_dict
        cdef list order_bits
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
                    """set cash and accout wrt"""
                    self.cash_manager.set_cash(payload)
                    self._create_and_send_snapshot(reason="account_sync", msg=msg, writer=False)
                
                elif msg.actor_id.MsgType == MsgType.Order:
                    await self.process_order(payload)

                    order_obj = <Order>payload
                    order_bits = [] # reset

                    # order snapshot
                    order_dict = order_obj.get_snapshot() 
                    order_dict['experiment_id'] = self.cached_uuid
                    order_dict.pop("sizer_ratio")
                    order_dict.pop("pricelimit")

                    for ordbit in order_obj.exbits:
                        ordbit_dict = ordbit.get_snapshot()
                        order_bits.append(ordbit_dict)

                    if order_bits:
                        self._put_buffer.append({"order": [order_dict, order_bits]})
                
                    self._create_and_send_snapshot(reason="order_sync", msg=msg, writer=False, trades=order_obj.serialize())

                elif msg.actor_id.MsgType == MsgType.Tplus1:
                    await self.on_dt_over(payload)

                    self._create_and_send_snapshot(reason="tplus1_eod", msg=msg, writer=True)

                elif msg.actor_id.MsgType == MsgType.Snapshot:

                    self._create_and_send_snapshot(reason="query", msg=msg, writer=False)

                # async put avoid put_nowait oom 
                if len(self._put_buffer) >= self.buffer_size:
                    print("TrackerActor _put_buffer: ", len(self._put_buffer))
                    await self._flush()

                if msg.reply_future and not msg.reply_future.done():
                    result = Resp(body=self._latest_snapshot)
                    msg.reply_future.set_result(result)

            except Exception as e:
                logger.error(f"Actor process error: {e}", exc_info=True)
                if msg.reply_future and not msg.reply_future.done():
                    msg.reply_future.set_exception(e)

    async def process_order(self, Order order):
        cdef OrderCoreData core = order.core
        cdef bytes sid = core.sid
        cdef bytes experiment_id = core.experiment_id
        cdef OrderExecutionBit ordbit
        cdef Position p_sid

        asset_info = await self.asset_cache.addinfo(sid)
        # p_objs = self.positions.setdefault(experiment_id, {}) # default value if key not exists
        if sid not in self.positions: 
            self.positions[sid] = Position(sid=sid, experiment_id=experiment_id, asset_info=asset_info, created_dt=core.created_dt)
        p_sid = self.positions[sid]

        acct = self.cash_manager.get_account(experiment_id)
        order.addinfo(asset_info)
        await self._fillers[order.filler](order, acct.core.cash, p_sid)

        if order.exbits:
            for ordbit in order.exbits:
                p_sid.update(ordbit)
            self.cash_manager.update(experiment_id, order.exbits, p_sid.core.pnl) # avoid position update increment

    async def on_dt_over(self, object event):
        cdef bytes experiment_id = event.experiment_id
        cdef int32_t last_sync_dts = event.body.start_date
        cdef int32_t current_dts = event.body.end_date
        cdef Position p_obj
        cdef list psids
        
        cdef int32_t close_dt
        cdef double close_price

        self._collect() # # avoid self.position explode
        psids = list(self.positions.keys())

        if not psids:
            self.cash_manager.sync(experiment_id, last_sync_dts, {})
            return

        closes_df_map, adjs_df_map, rgts_df_map = await self._fetch_from_rpc(last_sync_dts, current_dts, psids)

        for sid_bytes, p_obj in self.positions.items():
            close_df = closes_df_map.get(sid_bytes, None)
            
            if close_df is not None and close_df.height > 0:
                for day, close in close_df.select(["day", "close"]).rows():
                    close_dt = int(day)
                    close_price = float(close)
                    p_obj.on_dt_over(close_dt, close_price)
            else: # suspend 
                close_dt = ts2intdt(last_sync_dts)
                p_obj.on_dt_over(close_dt, 0.0)

        # T-1 Sync 
        self.cash_manager.sync(experiment_id, last_sync_dts, self.positions)
        # -------------------------------------------------------------
        # 2：T Event Corporate Actions
        # -------------------------------------------------------------
        if current_dts >0:
            self._sync_event(experiment_id, self.positions, adjs_df_map, rgts_df_map)

    cdef void _sync_event(self, bytes experiment_id, dict pobjs, dict py_adj_dfs, dict py_rgt_dfs):
        cdef double event_cash = 0.0
        cdef Position pos_obj  
        cdef unordered_map[int32_t, AdjustmentData] cpp_adj_map 
        cdef unordered_map[int32_t, RightData] cpp_rgt_map
        cdef vector[EventItem] v_events
        cdef EventItem temp
        cdef int32_t int_sid

        for sid_bytes, py_adj_df in py_adj_dfs.items():
            if py_adj_df is not None and py_adj_df.height > 0:
                for bonus_share, transfer, bonus in py_adj_df.select(["bonus_share", "transfer", "bonus"]).rows():
                    # int_sid = int(sid_bytes)
                    # safely bytes "000001" -> int 1
                    int_sid = int(sid_bytes.decode('utf-8')) 
                    cpp_adj_map[int_sid] = AdjustmentData(
                        bonus_share=float(bonus_share), 
                        transfer=float(transfer), 
                        bonus=float(bonus)
                    )

        for sid_bytes, py_rgt_df in py_rgt_dfs.items():
            if py_rgt_df is not None and py_rgt_df.height > 0:
                for ratio, price in py_rgt_df.select(["ratio", "price"]).rows():
                    # int_sid = int(sid_bytes)
                    # safely bytes "000001" -> int 1
                    int_sid = int(sid_bytes.decode('utf-8')) 
                    cpp_rgt_map[int_sid] = RightData(
                        ratio=float(ratio), 
                        price=float(price)
                    )

        for sid_bytes, pos_obj in pobjs.items():
            # int_sid = int(sid_bytes) 
            # safely bytes "000001" -> int 1
            int_sid = int(sid_bytes.decode('utf-8')) 
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

    async def _fetch_from_rpc(self, int32_t prev_dts, int32_t curr_dts, list psids): 
        """
        prev_dt: T-1 Close
        curr_dt: T   ex_dat Adj/Rgt
        """
        async def _fetch(object body, int32_t rpc_type):
            df_dict = await async_gt.rpc(body, rpc_type) 
            return df_dict 

        # 🌟 T-1 Close
        cdef int32_t last_dtint = ts2intdt(prev_dts)
        cdef int32_t curr_dtint = ts2intdt(curr_dts) if curr_dts > 0 else 0

        close_body = QueryBody(start_date=last_dtint, end_date=last_dtint, sid=psids) 
        close_task = asyncio.create_task(_fetch(close_body, RpcTopic.Close))
        
        if curr_dtint == 0:
            closes_df_map = await close_task
            return closes_df_map, {}, {}
            
        event_body = QueryBody(start_date=curr_dtint, end_date=curr_dtint, sid=psids) 
        adj_task = asyncio.create_task(_fetch(event_body, RpcTopic.Adjustment))
        rgt_task = asyncio.create_task(_fetch(event_body, RpcTopic.Rightment))
        
        closes_df_map, adjs_df_map, rgts_df_map = await asyncio.gather(close_task, adj_task, rgt_task) 
        return closes_df_map, adjs_df_map, rgts_df_map

    cdef void _collect(self): # filter psize=0
        cdef bytes sid
        cdef list dead_sids =[]
        cdef Position p
        
        for sid_key, p in self.positions.items():
            if p.core.size == 0:
                dead_sids.append(sid_key)
                
        for sid_key in dead_sids:
            del self.positions[sid_key]
 
    cdef void _create_and_send_snapshot(self, str reason, ActorMessage msg, bint writer=False, list trades=[]):
        # separate order --- event stream  from snapshot
        # 1 position / order and  1 account  daily avoid `UniqueConstraint`
        cdef bytes experiment_id
        cdef Position p_obj
        cdef Account acct

        cdef dict p_dict, a_dict 
        cdef list pos_snaps=[]
        cdef list pobj_body=[] 
        
        if msg is not None:
            experiment_id = msg.actor_id.experiment_id
        else:
            return 

        # account snapshot 
        acct = self.cash_manager.get_account(experiment_id).clone()
        a_dict = acct.get_snapshot()
        a_dict['experiment_id'] = self.cached_uuid

        # position snapshot
        for _, p_obj in self.positions.items():
            if p_obj.core.size == 0:
                continue

            # struct auto dict
            p_clone = p_obj.clone() 
            p_dict = p_clone.get_snapshot() # p.core 
            p_dict['experiment_id'] = self.cached_uuid
            
            pos_snaps.append(p_dict)
            pobj_body.append(p_obj.serialize().body)
            
        self._latest_snapshot = SnapshotBody(
            account=acct.serialize().body, 
            positions=pobj_body,
            trades=trades
        )

        if writer:
            payload = {
                "positions": pos_snaps,
                "account": a_dict,
            }
            self._put_buffer.append(payload)

    async def _flush(self):
        if not self._put_buffer: return

        await self._writer.push(self._put_buffer)
        self._put_buffer = []
    
    async def shutdown(self):
        await self._flush()
        await self._writer.push([MsgType.Sentinel])


cdef class Simulator:
    
    def __init__(self, int32_t q_size, int32_t buffer_size, BatchWriterActor actor):
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
            actor = TrackerActor(experiment_id, self._writer, self._asset_cache, self.q_size, self.buffer_size)
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

    async def get_snapshot(self, object event):
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
        # await asyncio.gather(*self._actor_tasks, return_exceptions=True)
        logger.info("All TrackerActors stopped.")
        await self._writer.wait_until_finished()
        logger.info("Simulator shutdown complete.")
