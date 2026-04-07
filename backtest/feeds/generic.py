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
import ray
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
from backtest.stores.generic import GenericStore
from backtest.utils.dateintern import num2date
from bt_sdk.core.protocol import QueryBody


class MetaParquetBase(DataBase.__class__):
    
    def __init__(cls, name, bases, dct):
        """auto Register with the store when type class __import__"""
        super(MetaParquetBase, cls).__init__(name, bases, dct)
        GenericStore.DataCls = cls

    def donew(cls, *args, **kwargs):
        # print("MetaParquetBase donew kwargs ", kwargs)
        _obj, args, kwargs = super(MetaParquetBase, cls).donew(*args, **kwargs)
        # print("MetaParquetBase donew kwargs after", kwargs)
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        # print("MetaParquetBase dopostinit kwargs ", kwargs)
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs) 
        # print("MetaParquetBase dopostinit kwargs ", kwargs)
        return _obj, args, kwargs


class ParquetData(with_metaclass(MetaParquetBase, DataBase)):
    
    params = (
        ("pattern", None),
        ("batch_size", 10000),
        ("rtbar", False,) # use RealTime 5 seconds bars
    )

    def _start(self, *args, **kwargs):
        super()._start(*args,**kwargs)

        lazy_df = pl.scan_parquet(pattern)
        lazy_df = (
            lazy_df
        )
        self._row_iter = self._make_iter()

    def _load(self):
        while True:
            try:
                row = next(self._row_iter)
                if self.p.rtbar:
                    self._load_rtbar(row)
                else:
                    self._load_bar(row)
                return True
            except StopIteration:
                return False
    
    def _make_iter(self, lazy_df):
         # self._row_iter = lazy_df.collect(streaming=True)
        for batch in lazy_df.collect_iter(batch_size=self.p.batch_size):
            for row in batch.iter_rows(named=True):
                yield row

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

    def stop(self):
        super().stop()
