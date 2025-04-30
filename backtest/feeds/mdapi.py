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
import queue

import backtest as bt
from backtest.feed import DataBase
from backtest import TimeFrame, date2num
from backtest.metabase import with_metaclass
from backtest.stores import ibstore
from bt_sdk.core.client import MdApi


class MetaMdData(DataBase.__class__):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaMdData, cls).__init__(name, bases, dct)

        # Register with the store
        ibstore.BtStore.DataCls = cls


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

      - ``qcheck`` (default: ``0.5``)

        Time in seconds to wake up if no data is received to give a chance to
        resample/replay packets properly and pass notifications up the chain

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
        ("tz", "Shanghai/Asia"),
        ('rtbar', False),  # use RealTime 5 seconds bars
        ('qcheck', 0.5),  # timeout in seconds (float) to check for events
        ('backfill', True),  # do backfilling when reconnecting
    )

    _store = ibstore.IBStore

    # Minimum size supported by real-time bars
    RTBAR_MINSIZE = (TimeFrame.Seconds, 3)

    # States for the Finite State Machine in _load
    # _ST_FROM, _ST_START, _ST_LIVE, _ST_HISTORBACK, _ST_OVER = range(5)

    def _timeoffset(self):
        return self.ib.timeoffset()

    def _gettz(self):
        # If no object has been provided by the user and a timezone can be
        # found via contractdtails, then try to get it from pytz, which may or
        # may not be available.
        tz = pytz.timezone(self.p.tz)
        return bt.utils.date.Localizer(tz)

    def islive(self):
        '''Returns ``True`` to notify ``Cerebro`` that preloading and runonce
        should be deactivated'''
        return self.p.rtbar

    def __init__(self, **kwargs):
        self.md = MdApi(**kwargs)

    def setenvironment(self, env):
        '''Receives an environment (cerebro) and passes it over to the store it
        belongs to'''
        super(MdData, self).setenvironment(env)
        env.addstore(self.ib)

    def start(self):
        '''Starts the IB connecction and gets the real contract and
        contractdetails if it exists'''
        super(MdData, self).start()
        # Kickstart store
        self.ib.start(data=self)

        self._rt = not self.p.rtbar
        self._subcription_valid = False  # subscription state

        if not self.ib.connected():
            return

        self.put_notification(self.CONNECTED)

    def stop(self):
        '''Stops and tells the store to stop'''
        super(MdData, self).stop()
        self.ib.stop()

    def reqdata(self, req):
        '''request real-time data. checks cash vs non-cash) and param useRT'''
        if self.contract is None or self._subcription_valid:
            return

        if self._rt:
            self.qlive = self.md.reqRealTimeBars(req)
        else:
            self.qlive = self.md.reqMktData(req)

        self._subcription_valid = True
        return self.qlive

    def canceldata(self):
        '''Cancels Market Data subscription, checking asset type and rtbar'''
        if self.contract is None:
            return

        if self._rt:
            self.md.cancelRealTimeBars(self.qlive)
        else:
            self.md.cancelMktData(self.qlive)

    def _load(self):
        """
           msg error code -354 self.NOTSUBSCRIBED
        """
        _load_bar = self._load_rtbar if self._rt else self._load_bar

        while True:
            try:
                msg = self.qlive.get(timeout=self._qcheck)
            except queue.Empty:
                if True:
                    return None

            if msg is None:  # Conn broken during historical/backfilling
                self._subcription_valid = False
                self.put_notification(self.CONNBROKEN)
                # Try to reconnect
                if not self.ib.reconnect(resub=True):
                    self.put_notification(self.DISCONNECTED)
                    return False  # failed

                continue
            if msg == -354:
                self._subcription_valid = False
                self.put_notification(self.NOTSUBSCRIBED)
                return False
            #  load_rtbar or load_bar
            _load_bar(msg)

    def _load_bar(self, bar, hist=False):
        # A complete 30 second bar made of real-time 3d ticks is delivered and
        # contains open/high/low/close/volume prices
        # The historical data has the same data but with 'date' instead of
        # 'time' for datetime
        # dt = date2num(bar.time if not hist else bar.date)
        dt = bar.tick
        if dt < self.lines.tick[-1] :
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt
        # Put the tick into the bar
        self.lines.open[0] = bar.open
        self.lines.high[0] = bar.high
        self.lines.low[0] = bar.low
        self.lines.close[0] = bar.close
        self.lines.volume[0] = bar.volume
        self.lines.openinterest[0] = 0

        return True

    def _load_rtbar(self, rtbar):
        # A single tick is delivered and is therefore used for the entire set
        # of prices. Ideally the
        # contains open/high/low/close/volume prices
        # Datetime transformation
        dt = date2num(rtbar.datetime)
        if dt < self.lines.datetime[-1]:
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt

        # Put the tick into the bar
        tick = rtbar.price
        self.lines.open[0] = tick
        self.lines.high[0] = tick
        self.lines.low[0] = tick
        self.lines.close[0] = tick
        self.lines.volume[0] = rtbar.size
        self.lines.openinterest[0] = 0
        return True
