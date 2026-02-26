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

from backtest.execution.core.gateway.interface import async_gt # cimport the async wrapper
from backtest.execution.core.gateway.interface cimport AsyncGateway, RpcTopic  # cimport the enum type

from backtest.execution.utils.util cimport ts2intdt # cdef func differ from cdef class
from backtest.execution.core.finance.order cimport OrderCoreData
from backtest.execution.core.finance.position cimport Position
from backtest.execution.core.finance.comminfo cimport CommInfo_Stocks, CommInfo_Futures
from backtest.execution.core.finance.trade cimport OrderExecutionBit
from backtest.protocol import QueryBody

cimport numpy as cnp
cnp.import_array() # 必须调用以初始化 numpy C-API


cdef inline int calculate(Order order, Position p_sid, double cash, double price):
    '''Returns the size for a given order'''
    cdef AssetCore info = order.info
    cdef OrderCoreData core = order.core
    cdef double tick_value, sizer_cash
    cdef int sizer_size
    cdef bint is_buy = order.isbuy
    
    """plimit or dt trans to price"""
    order.on_fix(price)
    tick_value = price * info.tick_size
    sizer_cash = core.sizer_ratio * cash
    if not is_buy:
        size = p_sid.get_available()
        # print("not is_buy filler calculate size :", size)
        sizer_size = <int>(size * core.sizer_ratio) 
        return sizer_size 

    if tick_value > cash:
        return 0

    # decimal, integer = np.modf(sizer_cash / tick_value)
    # size = integer * info.tick_size
    # if not info.increment:
    #     size += <int>(decimal * info.tick_size)
    # return size

    raw_shares = floor(sizer_cash / tick_value)
    return <int>(raw_shares * info.tick_size)


cdef class PseudoFiller:

    def __init__(self, 
                    double impact = 0.05, 
                    double thres = 0.01,
                    int batch_size = 1000,
                    double slip_perc = 0.0,
                    double slip_fixed = 0.0,
                    double commission = 0.0
                    ):

        self.impact = impact
        self.thres = thres
        self.batch_size = batch_size
        self.slip = Slippage(slip_perc=slip_perc, slip_fixed=slip_fixed)
        self.comm = CommInfo_Stocks(commission=commission) 
        
    async def _preload(self, Order ord, cache=None):
        """
            [[tick, open, high, low, close, volume, amount]]
        """
        cdef Lines lines = Lines() 
        cdef OrderCoreData core = ord.core 
        cdef int int_dt = ts2intdt(core.created_dt)
        cdef object request = QueryBody(int_dt, int_dt, [core.sid])

        async def loader(object req):
            cdef object batch
            cdef double[:, ::1] np_view
            # cdef double[:, ::1] buffer_view = np.empty((self.batch_size, cols), dtype=np.float64) # C-Row / Fortan-Col
            cdef list float_column = ["tick", "open", "high", "low", "close", "volume", "amount"]
            cdef object float_schema = pa.schema([
                (n, pa.float64()) for n in float_column
            ])

            try:
                # iterator = await async_gt.rpc(RpcTopic.Tick, req)
                # async for batch in iterator:
                #     select_batch = batch.select(float_column) # batch.drop(["sid"])
                #     cast_batch = select_batch.cast(float_schema) # ).to_tensor().to_numpy() despercated 
                #     arrays = [col.to_numpy() for col in cast_batch.columns] # Arrow to Numpy C-order
                #     np_view = np.column_stack(arrays) # C-Contiguous
                #     lines.batch_load(np_view)
                data = await async_gt.remote(RpcTopic.Tick, req) # sid: table
                table = data[req.sid[0]]
                select_table = table.select(float_column) # batch.drop(["sid"])
                cast_table = select_table.cast(float_schema) # ).to_tensor().to_numpy() despercated 
                arrays = [col.to_numpy() for col in cast_table.columns] # Arrow to Numpy C-order
                np_view = np.column_stack(arrays) # C-Contiguous
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
   
    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines):
        """Cdef bypass Python getattr"""
        cdef double plimit, price
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy 
        cdef int n = len(lines)
        
        plimit = (1 + core.pricelimit) * lines.open[loc] # c level line
        
        for i in range(loc, n): # C for replace np.where and mask / nogil
            if is_buy:
                if lines.high[i] <= plimit:
                    return i, lines.high[i]
            else:
                if lines.low[i] >= plimit:
                    return i, lines.low[i]
        return -1, 0.0

    cdef void _filler(self, Order order, Position p_sid, double cash, Lines lines):
        cdef double p_max, p_min, reach_limit, comm, _price, slip_price
        cdef int size, filler_size, loc
        cdef OrderExecutionBit order_bit
        cdef OrderCoreData core = order.core
        cdef bint is_buy = order.isbuy
            
        p_max = lines.max() # C-level properties for max/min
        p_min = lines.min()
        reach_limit = (p_max - p_min) / p_min

        if reach_limit < self.thres: 
            return

        on_slip = partial(self.slip, pmax=p_max, pmin=p_min, isbuy=is_buy)
        on_comm = partial(self.comm, order=order)

        is_in = lines.is_in(core.created_dt)
        if not is_in:
            raise AssertionError(f"{core.created_dt} out of lines tick`")

        loc = np.searchsorted(lines.tick, core.created_dt) # cnp.ndarray memoryview 

        if core.exec_type == 0:
            filler_price = lines.close[loc] 
            slip_price = on_slip(price=filler_price)

            size = calculate(order, p_sid, cash, filler_price)
            filler_size = min(size, int(lines.volume[loc] * self.impact)) # Use C-level self.impact
            comm = on_comm(size=filler_size, price=slip_price)
            # print(f"Exectype is price filler_size: {filler_size}, slip_price: {slip_price}, comm: {comm}")
            order_bit = OrderExecutionBit(
                              vtorder_id = core.vtorder_id,
                              executed_dt=lines.tick[loc],
                              executed_size=filler_size, 
                              executed_price=slip_price, 
                              comm=comm,
                              isbuy=is_buy)
            order.execute(order_bit)
        elif core.exec_type == 1:
            ploc, filler_price = self._exec_plimit(loc, order, lines) 
            if ploc < 0:
                return 
            slip_price = on_slip(price=filler_price) 

            size = calculate(order, p_sid, cash, filler_price) # np.vectorize(calc_size)(order=order)
            filler_size = min(size, int(lines.volume[ploc] * self.impact))
            comm = on_comm(size=filler_size, price=slip_price)
            # print(f"Exectype is price filler_size: {filler_size}, slip_price: {slip_price}, comm: {comm}")
            order_bit = OrderExecutionBit(
                            vtorder_id = core.vtorder_id,
                            executed_dt=lines.tick[ploc],
                            executed_size=filler_size, 
                            executed_price=slip_price, 
                            comm=comm,
                            isbuy=is_buy)
            order.execute(order_bit)
        else:
            raise NotImplementedError("stoplimit is not implemented")

    async def __call__(self, Order order, double cash, Position p_sid):
        try:
            lines = await self._preload(order)
            if len(lines) == 0:
                print("lines is empty order :", order)
                return
            self._filler(order, p_sid, cash, lines)
        except Exception as e:
            print(f"Error during filler preload: {e}")
            return


cdef class OCC(PseudoFiller):

    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines):
        cdef double plimit, price
        cdef bint is_buy = order.isbuy 
        cdef OrderCoreData core = order.core
        cdef int n = len(lines)
        
        plimit = (1 + core.pricelimit) * lines.close[loc]
        
        for i in range(loc, n):
            if is_buy:
                if lines.high[i] <= plimit:
                    return i, lines.high[i]
            else:
                if lines.low[i] >= plimit:
                    return i, lines.low[i]
        return -1, 0.0

    
cdef class Smooth(PseudoFiller):

    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines):
        cdef double plimit, price
        cdef bint is_buy = order.isbuy 
        cdef OrderCoreData core = order.core
        cdef int n = len(lines)
        
        smooth_price =  (lines.open[loc] + lines.close[loc] + lines.high[loc] + lines.low[loc]) / 4
        plimit = (1 + core.pricelimit)  * smooth_price
        
        for i in range(loc, n):
            if is_buy:
                if lines.high[i] <= plimit:
                    return i, lines.high[i]
            else:
                if lines.low[i] >= plimit:
                    return i, lines.low[i]
        return -1, 0.0


cdef class Likehood(PseudoFiller):

    cdef (int, double) _exec_plimit(self, int loc, Order order, Lines lines):
        cdef double plimit, price
        cdef bint is_buy = order.isbuy 
        cdef OrderCoreData core = order.core
        cdef int n = len(lines)
        
        for i in range(loc, n):
            if is_buy:
                plimit = (1 + core.pricelimit)  * lines.high[loc]
                if lines.high[i] <= plimit:
                    return i, lines.high[i]
            else:
                plimit = (1 + core.pricelimit)  * lines.low[loc]
                if lines.low[i] >= plimit:
                    return i, lines.low[i]
        return -1, 0.0
