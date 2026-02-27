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
import ray
import threading
import pyarrow as pa
import pyarrow.compute as pc
import reactivex.operators as ops

from typing import List

from backtest.feed import DataBase
from backtest.dataseries import TimeFrame
from backtest.metabase import with_metaclass
from backtest.stores.raystore import RayBtStore
from backtest.utils.dateintern import num2date
from bt_sdk.core.protocol import QueryBody

__all__ = ["RayBtData"]


class MetaRayBtData(DataBase.__class__):
    
    def __init__(cls, name, bases, dct):
        super(MetaRayBtData, cls).__init__(name, bases, dct)
        RayBtStore.RayDataCls = cls # auto Register with the store when type class __import__

    def donew(cls, *args, **kwargs):
        print("MetaRayBtData donew kwargs ", kwargs)
        _obj, args, kwargs = super(MetaRayBtData, cls).donew(*args, **kwargs)
        print("MetaRayBtData donew kwargs after", kwargs)
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        print("MetaRayBtData dopostinit kwargs ", kwargs)
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs) 
        print("MetaRayBtData dopostinit kwargs ", kwargs)
        _obj.agent = _obj.p.agent
        _obj.chan = queue.Queue()
        return _obj, args, kwargs


class RayBtData(with_metaclass(MetaRayBtData, DataBase)):
    
    params = (
        ("mdapi", None),
        ("agent", None),
        ("rtbar", False,), # use RealTime 5 seconds bars
        ("timeout", 10)
    )

    def _start(self, *args, **kwargs):
        super()._start(*args,**kwargs)
        self._row_iter = None 

        self.sids = kwargs["sid"]
        index = kwargs.get("benchmark", b"000001")
        start_date = kwargs["fromdate"]
        end_date = kwargs["todate"]
        
        str_sid = [sid.decode("utf-8") for sid in self.sids]
        self.extra_info = f"FeedInfo: {start_date}:{end_date}@{','.join(str_sid)}" 

        body = QueryBody(start_date=start_date, end_date=end_date, sid=self.sids)
        bench_body = QueryBody(start_date=start_date, end_date=end_date, sid=[index])
        self.preload(body, bench_body) 
            
        self._streaming_thread = threading.Thread(
        target=self._fetch_remote,
        daemon=True,
        args=(body,))
        self._streaming_thread.start()

    def preload(self, body: QueryBody, benh_body: QueryBody):
        fut_factor = self.agent.get_adjfactor.remote(body)
        fut_bench = self.agent.get_benchmark.remote(benh_body)

        self.bench = ray.get(fut_bench, timeout=20)
        self.adj_factors = ray.get(fut_factor, timeout=20)
        print(f"[_start] Benchmark and {self.sids} Factors received.", len(self.adj_factors), len(self.bench))

    def _fetch_remote(self, body: QueryBody):
        """
            daemon thread ---> Ray Actor ---> Pull and put to Queue
        """
        try:
            # ObjectRefGenerator
            remote_gen = self.agent.get_stream.remote(body) # Actor generator
            
            for data_ref in remote_gen:
                # inner_ref = ray.get(data_ref) # deref twice 
                # batch_table = ray.get(inner_ref)
                batch_table = ray.get(data_ref)  
                self.chan.put(batch_table)

            self.chan.put(StopIteration)
        except Exception as e:
            self.chan.put(e)

    def _load(self):
        while True:
            if self._row_iter is not None:
                try:
                    row = next(self._row_iter)
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

    def get_instrument(self):
        assets = ray.get(self.agent.get_instrument.remote())
        return assets

    def get_calendar(self):
        _calendar = ray.get(self.agent.get_calendar.remote())
        return _calendar
