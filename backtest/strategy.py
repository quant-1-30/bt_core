#!/usr/bin389/env python
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
import numpy as np
import warnings
import collections
import itertools
import operator
from collections import defaultdict

import backtest as bt
from .lineiterator import LineIterator, StrategyBase
from .lineroot import LineSingle
from .lineseries import LineSeriesStub
from .metabase import with_metaclass, ItemCollection, findowner
from backtest.utils.dateintern import num2date

MAXINT = np.iinfo(np.int_).max


class MetaStrategy(StrategyBase.__class__):
    _indcol = dict()

    def __new__(meta, name, bases, dct):
        return super(MetaStrategy, meta).__new__(meta, name, bases, dct)

    def __init__(cls, name, bases, dct):
        '''
        Class has already been created ... register subclasses
        '''
        # Initialize the class
        super(MetaStrategy, cls).__init__(name, bases, dct)

        if not cls.aliased and \
           name != 'Strategy' and not name.startswith('_'):
            cls._indcol[name] = cls

    def donew(cls, *args, **kwargs):
        _obj, args, kwargs = super(MetaStrategy, cls).donew(*args, **kwargs)

        # Find the owner and store it
        _obj.env = _obj.cerebro = cerebro = findowner(_obj, bt.cerebro.Cerebro)
        _obj._id = cerebro._next_stid()

        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopreinit(_obj, *args, **kwargs)

        _obj.sizer = _obj.env.sizer # add sizing to strategy
        _obj.store = store = _obj.env.store # add store to strategy
        _obj._dt_over = store._dt_over # get dt_over function from store
        
        _obj._minperiods = list()

        _obj._orders = defaultdict(list)
        _obj._trades = defaultdict(list) # AutoDictList

        _obj.stats = _obj.observers = ItemCollection()
        _obj.writers = list()

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopostinit(_obj, *args, **kwargs)
        
        _obj._periodset()
        _obj._next_experiment()
        return _obj, args, kwargs


class Strategy(with_metaclass(MetaStrategy, StrategyBase)):
    '''
    Base class to be subclassed for user defined strategies.
    '''

    _ltype = LineIterator.StratType

    lines = ('datetime',)

    def qbuffer(self, savemem=0):
        '''Enable the memory saving schemes. Possible values for ``savemem``:

          0: No savings. Each lines object keeps in memory all values

          1: All lines objects save memory, using the strictly minimum needed
        '''
        for line in self.lines: # datetime *** --- strategy lines
            line.qbuffer(savemem=savemem)

        # Tell datas to adjust buffer to minimum period
        for data in self.datas:
            data.qbuffer(savemem=savemem)
            data.minbuffer(self._minperiod) # make sure data minperiod is at least strategy's  

        # Save in all object types depending on the strategy
        for it in self._lineiterators[self.IndType]:
                it.qbuffer(savemem, self._minperiod)

    def _periodset(self):
        dataids = [id(data) for data in self.datas]

        _dminperiods = collections.defaultdict(list)
        for lineiter in self._lineiterators[LineIterator.IndType]:
            clk = getattr(lineiter, '_clock', None)
            if clk is None:
                clk = getattr(lineiter._owner, '_clock', None)
                if clk is None:
                    continue

            while True:
                if id(clk) in dataids:
                    break  # already top-level clock (data feed)

                clk2 = getattr(clk, '_clock', None)
                if clk2 is None:
                    clk2 = getattr(clk._owner, '_clock', None)

                if clk2 is None:
                    break 

                clk = clk2

            if clk is None:
                continue  

            if isinstance(clk, LineSeriesStub):
                clk = clk.lines[0]

            _dminperiods[clk].append(lineiter._minperiod)

        # calc data minperiods
        for data in self.datas:
            dlminperiods = _dminperiods[data]
            for l in data.lines:  # search each line for min periods
                if l in _dminperiods:
                    dlminperiods += _dminperiods[l]  # found, add it

            # keep the reference to the line if any was found
            _dminperiods[data] = [max(dlminperiods)] if dlminperiods else []

            dminperiod = max(_dminperiods[data] or [data._minperiod])
            self._minperiods.append(dminperiod)

    def _start(self):
        self._periodrecalc()

        for obs in self.observers:
            if not isinstance(obs, list):
                obs = [obs]  # support of multi-data observers

            for o in obs:
                o._start()

        self._minperstatus = MAXINT  # start in prenext
        self.start()

    def start(self):
        '''Called right before the backtesting is about to be started.'''
        pass

    def _settz(self, tz):
        self.lines.datetime._settz(tz)

    def getdtkey(self):
        '''Return the datetime key for the given datetime or the current one'''
        dt = num2date(self.lines.datetime[0])
        return num2date(dt)
    
    def _next_experiment(self):
        self.experment_id = self.store.register(self)

    def _getminperstatus(self):
        dlens = map(operator.sub, self._minperiods, map(len, self.datas))
        self._minperstatus = minperstatus = max(dlens)
        print("_getminperstatus ", self._minperstatus)
        return minperstatus

    def _addindicator(self, indcls, *indargs, **indkwargs):
        indcls(*indargs, **indkwargs) # postinit will take care of the rest

    # def _addanalyzer_slave(self, ancls, *anargs, **ankwargs):
    #     '''Like _addanalyzer but meant for observers (or other entities) which
    #     rely on the output of an analyzer for the data. These analyzers have
    #     not been added by the user and are kept separate from the main
    #     analyzers

    #     Returns the created analyzer
    #     '''
    #     analyzer = ancls(*anargs, **ankwargs)
    #     self._slave_analyzers.append(analyzer)
    #     return analyzer

    # def _getanalyzer_slave(self, idx):
    #     return self._slave_analyzers.append[idx]

    # def _addanalyzer(self, ancls, *anargs, **ankwargs):
    #     anname = ankwargs.pop('_name', '') or ancls.__name__.lower()
    #     nsuffix = next(self._alnames[anname])
    #     anname += str(nsuffix or '')  # 0 (first instance) gets no suffix
    #     analyzer = ancls(*anargs, **ankwargs)
    #     self.analyzers.append(analyzer, anname)

    def _addobserver(self, multi, obscls, *obsargs, **obskwargs):
        obsname = obskwargs.pop('obsname', '')
        if not obsname:
            obsname = obscls.__name__.lower()

        if not multi:
            newargs = list(itertools.chain(self.datas, obsargs))
            obs = obscls(*newargs, **obskwargs)
            self.stats.append(obs, obsname)
            return

        setattr(self.stats, obsname, list())
        l = getattr(self.stats, obsname)

        for data in self.datas:
            obs = obscls(data, *obsargs, **obskwargs)
            l.append(obs)
 
    def _next_observers(self, minperstatus):
        for observer in self.observers:
            for analyzer in observer._analyzers:
                if minperstatus < 0:
                    analyzer._next()
                elif minperstatus == 0:
                    analyzer._nextstart()  # only called for the 1st value
                else:
                    analyzer._prenext()
            observer._next()

    # def _next_analyzers(self, minperstatus):
    #     for analyzer in self.analyzers:
    #         if minperstatus < 0:
    #             analyzer._next()
    #         elif minperstatus == 0:
    #             analyzer._nextstart()  # only called for the 1st value
    #         else:
    #             analyzer._prenext()

    def _next(self):

        self.store.on_dt_over(self.experment_id) # restricted by T + 1 
        super(Strategy, self)._next() # lineiterator _next
        minperstatus = self._getminperstatus()
        self._next_observers(minperstatus)
        # self._next_analyzers(minperstatus)

        self.clear()

    def buy(self, sid="", price=0.0, plimit=0.0,
            exectype=None, ordertype=None, **kwargs):
        '''Create a buy (long) order and send it to the broker

          - ``exectype`` (default: ``None``)

            Possible values:

            - ``Order.Market`` or ``None``. A market order will be executed
              with the next available price. In backtesting it will be the
              opening price of the next bar

            - ``Order.Limit``. An order which can only be executed at the given
              ``price`` or better

            - ``Order.Stop``. An order which is triggered at ``price`` and
              executed like an ``Order.Market`` order

            - ``Order.Close``. An order which can only be executed with the
              closing price of the session (usually during a closing auction)

          - ``**kwargs``: additional broker implementations may support extra
            parameters. ``backtrader`` will pass the *kwargs* down to the
            created order objects

        Returns:
          - the submitted order
        '''
        sizer_ratio = self._sizer.getsizing()[self._id]
        ordermeta, trades = self.store.submit(self.experment_id, 
                                    sid, 
                                    sizer_ratio=sizer_ratio, 
                                    price=price, 
                                    plimit=plimit,
                                    exectype=exectype, 
                                    ordertype=ordertype, 
                                    **kwargs)
        # dt
        dt = self.getdtkey()
        self.orders[dt].append(ordermeta)
        self.trades[dt].append(trades)
        
    def sell(self, sid, price=0.0, plimit=0.0,
             exectype=None, ordertype=None, **kwargs):
        '''
        To create a selll (short) order and send it to the broker

        See the documentation for ``buy`` for an explanation of the parameters

        Returns: the submitted order
        '''
        sizer_ratio = self._sizer.getsizing(isbuy=False)[self._id]
        ordermeta, trades = self.store.submit(self.experment_id, 
                          sid, 
                          size=sizer_ratio, 
                          price=price, 
                          plimit=plimit, 
                          exectype=exectype, 
                          ordertype=ordertype, 
                          **kwargs)
        dt = self.getdtkey()
        self.orders[dt].append(ordermeta)
        self.trades[dt].append(trades)
    
    def _addwriter(self, writer):
        '''
        Unlike the other _addxxx functions this one receives an instance
        because the writer works at cerebro level and is only passed to the
        strategy to simplify the logic
        '''
        self.writers.append(writer)

    def get_value(self, complete=False):
        '''Returns the current value of the portfolio

        If ``complete`` is ``False`` (default) the value of the cash in hand
        plus the market value of the open positions is returned.

        If ``complete`` is ``True`` the value of all positions is calculated
        as if they were closed at the current market price and then added to
        the cash in hand.
        '''
        if complete:
            # warnings.warn("complete=True not implemented in BTStore")
            v = self.store.subcribe(self.experment_id, "account")
            return v
        v = self.store.get_value(self.experment_id)
        return v
    
    def get_position(self, complete=False):
        '''Returns the current position of the portfolio'''
        if complete:
            # warnings.warn("complete=True not implemented in BTStore")
            v = self.store.subcribe(self.experment_id, "account")
            return v
        v = self.store.get_position(self.experment_id)
        return v
    
    def _stop(self):
        self.stop()
        # change operators back to stage 1 - allows reuse of datas
        # self._stage1()

    def stop(self):
        '''Called right before the backtesting is about to be stopped'''
        self.store.stop(self.experment_id, last=True)
    
    def cancel(self, order_id):
        '''Cancels the order in the broker'''
        self.store.cancel(order_id)


class MetaSigStrategy(Strategy.__class__): # Stragey元类 / obj.__class__ 类 / class.__class__ 元类

    def __new__(meta, name, bases, dct):
        # map user defined next to custom to be able to call own method before
        if 'next' in dct:
            dct['_next_custom'] = dct.pop('next')

        cls = super(MetaSigStrategy, meta).__new__(meta, name, bases, dct)

        # after class creation remap _next_catch to be next
        cls.next = cls._next_catch
        return cls

    def dopreinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaSigStrategy, cls).dopreinit(_obj, *args, **kwargs)

        _obj._signals = collections.defaultdict(list)

        _data = _obj.p._data
        if _data is None:
            _obj._dtarget = _obj.data0
        elif isinstance(_data, int):
            _obj._dtarget = _obj.datas[_data]
        elif isinstance(_data, str):
            _obj._dtarget = _obj.getdatabyname(_data)
        elif isinstance(_data, bt.LineRoot):
            _obj._dtarget = _data
        else:
            _obj._dtarget = _obj.data0

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaSigStrategy, cls).dopostinit(_obj, *args, **kwargs) # experiment_id

        for sigtype, sigcls, sigargs, sigkwargs in _obj.p.signals:
            _obj._signals[sigtype].append(sigcls(*sigargs, **sigkwargs))

        # Record types of signals
        _obj._longshort = bool(_obj._signals[bt.SIGNAL_LONG])
        _obj._long = bool(_obj._signals[bt.SIGNAL_LONG])
        _obj._longexit = bool(_obj._signals[bt.SIGNAL_LONGEXIT])
        return _obj, args, kwargs


class SignalStrategy(with_metaclass(MetaSigStrategy, Strategy)):
    '''This subclass of ``Strategy`` is meant to to auto-operate using
    **signals**.

    *Signals* are usually indicators and the expected output values:

      - ``> 0`` is a ``long`` indication

      - ``< 0`` is a ``short`` indication

    There are 5 types of *Signals*, broken in 2 groups, short is not suppored

    **Main Group**:

      - ``LONG``:
        - ``long`` indications are taken to go long

          - If a ``LONGEXIT`` (see below) signal is in the system it will be
            used to exit the long

    **Exit Group**:

      - ``LONGEXIT``: ``short`` indications are taken to exit ``long``
        positions

    Params:

      - ``signals`` (default: ``[]``): a list/tuple of lists/tuples that allows
        the instantiation of the signals and allocation to the right type

        This parameter is expected to be managed through ``cerebro.add_signal``

      - ``_accumulate`` (default: ``False``): allow to enter the market
        (long/short) even if already in the market

      - ``_concurrent`` (default: ``False``): allow orders to be issued even if
        orders are already pending execution

      - ``_data`` (default: ``None``): if multiple datas are present in the
        system which is the target for orders. This can be

        - ``None``: The first data in the system will be used

        - An ``int``: indicating the data that was inserted at that position

        - An ``str``: name given to the data when creating it (parameter
          ``name``) or when adding it cerebro with ``cerebro.adddata(...,
          name=)``
    '''
    params = (
        ('signals', []),
        ('_accumulate', False),
        ('_concurrent', False),
        ('_data', None),
    )

    def _start(self):
        self._sentinel = None  # sentinel for order concurrency
        super(SignalStrategy, self)._start()

    def signal_add(self, sigtype, signal):
        self._signals[sigtype].append(signal)

    def _next_catch(self): # next
        self._next_signal()
        if hasattr(self, '_next_custom'):
            self._next_custom()

    def _next_signal(self):
        if self._sentinel is not None and not self.p._concurrent:
            return  # order active and more than 1 not allowed

        sigs = self._signals
        nosig = [[0.0]]

        # Calculate current status of the signals
        ls_long = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONG] or nosig)

        l_enter0 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONG] or nosig)
        l_enter1 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONG_INV] or nosig)
        l_enter2 = all(x[0] for x in sigs[bt.SIGNAL_LONG_ANY] or nosig)
        l_enter = l_enter0 or l_enter1 or l_enter2

        # aim to sell long position
        l_ex0 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONGEXIT] or nosig)
        l_ex1 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONGEXIT_INV] or nosig)
        l_ex2 = all(x[0] for x in sigs[bt.SIGNAL_LONGEXIT_ANY] or nosig)
        l_exit = l_ex0 or l_ex1 or l_ex2


        # Opposite of individual long  underlies to sell long position
        l_leav0 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONG] or nosig)
        l_leav1 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONG_INV] or nosig)
        l_leav2 = all(x[0] for x in sigs[bt.SIGNAL_LONG_ANY] or nosig)
        l_leave = l_leav0 or l_leav1 or l_leav2

        # Invalidate long leave if longexit signals are available
        l_leave = not self._longexit and l_leave

        # Take size and start logic
        size = self.getposition(self._dtarget).size
        if not size:
            if ls_long or l_enter:
                self._sentinel = self.buy(self._dtarget)
        elif size > 0:  # current long position
            if l_exit or l_leave:
                # closing position - not relevant for concurrency
                self.close(self._dtarget)

            if ls_long or l_enter:
                if self.p._accumulate:
                    self._sentinel = self.buy(self._dtarget)

        elif size < 0:  # current short position
            raise NotImplementedError("short is not supported")
