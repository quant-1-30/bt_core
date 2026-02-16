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


class Calendar:
    '''Descriptor calendar'''
    def __init__(self, max_expected_size=100000):
        self._calendar = []

    def __get__(self, instance, owner):
        if instance is None: return self
        
        mdapi = getattr(instance, 'mdapi', None)
        if not self._calendar:
            datas = mdapi.get_calendar()
            from itertools import chain
            self._calendar = list(chain(*datas))
        return self._calendar


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
        if len(self.assets) == 0:
            table = mdapi.get_instrument() 
            # ctable = pa.concat_tables(tables, promote_options="permissive") # zero_copy , but combine_chunk is heavy memory ops
            self.assets = table.to_pylist() # row-wise dict list / table.to_pandas() and df.to_dict('records') # Arrow --> Pandas
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
        index = kwargs.get("benchmark", b"000001")
        bench_body = QueryBody(start_date=start_date, end_date=end_date, sid=[index]) 
        self.preload(body, bench_body)

        observable = self.mdapi.subscribe(body)
        observable.subscribe( # nonblocking 
            on_next=self.chan.put,
            on_error=lambda e: self.chan.put(e),
            on_completed=lambda: self.chan.put(StopIteration) 
        )

        self.sids = sids
        sid_str = [sid.decode("utf-8") for sid in sids]
        self.extra_info = f"FeedInfo: {start_date}:{end_date}@{','.join(sid_str)}" # any extra info to relate with feed

    def preload(self, body: QueryBody, bench_body: QueryBody):
        self.bench = self.mdapi.get_benchmark(bench_body)
        
        adj = self.mdapi.get_factor(body)
        factors = adj.raw_factors if adj else {} # adj_factors
        if factors:
            factors = dict(sorted(factors.items())) # sort by key
            self.adj_factors = factors
        print(f"[_start] Benchmark and {self.sids} Factors received.", len(self.adj_factors), len(self.bench))

    def _load(self):
        while True:
            if self._row_iter is not None:
                try:
                    row = next(self._row_iter)
                    # print("_load row ", row)
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

            self._row_iter = self._make_iter(msg)

    def _make_iter(self, table):
        cols = [table[name].to_numpy() for name in ['tick', 'open', 'high', 'low', 'close', 'volume', 'amount']] # iter(msg.to_pylist()) 
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
        factors = adj.raw_factors if adj else {} # adj_factors
        if factors:
            factors = dict(sorted(factors.items())) # sort by key
            self.adj_factors = factors

    def calc_benchmark(self, body: QueryBody):
        self.bench = self.mdapi.get_benchmark(body)

    def stop(self):
        super().stop()
        self.mdapi.disconnect()
