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

import queue

import backtest as bt
from backtest.feed import DataBase
from backtest import TimeFrame, date2num, num2date
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

      - ``sectype`` (default: ``STK``)

        Default value to apply as *security type* if not provided in the
        ``dataname`` specification

      - ``historical`` (default: ``False``)

        If set to ``True`` the data feed will stop after doing the first
        download of data.

        The standard data feed parameters ``fromdate`` and ``todate`` will be
        used as reference.

        The data feed will make multiple requests if the requested duration is
        larger than the one allowed by IB given the timeframe/compression
        chosen for the data.

      - ``what`` (default: ``None``)

        If ``None`` the default for different assets types will be used for
        historical data requests:

          - 'BID' for CASH assets
          - 'TRADES' for any other

        Use 'ASK' for the Ask quote of cash assets
        
        Check the IB API docs if another value is wished

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

      - ``backfill_start`` (default: ``True``)

        Perform backfilling at the start. The maximum possible historical data
        will be fetched in a single request.

      - ``backfill`` (default: ``True``)

        Perform backfilling after a disconnection/reconnection cycle. The gap
        duration will be used to download the smallest possible amount of data

      - ``backfill_from`` (default: ``None``)

        An additional data source can be passed to do an initial layer of
        backfilling. Once the data source is depleted and if requested,
        backfilling from IB will take place. This is ideally meant to backfill
        from already stored sources like a file on disk, but not limited to.

      - ``latethrough`` (default: ``False``)

        If the data source is resampled/replayed, some ticks may come in too
        late for the already delivered resampled/replayed bar. If this is
        ``True`` those ticks will bet let through in any case.

        Check the Resampler documentation to see who to take those ticks into
        account.

        This can happen especially if ``timeoffset`` is set to ``False``  in
        the ``IBStore`` instance and the TWS server time is not in sync with
        that of the local computer

      - ``tradename`` (default: ``None``)
        Useful for some specific cases like ``CFD`` in which prices are offered
        by one asset and trading happens in a different onel

        - SPY-STK-SMART-USD -> SP500 ETF (will be specified as ``dataname``)

        - SPY-CFD-SMART-USD -> which is the corresponding CFD which offers not
          price tracking but in this case will be the trading asset (specified
          as ``tradename``)

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
        ('sectype', 'STK'),  # usual industry value
        ('exchange', 'SMART'),  # usual industry value
        ('rtbar', False),  # use RealTime 5 seconds bars
        ('historical', True),  # only historical download
        ('what', None),  # historical - what to show
        ('useRTH', False),  # historical - download only Regular Trading Hours
        ('qcheck', 0.5),  # timeout in seconds (float) to check for events
        ('backfill_start', True),  # do backfilling at the start
        ('backfill', True),  # do backfilling when reconnecting
        ('backfill_from', None),  # additional data source to do backfill from
        ('latethrough', False),  # let late samples through
        ('tradename', None),  # use a different asset as order target
    )

    _store = ibstore.IBStore

    # Minimum size supported by real-time bars
    RTBAR_MINSIZE = (TimeFrame.Seconds, 5)

    # States for the Finite State Machine in _load
    _ST_FROM, _ST_START, _ST_LIVE, _ST_HISTORBACK, _ST_OVER = range(5)

    def _timeoffset(self):
        return self.ib.timeoffset()

    def _gettz(self):
        # If no object has been provided by the user and a timezone can be
        # found via contractdtails, then try to get it from pytz, which may or
        # may not be available.

        # The timezone specifications returned by TWS seem to be abbreviations
        # understood by pytz, but the full list which TWS may return is not
        # documented and one of the abbreviations may fail
        tzstr = isinstance(self.p.tz, str)
        if self.p.tz is not None and not tzstr:
            return bt.utils.date.Localizer(self.p.tz)

        if self.contractdetails is None:
            return None  # nothing can be done

        try:
            import pytz  # keep the import very local
        except ImportError:
            return None  # nothing can be done

        tzs = self.p.tz if tzstr else self.contractdetails.m_timeZoneId

        if tzs == 'CST':  # reported by TWS, not compatible with pytz. patch it
            tzs = 'CST6CDT'

        try:
            tz = pytz.timezone(tzs)
        except pytz.UnknownTimeZoneError:
            return None  # nothing can be done

        # contractdetails there, import ok, timezone found, return it
        return tz

    def islive(self):
        '''Returns ``True`` to notify ``Cerebro`` that preloading and runonce
        should be deactivated'''
        return not self.p.historical

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
        # Kickstart store and get queue to wait on
        self.qlive = self.ib.start(data=self)
        self.qhist = None

        self._usertvol = not self.p.rtbar

        tfcomp = (self._timeframe, self._compression)
        if tfcomp < self.RTBAR_MINSIZE:
            # Requested timeframe/compression not supported by rtbars
            self._usertvol = True

        self.contract = None
        self.contractdetails = None

        self._statelivereconn = False  # if reconnecting in live state
        self._subcription_valid = False  # subscription state
        self._storedmsg = dict()  # keep pending live message (under None)

        if not self.ib.connected():
            return

        self.put_notification(self.CONNECTED)

        if self._state == self._ST_START:
            self._start_finish()  # to finish initialization
            self._st_start()

    def stop(self):
        '''Stops and tells the store to stop'''
        super(MdData, self).stop()
        self.ib.stop()

    def reqdata(self):
        '''request real-time data. checks cash vs non-cash) and param useRT'''
        if self.contract is None or self._subcription_valid:
            return

        if self._usertvol:
            self.qlive = self.md.reqMktData(self.contract, self.p.what)
        else:
            self.qlive = self.md.reqRealTimeBars(self.contract)

        self._subcription_valid = True
        return self.qlive

    def canceldata(self):
        '''Cancels Market Data subscription, checking asset type and rtbar'''
        if self.contract is None:
            return

        if self._usertvol:
            self.md.cancelMktData(self.qlive)
        else:
            self.md.cancelRealTimeBars(self.qlive)

    def haslivedata(self):
        return bool(self._storedmsg or self.qlive)

    def _load(self):
        """
           msg error code -354 self.NOTSUBSCRIBED
        """
        if self.contract is None or self._state == self._ST_OVER:
            return False  # nothing can be done

        while True:
            if self._state == self._ST_LIVE:
                try:
                    msg = (self._storedmsg.pop(None, None) or
                           self.qlive.get(timeout=self._qcheck))
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

                    self._statelivereconn = self.p.backfill
                    continue
                if msg == -354:
                    # self._subcription_valid = False
                    # self._statelivereconn = self.p.backfill
                    self.put_notification(self.NOTSUBSCRIBED)
                    return False
                # reqHistoricalDataEx
                #  load_rtbar or load_rtvolume
                self._load_rtbar(msg)

    def _load_rtbar(self, rtbar, hist=False):
        # A complete 5 second bar made of real-time ticks is delivered and
        # contains open/high/low/close/volume prices
        # The historical data has the same data but with 'date' instead of
        # 'time' for datetime
        dt = date2num(rtbar.time if not hist else rtbar.date)
        if dt < self.lines.datetime[-1] and not self.p.latethrough:
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt
        # Put the tick into the bar
        self.lines.open[0] = rtbar.open
        self.lines.high[0] = rtbar.high
        self.lines.low[0] = rtbar.low
        self.lines.close[0] = rtbar.close
        self.lines.volume[0] = rtbar.volume
        self.lines.openinterest[0] = 0

        return True

    def _load_rtvolume(self, rtvol):
        # A single tick is delivered and is therefore used for the entire set
        # of prices. Ideally the
        # contains open/high/low/close/volume prices
        # Datetime transformation
        dt = date2num(rtvol.datetime)
        if dt < self.lines.datetime[-1] and not self.p.latethrough:
            return False  # cannot deliver earlier than already delivered

        self.lines.datetime[0] = dt

        # Put the tick into the bar
        tick = rtvol.price
        self.lines.open[0] = tick
        self.lines.high[0] = tick
        self.lines.low[0] = tick
        self.lines.close[0] = tick
        self.lines.volume[0] = rtvol.size
        self.lines.openinterest[0] = 0
        return True
