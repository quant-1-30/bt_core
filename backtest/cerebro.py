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
import json
import numpy as np
import datetime
import itertools
from collections import OrderedDict
from pytz import timezone

from . import observers
from .writer import WriterFile
from .metabase import MetaParams, with_metaclass
from .strategy import Strategy, SignalStrategy
from .sizers import _sizers
from .pnc import Pnc
from .timer import Timer, Session
from .errors import *
from .stores import _stores
from .plot import Plot
from .utils.wrapper import consume_time
from .utils.encoder import CustomJSONEncoder


class Cerebro(with_metaclass(MetaParams, object)):
    '''Params:

      - ``maxcpus`` (default: None -> all available cores)

         How many cores to use simultaneously for optimization

      - ``stdstats`` (default: ``True``)

        If True default Observers will be added: Broker (Cash and Value),
        Trades and BuySell

      - ``writer`` (default: ``False``)

        If set to ``True`` a default WriterFile will be created which will
        print to stdout. It will be added to the strategy (in addition to any
        other writers added by the user code)
    
      - ``oldsync`` (default: ``False``)

        Starting with release 1.9.0.99 the synchronization of multiple datas
        (same or different timeframes) has been changed to allow datas of
        different lengths.

        If the old behavior with data0 as the master of the system is wished,
        set this parameter to true

      - ``tz`` (default: ``None``)

        Adds a global timezone for strategies. The argument ``tz`` can be

          - ``None``: in this case the datetime displayed by strategies will be
            in UTC, which has been always the standard behavior

          - ``pytz`` instance. It will be used as such to convert UTC times to
            the chosen timezone

          - ``string``. Instantiating a ``pytz`` instance will be attempted.

          - ``integer``. Use, for the strategy, the same timezone as the
            corresponding ``data`` in the ``self.datas`` iterable (``0`` would
            use the timezone from ``data0``)

        Broker notifications are delivered right before the delivery of the
        *next* prices. For backtesting this has no implications, but with live
        brokers a notification can take place long before the bar is
        delivered. When set to ``True`` notifications will be delivered as soon
        as possible (see ``qcheck`` in live feeds)

        Set to ``False`` for compatibility. May be changed to ``True``

    '''
    params = (
        ("client_id", ""),
        ('savemem', 1),
        ('oldsync', False),
        ('tz', None),
        ("timeout", 10),
        ('stdstats', True),
        ("isplot", False),
        ('writer', True),
    )

    def __init__(self):
        self.cash = 0.0
        self.u_id = "" 

        self.datas = list()
        self.strats = list()
        self.observers = list()
        self.indicators = list()
        self.signals = list()
        self._signal_strat = (None, None, None)
        self._signal_accumulate = True
        
        self.optcbs = list()  
        self.storecbs = list()

        self._pretimers = list()
        self._mcstimers = list()
        
        self.writers = list()
        self._plot = Plot()

# ----------------------------------------------------------------- timer --------------------------------------------------------------
    
    def addtz(self, tz):
        '''
        This can also be done with the parameter ``tz``

        Adds a global timezone for strategies. The argument ``tz`` can be

          - ``None``: in this case the datetime displayed by strategies will be
            in UTC, which has been always the standard behavior

          - ``pytz`` instance. It will be used as such to convert UTC times to
            the chosen timezone

          - ``string``. Instantiating a ``pytz`` instance will be attempted.

          - ``integer``. Use, for the strategy, the same timezone as the
            corresponding ``data`` in the ``self.datas`` iterable (``0`` would
            use the timezone from ``data0``)
        '''
        tz = self.p.tz
        if isinstance(tz, int):
            tz = self.datas[tz]._tz
        else:
            tz = timezone(tz)

    def _add_timer(self, when,
                   offset=datetime.timedelta(), repeat=datetime.timedelta(),
                   weekdays=[], weekcarry=False,
                   monthdays=[], monthcarry=True,
                   allow=None,
                   tzdata=None,
                   *args, **kwargs):
        '''Internal method to really create the timer (not started yet) which
        can be called by cerebro instances or other objects which can access
        cerebro'''

        timer = Timer(
            when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata,
            *args, **kwargs
        )

        self._pretimers.append(timer)
        return timer

    def add_timer(self, when,
                  offset=datetime.timedelta(), repeat=datetime.timedelta(),
                  weekdays=[], weekcarry=False,
                  monthdays=[], monthcarry=True,
                  allow=None,
                  tzdata=None):
        '''
        Arguments:

          - ``when``: can be

            - ``datetime.time`` instance (see below ``tzdata``)
            - ``bt.timer.SESSION_START`` to reference a session start
            - ``bt.timer.SESSION_END`` to reference a session end

         - ``offset`` which must be a ``datetime.timedelta`` instance

           Used to offset the value ``when``. It has a meaningful use in
           combination with ``SESSION_START`` and ``SESSION_END``, to indicated
           things like a timer being called ``15 minutes`` after the session
           start.

          - ``repeat`` which must be a ``datetime.timedelta`` instance

            Indicates if after a 1st call, further calls will be scheduled
            within the same session at the scheduled ``repeat`` delta

            Once the timer goes over the end of the session it is reset to the
            original value for ``when``

          - ``weekdays``: a **sorted** iterable with integers indicating on
            which days (iso codes, Monday is 1, Sunday is 7) the timers can
            be actually invoked

            If not specified, the timer will be active on all days

          - ``weekcarry`` (default: ``False``). If ``True`` and the weekday was
            not seen (ex: trading holiday), the timer will be executed on the
            next day (even if in a new week)

          - ``monthdays``: a **sorted** iterable with integers indicating on
            which days of the month a timer has to be executed. For example
            always on day *15* of the month

            If not specified, the timer will be active on all days

          - ``monthcarry`` (default: ``True``). If the day was not seen
            (weekend, trading holiday), the timer will be executed on the next
            available day.

          - ``allow`` (default: ``None``). A callback which receives a
            `datetime.date`` instance and returns ``True`` if the date is
            allowed for timers or else returns ``False``

          - ``tzdata`` which can be either ``None`` (default), a ``pytz``
            instance or a ``data feed`` instance.

            ``None``: ``when`` is interpreted at face value (which translates
            to handling it as if it where UTC even if it's not)

            ``pytz`` instance: ``when`` will be interpreted as being specified
            in the local time specified by the timezone instance.

            ``data feed`` instance: ``when`` will be interpreted as being
            specified in the local time specified by the ``tz`` parameter of
            the data feed instance.

            **Note**: If ``when`` is either ``SESSION_START`` or
              ``SESSION_END`` and ``tzdata`` is ``None``, the 1st *data feed*
              in the system (aka ``self.data0``) will be used as the reference
              to find out the session times.

        Return Value:

          - The created timer

        '''
        return self._add_timer(when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata)
    
    def _check_timers(self, runstrats, dt0):
        if dt0:
            for t in self._pretimers:
                if not t.check(dt0):
                    continue
                print("_check_timer trigger", dt0)
                for strat in runstrats:
                    strat.notify_timer(dt0)

            for _t in self._mcstimers: # mcstimers: metricstimer
                self.notify_timer()

# ------------------------------------------------------------------ data  --------------------------------------------------------------

    def adddata(self, *args, dmaster=False): # dmaster not dataclone
        '''
        Adds a ``Data Feed`` instance to the mix.

        If ``name`` is not None it will be put into ``data._name`` which is
        meant for decoration/plotting purposes.
        '''
        for _d in args:
            self.datas.append(_d)

        if dmaster:
            # add default datamaster
            datamaster = self.store.get_feed()
            self.datas.insert(0, datamaster)

    def resampledata(self, **kwargs):
        '''
        Adds a ``Data Feed`` to be resample by the system

        If ``name`` is not None it will be put into ``data._name`` which is
        meant for decoration/plotting purposes.

        Any other kwargs like ``timeframe``, ``compression``, ``todate`` which
        are supported by the resample filter will be passed transparently
        '''
        data0 = self.store.get_feed()

        dataname = data0.clone() # DataClone
        dataname.resample(**kwargs)
        self.adddata(dataname)
        return dataname

# ---------------------------------------------------------------- control ------------------------------------------------------------

    def addstore(self, store: str="local", **kwargs):
        '''Adds an ``Store`` instance to the if not already present'''
        storecls = _stores[store]
        self.store = storecls(client_id=self.p.client_id, timeout=self.p.timeout, **kwargs)
    
    def addcontrol(self, lock_days, sizer_name: str="fixed", **kwargs):
        '''Adds a TaskPlan instance to the system'''
        self.pnc = Pnc(lock_days, sizer_name, **kwargs)

# ---------------------------------------------------------------- strategy ------------------------------------------------------------

    def addstrategy(self, strategy, *args, **kwargs):
        '''
        Adds a ``Strategy`` class to the mix for a single pass run.
        Instantiation will happen during ``run`` time.

        args and kwargs will be passed to the strategy as they are during
        instantiation.
        '''
        self.strats.append([(strategy, args, kwargs)])

    def addindicator(self, indcls, *args, **kwargs): # signal is indicator
        '''
        Adds an ``Indicator`` class to the mix. Instantiation will be done at
        ``run`` time in the passed strategies
        '''
        self.indicators.append((indcls, args, kwargs))
    
    def addobserver(self, multi, obscls, *args, **kwargs):
        '''
        Adds an ``Observer`` class to the mix. Instantiation will be done at
        ``run`` time
        multi: bool
        '''
        self.observers.append((multi, obscls, args, kwargs))

    def signal_strategy(self, stratcls, *args, **kwargs):
        '''Adds a SignalStrategy subclass which can accept signals'''
        self._signal_strat = (stratcls, args, kwargs)

    def add_signal(self, sigtype, sigcls, *sigargs, **sigkwargs):
        '''Adds a signal to the system which will be later added to a
        ``SignalStrategy``'''
        self.signals.append((sigtype, sigcls, sigargs, sigkwargs))

    def signal_accumulate(self, onoff):
        '''If signals are added to the system and the ``accumulate`` value is
        set to True, entering the market when already in the market, will be
        allowed to increase a position'''
        self._signal_accumulate = onoff

# ------------------------------------------------------------------ callback --------------------------------------------------------------

    def addstorecb(self, callback):
        '''Adds a callback to get messages which would be handled by the
        notify_store method

        The signature of the callback must support the following:

          - callback(msg, \*args, \*\*kwargs)

        The actual ``msg``, ``*args`` and ``**kwargs`` received are
        implementation defined (depend entirely on the *data/broker/store*) but
        in general one should expect them to be *printable* to allow for
        reception and experimentation.
        '''
        self.storecbs.append(callback)

    def optcallback(self, cb):
        '''
        Adds a *callback* to the list of callbacks that will be called with the
        optimizations when each of the strategies has been run

        The signature: cb(strategy)
        '''
        self.optcbs.append(cb)

# ---------------------------------------------------------------- run -------------------------------------------------------------------
    
    def __call__(self, iterstrat):
        '''
        Used during optimization to pass the cerebro over the multiprocesing
        module without complains
        '''
        return self.runstrategies(iterstrat)

    def _next_stid(self, run_kwargs):
        # self.stcount = itertools.count(0)
        # return next(self.stcount)
        extra_info = [f"RunKwargs: {json.dumps(run_kwargs, cls=CustomJSONEncoder, indent=2)}"]
        for strat in self.strats:
            sig_type, args, kwargs = strat[0]
            _info = f" {sig_type.__class__.__name__}({json.dumps(kwargs)})"
            extra_info.append(_info)
        self.u_id = ','.join(extra_info)

    @consume_time
    def run(self, **kwargs):
        '''The core method to perform backtesting. Any ``kwargs`` passed to it
        will affect the value of the standard parameters ``Cerebro`` was
        instantiated with.

        If ``cerebro`` has not datas the method will immediately bail out.

        It has different return values:

          - For No Optimization: a list contanining instances of the Strategy
            classes added with ``addstrategy``

          - For Optimization: a list of lists which contain instances of the
            Strategy classes added with ``addstrategy``
        '''
        self._next_stid(kwargs) 

        # Prepare feed
        print("cerebro run data start")
        self.adddata(dmaster=True)
        
        for data in self.datas:
            data._start(**kwargs)

        print("cerebro run data._start finish")

        # Prepare timers
        if not self._pretimers:
            self._pretimers.append(Timer(when=Session.SESSION_START)) # T + 1 policy to update on 9:30 
        for timer in itertools.chain(self._pretimers, self._mcstimers):
            timer.start(self.datas[0]) # preprocess tzdata if needed

        self.runstrats = list()
        self.runwriters = list()
        self._event_stop = False  # Stop is requested

        if not self.store:
            return []  # nothing can be run
        
        # update params with run kwargs
        pkeys = self.params._getkeys()
        for key, val in kwargs.items():
            if key in pkeys:
                setattr(self.params, key, val)

        # Add the system default writer if requested
        if self.p.writer is True:
            wr = WriterFile(out=kwargs["out"], csv=True)
            self.runwriters.append(wr)

        # Instantiate any other writers
        for wrcls, wrargs, wrkwargs in self.writers:
            wr = wrcls(*wrargs, **wrkwargs)
            self.runwriters.append(wr)

        # Write down if any writer wants the full csv output
        self.writers_csv = any(map(lambda x: x.p.csv, self.runwriters))

        if self.writers_csv:
            wheaders = list()
            for data in self.datas:
                if data.csv:
                    wheaders.extend(data.getwriterheaders())

            for writer in self.runwriters:
                if writer.p.csv:
                    writer.addheaders(wheaders)

        # signal strategy
        if self.signals:  # allow processing of signals
            signalst, sargs, skwargs = self._signal_strat
            if signalst is None:
                # Try to see if the 1st regular strategy is a signal strategy
                try:
                    signalst, sargs, skwargs = self.strats.pop(0)
                except IndexError:
                    pass  # Nothing there
                else:
                    if not isinstance(signalst, SignalStrategy):
                        # no signal ... reinsert at the beginning
                        self.strats.insert(0, (signalst, sargs, skwargs))
                        signalst = None  # flag as not presetn

            if not signalst:  # recheck
                # Still None, create a default one
                signalst, sargs, skwargs = SignalStrategy, tuple(), dict()

            # Add the signal strategy
            self.addstrategy(signalst,
                             _accumulate=self._signal_accumulate,
                             signals=self.signals,
                             *sargs,
                             **skwargs)

        # strategy cartesian product
        print("cerebro run runstrategies")
        iterstrats = itertools.product(*self.strats)
        for iterstrat in iterstrats: # let's skip process "spawning" when mp
            runstrat = self.runstrategies(iterstrat, **kwargs)
            self.runstrats.append(runstrat)
            for cb in self.optcbs:
                cb(runstrat)  # callback receives finished strategy

        if self.p.isplot:
            dstrat = self.runningstrats[0]
            self.plot(self, num_data=len(self.datas), 
                            num_ind=len(dstrat._lineiterators[0]), 
                            num_obs=len(dstrat._lineiterators[2]),
                            out=kwargs.get("out", ""), freq=kwargs.get("freq", "D")) 
        
        # metrics
        # return {"sharpe": np.random.randn(), "pnl": np.random.randn()}

     
    def runstrategies(self, iterstrat, **kwargs):
        '''
        Internal method invoked by ``run``` to run a set of strategies
        '''
        self.runningstrats = runstrats = list()
        for stratcls, sargs, skwargs in iterstrat:
            sargs = self.datas + list(sargs)
            try:
                strat = stratcls(*sargs, **skwargs)
            except StrategySkipError:
                continue  # do not add strategy to the mix
            runstrats.append(strat)

        if runstrats:
            for _, strat in enumerate(runstrats):
                if self.p.stdstats: # ('timeframe', bt.TimeFrame.Days) ('compression', None),
                    strat._addobserver(False, observers.Broker, barplot=True)
                    strat._addobserver(False, observers.Trades, barplot=True)
                    strat._addobserver(False, observers.BuySell, barplot=True)
                    strat._addobserver(False, observers.DrawDown, barplot=True)
                    strat._addobserver(False, observers.DrawDownLength, barplot=True)
                    strat._addobserver(False, observers.TimeReturn, barplot=True)
                    strat._addobserver(False, observers.Benchmark, barplot=True)

                for multi, obscls, obsargs, obskwargs in self.observers:
                    strat._addobserver(multi, obscls, *obsargs, **obskwargs)

                for indcls, indargs, indkwargs in self.indicators:
                    strat._addindicator(indcls, *indargs, **indkwargs)
        
                for writer in self.runwriters:
                    if writer.p.csv:
                        writer.addheaders(strat.getwriterheaders())
                
                strat._start(self.p.savemem, **kwargs)
                
            for writer in self.runwriters:
                writer.start()

            self._runnext(runstrats)

            self.stop_writers(runstrats) 
            print("stop writer")     

            for strat in runstrats:
                strat._stop()
            print("strat stop")

        for data in self.datas:
            data.stop()
        print("feed data stop")

        return runstrats

    # @profile
    def _runnext(self, runstrats):
        '''
        Actual implementation of run in full next mode. All objects have its
        ``next`` method invoke on each data arrival
        '''
        d0ret = True
        datas = sorted(self.datas,
                       key=lambda x: (x._timeframe, x._compression))

        rsonly = [i for i, x in enumerate(datas) if x.resampling]
        onlyresample = len(datas) == len(rsonly)
        noresample = not rsonly

        while d0ret:
            if self._event_stop:  # stop if requested
                return

            drets = []
            for d in datas:
                drets.append(d.next())
            
            d0ret = any((dret for dret in drets))

            if d0ret:
                dts = []
                for i, ret in enumerate(drets):
                    dts.append(datas[i].datetime[0] if ret else None)
                # print("dts ", dts)

                if not drets[0]: # last for resamplefilter
                    for d in datas: 
                        d._last()
                    d0ret = False # alias break

                self._check_timers(runstrats, dts[0]) # notify_timer to control next

                for strat in runstrats: # to process nan in indicator due to forward
                    strat._next()
                    
                self._next_writers(runstrats)
        return
                
# ---------------------------------------------------------------------- writer ------------------------------------------------------------

    def addwriter(self, wrtcls, *args, **kwargs):
        '''Adds an ``Writer`` class to the mix. Instantiation will be done at
        ``run`` time in cerebro
        '''
        self.writers.append((wrtcls, args, kwargs))

    def _next_writers(self, runstrats):
        if not self.runwriters:
            return

        if self.writers_csv:
            wvalues = list()
            for data in self.datas:
                if data.csv:
                    wvalues.extend(data.getwritervalues())

            for strat in runstrats:
                wvalues.extend(strat.getwritervalues())

            for writer in self.runwriters:
                if writer.p.csv:
                    writer.addvalues(wvalues)
                    writer.next()

    def stop_writers(self, runstrats):
        cerebroinfo = OrderedDict()
        datainfos = OrderedDict()

        for i, data in enumerate(self.datas):
            datainfos['Data%d' % i] = data.getwriterinfo()

        cerebroinfo['Datas'] = datainfos

        stratinfos = dict()
        for strat in runstrats:
            stname = strat.__class__.__name__
            stratinfos[stname] = strat.getwriterinfo()

        cerebroinfo['Strategies'] = stratinfos

        for writer in self.runwriters:
            # writer.writedict(dict(Cerebro=cerebroinfo))
            writer.stop()
    
    def runstop(self):
        '''If invoked from inside a strategy or anywhere else, including other
        threads the execution will stop as soon as possible.'''
        self._event_stop = True  # signal a stop has been requested

# ---------------------------------------------------------------------- writer ------------------------------------------------------------
    
    def collector_timer(self, when,
                  offset=datetime.timedelta(), repeat=datetime.timedelta(),
                  weekdays=[], weekcarry=False,
                  monthdays=[], monthcarry=True,
                  allow=None,
                  tzdata=None):
        """
            timer to collector metrics such as CPU Memory
        """
        _timer = self._add_timer(when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata)
        self._mtimers.append(_timer)

    def notify_timer(self): # connect to monitor system
        '''Receives a timer notification where ``timer`` is the timer which was
        returned by ``add_timer``, and ``when`` is the calling time. ``args``
        and ``kwargs`` are any additional arguments passed to ``add_timer``

        The actual ``when`` time can be later, but the system may have not be
        able to call the timer before. This value is the timer value and no the
        system time.
        '''
        pass
    
    def plot(self, num_data=0, num_ind=1, num_obs=1, source="", freq="D", **kwargs):
        '''
        Plots the strategies inside cerebro

        If ``plotter`` is None a default ``Plot`` instance is created and
        ``kwargs`` are passed to it during instantiation.

        ``numfigs`` split the plot in the indicated number of charts reducing
        chart density if wished

        ``iplot``: if ``True`` and running in a ``notebook`` the charts will be
        displayed inline

        ``data_path``: str where save feed strategy indicator observer data
        
        ``freq``: default D  which frequency to plot data

        ``width``: in inches of the saved figure

        ``height``: in inches of the saved figure

        ``dpi``: quality in dots per inches of the saved figure

        ``tight``: only save actual content and not the frame of the figure
        '''
        self._plot.plot(num_data=num_data, num_ind=num_ind, num_obs=num_obs, source=source, freq=freq, **kwargs)
