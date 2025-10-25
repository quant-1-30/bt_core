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
import threading
from datetime import datetime, timedelta

from bt_sdk.core.model import Query
from backtest.feed import DataBase
from backtest.dataseries import TimeFrame
from backtest.metabase import with_metaclass
from backtest.stores.btstore import BTStore
from backtest.utils.dateintern import num2date


__all__ = ["MdData"]


class Descr(object):
    '''Descriptor for calendar and instrument data'''
    def __init__(self):
        self.calendar = ()
        self.assets = ()

        self._evt_cal = threading.Event()
        self._evt_asset = threading.Event()

    def data_thd(self, api):
        t = threading.Thread(target=self._t_cal, args=(api,), daemon=True)
        t_ = threading.Thread(target=self._t_asset, args=(api,), daemon=True)
        t.start()
        self._evt_cal.wait() # api async run in same thread and event loop

        t_.start()
        self._evt_asset.wait()

    def _t_cal(self, api):
        msg = api.get_calendar()
        print("calendar msg: ", msg)
        self.calendar = msg
        self._evt_cal.set()

    def _t_asset(self, api):
        msg = api.get_instrument()
        print("asset msg ", msg)
        self.assets = msg
        self._evt_asset.set()

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")
    
    def __get__(self, instance, owner):
        if len(self.calendar) ==0 or len(self.assets) ==0:
            self.data_thd(instance.mdapi)
        return self.calendar, self.assets


class MetaMdData(DataBase.__class__):
    
    def __init__(cls, name, bases, dct):
        """auto Register with the store when type class __import__"""
        super(MetaMdData, cls).__init__(name, bases, dct)
        BTStore.DataCls = cls

    def doinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = super().doinit(_obj, *args, **kwargs) # __init__
        _obj.mdapi = _obj.p.mdapi
        _obj.buffer = None # 
        _obj.adj_factors = None # 
        _obj.appendix = "" # any extra info to relate with request
        return _obj, args, kwargs


class MdData(with_metaclass(MetaMdData, DataBase)):
    
    params = (
        ("mdapi", None),
        ('rtbar', False,), # use RealTime 5 seconds bars
    )

    RTBAR_MINSIZE = (TimeFrame.Seconds, 3) # Minimum size supported by real-time bars
    
    descr = Descr()

    def __init__(self, **kwargs):
        self.ctx = None
        self.channel = None

    def _start(self, **kwargs):
        super()._start()

        # optimize ReqMeta
        sdate = kwargs.get("start_date", 19900101)
        edate = kwargs.get("end_date", datetime.now().strftime("%Y%m%d"))
        # _from = datetime.strptime(str(sdate), "%Y%m%d") + timedelta(hours=9, minutes=30)
        # _to = datetime.strptime(str(edate), "%Y%m%d") + timedelta(hours=15, minutes=0)
        # reqmeta = ReqMeta(sid=kwargs["sid"], start_date=int(_from.timestamp()), end_date=int(_to.timestamp()))
        qty = Query(sid=kwargs["sid"], start_date=sdate, end_date=edate)
        
        self.calc_adjfactor(qty)
        # wrap by contextmanager 整合迭代器与session 手动获取上下文
        self.ctx = self.mdapi.subscribe(qty)
        self.channel = self.ctx.__enter__()
        if self.channel is None:
            warnings.warn("buffer is None, must subscribe first")
            return

    def _load_bar(self, msg):
        data = msg["body"]["line"][0]
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= data[0]:
            import pdb; pdb.set_trace()
            return False  # cannot deliver earlier than already delivered
        print(f"linebuffer current tick {dt} and msg tick {data[0]}")

        self.lines.datetime[0] = data[0]
        self.lines.open[0] = data[1]
        self.lines.high[0] = data[2]
        self.lines.low[0] = data[3]
        self.lines.close[0] = data[4]
        self.lines.volume[0] = data[5]
        self.lines.amount[0] = data[6]
        # import pdb; pdb.set_trace()
        return True

    def _load_rtbar(self, rtbar): # tick 3s
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= rtbar[0]:
            import pdb; pdb.set_trace()
            return False  # cannot deliver earlier than already delivered
        # Put the tick into the bar
        self.lines.datetime[0] = rtbar[0]
        self.lines.open[0] = rtbar[1]
        self.lines.high[0] = rtbar[1]
        self.lines.low[0] = rtbar[1]
        self.lines.close[0] = rtbar[1]
        self.lines.volume[0] = rtbar[2]
        self.lines.amount[0] = rtbar[3]
        return True

    def _load(self):
        msg = self.channel.get()
        print("_load msg :", msg)
        if msg == "eof":
            self.ctx.__exit__(None, None, None) #
            return False  # Conn broken during historical/backfilling
        if self.p.rtbar:
            self._load_rtbar(msg)
        else:
            self._load_bar(msg)
        return True
    
    def calc_adjfactor(self, reqmeta):
        adj = self.mdapi.factor(reqmeta)
        factors = adj.adj_factors
        if factors:
            factors = dict(sorted(factors.items())) # sort by key
            self.adj_factors = factors
    
    def stop(self):
        super().stop()
        self.mdapi.disconnected()
