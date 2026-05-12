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
import math
import warnings
import collections
import itertools
import operator
import json
import hashlib
from collections import defaultdict
from bt_sdk.core.protocol import OrderBody, SnapshotBody

import backtest as bt
from .lineiterator import LineIterator, StrategyBase
from .lineseries import LineSeriesStub
from .metabase import with_metaclass, findowner
from .utils.autodict import AutoOrderedDict
from .shm import SharedRingBuffer

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

        # Find the _owner and store it
        _obj.env = env = cerebro = findowner(_obj, bt.cerebro.Cerebro)
        _obj.pnc = env.pnc # pnc contain sizer and risk

        # register strategy to store with unique id
        _obj.store = store = env.store
        _obj.experiment_id = experiment_id = store.register(_obj.__class__.__name__, env.u_id)
        # setup shared memory channel for strategy to publish data to writer
        # import uuid
        # shm_name = uuid.UUID(bytes=experiment_id) # file name 36 too long
        shm_name = hashlib.md5(experiment_id).hexdigest()[:24]
        _obj.shm_chan = SharedRingBuffer(shm_name=str(shm_name), capacity=100000, is_creator=True)
        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopreinit(_obj, *args, **kwargs)
        
        _obj._minperiods = list()

        # _obj.analyzers = ItemCollection()
        # _obj._alnames = collections.defaultdict(itertools.count) # unique analyzer id
        _obj.analyzers = list()
        _obj.observers = list()

        _obj.stats = {}
        # _obj.stats = _obj.observers = ItemCollection()

        # _obj.writers = list()
        # _obj._orders = list()
        # _obj._trades = list()

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
    plotinfo = dict(plot=True, plotname="Strategy")

    _ltype = LineIterator.StratType

    lines = ('datetime', 'buy', 'sell') # lines = ('datetime',)

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
    
    def minbuffer(self):
        _minperiod = self._minperiod
        self.lines.minbuffer(_minperiod)

        for data in self.datas:
            data.minbuffer(_minperiod) # make sure data minperiod is at least strategy's  
        
        for itcls in self._lineiterators:
            for it in self._lineiterators[itcls]:
                it.minbuffer(_minperiod)

    def qbuffer(self, savemem=1):
        '''Enable the memory saving schemes. Possible values for ``savemem``:

          0: No savings. Each lines object keeps in memory all values

          1: All lines objects save memory, using the strictly minimum needed
        '''
        super().qbuffer(savemem=savemem)
        self.minbuffer()
    
    def notify(self, snapshot):
        # need to know if quicknotify is on, to not reprocess pendingorders
        # and pendingtrades, which have to exist for things like observers
        # which look into it
        self.shm_chan.publish_snapshot(self.experiment_id, snapshot) # publish trade to shared memory for writer to consume

    def on_timer(self, dts):
        self.on_dt_over = True
        snapshot = self.store.on_dt_over(self.experiment_id) 
        if snapshot:
            self.shm_chan.publish_snapshot(self.experiment_id, snapshot) # publish snapshot to shared memory for writer to consume
        self.on_dt_over = False

    def _start(self, savemem, **kwargs):
        '''Called right before the backtesting is about to be started.'''
        self.set_cash(**kwargs)
        self.qbuffer(savemem=savemem)
        self._periodrecalc()

        for analyzer in self.analyzers: # itertools.chain(self.analyzers, self._slave_analyzers)
            analyzer._start()

        for obs in self.observers:
            if not isinstance(obs, list):
                obs = [obs]  # support of multi-data observers

            for o in obs:
                o._start()

        # self._minperstatus = MAXINT  # start in prenext
        self._dlens = np.array([len(data) for data in self.datas])
        self.on_dt_over = False

    def _settz(self, tz):
        self.lines.datetime._settz(tz)
    
    def _addindicator(self, indcls, *indargs, **indkwargs):
        indcls(*indargs, **indkwargs) # postinit will take care of the rest

    def _addanalyzer(self, ancls, *anargs, **ankwargs):
        # anname = ankwargs.pop('_name', '') or ancls.__name__.lower()
        # nsuffix = next(self._alnames[anname])
        # anname += str(nsuffix or '')  # 0 (first instance) gets no suffix
        analyzer = ancls(*anargs, **ankwargs)
        # self.analyzers.append(analyzer, anname)
        self.analyzers.append(analyzer)
        return analyzer

    def _addobserver(self, multi, obscls, *obsargs, **obskwargs):
        obsname = obskwargs.pop('obsname', '')
        if not obsname:
            obsname = obscls.__name__.lower()

        if not multi:
            newargs = list(itertools.chain(self.datas, obsargs))
            obs = obscls(*newargs, **obskwargs)
            # self.stats.append(obs, obsname)
            self.observers.append(obs)
            self.stats[obsname] = obs
            return

        # setattr(self.stats, obsname, list())
        # l = getattr(self.stats, obsname)

        for data in self.datas:
            obs = obscls(data, *obsargs, **obskwargs)
            # l.append(obs)
            self.observers.append(obs)
            self.stats[obsname] = obs
    
    def _getminperstatus(self):
        dlens = map(operator.sub, self._minperiods, map(len, self.datas))
        # self._minperstatus = minperstatus = np.max(dlens)
        minperstatus = max(dlens)
        return minperstatus

    def clk_update(self):
        newdlens = np.array([len(d) for d in self.datas])
        if any(nl > l for l, nl in zip(self._dlens, newdlens)):
            self.forward()

        self.lines.datetime[0] = np.max([d.datetime[0]
                                     for d in self.datas if len(d)])      
        self._dlens = newdlens

    # @profile
    def _next_observers(self, minperstatus):
        if minperstatus < 0:
            for analyzer in self.analyzers:
                analyzer._next()
        elif minperstatus == 0 :
            for analyzer in self.analyzers:
                analyzer._nextstart()
        else:
            for analyzer in self.analyzers:
                analyzer._prenext()

        for observer in self.observers:
            observer._next()

    def _next(self):
        self.clk_update() # differ from lineiterator _clk_update 
        super(Strategy, self)._next()
        minperstatus = self._getminperstatus()
        self._next_observers(minperstatus)

    def set_cash(self, **kwargs):
        cash = kwargs.pop("cash", 100000)
        session = kwargs["fromdate"]
        self.store.set_cash(self.experiment_id, session, cash)
    
    def buy(self, buys, plimit: float=0.0, execType=0, filler=b"oco"):
        '''Create a buy (long) order and send it to the broker 
          
          - ``plimit`` (default: ``0.0``) means set price limit or not

          - ``exectype`` (default: ``int``)

            Possible values:

            - ``0 `` alias for Order.Market. An order will be executed
              on created_dt 

            - ``1 ``. alias for Order.Limit. An order be executed at the given
                price`` or better. e.g.  oco / occ / smooth / trend

            - ``2 ``. alias for Order.Stop is not supported by A stock 

            - ``3``. alias for StopLimit is not supported by A stock  

          - ``filler``: logic for simulate executed price on created_dt
            
            Possible values:

            - ``oco``. An order which can only be executed on order created_dt 
                where open price be base of plimit

            - ``occ``. An order which can only be executed on order created_dt
                where close price be base of plimit

            - ``smooth``. An order which can only be executed on order created_dt
                where mean of ohlc

            - ``likehood``. An order which can only be executed on order created_dt 
                where high for buy order or low for sell order

          - ``**kwargs``: additional broker implementations may support extra
            parameters. ``backtrader`` will pass the *kwargs* down to the
            created order objects

        Returns:
          - the submitted order
        '''
        created_dt = self.lines.datetime[0]
        created_dt = 0.0 if np.isnan(created_dt) else created_dt

        for bplan in buys:
            core = bplan.core
            order = OrderBody(
                        core["sid"],
                        sizer_ratio=core["weight"], 
                        pricelimit=plimit,
                        order_type=0,
                        exec_type=0, 
                        created_dt=int(created_dt),
                        filler=filler)
            snapshot = self.store.submit(self.experiment_id, order)
            if snapshot.trades:
                self.lines.buy[0] = 1 
                self.notify(snapshot)
        
    def sell(self, sells, plimit: float=0.0, execType=0, filler=b"oco"):
        '''
        To create a selll (short) order and send it to the broker

        See the documentation for ``buy`` for an explanation of the parameters

        Returns: the submitted order
        '''
        created_dt = self.lines.datetime[0]
        created_dt = 0.0 if np.isnan(created_dt) else created_dt
        filled = {}

        for splan in sells:
            core = splan.core
            order = OrderBody(
                        core["sid"],
                        sizer_ratio=core["weight"], 
                        pricelimit=plimit,     
                        order_type=1,
                        exec_type=execType, 
                        created_dt=int(created_dt),
                        filler=filler)
        
            snapshot = self.store.submit(self.experiment_id, order)
            trades = snapshot.trades
            if trades:
                self.lines.sell[0] = -1
                self.notify(snapshot)
                filled[core["sid"]] = trades 
        
        self.pnc.on_filled(filled)
    
    def cancel(self, order_id):
        '''Cancels the order in the broker'''
        self.store.cancel(order_id)

    def get_snapshot(self)-> SnapshotBody: 
        snapshot = self.store.get_snapshot(self.experiment_id) 
        return snapshot
         
    def getwriterheaders(self):
        self.indobscsv = [self]

        indobs = itertools.chain(
            self.getindicators_lines(), self.getobservers())
        self.indobscsv.extend(filter(lambda x: x.csv, indobs))

        headers = list()

        # prepare the indicators/observers data headers
        for iocsv in self.indobscsv:
            name = iocsv.plotinfo.plotname or iocsv.__class__.__name__
            headers.append(name)
            col_alias = ",".join(iocsv.getlinealiases())
            headers.append(col_alias)
        
        return headers

    def getwritervalues(self):
        values = list()

        for iocsv in self.indobscsv:
            name = iocsv.plotinfo.plotname or iocsv.__class__.__name__
            values.append(name)
            lio = len(iocsv)
            if lio:
                v = map(lambda l: str(l[0]), iocsv.lines.itersize())
            else:
                v = [''] * iocsv.lines.size()
            values.append(",".join(v))

        return values

    def getwriterinfo(self):
        wrinfo = AutoOrderedDict()

        wrinfo['Params'] = self.p._getkwargs()

        sections = [
            ['Indicators', self.getindicators_lines()],
            ['Observers', self.getobservers()]
        ]

        for sectname, sectitems in sections:
            sinfo = wrinfo[sectname]
            for item in sectitems:
                itname = item.__class__.__name__
                sinfo[itname].Lines = item.lines.getlinealiases() or None
                sinfo[itname].Params = item.p._getkwargs() or None

        ainfo = wrinfo.Analyzers

        # Internal Value Analyzer
        snapshot = self.get_snapshot()
        acct = snapshot.account
        ainfo.Value.End = acct.portfolio_value if acct else 0

        # no slave analyzers for writer
        # for aname, analyzer in self.analyzers.getitems():
        for analyzer in self.analyzers:
            aname = analyzer.__class__.__name__.lower()
            ainfo[aname].Params = analyzer.p._getkwargs() or None
            ainfo[aname].Analysis = analyzer.get_analysis()

        return wrinfo
    
    def _stop(self):
        self.stop()

    def stop(self):
        '''Called right before the backtesting is about to be stopped'''
        self.store.stop(self.experiment_id)
    

class MetaSigStrategy(Strategy.__class__): # Stragey元类 / obj.__class__ 类 / class.__class__ 元类

    def __new__(meta, name, bases, dct):
        # map user defined next to custom to be able to call own method before
        # if 'next' in dct:
        #     dct['_next_custom'] = dct.pop('next')

        cls = super(MetaSigStrategy, meta).__new__(meta, name, bases, dct)

        # after class creation remap _next_catch to be next
        # cls._next = cls._next_catch
        return cls

    def dopreinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaSigStrategy, cls).dopreinit(_obj, *args, **kwargs)
        
        _obj._signals = collections.defaultdict(list)

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        for sigtype, sigcls, sigargs, sigkwargs in _obj.p.signals:
            _obj._signals[sigtype].append(sigcls(*sigargs, **sigkwargs)) # autoregister signal indicator
        
        _obj, args, kwargs = \
            super(MetaSigStrategy, cls).dopostinit(_obj, *args, **kwargs)

        # Record types of signals
        _obj._long = bool(_obj._signals[bt.SIGNAL_LONG])
        _obj._short = bool(_obj._signals[bt.SIGNAL_SHORT])

        _obj._longexit = bool(_obj._signals[bt.SIGNAL_LONGEXIT])
        _obj._shortexit = bool(_obj._signals[bt.SIGNAL_SHORTEXIT])

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
        ('_accumulate', True),
    )
    
    def _start(self, savemem, **kwargs):
        # self._sentinel = None  # sentinel for order concurrency
        super(SignalStrategy, self)._start(savemem, **kwargs)

    def signal_add(self, sigtype, signal):
        self._signals[sigtype].append(signal)

    def _next(self): # next
        super(SignalStrategy, self)._next()
        self._next_signal()
        # if hasattr(self, '_next_custom'):
        #     self._next_custom()

    def _next_signal(self): # not supported short sell 

        sigs = self._signals
        nosig = [[0.0]]

        # Calculate current status of the signals
        # ls_long = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONGSHORT] or nosig)
        # ls_short = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONGSHORT] or nosig)

        l_enter0 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONG] or nosig)
        l_enter1 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONG_INV] or nosig)
        l_enter2 = any(x[0] for x in sigs[bt.SIGNAL_LONG_ANY] or nosig)
        l_enter = l_enter0 or l_enter1 or l_enter2

        s_enter0 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_SHORT] or nosig)
        s_enter1 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_SHORT_INV] or nosig)
        s_enter2 = any(x[0] for x in sigs[bt.SIGNAL_SHORT_ANY] or nosig)
        s_enter = s_enter0 or s_enter1 or s_enter2

        l_ex0 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONGEXIT] or nosig)
        l_ex1 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONGEXIT_INV] or nosig)
        l_ex2 = any(x[0] for x in sigs[bt.SIGNAL_LONGEXIT_ANY] or nosig)
        l_exit = l_ex0 or l_ex1 or l_ex2

        s_ex0 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_SHORTEXIT] or nosig)
        s_ex1 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_SHORTEXIT_INV] or nosig)
        s_ex2 = any(x[0] for x in sigs[bt.SIGNAL_SHORTEXIT_ANY] or nosig)
        s_exit = s_ex0 or s_ex1 or s_ex2

        # but only if no "xxxExit" exists
        l_rev = not self._longexit and s_enter # reverse --- longexit
        s_rev = not self._shortexit and l_enter # reverse --- shortexit

        # Opposite of individual long and short
        l_leav0 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONG] or nosig)
        l_leav1 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONG_INV] or nosig)
        l_leav2 = any(x[0] for x in sigs[bt.SIGNAL_LONG_ANY] or nosig)
        l_leave = l_leav0 or l_leav1 or l_leav2

        s_leav0 = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_SHORT] or nosig)
        s_leav1 = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_SHORT_INV] or nosig)
        s_leav2 = any(x[0] for x in sigs[bt.SIGNAL_SHORT_ANY] or nosig)
        s_leave = s_leav0 or s_leav1 or s_leav2

        # Invalidate long leave if longexit signals are available
        l_leave = not self._longexit and l_leave
        # Invalidate short leave if shortexit signals are available
        s_leave = not self._shortexit and s_leave

        current_prices = {self.data0.sid[0]: self.data0.close[0]} # only support one data feed for now
        snapshot = self.get_snapshot()
        plan = self.pnc.generate_plan(current_prices, current_prices, snapshot, self.stats)  

        if l_enter:
            if self.p._accumulate:
                self.buy(plan["buy"])
        # elif l_exit or l_rev or l_leave:
        else:
            # closing position - not relevant for concurrency
            self.sell(plan["sell"]) # sell means close
