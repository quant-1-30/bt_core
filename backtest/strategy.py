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
import json
from collections import defaultdict
from bt_sdk.constant import OrderType, ExecType
from bt_sdk.core.model import Order

import backtest as bt
from .lineiterator import LineIterator, StrategyBase
from .lineseries import LineSeriesStub
from .metabase import with_metaclass, ItemCollection, findowner
from .utils.dateintern import num2date
from .utils.autodict import AutoOrderedDict

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
        _obj.env = cerebro = findowner(_obj, bt.cerebro.Cerebro)
        _obj.sizer = cerebro.sizer # add sizing to strategy
        _obj.store = cerebro.store # add store to strategy
        _obj.risk_control = cerebro.risk_control # add risk control to strategy

        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopreinit(_obj, *args, **kwargs)
        
        _obj._minperiods = list()

        _obj.stats = _obj.observers = ItemCollection()
        _obj.analyzers = ItemCollection()
        _obj._alnames = collections.defaultdict(itertools.count) # unique analyzer id
        _obj.writers = list()
        _obj._orders = list()
        _obj._trades = list()

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopostinit(_obj, *args, **kwargs)
        
        _obj._periodset()
        
        _obj.experiment_id = _obj._next_exp()

        return _obj, args, kwargs


class Strategy(with_metaclass(MetaStrategy, StrategyBase)):
    '''
    Base class to be subclassed for user defined strategies.
    '''
    plotinfo = dict(plot=True, plotname="Strategy")

    _ltype = LineIterator.StratType

    # lines = ('datetime',)
    lines = ('datetime', 'buy', 'sell')

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

    def _start(self, **kwargs):
        self.start()
        
        self._periodrecalc()

        # for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        for analyzer in self.analyzers:
            analyzer._start()

        for obs in self.observers:
            if not isinstance(obs, list):
                obs = [obs]  # support of multi-data observers

            for o in obs:
                o._start()

        self._minperstatus = MAXINT  # start in prenext

        self._dlens = [len(data) for data in self.datas]

    def start(self):
        '''Called right before the backtesting is about to be started.'''
        store = self.store
        store.set_cash(self, self.env.cash)

    def _settz(self, tz):
        self.lines.datetime._settz(tz)
    
    def _next_exp(self) -> str:
        """
            Return experiment_id: str 
        """
        p_str = json.dumps(self.p._getkwargs())
        _identity = f"{self.__class__.__name__}({p_str})"
        exp_id = self.store.make_experiment(_identity)
        return exp_id

    def _getminperstatus(self):
        dlens = map(operator.sub, self._minperiods, map(len, self.datas))
        self._minperstatus = minperstatus = max(dlens)
        # print("_getminperstatus ", self._minperstatus)
        return minperstatus

    def _addindicator(self, indcls, *indargs, **indkwargs):
        indcls(*indargs, **indkwargs) # postinit will take care of the rest

    def _addanalyzer(self, ancls, *anargs, **ankwargs):
        anname = ankwargs.pop('_name', '') or ancls.__name__.lower()
        nsuffix = next(self._alnames[anname])
        anname += str(nsuffix or '')  # 0 (first instance) gets no suffix
        analyzer = ancls(*anargs, **ankwargs)
        self.analyzers.append(analyzer, anname)
        return analyzer

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
            else:
                observer._next()

    def _clk_update(self):
        newdlens = [len(d) for d in self.datas]
        if any(nl > l for l, nl in zip(self._dlens, newdlens)):
            self.forward()

        self.lines.datetime[0] = max(d.datetime[0]
                                     for d in self.datas if len(d))
        
        self._dlens = newdlens

        return len(self)

    def on_dt_over(self, last=False)->bool:
        """
            on_dt_over is used to adapt T + 1 policy:
                a. process position with adjustment or rightment on next trading_date
                b. process account and position on preclose_date
        """
        dt_over = self.store.on_dt_over(self.experiment_id, last)
        return dt_over
    
    def _next(self):
        dtover = self.on_dt_over()

        super(Strategy, self)._next() # lineiterator _next
        minperstatus = self._getminperstatus()
        self._next_observers(minperstatus)

        if dtover:
            self.clear()

    def _notify(self, qorder, qtrades=[]):
        # need to know if quicknotify is on, to not reprocess pendingorders
        # and pendingtrades, which have to exist for things like observers
        # which look into it
        self._orders.append(qorder)
        if qtrades:
            self._trades.extend(qtrades)

    def buy(self, execType=ExecType.Market, plimit: int=0):
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

          - ``plimit``: plimit for limit/stop orders, int 

          - ``**kwargs``: additional broker implementations may support extra
            parameters. ``backtrader`` will pass the *kwargs* down to the
            created order objects

        Returns:
          - the submitted order
        '''
        if not self.risk_control.is_restricted(self):
            _sizer = int(self.sizer.getsizing(self.datas)) # 单位100

            order = Order(sid=self.datas[0].p.sid[0],
                        pricelimit=plimit,
                        sizer_ratio=_sizer, 
                        order_type=OrderType.Buy.value,
                        exec_type=execType.value, 
                        created_dt=int(self.lines.datetime[0]))

            ord, trades = self.store.submit(self.experiment_id, order)
            if trades:
                self.lines.buy[0] = 1 

            self._notify(ord, trades)
        
    def sell(self, execType=ExecType.Market, plimit: int=0):
        '''
        To create a selll (short) order and send it to the broker

        See the documentation for ``buy`` for an explanation of the parameters

        Returns: the submitted order
        '''
        if not self.risk_control.is_restricted(self):
            _sizer = int(self.sizer.getsizing(self.datas, isbuy=False))

            order = Order(sid=self.datas[0].p.sid[0],
                          sizer_ratio=_sizer, 
                          pricelimit=plimit,     
                          order_type=OrderType.Sell.value,
                          exec_type=execType.value, 
                          created_dt=int(self.lines.datetime[0]))
        

            ord, trades = self.store.submit(self.experiment_id, order)
            if trades:
                self.lines.sell[0] = -1
                self.sizer.restore() # reset sizing pyramid 
        
            self._notify(ord, trades)
        
    def getsizing(self, isbuy=True):
        '''Get the current sizing for the strategy'''
        return self._sizer.getsizing()[self._id]
    
    def _addwriter(self, writer):
        '''
        Unlike the other _addxxx functions this one receives an instance
        because the writer works at cerebro level and is only passed to the
        strategy to simplify the logic
        '''
    
    def getwriterheaders(self):
        self.indobscsv = [self]

        indobs = itertools.chain(
            self.getindicators_lines(), self.getobservers())
        self.indobscsv.extend(filter(lambda x: x.csv, indobs))

        headers = list()

        # prepare the indicators/observers data headers
        for iocsv in self.indobscsv:
            name = iocsv.plotinfo.plotname or iocsv.extra_info
            headers.append(name)
            col_alias = ",".join(iocsv.getlinealiases())
            headers.append(col_alias)
        
        return headers

    def getwritervalues(self):
        values = list()

        for iocsv in self.indobscsv:
            name = iocsv.plotinfo.plotname or iocsv.extra_info # iocsv.__class__.__name__
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
        acct = self.store.getaccount(self.experiment_id)
        ainfo.Value.End = acct.portfolio_value if acct else 0

        # no slave analyzers for writer
        for aname, analyzer in self.analyzers.getitems():
            ainfo[aname].Params = analyzer.p._getkwargs() or None
            ainfo[aname].Analysis = analyzer.get_analysis()

        return wrinfo
    
    def getvalue(self, isall=False):
        '''Returns the portfolio value and positions of strategy

        If ``isall`` is ``False`` (default) the value of the cash in hand
        plus the market value of the open positions is returned.

        If ``isall`` is ``True`` the value of all positions is calculated
        as if they were closed at the current market price and then added to
        the cash in hand.
        '''
        if isall:
            acct = self.store.subscribe(self.experiment_id, "account")
            postn = self.store.subscribe(self.experiment_id, "position")
        else:
            acct = self.store.getaccount(self.experiment_id)
            postn = self.store.getposition(self.experiment_id) # vector
        # print("strategy getvalue :", acct, postn)
        return (acct, postn)
    
    def clear(self):
        self._orders.clear()
        self._trades.clear()
    
    def _stop(self):
        self.stop()

    def stop(self):
        '''Called right before the backtesting is about to be stopped'''
        self.store.stop(self.experiment_id)
    
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
