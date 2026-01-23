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
import warnings
import numpy as np
import queue
import pyarrow as pa
import pyarrow.compute as pc
import reactivex.operators as ops

from typing import List

from backtest.feed import DataBase
from backtest.dataseries import TimeFrame
from backtest.metabase import with_metaclass
from backtest.stores.btstore import BTStore
from backtest.utils.dateintern import num2date
from bt_sdk.core.protocol import QueryBody


__all__ = ["BtData"]


def chain_table(tables: List[pa.Table]):
    ctable = pa.concat_tables(tables, promote_options="permissive") # zero_copy , but combine_chunk is heavy memory ops
    return ctable


class Calendar:
    '''Descriptor calendar'''
    def __init__(self, max_expected_size=100000):
        self._current_idx = 0
        self._allocated_buf = np.empty(max_expected_size, dtype=np.int32)

    def _fill_buffer(self, table: pa.Table):
        num_rows = table.num_columns
        self._allocated_buf[self._current_idx: num_rows + self._current_idx] = table["date"].to_numpy()
        self._current_idx += num_rows

    def __get__(self, instance, owner):
        if instance is None: return self
        
        mdapi = getattr(instance, 'mdapi', None)
        
        if self._current_idx == 0:
            obs = mdapi.get_calendar()
            obs.subscribe( # Disposable 
                on_next=self._fill_buffer,
                on_completed=lambda: print("Calendar Loaded")
            )
            obs.run() # block api
        return self._allocated_buf[:self._current_idx]


class Instrument(object):
    '''Descriptor instrument'''
    def __init__(self, batch_size=10):
        self.batch_size = batch_size
        self.assets = {}
    
    def __set__(self, instance, value):
        raise AttributeError("not allowed to set")
    
    def __get__(self, instance, owner):
        if instance is None: return self
        
        mdapi = getattr(instance, 'mdapi', None)

        def process_batch(batch_list):
            datas.extend(batch_list)

        if len(self.assets) == 0:
            datas = []
            # ops.buffer_with_count(self.batch_size) # ops.to_list()
            obs = mdapi.get_instrument().pipe(
                ops.buffer_with_time_or_count(
                    timespan=0.5,            
                    count=self.batch_size    
                    )
                )
            obs.subscribe(
                on_next=process_batch
            )
            obs.run() # run block api
            
            table = pa.concat_tables(datas)
            # df = table.to_pandas()  # Arrow → Pandas
            # self.assets = df.to_dict('records')  # row_dict
            self.assets = table.to_pylist() # row-wise dict list
        return self.assets


class MetaBtData(DataBase.__class__):
    
    def __init__(cls, name, bases, dct):
        """auto Register with the store when type class __import__"""
        super(MetaBtData, cls).__init__(name, bases, dct)
        BTStore.DataCls = cls

    def donew(cls, *args, **kwargs):
        print("MetaBtData donew kwargs ", kwargs)
        _obj, args, kwargs = super(MetaBtData, cls).donew(*args, **kwargs)
        print("MetaBtData donew kwargs after", kwargs)
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        print("MetaBtData dopostinit kwargs ", kwargs)
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs) 
        print("MetaBtData dopostinit kwargs ", kwargs)
        _obj.mdapi = _obj.p.mdapi
        _obj.chan = queue.Queue()
        return _obj, args, kwargs


class BtData(with_metaclass(MetaBtData, DataBase)):
    
    params = (
        ("mdapi", None),
        ("rtbar", False,), # use RealTime 5 seconds bars
        ("batch_size", 10)
    )

    calendar = Calendar() 
    instrument = Instrument()

    def _start(self, *args, **kwargs):
        super()._start(*args,**kwargs)
        self._row_iter = None # initialize iter buffer

        sids = kwargs["sid"]
        start_date = kwargs["fromdate"]
        end_date = kwargs["todate"]

        # calculate tick and adj
        body = QueryBody(start_date=start_date, end_date=end_date, sid=sids)
        observable = self.mdapi.subscribe(body)
        observable.subscribe( # nonblocking 
            on_next=self.chan.put,
            on_error=lambda e: self.chan.put(e),
            on_completed=lambda: self.chan.put(StopIteration) 
        )
        self.calc_adjfactor(body)

        # calculate benchmark
        index = kwargs.get("benchmark", b"000001")
        body = QueryBody(start_date=start_date, end_date=end_date, sid=[index]) 
        self.calc_benchmark(body)

        # setattr
        self.sid = sids
        sid_str = [sid.decode("utf-8") for sid in sids]
        self.extra_info = f"FeedInfo: {start_date}:{end_date}@{','.join(sid_str)}" # any extra info to relate with feed

    def _load(self):
        while True:
            if self._row_iter is not None:
                try:
                    row = next(self._row_iter)
                    # print("row :", row)
                    if self.p.rtbar:
                        self._load_rtbar(row)
                    else:
                        self._load_bar(row)
                    return True
                except StopIteration:
                    self._row_iter = None

            msg = self.chan.get() # next pa.Table
            if msg is StopIteration:
                return False
            if isinstance(msg, Exception):
                raise msg

            self._row_iter = self._make_iter(msg) # self._row_iter = iter(msg.to_pylist()) 

    def _make_iter(self, table):
        cols = [table[name].to_numpy() for name in ['tick', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        return zip(*cols)

    def _load_bar(self, row):
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= row[0]:
            return False 
        
        self.lines.datetime[0] = row[0]
        self.lines.open[0] = row[1]
        self.lines.high[0] = row[2]
        self.lines.low[0] = row[3]
        self.lines.close[0] = row[4]
        self.lines.volume[0] = row[5]
        self.lines.amount[0] = row[6]
        return True

    def _load_rtbar(self, row): # tick 3s
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= row[0]:
            return False  
        
        self.lines.datetime[0] = row[0]
        self.lines.open[0] = row[1]
        self.lines.high[0] = row[1]
        self.lines.low[0] = row[1]
        self.lines.close[0] = row[1]
        self.lines.volume[0] = row[2]
        self.lines.amount[0] = row[3]
        return True

    def calc_adjfactor(self, body: QueryBody):
        adj = self.mdapi.get_factor(body)
        factors = adj.raw_factors # adj_factors
        if factors:
            factors = dict(sorted(factors.items())) # sort by key
            self.adj_factors = factors

    def calc_benchmark(self, body: QueryBody):

        def process_batch(batch_list):
            data.extend(batch_list)

        data = []
        obs = self.mdapi.get_benchmark(body).pipe( # pipe return observal
            ops.buffer_with_time_or_count(
                timespan=0.5,            
                count=self.p.batch_size    
                ),
            # ops.do_action(on_next=process_batch)
            )
        obs.subscribe(
            on_next=process_batch
        )
        obs.run() 
        self.bench = pa.concat_tables(data)

    def stop(self):
        super().stop()
        self.mdapi.disconnect()
