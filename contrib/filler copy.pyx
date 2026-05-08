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
# distutils: language = c++
# cython: profile=False
# cython: language_level=3

import asyncio
import pyarrow as pa
import numpy as np
from functools import partial

from libc.math cimport floor 

from backtest.execution.gateway.interface import async_gt # cimport the async wrapper
from backtest.execution.gateway.interface cimport AsyncGateway  # cimport the enum type

from backtest.execution.utils.util cimport ts2intdt # cdef func differ from cdef class
from backtest.execution.core.finance.order cimport OrderCoreData
from backtest.execution.core.finance.position cimport Position
from backtest.execution.core.finance.slippage cimport PercSlip
from backtest.execution.core.finance.comminfo cimport CommInfo_Stocks
from backtest.execution.core.finance.trade cimport OrderExecutionBit
from bt_sdk.core.protocol import QueryBody
from bt_sdk.core.client import RpcTopic

cimport numpy as cnp
cnp.import_array() # 必须调用以初始化 numpy C-API


cdef inline int calculate(Order order, Position p_sid, double cash, double price):
    '''Returns the size for a given order'''
    cdef AssetCore info = order.info
    cdef OrderCoreData core = order.core
    cdef double tick_value, sizer_cash
    cdef int32_t sizer_size
    cdef bint is_buy = order.isbuy
    
    """plimit or dt trans to price"""
    order.on_fix(price)
    tick_value = price * info.tick_size
    sizer_cash = core.sizer_ratio * cash
    # print("price , tick_value :", price, tick_value, sizer_cash)
    if not is_buy:
        size = p_sid.get_available()
        # print("not is_buy filler calculate size :", size)
        sizer_size = <int32_t>(size * core.sizer_ratio) 
        return sizer_size 

    if tick_value > cash:
        return 0

    # decimal, integer = np.modf(sizer_cash / tick_value)
    # size = integer * info.tick_size
    # if not info.increment:
    #     size += <int>(decimal * info.tick_size)
    # return size

    raw_shares = floor(sizer_cash / tick_value)
    return <int32_t>(raw_shares * info.tick_size)


cdef class PseudoFiller:

    def __init__(self, 
                    double impact = 0.05, 
                    int32_t batch_size = 1000,
                    double slip_perc = 0.005,
                    ):

        self.impact = impact
        self.batch_size = batch_size
        self.slip = PercSlip(slip_perc=slip_perc)
        self.comm = CommInfo_Stocks() 
        
    async def _preload(self, Order ord, cache=None):
        """
            [[tick, open, high, low, close, volume, amount]]
        """
        cdef Lines lines = Lines() 
        cdef OrderCoreData core = ord.core 
        cdef int32_t int_dt = ts2intdt(core.created_dt)
        cdef object request = QueryBody(int_dt, int_dt, [core.sid])

        async def loader(object req):
              cdef double[:, ::1] np_view
              cdef list float_column =["tick", "open", "high", "low", "close", "volume", "amount"]
              cdef object df, cast_df, np_arr

              try:
                  import polars as pl
                  import numpy as np

                  data = await async_gt.remote(RpcTopic.Tick, req) # sid: pl.DataFrame
                  df = data[req.sid[0]]

                  cast_df = df.select(pl.col(float_column).cast(pl.Float64))
                  # 2D Numpy Array np.ascontiguousarray double[:, ::1] (C-Contiguous)
                  np_arr = np.ascontiguousarray(cast_df.to_numpy())

                  np_view = np_arr # Cython MemoryView
                  lines.batch_load(np_view)
              except GeneratorExit:
                  print("GeneratorExit Error means error during line batch_load")
                  pass
              except Exception as e:
                  print(f"Loader Error: {e}")

        if cache is not None:
            data = await cache.get_or_load(request, loader)
            lines.batch_load(data)
        else:
            await loader(request)
        return lines

    cdef (int32_t, double) _exec_fixed(self, int32_t loc, Order order, Lines lines):
        """Time + Fixed Price and Gap"""
        cdef double limit_price = order.core.price
        cdef bint is_buy = order.isbuy
        cdef int32_t n = len(lines)
        cdef int32_t i
        
        for i in range(loc, n): 
            if is_buy:
                if lines.low[i] <= limit_price:
                    if lines.open[i] < limit_price:
                        return i, lines.open[i]
                    return i, limit_price
            else:
                if lines.high[i] >= limit_price:
                    if lines.open[i] > limit_price:
                        return i, lines.open[i]
                    return i, limit_price
                    
        return -1, 0.0

    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines):
        # 算基准价用 loc，没问题，因为这是根据“已知”状态下达的策略
        return (1 + order.core.pricelimit) * lines.close[loc]

    cdef (int32_t, double) _exec_dynamic(self, int32_t loc, Order order, Lines lines):
        """Time + PriceLimit"""
        cdef double trigger_price
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy 
        cdef int32_t n = len(lines)
        cdef int32_t i
        
        trigger_price = (1 + core.pricelimit) * lines.open[loc] 
        trigger_price = self._calc_dynamic_price(loc, order, lines)
        
        for i in range(loc, n): # C for replace np.where and mask / nogil
            if is_buy:
                if lines.low[i] <= trigger_price: 
                    return i, trigger_price
            else:
                if lines.high[i] >= trigger_price: 
                    return i, trigger_price
        return -1, 0.0

    cdef void _filler(self, Order order, Position p_sid, double cash, Lines lines):
        cdef double p_max, p_min, reach_limit, comm, order_price, slip_price
        cdef int32_t size, filler_size, loc, exec_loc
        cdef OrderExecutionBit order_bit
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy
            
        p_max = lines.max() 
        p_min = lines.min()
        reach_limit = (p_max - p_min) / p_min

        if reach_limit < 0.01: # # filter stock reachlimit 
            return

        on_slip = partial(self.slip, pmax=p_max, pmin=p_min, isbuy=is_buy)
        on_comm = partial(self.comm, order=order)

        is_in = lines.is_in(core.created_dt)
        if not is_in:
            raise AssertionError(f"{core.created_dt} out of lines tick")

        loc = np.searchsorted(lines.tick, core.created_dt) 

        # ----------------------------------------------------
        # simulate route logic
        # ----------------------------------------------------
        exec_loc = -1
        
        if core.exec_type == 0: # Market
            exec_loc = loc
            order_price = lines.close[loc] 
            
        elif core.exec_type == 1: # Fixed Limit
            exec_loc, order_price = self._exec_fixed(loc, order, lines)
            
        elif core.exec_type == 2: # Dynamic Limit
            exec_loc, order_price = self._exec_dynamic(loc, order, lines)
            
        else:
            raise NotImplementedError(f"exec_type {core.exec_type} is not implemented")

        # ----------------------------------------------------
        # execute
        # ----------------------------------------------------
        if exec_loc >= 0:

            slip_price = on_slip(price=order_price)
            size = calculate(order, p_sid, cash, order_price) 
            
            if size <= 0:
                return

            filler_size = min(size, <int32_t>(lines.volume[exec_loc] * self.impact))
            comm = on_comm(size=filler_size, price=slip_price)
            
            print(f"Executed! Type: {core.exec_type}, filler_size: {filler_size}, slip_price: {slip_price}, comm: {comm}")
            
            order_bit = OrderExecutionBit(
                              vtorder_id = core.vtorder_id,
                              executed_dt=lines.tick[exec_loc], 
                              executed_size=filler_size, 
                              executed_price=slip_price, 
                              comm=comm,
                              isbuy=is_buy)
                              
            order.execute(size, order_price, order_bit)


    cdef (int32_t, double) _find_limit_execution(self, int32_t loc, double limit_price, bint is_buy, Lines lines):
        """核心寻价引擎：无论是固定限价还是动态比例，底层撮合逻辑是一致的"""
        cdef int32_t n = len(lines)
        cdef int32_t i
        
        for i in range(loc, n): 
            if is_buy:
                # 买单：价格跌到或跌破 limit_price
                if lines.low[i] <= limit_price:
                    # 跳空低开福利：开盘直接低于你的限价，以开盘价成交
                    if lines.open[i] < limit_price:
                        return i, lines.open[i]
                    return i, limit_price
            else:
                # 卖单：价格涨到或突破 limit_price
                if lines.high[i] >= limit_price:
                    # 跳空高开福利：开盘直接高于你的限价，以开盘价成交
                    if lines.open[i] > limit_price:
                        return i, lines.open[i]
                    return i, limit_price
                    
        return -1, 0.0


    cdef void _filler(self, Order order, Position p_sid, double cash, Lines lines):
        cdef double p_max, p_min, reach_limit, comm, order_price, slip_price
        cdef double target_limit_price = 0.0
        cdef int32_t total_size, filler_size, loc, exec_loc, remains
        cdef OrderExecutionBit order_bit
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy
        cdef int32_t n = len(lines)
            
        p_max = lines.max() 
        p_min = lines.min()
        reach_limit = (p_max - p_min) / p_min

        # 过滤一字涨跌停 (无流动性，无法撮合成交)
        if reach_limit < 0.01: 
            return

        on_slip = partial(self.slip, pmax=p_max, pmin=p_min, isbuy=is_buy)
        on_comm = partial(self.comm, order=order)

        is_in = lines.is_in(core.created_dt)
        if not is_in:
            raise AssertionError(f"{core.created_dt} out of lines tick")

        # 找到下单时的初始 Tick 位置
        loc = np.searchsorted(lines.tick, core.created_dt) 

        # ==========================================
        # 1. 确定订单的目标总数量 (Total Size)
        # ==========================================
        # 如果这是一个刚生成的新订单，需要计算它一共要买/卖多少
        if core.size == 0:
            # 使用一个参考价格来测算数量
            order_price = core.price if core.exec_type == 1 else lines.close[loc]
            total_size = calculate(order, p_sid, cash, order_price) 
            
            if total_size <= 0:
                return
            # 锁定该订单的理论总规模
            core.size = total_size 
        else:
            # 如果是之前部分成交留下的挂单，直接取已有 size
            total_size = core.size

        # 计算剩余需要吃货的数量 (前提是 order.execute 里有维护 executed_size 的累加逻辑)
        remains = total_size - core.executed_size

        # ==========================================
        # 2. 预先计算限价单的目标价格
        # ==========================================
        if core.exec_type == 1:
            target_limit_price = core.price
        elif core.exec_type == 2:
            # 动态单：基准价永远是下单那一刻（loc）的开盘价，算好后就成了固定限价！
            target_limit_price = (1 + core.pricelimit) * lines.open[loc]

        # ==========================================
        # 3. Eager 吃货循环 (支持 Partial Fill)
        # ==========================================
        while remains > 0 and loc < n:
            exec_loc = -1
            
            if core.exec_type == 0:
                # 市价单：在此刻无脑吃货，如果吃不完，下一秒(loc+1)继续市价吃货
                exec_loc = loc
                order_price = lines.close[loc] 
            else:
                # 限价单 & 条件单：去未来的 Tick 寻找击穿价格的机会
                exec_loc, order_price = self._find_limit_execution(loc, target_limit_price, is_buy, lines)

            # 如果在这批 K 线里再也找不到满足限价的机会了，挂单继续等待下一次数据
            if exec_loc < 0:
                break

            # ------------------------------------
            # 成功寻价，执行局部撮合 (Partial Fill)
            # ------------------------------------
            slip_price = on_slip(price=order_price)

            # 流动性限制：本 Tick 最多能吃掉的市场量
            filler_size = min(remains, <int32_t>(lines.volume[exec_loc] * self.impact))
            
            # 如果该 Tick 连 1 股都吃不到（如流动性极差），跳到下一个 Tick 继续尝试
            if filler_size <= 0:
                loc = exec_loc + 1
                continue

            comm = on_comm(size=filler_size, price=slip_price)
            
            order_bit = OrderExecutionBit(
                              vtorder_id = core.vtorder_id,
                              executed_dt = lines.tick[exec_loc],
                              executed_size = filler_size, 
                              executed_price = slip_price, 
                              comm = comm,
                              isbuy = is_buy)
                              
            # 【关键】将这次的部分成交信息传入，底层应累加 `core.executed_size += filler_size`
            order.execute(total_size, order_price, order_bit)

            # 更新还剩多少没买完
            remains -= filler_size

            # 将游标向后推一个 Tick，如果 remains > 0，下一次循环将从下一分钟继续吃货
            loc = exec_loc + 1
            
        # 循环结束：如果 remains == 0，代表此单已彻底宣告完结 (Filled)
        # 如果 remains > 0 但 n 跑完了，代表收盘了或这批数据跑完了，保持 Partial 状态，留到下一批！

    async def __call__(self, Order order, double cash, Position p_sid):
        try:
            lines = await self._preload(order)
            if len(lines) == 0:
                print("order lines is empty :", order)
                return
            self._filler(order, p_sid, cash, lines)
        except Exception as e:
            print(f"Error during filler preload: {e}")
            return


cdef class OCC(PseudoFiller):

    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines):
        return (1 + order.core.pricelimit) * lines.close[loc]

cdef class Smooth(PseudoFiller):

    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines):
        cdef double smooth_price = (lines.open[loc] + lines.close[loc] + lines.high[loc] + lines.low[loc]) / 4
        return (1 + order.core.pricelimit) * smooth_price

cdef class Likehood(PseudoFiller):

    cdef double _calc_dynamic_price(self, int32_t loc, Order order, Lines lines):
        if order.isbuy:
            return (1 + order.core.pricelimit) * lines.high[loc]
        else:
            return (1 + order.core.pricelimit) * lines.low[loc]
