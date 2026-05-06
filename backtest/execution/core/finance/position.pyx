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
# distutils: language = c++
# cython: language_level=3
import uuid
import json

from bt_sdk.core.protocol import PositionBody, Resp
from backtest.execution.gateway.operator.schema import vtPosition

from backtest.execution.utils.util cimport ts2intdt, num2date
from backtest.execution.core.finance.function cimport calc_ratio, cRatio
from backtest.execution.core.finance.trade cimport OrderExbitData


cdef class Position:
    '''
    Keeps and updates the size and price of a position. The object has no
    relationship to any asset. It only keeps size and price.

    Member Attributes:
      - size (int): current size of the position
      - price (float): current price of the position

    The Position instances can be tested using len(position) to see if size
    is not null
    '''
    def __init__(self, 
                bytes experiment_id, 
                bytes sid, 
                dict asset_info,
                int64_t datetime=0, 
                int32_t size=0, 
                int32_t available=0, 
                double cost_basis=0.0,
                double pnl=0.0
               ):
        self.core.experiment_id = experiment_id
        self.core.sid = sid
        self.core.datetime = datetime

        self.core.size = size
        self.core.available = available # due to T + 1
        self.core.cost_basis = cost_basis
        self.core.pnl = pnl
        self.core.pval = 0.0
        
        self.asset_info = AssetCore(asset_info["first_trading"], asset_info["delist"], asset_info["tick_size"], asset_info["increment"])

    property closed:
        def __get__(self):
            return self.core.size == 0
    
    cdef int32_t get_available(self):
        return self.core.available
    
    cdef void update(self, OrderExecutionBit orderbit):
        '''
        Updates the current position and returns the updated size, price and
        units used to open/close a position

        Args:
            size (int32_t): amount to update the position size
                size < 0: A sell operation has taken place
                size > 0: A buy operation has taken place

            cost_basis (float):
                Must always be positive to ensure consistency

        Returns:
            A tuple (non-named) contaning
               size - new position size
                   Simply the sum of the existing size plus the "size" argument
               cost_basis - new position cost_basis
                   If a position is increased the new average cost_basis will be
                   returned
                   If a position is reduced the cost_basis of the remaining size
                   does not change
                   If a position is closed the cost_basis is nullified
                   If a position is reversed the cost_basis is the cost_basis given as
                   argument
               opened - amount of contracts from argument "size" that were used
                   to open/increase a position.
                   A position can be opened from 0 or can be a reversal.
                   If a reversal is performed then opened is less than "size",
                   because part of "size" will have been used to close the
                   existing position
               closed - amount of units from arguments "size" that were used to
                   close/reduce a position

            Both opened and closed carry the same sign as the "size" argument
            because they refer to a part of the "size" argument
        '''
        cdef OrderExbitData core = orderbit.core
        cdef int32_t sign = 1 if core.isbuy else -1
        cdef int32_t size = sign * core.executed_size 
        cdef double price = core.executed_price

        cdef double cost_basis = self.core.cost_basis
        cdef int32_t orig_size = self.core.size
        cdef int32_t available = self.core.available + size

        if available < 0:
            print("not supported short order") 
            return 

        self.core.size += size

        if not self.core.size: # Update closed existing position 
            opened, closed = 0, size
            self.core.available = 0
        elif not orig_size: # Update opened a position from 0 and available stay same
            opened, closed = size, 0
            self.core.cost_basis = price
        elif orig_size > 0:  # existing "long" position
            if size > 0:  # increased position
                opened, closed = size, 0
                self.core.cost_basis = (cost_basis * orig_size + size * price) / (orig_size + size)
            else : # decrease position under available
                opened, closed = 0, size
                self.core.available = available
                self.core.cost_basis = cost_basis - (price - cost_basis) * size / self.core.size
        else:
            return
        
        self._execute(orderbit) 

    cdef _execute(self, OrderExecutionBit orderbit):
        cdef OrderExbitData trade_core = orderbit.core
        cdef double trade_price = trade_core.executed_price
        cdef int64_t trade_dts = trade_core.executed_dt

        self.core.datetime = trade_dts
        self.core.pnl = self.core.size * (trade_price - self.core.cost_basis)
        # self.core.pval = self.core.size * trade_price
        # self.core.cash = trade_core.cash 
        self.core.pval += trade_core.val
 
    cdef double process_events(self, vector[EventItem]& events):
        cdef double total_bonus = 0.0
        cdef int32_t i
        cdef int32_t n = events.size()
        
        for i in range(n):
            total_bonus += self._process_event(events[i])
            
        return total_bonus

    cdef double _process_event(self, EventItem item):
        cdef cRatio cr
        cdef double event_bonus = 0.0
        cdef double sizer_ratio , bonus_ratio
        cdef double cost_basis = self.core.cost_basis
        cdef int32_t origin_size = self.core.size 
        
        if item.event_type == 0:  # adjustment
            cr = calc_ratio(item.adj)
            sizer_ratio = cr.sizer_ratio
            bonus_ratio = cr.bonus_ratio

            self.core.size = <int32_t>(origin_size * sizer_ratio)
            self.core.cost_basis = cost_basis / sizer_ratio
            event_bonus = origin_size * bonus_ratio
            # print("_process_event", origin_size, sizer_ratio, bonus_ratio)
            return event_bonus
        else: 
            sizer_ratio = item.rgt.ratio / 10
            right_price = cost_basis + item.rgt.price * sizer_ratio
            self.core.cost_basis = right_price / (1 + sizer_ratio)
            return 0.0
 
    cdef void _dt_over(self, int32_t end_dt, double close):
        cdef int32_t size = self.core.size
        cdef double cost_basis = self.core.cost_basis
        cdef int32_t delist = self.asset_info.delist

        if delist > 0 and delist <= end_dt:
            self.core.size = 0
            self.core.available = 0
            self.core.pnl = 0
        else:
            self.core.pnl = size * (close - cost_basis)
            self.core.pval = size * close
        
        # self.core.datetime = int(num2date(end_dt).timestamp()) + 86399 # 24 * 3600 -1
        self.core.datetime = end_dt

    cdef void on_dt_over(self, int32_t end_dt, double close):
        print("position on_dt_over: ", end_dt, close)
        # sync size due to T + 1
        cdef int32_t size = self.core.size
        self.core.available = size

        self._dt_over(end_dt, close)

    cdef Position clone(self):
        cdef Position obj = Position.__new__(Position) # only allocate memory
        cdef PositionCoreData core 

        core.experiment_id = self.core.experiment_id
        core.sid = self.core.sid
        core.datetime = self.core.datetime
        core.size = self.core.size
        core.available = self.core.available
        core.pnl = self.core.pnl
        core.cost_basis = self.core.cost_basis

        obj.core = core
        obj.asset_info = self.asset_info
        return obj
       
    cdef object serialize(self):
        cdef object body, resp
        
        body = PositionBody(experiment_id=self.core.experiment_id, sid=self.core.sid, size=self.core.size, available=self.core.available,
                            cost_basis=self.core.cost_basis, datetime=self.core.datetime, pnl=self.core.pnl)
        resp = Resp(body=body)
        return resp

    cdef object to_schema(self):
        # cdef object experiment_id = uuid.UUID(self.core.experiment_id.decode("utf-8"))
        cdef object experiment_id = uuid.UUID(bytes=self.core.experiment_id)

        return vtPosition(experiment_id=experiment_id, sid=self.core.sid, 
                        datetime=self.core.datetime, size=self.core.size, available=self.core.available,
                        pnl=self.core.pnl, cost_basis=self.core.cost_basis)

    def __len__(self):
        return self.core.size

    def __bool__(self):
        return bool(self.core.size != 0)

    def __reduce__(self): # sq same as __init__
        return (Position, (self.core.experiment_id, self.core.sid, self.asset_info, self.core.datetime, self.core.size, self.core.available, self.core.cost_basis, self.core.pnl))
    
    def __repr__(self):
        template = "Position(experiment_id={experiment_id} ," \
                   "sid={sid} ," \
                   "asset_info={asset_info} , "\
                   "datetime={datetime} ," \
                   "size={size} ," \
                   "available={available} ," \
                   "cost_basis={cost_basis} ," \
                   "pnl={pnl})"
        formatted_asset_info = json.dumps(self.asset_info, ensure_ascii=False)

        return template.format(
            experiment_id=self.core.experiment_id,
            sid=self.core.sid,
            asset_info=formatted_asset_info,
            datetime=self.core.datetime,
            size=self.core.size,
            available=self.core.available,
            cost_basis=self.core.cost_basis,
            pnl=self.core.pnl
        )
