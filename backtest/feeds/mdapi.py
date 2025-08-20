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
import threading
from datetime import datetime

from bt_sdk.core.model import ReqMeta
from backtest.feed import DataBase
from backtest.dataseries import TimeFrame
from backtest.metabase import with_metaclass
from backtest.stores.btstore import BTStore


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
        return _obj, args, kwargs


class MdData(with_metaclass(MetaMdData, DataBase)):
    
    params = (
        ("mdapi", None),
        ('rtbar', False) # use RealTime 5 seconds bars
    )

    RTBAR_MINSIZE = (TimeFrame.Seconds, 3) # Minimum size supported by real-time bars
    
    descr = Descr()

    def _start(self, **kwargs):
        super()._start()

        start_date = kwargs.get("start_date", 19900101)
        end_date = kwargs.get("end_date", datetime.now())

        fromdate = datetime.strptime(str(start_date), "%Y%m%d")

        if not isinstance(end_date, datetime):
            todate = datetime.strptime(str(end_date), "%Y%m%d") + datetime.time(23, 59, 59, 999990)
        else:
            todate = end_date 

        reqmeta = ReqMeta(sid=kwargs["sid"], start_date=int(fromdate.timestamp()), end_date=int(todate.timestamp()))
        self.buffer = self.mdapi.subscribe(reqmeta)
        # import pdb; pdb.set_trace()

    def _load_bar(self, msg):
        line = msg["msg"]["line"][0]
        dt = line[0]
        if dt < self.lines.datetime[-1] :
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt
        self.lines.open[0] = line[1]
        self.lines.high[0] = line[2]
        self.lines.low[0] = line[3]
        self.lines.close[0] = line[4]
        self.lines.volume[0] = line[5]
        self.lines.amount[0] = line[6]
        # self.lines.openinterest[0] = 0
        return True

    def _load_rtbar(self, rtbar): # tick 3s
        dt = rtbar[0]
        if dt < self.lines.datetime[-1]:
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt
        # Put the tick into the bar
        tick = rtbar[1]
        self.lines.open[0] = tick
        self.lines.high[0] = tick
        self.lines.low[0] = tick
        self.lines.close[0] = tick
        self.lines.volume[0] = rtbar[2]
        self.lines.amount[0] = rtbar[3]
        return True

    def _load(self):
        if self.buffer is None:
            warnings.warn("buffer is None, must subscribe first")
            return
        msg = self.buffer.get()
        # import pdb; pdb.set_trace()
        if msg == "eof":
            return False  # Conn broken during historical/backfilling
        if self.p.rtbar:
            self._load_rtbar(msg)
        else:
            self._load_bar(msg)
        return True

    def stop(self):
        super().stop()
        self.mdapi.disconnected()
