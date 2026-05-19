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
import polars as pl
import reactivex.operators as ops

from toolz import valmap
from typing import List, Mapping, Any

from backtest.feed import DataBase
from backtest.dataseries import TimeFrame
from backtest.metabase import with_metaclass
from backtest.stores.localstore import LocalStore
from backtest.utils.dateintern import num2date
from bt_sdk.core.protocol import QueryBody
from bt_sdk.core.client import FactorTopic


__all__ = ["RemoteData"]


class Instrument(object):
    '''Descriptor instrument'''
    def __init__(self):
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


class MetaRemoteData(DataBase.__class__):
    
    def __init__(cls, name, bases, dct):
        """auto Register with the store when type class __import__"""
        super(MetaRemoteData, cls).__init__(name, bases, dct)
        LocalStore.DataCls = cls

    def donew(cls, *args, **kwargs):
        print("MetaRemoteData donew kwargs ", kwargs)
        _obj, args, kwargs = super(MetaRemoteData, cls).donew(*args, **kwargs)
        print("MetaRemoteData donew kwargs after", kwargs)
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        print("MetaRemoteData dopostinit kwargs ", kwargs)
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs) 
        print("MetaRemoteData dopostinit kwargs ", kwargs)
        _obj.mdapi = _obj.p.mdapi
        _obj.chan = queue.Queue()
        return _obj, args, kwargs


class RemoteData(with_metaclass(MetaRemoteData, DataBase)):
    
    params = (
        ("mdapi", None),
        ("rtbar", False,), # use RealTime 5 seconds bars
    )

    instrument = Instrument()

    def _prepare(self, _loop): 
        self.mdapi.start(_loop)

    def _start(self, *args, **kwargs):
        super()._start(*args,**kwargs)
        self._row_iter = None
        self.sid = kwargs["sid"]

        body = QueryBody(start_date=kwargs["fromdate"], end_date=kwargs["todate"], sid=self.sid)
        self.get_adjfactor(body)

        body = QueryBody(start_date=kwargs["fromdate"], end_date=kwargs["todate"], sid=kwargs["benchmark"])
        self.get_dret(body)

        observable = self.mdapi.subscribe(body, FactorTopic.Raw)
        observable.subscribe( # nonblocking 
            on_next=self.chan.put,
            on_error=lambda e: self.chan.put(e),
            on_completed=lambda: self.chan.put(StopIteration) 
        )

    def _load(self):
        while True:
            if self._row_iter is not None:
                try:
                    row = next(self._row_iter)
                    if self.p.rtbar:
                        ret = self._load_rtbar(row)
                    else:
                        ret = self._load_bar(row)
                    return ret
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

    def get_snapshot(self, psids: List[bytes], tick: int) -> Mapping[str, Any]:
        body = QueryBody(start_date=tick, end_date=tick, sid=psids)
        df = self.mdapi.get_subscribe(body, FactorTopic.Raw)
        snapshot = {}
        if df:
            snapshot = valmap(lambda x : x["close"][0], df)
        return snapshot

    def get_adjfactor(self, body: QueryBody):
        adj_data = self.mdapi.get_factor(body, FactorTopic.Qfq)
        adj = adj_data[body.sid[0]]
        factors = adj.raw_factors if adj else {} # adj_factors
        if factors:
            factors = dict(sorted(factors.items())) # sort by key
            self.adj_factors = factors

    def get_dret(self, body: QueryBody):
        raw_data = self.mdapi.get_close(body, FactorTopic.Qfq)
        close = raw_data[body.sid[0]]

        self.benchmark_dret = close.with_columns(
            pl.col("close").pct_change().fill_null(0).alias("ret")
        ).select(["day", "ret"])

    def stop(self):
        super().stop()
        self.mdapi.disconnect()
