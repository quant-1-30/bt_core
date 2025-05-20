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
import pytz

from backtest.feed import DataBase
from backtest.dataseries import TimeFrame
from backtest.utils.dateintern import Localizer
from backtest.metabase import with_metaclass
from backtest.stores.btstore import BTStore
from bt_sdk.core.client import MdApi


# class RTVolume(object):
#     '''Parses a tickString tickType 48 (RTVolume) event from the IB API into its
#     constituent fields

#     Supports using a "price" to simulate an RTVolume from a tickPrice event
#     '''
#     _fields = [
#         ('price', float),
#         ('size', int),
#         ('datetime', _ts2dt),
#         ('volume', int),
#         ('vwap', float),
#         ('single', bool)
#     ]

#     def __init__(self, rtvol='', price=None, tmoffset=None):
#         # Use a provided string or simulate a list of empty tokens
#         tokens = iter(rtvol.split(';'))

#         # Put the tokens as attributes using the corresponding func
#         for name, func in self._fields:
#             setattr(self, name, func(next(tokens)) if rtvol else func())

#         # If price was provided use it
#         if price is not None:
#             self.price = price

#         if tmoffset is not None:
#             self.datetime += tmoffset


class MetaMdData(DataBase.__class__):

    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaMdData, cls).__init__(name, bases, dct)

        # auto Register with the store when type class __import__ 
        BTStore.DataCls = cls


class MdData(with_metaclass(MetaMdData, DataBase)):
    '''Interactive Brokers Data Feed.

    Supports the following contract specifications in parameter ``dataname``:

          - TICKER-STK-EXCHANGE  # Stock

    Params:

      - ``sectype`` (default: ``instrument``)

        Default value to apply as *security type* if not provided in the
        ``dataname`` specification

      - ``rtbar`` (default: ``False``)

        If ``True`` the ``5 Seconds Realtime bars`` provided by Interactive
        Brokers will be used as the smalles tick. According to the
        documentation they correspond to real-time values (once collated and
        curated by IB)

        If ``False`` then the ``RTVolume`` prices will be used, which are based
        on receiving ticks. In the case of ``CASH`` assets (like for example
        EUR.JPY) ``RTVolume`` will always be used and from it the ``bid`` price
        (industry de-facto standard with IB according to the literature
        scattered over the Internet)

        Even if set to ``True``, if the data is resampled/kept to a
        timeframe/compression below Seconds/5, no real time bars will be used,
        because IB doesn't serve them below that level

      - ``backfill`` (default: ``True``)

        Perform backfilling after a disconnection/reconnection cycle. The gap
        duration will be used to download the smallest possible amount of data

    The default values in the params are the to allow things like ```TICKER``,
    to which the parameter ``sectype`` (default: ``STK``) and ``exchange``
    (default: ``SMART``) are applied.

    Some assets like ``AAPL`` need full specification including ``currency``
    (default: '') whereas others like ``TWTR`` can be simply passed as it is.

      - ``AAPL-STK-SMART-USD`` would be the full specification for dataname

        Or else: ``IBData`` as ``IBData(dataname='AAPL', currency='USD')``
        which uses the default values (``STK`` and ``SMART``) and overrides
        the currency to be ``USD``
    '''
    params = (
        ('sectype', 'instrument'),  # usual industry value
        ("tz", "Asia/Shanghai"),
        ('rtbar', False),  # use RealTime 5 seconds bars
        ('backfill', True), \
    )

    # _store = ibstore.IBStore
    
    # Minimum size supported by real-time bars
    RTBAR_MINSIZE = (TimeFrame.Seconds, 3)

    # _ST_FROM, _ST_START, _ST_LIVE, _ST_HISTORBACK, _ST_OVER = range(5)

    # def __init__(self, **kwargs):
    #     addr = kwargs.get('addr', ("127.0.0.1", 8888))
    #     self.mdapi = MdApi(addr)

    def __init__(self, mdapi, **kwargs):
        super(MdData, self).__init__(**kwargs)
        self.mdapi = mdapi

    def _gettz(self):
        # If no object has been provided by the user and a timezone can be
        # found via contractdtails, then try to get it from pytz, which may or
        # may not be available.
        tz = pytz.timezone(self.p.tz)
        return Localizer(tz)

    def islive(self):
        '''Returns ``True`` to notify ``Cerebro`` that preloading and runonce
        should be deactivated'''
        return self.p.rtbar

    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(MdData, self).setenvironment(env)
        # env.addstore(self.ib)

    def start(self):
        '''Starts the mdapi connecction and gets the real contract and
        contractdetails if it exists'''

        if not self.mdapi.connected():
            return

        self._subcription_valid = False  # subscription state
        # self.put_notification(self.CONNECTED)
 
    def stop(self):
        '''Stops and tells the store to stop'''
        # super(MdData, self).stop()
        self.mdapi.disconnected()

    def get_calendar(self):
        return self.mdapi.get_calendar()
    
    def get_instrument(self, req):
        return self.mdapi.get_instrument(req)
    
    def reqdata(self, req):
        # dtkwargs['start'] = int((dtbegin - self._DTEPOCH).total_seconds())
        '''request real-time data. checks cash vs non-cash) and param useRT'''
        self._subcription_valid = True
        self.qlive = self.mdapi.reqMktData(req)
    
    def reqEvents(self, req):
        return self.mdapi.reqEvents(req)
    
    def canceldata(self):
        '''Cancels Market Data subscription, checking asset type and rtbar'''
        if self.qlive is None:
            return

        self.mdapi.canceledData(self.qlive)

    def _load(self):
        """
           msg error code -354 self.NOTSUBSCRIBED
        """
        _load_bar = self._load_rtbar if self.p.rtbar else self._load_bar

        while True:
            msg = self.qlive.get()
            print("msg: ", msg)
            if msg == "eof":
                break  # Conn broken during historical/backfilling

            # if msg == "****" :  # Conn broken during historical/backfilling
            #     self._subcription_valid = False
            #     self.put_notification(self.CONNBROKEN)
            #     # Try to reconnect
            #     if not self.ib.reconnect(resub=True):
            #         self.put_notification(self.DISCONNECTED)
            #         return False  # failed

            #     continue
            # if msg == -354:
            #     self._subcription_valid = False
            #     self.put_notification(self.NOTSUBSCRIBED)
            #     return False
            #  load_rtbar or load_bar
            _load_bar(msg)


    def _load_bar(self, bar, hist=False):
        # A complete 30 second bar made of real-time 3d ticks is delivered and
        # contains open/high/low/close/volume prices
        # The historical data has the same data but with 'date' instead of
        # 'time' for datetime
        # dt = date2num(bar.time if not hist else bar.date)
        dt = bar[0]
        if dt < self.lines.datetime[-1] :
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt
        # Put the tick into the bar
        self.lines.open[0] = bar[1]
        self.lines.high[0] = bar[2]
        self.lines.low[0] = bar[3]
        self.lines.close[0] = bar[4]
        self.lines.volume[0] = bar[5]
        self.lines.amount[0] = bar[6]
        # self.lines.openinterest[0] = 0

        return True

    def _load_rtbar(self, rtbar):
        # A single tick is delivered and is therefore used for the entire set
        # of prices. Ideally the
        # contains open/high/low/close/volume prices
        # Datetime transformation
        # dt = date2num(rtbar[0])
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
