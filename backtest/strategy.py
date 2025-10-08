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
import datetime
import itertools
import operator

import backtest as bt
from .lineiterator import LineIterator, StrategyBase
from .lineroot import LineSingle
from .lineseries import LineSeriesStub
from .metabase import with_metaclass, ItemCollection, findowner
from backtest.utils.dateintern import num2date


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

        _obj.store = _obj.env.store # add store to strategy
        _obj.sizer = _obj.env.sizer # add store to strategy
        _obj._minperiods = list()
        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopostinit(_obj, *args, **kwargs)
        
        _obj._periodset()

        return _obj, args, kwargs


class Strategy(with_metaclass(MetaStrategy, StrategyBase)):
    '''
    Base class to be subclassed for user defined strategies.
    '''

    _ltype = LineIterator.StratType

    lines = ('datetime',)

    # def qbuffer(self, savemem=0):
    #     '''Enable the memory saving schemes. Possible values for ``savemem``:

    #       0: No savings. Each lines object keeps in memory all values

    #       1: All lines objects save memory, using the strictly minimum needed
    #     '''
    #     if not savemem:
    #         for data in self.datas:
    #             data.qbuffer(savemem=1)
    #     # Save in all object types depending on the strategy
    #     for itcls in self._lineiterators:
    #         for it in self._lineiterators[itcls]:
    #             it.qbuffer(savemem=1)

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

    def _periodcalc(self):
        # last check in case not all lineiterators were assigned to
        # lines (directly or indirectly after some operations)
        # An example is Kaufman's Adaptive Moving Average
        indicators = self._lineiterators[LineIterator.IndType] # include LinesOperation
        inds = [ind for ind in indicators if isinstance(ind, bt.indicators.Indicator)]
        minperiod = max(self._minperiods) + len(inds) - 1 # due to default _minperiod is 1
        print("strategy _periodcalc :", minperiod)
        self._minperiod = minperiod
        # import pdb; pdb.set_trace()
     
    def _start(self):
        self._periodcalc()

        # Tell datas to adjust buffer to minimum period
        for data in self.datas:
            data.minbuffer(self._minperiod) # make sure data minperiod is at least strategy's     

        self._minperstatus = np.iinfo(np.int_).max  # start in prenext
        self.start()

    def start(self):
        '''Called right before the backtesting is about to be started.'''
        pass

    def _getminperstatus(self):
        dlens = map(operator.sub, self._minperiods, map(len, self.datas))
        self._minperstatus = minperstatus = max(dlens)
        # print("_getminperstatus ", self._minperstatus)
        return minperstatus

    def _addwriter(self, writer):
        '''
        Unlike the other _addxxx functions this one receives an instance
        because the writer works at cerebro level and is only passed to the
        strategy to simplify the logic
        '''
        self.writers.append(writer)

    def _addindicator(self, indcls, *indargs, **indkwargs):
        indcls(*indargs, **indkwargs) # postinit will take care of the rest
 
    def _next(self):
        super(Strategy, self)._next() # lineiterator _next

    def _settz(self, tz):
        self.lines.datetime._settz(tz)

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
        self.store.submit(sid, sizer_ratio=sizer_ratio, price=price, plimit=plimit,
                            exectype=exectype, ordertype=ordertype, **kwargs)
        
    def sell(self, sid, price=0.0, plimit=0.0,
             exectype=None, ordertype=None, **kwargs):
        '''
        To create a selll (short) order and send it to the broker

        See the documentation for ``buy`` for an explanation of the parameters

        Returns: the submitted order
        '''
        sizer_ratio = self._sizer.getsizing()[self._id]
        self.store.submit(sid, size=sizer_ratio, price=price, plimit=plimit, 
                          exectype=exectype, ordertype=ordertype, **kwargs)
    
    def _stop(self):
        self.stop()
        # change operators back to stage 1 - allows reuse of datas
        # self._stage1()

    def stop(self):
        '''Called right before the backtesting is about to be stopped'''
        self.store.stop()
    
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
            super(MetaSigStrategy, cls).dopostinit(_obj, *args, **kwargs)

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
