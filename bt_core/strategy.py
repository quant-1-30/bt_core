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
import json
import hashlib
from collections import defaultdict

import bt_core as bt
from .lineiterator import LineIterator, StrategyBase, _resolve_clock_feed
from .metabase import with_metaclass, findowner
from .utils import AutoOrderedDict, fast_uuid4_bytes, ts2intdt
from .utils.comparsion import check_gt_zero, check_lt_zero, check_nanzero
from .shm import SharedRingBuffer

from bt_protocol._protocol import OrderBody, SnapshotBody

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
        _obj.pnc = env.pnc
        _obj.log_shm = env.log_shm

        # register strategy to generate unique id and setup shm for strategy
        _obj.store = store = env.store

        _name = _obj.p._get("name", _obj.__class__.__name__)
        experiment_id = store.register(_name, env.cerebro_id)

        # uuid.UUID(bytes=experiment_id) # file_name <= 36
        shm_name = hashlib.md5(experiment_id).hexdigest()[:24] 
        _obj.shm_chan = SharedRingBuffer(shm_name=str(shm_name), capacity=10000000, is_creator=True)
        _obj.experiment_id = experiment_id
        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopreinit(_obj, *args, **kwargs)
        
        _obj._minperiods = list()
        _obj.analyzers = list() # ItemCollection()
        _obj.stats = {} 
        _obj.metrics = [] 

        _obj.snapshot = None
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

    lines = ('datetime',)

    params = (
        ("tz", "utc"),
    ) 
    
    def _settz(self, tz):
        self.lines.datetime._settz(tz)

    def _periodset(self):
        target_ids = {id(d) for d in self.datas} | {id(l) for d in self.datas for l in d.lines}

        # Traverse the full indicator tree (including nested cross-timeframe
        # child indicators such as a weekly SMA inside WeekPriceSignal) so
        # every resampled data feed in self.datas gets its true _minperiod.
        _dminperiods = collections.defaultdict(list)
        stack = list(self._lineiterators[LineIterator.IndType])
        while stack:
            lineiter = stack.pop()
            children = getattr(lineiter, '_lineiterators', None)
            if children:
                stack.extend(children.get(LineIterator.IndType, ()))

            clk = getattr(lineiter, '_clock', None)
            if clk is None:
                clk = getattr(lineiter._owner, '_clock', None)
            clk = _resolve_clock_feed(clk, stop_ids=target_ids)
            if clk is not None:
                _dminperiods[clk].append(lineiter._minperiod)

        # calc data minperiods
        for data in self.datas:
            dlminperiods = _dminperiods[data]
            for l in data.lines:  # search each line for min periods
                if l in _dminperiods:
                    dlminperiods += _dminperiods[l]  # found, add it

            self._minperiods.append(max(dlminperiods, default=data._minperiod))
    
    def minbuffer(self):
        _minperiod = self._minperiod
        self.lines.minbuffer(_minperiod)

        for data, dmin in zip(self.datas, self._minperiods or [1] * len(self.datas)):
            data.minbuffer(max(_minperiod, dmin))
        
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
    
    def _start(self, savemem, **kwargs):
        '''Called right before the bt_coreing is about to be started.'''
        self._periodrecalc()
        self.qbuffer(savemem=savemem)

        self._minperstatus = MAXINT
        self._dlens = [len(data) for data in self.datas]

        # initialize snapshot and shm_chan
        self.set_cash(**kwargs)
        self.snapshot = self.store.get_snapshot(self.experiment_id)
        self.shm_chan.publish_sentinel(0) 
        
        for analyzer in self.analyzers: # itertools.chain(self.analyzers, self._slave_analyzers)
            analyzer._start()

        # setup metric
        self._setupMetrics()

        # pnc _start
        trading_days = self.data0.benchmark_dret["day"].to_list()
        self.pnc._start(trading_days)

    def set_cash(self, **kwargs):
        cash = kwargs.pop("cash", 100000)
        session = kwargs.pop("fromdate", 0)
        snapshot = self.store.set_cash(self.experiment_id, session, cash)
        self.shm_chan.publish_snapshot(snapshot)

    def _setupMetrics(self):
        seen_names = collections.Counter()

        for _line in self.getindicators_lines():
            line_name = _line.plotinfo.plotname or _line.__class__.__name__

            for i, line_alias in enumerate(_line.lines.getlinealiases()):
                base_name = f"ind_{line_name}_{line_alias}"
                cnt = seen_names[base_name]
                seen_names[base_name] += 1
                
                metric_str = base_name if cnt == 0 else f"{base_name}_{cnt}"
                self.metrics.append(
                    (_line.lines[i], metric_str.encode("utf-8"))
                )

    def _addindicator(self, indcls, *indargs, **indkwargs):
        indcls(*indargs, **indkwargs) # postinit will take care of the rest

    def _addanalyzer(self, ancls, *anargs, **ankwargs):
        anname = ankwargs.pop('_name', '') or ancls.__name__.lower()
        # nsuffix = next(self._alnames[anname])
        # anname += str(nsuffix or '')  # 0 (first instance) gets no suffix
        analyzer = ancls(*anargs, **ankwargs)
        # self.analyzers.append(analyzer, anname)
        self.analyzers.append(analyzer)
        self.stats[anname] = analyzer
        return analyzer

    def _getminperstatus(self):
        if getattr(self, '_minperstatus', 1) < 0:
            return -1

        self._minperstatus = max(
            (mp - len(d) for d, mp in zip(self.datas, self._minperiods) if len(d) > 0 or mp > 1),
            default=1,
        )
        return self._minperstatus

    def clk_update(self):
        newdlens = [len(d) for d in self.datas]
        if any(nl > l for l, nl in zip(self._dlens, newdlens)):
            self.forward()
            self.lines.datetime[0] = max(
                (d.datetime[0] for d in self.datas if len(d)), default=0.0)
            self._dlens = newdlens

    def on_dt_over(self, last_dts: int, dts: int):
        snapshot = self.store.on_dt_over(self.experiment_id, last_dts, dts)
        if snapshot:
            self.shm_chan.publish_snapshot(snapshot)
            self.snapshot = snapshot

        # final settlement calls on_dt_over(last, 0): curr=0 tells the
        # simulator "no events today" (re-applying dividends would corrupt
        # positions), but downstream consumers must not see a bogus
        # 1970-01-01 dt row -> publish under the real last trading day
        publish_dts = dts if dts > 0 else last_dts
        self.shm_chan.publish_sentinel(publish_dts)

        for analyzer in self.analyzers:
            if hasattr(analyzer, 'on_dt_over'):
                analyzer.on_dt_over(publish_dts, snapshot)

        for _d in self.datas:
            _d.on_dt_over(publish_dts)

    def notify_metrics(self, last_dts: int): 
        """
        This method is called when a timer event is triggered. 
        It can be used to log indicator metrics and notify analyzers that are interested in timer events.
        """
        self.shm_chan.publish_sentinel(last_dts)

        for ind_line, metric in self.metrics:
            if len(ind_line) == 0:
                continue

            val = ind_line[0]
            if np.isnan(val):
                continue

            self.log_shm.publish_metric(metric, val, last_dts)

        for analyzer in self.analyzers:
            if hasattr(analyzer, 'notify_metrics'):
                analyzer.notify_metrics(last_dts) # get_shm_events
        
        for _d in self.datas:
            _d.notify_metrics(last_dts)

    def _next(self):
        self.clk_update() # advance differ from lineiterator _clk_update
        super(Strategy, self)._next()

    def on_risk(self, current_dts: int): # position risk is not applied
        snapshot = self.get_snapshot()
        current_day = ts2intdt(current_dts)
        sell_plans = self.pnc.on_risk(snapshot, self.stats, current_day)

        if sell_plans:
            self.sell(sell_plans) 

    def on_trade(self, current_dts: int):
        # print(f"[Strategy] Trigger on {current_dts}")  # 每次触发都打, 刷屏

        current_day = ts2intdt(current_dts)
        topk = self.datas[-1].get_topk(current_day)

        snapshot = self.get_snapshot()
        _plan = self.pnc.generate_plan(current_day, topk, snapshot)
        self.sell(_plan[b"sell"])
        self.buy(_plan[b"buy"])

    def _submit_orders(self, plans, order_type: int):
        filled = {}
        dt = self.lines.datetime[0]
        created_dt = 0 if np.isnan(dt) else int(dt)

        for plan in plans:
            sid = plan["sid"]
            order = OrderBody(
                sid=sid,
                order_id=fast_uuid4_bytes(),
                sizer_ratio=plan["weight"],
                price=plan.get("price", 0.0),
                order_type=order_type,
                exec_type=plan["execType"],
                created_dt=created_dt,
                filler=plan["filler"],
            )
            snapshot = self.store.submit(self.experiment_id, order)
            if snapshot.trades:
                self.shm_chan.publish_snapshot(snapshot)
                filled[sid] = snapshot.trades
            self.shm_chan.publish_order(order)

        self.snapshot = snapshot
        return filled

    def buy(self, buys):
        '''Create a buy (long) order and send it to the broker'''
        if not buys:
            return
        self._submit_orders(buys, 0)

    def sell(self, sells):
        '''To create a sell (short) order and send it to the broker'''
        if not sells:
            return
        filled = self._submit_orders(sells, 1)
        self.pnc.on_execute(filled)

    def get_snapshot(self)-> SnapshotBody: 
        return self.snapshot

    def cancel(self, order_id):
        '''Cancels the order in the broker'''
        self.store.cancel(order_id)
   
    def _stop(self):
        self.stop()

    def stop(self):
        '''Called right before the bt_coreing is about to be stopped'''
        last_dts = (self.lines.datetime[0]
                    if len(self.lines.datetime) else self.data.datetime[0])
        if not np.isnan(last_dts) and last_dts > 0:
            self.on_dt_over(int(last_dts), 0)

        for analyzer in self.analyzers:
            analyzer._stop()

        self.store.stop()

        self.shm_chan.close()
        self.shm_chan.unlink()
    

class MetaSigStrategy(Strategy.__class__): # Stragey元类 / obj.__class__ 类 / class.__class__ 元类

    def __new__(meta, name, bases, dct): # map user defined next to custom to be able to call own method before
        # if 'next' in dct:
        #     dct['_next_custom'] = dct.pop('next')

        cls = super(MetaSigStrategy, meta).__new__(meta, name, bases, dct)
        # cls._next = cls._next_catch # after class creation remap _next_catch to be next
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

        _obj._accumulate = _accumulate = _obj.p._accumulate
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

    def on_trade(self, current_dts: int): 
        sigs = self._signals
        nosig = [[0.0]]

        # Calculate current status of the signals
        # ls_long = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONGSHORT] or nosig)
        # ls_short = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONGSHORT] or nosig)

        l_enter0 = check_gt_zero(sigs[bt.SIGNAL_LONG], nosig)
        l_enter1 = check_lt_zero(sigs[bt.SIGNAL_LONG_INV], nosig)
        l_enter2 = check_nanzero(sigs[bt.SIGNAL_LONG_ANY], nosig)
        l_enter = l_enter0 or l_enter1 or l_enter2

        s_enter0 = check_lt_zero(sigs[bt.SIGNAL_SHORT], nosig)
        s_enter1 = check_gt_zero(sigs[bt.SIGNAL_SHORT_INV], nosig)
        s_enter2 = check_nanzero(sigs[bt.SIGNAL_SHORT_ANY], nosig)
        s_enter = s_enter0 or s_enter1 or s_enter2

        l_ex0 = check_lt_zero(sigs[bt.SIGNAL_LONGEXIT], nosig)
        l_ex1 = check_gt_zero(sigs[bt.SIGNAL_LONGEXIT_INV], nosig)
        l_ex2 = check_nanzero(sigs[bt.SIGNAL_LONGEXIT_ANY], nosig)
        l_exit = l_ex0 or l_ex1 or l_ex2

        s_ex0 = check_gt_zero(sigs[bt.SIGNAL_SHORTEXIT], nosig)
        s_ex1 = check_lt_zero(sigs[bt.SIGNAL_SHORTEXIT_INV], nosig)
        s_ex2 = check_nanzero(sigs[bt.SIGNAL_SHORTEXIT_ANY], nosig)
        s_exit = s_ex0 or s_ex1 or s_ex2

        # but only if no "xxxExit" exists
        l_rev = not self._longexit and s_enter # reverse --- longexit
        s_rev = not self._shortexit and l_enter # reverse --- shortexit

        # Opposite of individual long and short
        l_leav0 = check_lt_zero(sigs[bt.SIGNAL_LONG], nosig)
        l_leav1 = check_gt_zero(sigs[bt.SIGNAL_LONG_INV], nosig)
        l_leav2 = check_nanzero(sigs[bt.SIGNAL_LONG_ANY], nosig)
        l_leave = l_leav0 or l_leav1 or l_leav2

        s_leav0 = check_gt_zero(sigs[bt.SIGNAL_SHORT], nosig)
        s_leav1 = check_lt_zero(sigs[bt.SIGNAL_SHORT_INV], nosig)
        s_leav2 = check_nanzero(sigs[bt.SIGNAL_SHORT_ANY], nosig)
        s_leave = s_leav0 or s_leav1 or s_leav2

        # Invalidate long leave if longexit signals are available
        l_leave = not self._longexit and l_leave
        # Invalidate short leave if shortexit signals are available
        s_leave = not self._shortexit and s_leave

        # execute pnc
        has_signal = l_enter or l_exit or l_rev or l_leave or s_enter or s_exit or s_rev or s_leave
        
        if not has_signal: 
            return

        current_day = ts2intdt(current_dts)
        topk = self.datas[-1].get_topk(current_day)
        
        snapshot = self.get_snapshot()

        _plan = self.pnc.generate_plan(current_day, topk, snapshot)
        # print("generate_plan", _plan)  

        if l_enter:
            if self._accumulate:
                self.buy(_plan[b"buy"])
        else:
            self.sell(_plan[b"sell"]) 
