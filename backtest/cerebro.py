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
import itertools
from datetime import timedelta
from pytz import timezone


from .metabase import MetaParams, with_metaclass
from .strategy import Strategy, SignalStrategy
from .sizers import _sizers
from .control.pnc import Pnc
from .timer import Timer, Session, TimerEvent
from .errors import *
from .stores import _stores
from . import analyzers
from .plot import Plot
from .shm import LogRingBuffer
from .utils.wrapper import consume_time
from .utils.encoder import CustomJSONEncoder
from .utils.dt_cmp import get_dt_cmpkey
from .logger import LogConsumerThread


class Cerebro(with_metaclass(MetaParams, object)):
    '''Params:

      - ``maxcpus`` (default: None -> all available cores)

         How many cores to use simultaneously for optimization

      - ``stdstats`` (default: ``True``)

        If True default Analyzers will be added: Broker (Cash and Value),
        Trades and BuySell

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
        ('tz', None),
        ("timeout", 10),
        ('stdstats', True),
        ("isplot", False),
        # log
        ("log_id", "cerebro"),
        ("capacity", 1000000),
        ("fmt", "json"),
        ("output", "/Users/hengxinliu/startup/backtest/tests")
    )

    def __init__(self):
        self.datas = list()
        self.strats = list()
        self.analyzers = list()
        self.indicators = list()
        self.signals = list()
        self._signal_strat = (None, None, None)
        self._signal_accumulate = True
        
        self.optcbs = list()  
        self.storecbs = list()

        self._pretimers = list()
        
        self._plot = Plot()
        
        self.cerebro_id = ""
        self.dtcmp = 0 # dtcmp = np.iinfo(np.int_).max

        # logshm
        self.log_shm = LogRingBuffer(shm_name="log_shm", capacity=self.p.capacity, is_creator=True)
        self.log_background = LogConsumerThread(self.log_shm, log_id=self.p.log_id, fmt=self.p.fmt, output_dir=self.p.output)
 
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
                   offset=timedelta(), repeat=timedelta(),
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
                  offset=timedelta(), repeat=timedelta(),
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

         - ``offset`` which must be a ``timedelta`` instance

           Used to offset the value ``when``. It has a meaningful use in
           combination with ``SESSION_START`` and ``SESSION_END``, to indicated
           things like a timer being called ``15 minutes`` after the session
           start.

          - ``repeat`` which must be a ``timedelta`` instance

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

    # def _dt_over(self, dt, last_dt):
    #     # -Gap Detection to solve missing 14:59 / 9:31 ensure eod
    #     # enum in dt_cmp.pxd | TF_Days = 5
    #     dtcmp = get_dt_cmpkey(dt, 5)
    #     if dtcmp > self.dtcmp:
    #         self.dtcmp = dtcmp
    #         return True
    #     return False
    
    def _dt_over(self, dt0: int, last_dt0: int):
        if last_dt0 and (dt0 - last_dt0 >= 12 * 3600): 
            # -Gap Detection to solve missing 14:59 / 9:31 ensure eod
            print("check timer on_dt_over: ", dt0)
            return True
        return False
    
    def _check_timers(self, runstrats: list, dt0: int, last_dt0: int):
        '''Receives a timer notification where ``timer`` is the timer which was
        returned by ``add_timer``, and ``when`` is the calling time. ``args``
        and ``kwargs`` are any additional arguments passed to ``add_timer``

        The actual ``when`` time can be later, but the system may have not be
        able to call the timer before. This value is the timer value and no the
        system time.
        '''
        if not dt0:
            return
            
        if self._dt_over(dt0, last_dt0):
            print("check timer on_dt_over: ", dt0)
            self._dispatch(runstrats, TimerEvent.EOD, last_dt0)

        # --- Scheduled Timers ---
        # self._pretimers.append(Timer(when=Session.SESSION_START, event_type=0)) 
        for t in self._pretimers:
            if t.check(dt0):
                self._dispatch(runstrats, t.event_type, last_dt0)

    def _dispatch(self, runstrats: list, event_type: int, dts: int):
        for strat in runstrats:
            if event_type == TimerEvent.EOD: # on_dt_over ---> T+1 settlement
                strat.on_dt_over(dts) 

            elif event_type == TimerEvent.METRIC: # log shm
                strat.notify_timer(event_type, dts)

            elif event_type == TimerEvent.RISK: # risk control 
                if hasattr(strat, 'check_risk'):
                    strat.check_risk(dts)

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

# ---------------------------------------------------------------- risk and strategy ------------------------------------------------------------
    
    def addpnc(self, sizer_name: str="fixed", **kwargs):
        '''Adds a TaskPlan instance to the system'''
        self.pnc = Pnc(sizer_name, **kwargs)
    
    def addstore(self, store: str="local", **kwargs):
        '''Adds an ``Store`` instance to the if not already present'''
        storecls = _stores[store]
        self.store = storecls(client_id=self.p.client_id, timeout=self.p.timeout, **kwargs)
    
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
    
    def addanalyzer(self, ancls, *args, **kwargs):
        '''
        Adds an `analyzer` class to the mix. Instantiation will be done at
        ``run`` time
        '''
        self.analyzers.append((obscls, args, kwargs))

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

    def _next_id(self, run_kwargs):
        extra_info = [f"RunKwargs: {json.dumps(run_kwargs, cls=CustomJSONEncoder, indent=2)}"]
        for strat in self.strats:
            sig_type, args, kwargs = strat[0]
            _info = f" {sig_type.__class__.__name__}({json.dumps(kwargs)})"
            extra_info.append(_info)
        self.cerebro_id = ','.join(extra_info)

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
        self.log_background.start()

        self._next_id(kwargs) 

        # Prepare feed
        print("cerebro run data start")
        self.adddata(dmaster=True)
        
        for data in self.datas:
            data._start(**kwargs)

        print("cerebro run data._start finish")

        # timers trigger
        for timer in self._pretimers: # itertools.chain(self._pretimers, self._mcstimers)
            timer.start(self.datas[0]) # preprocess tzdata if needed

        self.runstrats = list()
        self._event_stop = False  # Stop is requested

        if not self.store:
            return []  # nothing can be run
        
        # update params with run kwargs
        pkeys = self.params._getkeys()
        for key, val in kwargs.items():
            if key in pkeys:
                setattr(self.params, key, val)

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

            # Add the signal strategy #  _obj.p.signals
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
        
        # stop log thread and shm
        print("_shutdown")
        self._shutdown()
        # isplot 
        
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
                if self.p.stdstats: 
                    strat._addanalyzer(analyzers.Benchmark) 
                    # strat._addanalyzer(analyzers.Calmar) 
                    strat._addanalyzer(analyzers.DrawDown) 
                    strat._addanalyzer(analyzers.Orders) 
                    strat._addanalyzer(analyzers.PeriodStats) 
                    strat._addanalyzer(analyzers.PyFolio)
                    strat._addanalyzer(analyzers.Returns)
                    strat._addanalyzer(analyzers.SharpeRatio)
                    strat._addanalyzer(analyzers.SQN)
                    strat._addanalyzer(analyzers.TimeReturn) 
                    strat._addanalyzer(analyzers.TradeAnalyzer) 
                    strat._addanalyzer(analyzers.Transactions) 

                for indcls, indargs, indkwargs in self.indicators:
                    strat._addindicator(indcls, *indargs, **indkwargs)
        
                strat._start(self.p.savemem, **kwargs)
                
            self._runnext(runstrats)

            for strat in runstrats:
                strat._stop() # on_dt_over on last_dts
            print("strat stop")

        for data in self.datas:
            data.stop()
        print("feed data stop")

        return runstrats

    def _runnext(self, runstrats):
        '''
        Actual implementation of run in full next mode. All objects have its
        ``next`` method invoke on each data arrival
        '''
        d0ret = True
        datas = sorted(self.datas, key=lambda x: (x._timeframe, x._compression)) # ensure high freq ---> master datas[0]

        while d0ret:
            if self._event_stop:  # stop if requested
                return

            drets = [d.next() for d in datas]
            d0ret = any(drets)

            if d0ret:
                if not drets[0]:
                    for d in datas: 
                        d._last()
                    break  

                dt0 = datas[0].datetime[0]
                if len(datas[0]) > 1:
                    last_dt0 = datas[0].datetime[-1]
                else:
                    last_dt0 = dt0

                self._check_timers(runstrats, dt0, last_dt0)

                for strat in runstrats:
                    strat._next()
        return

# ---------------------------------------------------------------------- plot ------------------------------------------------------------
 
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

# ---------------------------------------------------------------------- exit ------------------------------------------------------------

    def runstop(self):
        '''If invoked from inside a strategy or anywhere else, including other
        threads the execution will stop as soon as possible.'''
        self._event_stop = True  # signal a stop has been requested

    def _shutdown(self):
        self.log_background.stop() 
        self.log_background.join()
        self.log_shm.close()
        self.log_shm.unlink()
        print("Cerebro shutdown complete.")
