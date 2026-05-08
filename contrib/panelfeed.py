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
from backtest.stores.localstore import LocalStore
from backtest.utils.dateintern import num2date
from bt_sdk.core.protocol import QueryBody


class MetaPanelBase(DataBase.__class__):

    lines = (("fsm"),)
    
    def __init__(cls, name, bases, dct):
        """auto Register with the store when type class __import__"""
        super(MetaParquetBase, cls).__init__(name, bases, dct)
        LocalStore.DataCls = cls

    def donew(cls, *args, **kwargs):
        _obj, args, kwargs = super(MetaParquetBase, cls).donew(*args, **kwargs)
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs) 
        return _obj, args, kwargs


class PanelData(with_metaclass(MetaParquetBase, DataBase)):
    
    params = (
        ("parquet_path", None),
        ("batch_size", 10000),
    )

    def _start(self, *args, **kwargs):
        super()._start(*args,**kwargs)

        df = pl.scan_parquet(parquet_path).sort("day").collect()

        self._idx = 0
        self.current_panel = None

        self._dates = df["day"].unique().sort().to_numpy()
        self._panel_dict = {
            date_val: group_df for date_val, group_df in df.group_by("day")
        }
        
    def _load(self):
        if self._idx >= len(self._dates):
            return False  

        current_day = self._dates[self._idx] # 14:55:00
        
        year = current_date_int // 10000
        month = (current_date_int % 10000) // 100
        day = current_date_int % 100
        dt = datetime.datetime(year, month, day, 
                               self.p.trigger_time.hour, 
                               self.p.trigger_time.minute)
        
        self.lines.datetime[0] = bt.date2num(dt)
        self._idx += 1

        self.current_panel = self._panel_dict[current_day]
        return True

    def getvalue(self): 
        return self.current_panel

    def stop(self):
        super().stop()
