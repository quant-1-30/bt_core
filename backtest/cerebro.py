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

import datetime

import itertools
import multiprocessing
from pytz import tzparse

from backtest.metabase import MetaParams, with_metaclass
from backtest import observers
from backtest.strategy import Strategy, SignalStrategy
from backtest.sizers import NoSizer
from .timer import Timer


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

      - ``quicknotify`` (default: ``False``)

        Broker notifications are delivered right before the delivery of the
        *next* prices. For backtesting this has no implications, but with live
        brokers a notification can take place long before the bar is
        delivered. When set to ``True`` notifications will be delivered as soon
        as possible (see ``qcheck`` in live feeds)

        Set to ``False`` for compatibility. May be changed to ``True``

    '''
    params = (
        ('maxcpus', 1),
        ('stdstats', True),
        ('writer', False),
        ('tz', None),
        ('quicknotify', False),
    )

    def __init__(self):

        self.store = None
        self.datas = list()
        self.strats = list()
        
        self.observers = list()
        self.analyzers = list()
        self.indicators = list()
        self.sizer = NoSizer() # default sizer
        self.writers = list()

        self._dooptimize = False
        self._pretimers = list()
        self.storecbs = list()

    def adddata(self, data, init=False):
        '''
        Adds a ``Data Feed`` instance to the mix.

        If ``name`` is not None it will be put into ``data._name`` which is
        meant for decoration/plotting purposes.
        '''
        # data._id = next(self._dataid)
        if init:
            self.datas.insert(0, data)
        else:
            self.datas.append(data)

    def resampledata(self, dataname, name=None, **kwargs):
        '''
        Adds a ``Data Feed`` to be resample by the system

        If ``name`` is not None it will be put into ``data._name`` which is
        meant for decoration/plotting purposes.

        Any other kwargs like ``timeframe``, ``compression``, ``todate`` which
        are supported by the resample filter will be passed transparently
        '''
        if any(dataname is x for x in self.datas):
            dataname = dataname.clone()

        dataname.resample(**kwargs)
        self.adddata(dataname, name=name)
        self._doreplay = True

    def addstore(self, store):
        '''Adds an ``Store`` instance to the if not already present'''
        store.start()
        self.store = store 
        self.adddata(store._feed, init=True) 
 
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

    def addwriter(self, wrtcls, *args, **kwargs):
        '''Adds an ``Writer`` class to the mix. Instantiation will be done at
        ``run`` time in cerebro
        '''
        self.writers.append((wrtcls, args, kwargs))

# -------------------------------------------------timer-----------------------------------------------------
    
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
            tz = tzparse(tz)

    def _add_timer(self, owner, when,
                   offset=datetime.timedelta(), repeat=datetime.timedelta(),
                   weekdays=[], weekcarry=False,
                   monthdays=[], monthcarry=True,
                   allow=None,
                   tzdata=None, strats=False, cheat=False,
                   *args, **kwargs):
        '''Internal method to really create the timer (not started yet) which
        can be called by cerebro instances or other objects which can access
        cerebro'''

        timer = Timer(
            tid=len(self._pretimers),
            owner=owner, strats=strats,
            when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata, cheat=cheat,
            *args, **kwargs
        )

        self._pretimers.append(timer)
        return timer

    def add_timer(self, when,
                  offset=datetime.timedelta(), repeat=datetime.timedelta(),
                  weekdays=[], weekcarry=False,
                  monthdays=[], monthcarry=True,
                  allow=None,
                  tzdata=None,
                  *args, **kwargs):
        '''
        Schedules a timer to invoke ``notify_timer``

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

          - ``*args``: any extra args will be passed to ``notify_timer``

          - ``**kwargs``: any extra kwargs will be passed to ``notify_timer``

        Return Value:

          - The created timer

        '''
        return self._add_timer(
            owner=self, when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata,
            *args, **kwargs)
    
    def _check_timers(self, runstrats, dt0):
        # timers = self._timers if not cheat else self._timerscheat
        for t in self._timers:
            if not t.check(dt0):
                continue

            t.params.owner.notify_timer(t, t.lastwhen, *t.args, **t.kwargs)

            if t.params.strats:
                for strat in runstrats:
                    strat.notify_timer(t, t.lastwhen, *t.args, **t.kwargs)

# -------------------------------------------------analyzer-----------------------------------------------------

    def addanalyzer(self, ancls, *args, **kwargs):
        '''
        Adds an ``Analyzer`` class to the mix. Instantiation will be done at
        ``run`` time
        '''
        self.analyzers.append((ancls, args, kwargs))

    def addobserver(self, obscls, *args, **kwargs):
        '''
        Adds an ``Observer`` class to the mix. Instantiation will be done at
        ``run`` time
        '''
        self.observers.append((False, obscls, args, kwargs))

    def addobservermulti(self, obscls, *args, **kwargs):
        '''
        Adds an ``Observer`` class to the mix. Instantiation will be done at
        ``run`` time

        It will be added once per "data" in the system. A use case is a
        buy/sell observer which observes individual datas.

        A counter-example is the CashValue, which observes system-wide values
        '''
        self.observers.append((True, obscls, args, kwargs))
    
# -------------------------------------------------notify-----------------------------------------------------
    
    def notify_timer(self, timer, when, *args, **kwargs):
        '''Receives a timer notification where ``timer`` is the timer which was
        returned by ``add_timer``, and ``when`` is the calling time. ``args``
        and ``kwargs`` are any additional arguments passed to ``add_timer``

        The actual ``when`` time can be later, but the system may have not be
        able to call the timer before. This value is the timer value and no the
        system time.
        '''
        pass

# -------------------------------------------------strategy-----------------------------------------------------
    
    def addsizer(self, sizercls, *args, **kwargs):
        '''Adds a ``Sizer`` class (and args) which is the default sizer for any
        strategy added to cerebro
        '''
        self.sizer = (sizercls, args, kwargs)

    def addindicator(self, indcls, *args, **kwargs): # signal is indicator
        '''
        Adds an ``Indicator`` class to the mix. Instantiation will be done at
        ``run`` time in the passed strategies
        '''
        self.indicators.append((indcls, args, kwargs))

    def addstrategy(self, strategy, *args, **kwargs):
        '''
        Adds a ``Strategy`` class to the mix for a single pass run.
        Instantiation will happen during ``run`` time.

        args and kwargs will be passed to the strategy as they are during
        instantiation.
        '''
        self.strats.append([(strategy, args, kwargs)])

    def __call__(self, iterstrat):
        '''
        Used during optimization to pass the cerebro over the multiprocesing
        module without complains
        '''
        return self.runstrategies(iterstrat)

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
        self.runstrats = list()
        self._event_stop = False  # Stop is requested

        if not self.store:
            return []  # nothing can be run

        # update params with run kwargs
        pkeys = self.params._getkeys()
        for key, val in kwargs.items():
            if key in pkeys:
                setattr(self.params, key, val)

        if self.p.maxcpus == 1:
            # If no optimmization is wished ... or 1 core is to be used / skipping spawn
            for iterstrat in self.strats:
                runstrat = self.runstrategies(iterstrat)
                self.runstrats.append(runstrat)
        else:
            pool = multiprocessing.Pool(self.p.maxcpus or None)
            for r in pool.imap(self, self.strats): # __call__
                self.runstrats.append(r)

            pool.close()

            if self.p.optdatas and self._dopreload and self._dorunonce:
                for data in self.datas:
                    data.stop()
        return self.runstrats
    
    def runstrategies(self, iterstrat):
        '''
        Internal method invoked by ``run``` to run a set of strategies
        '''
        self.runningstrats = runstrats = list()

        for data in self.datas:
            data.reset()
            data._start()

        # initialize strategy
        stratcls, sargs, skwargs = iterstrat
        sargs = self.datas + list(sargs)
        strat = stratcls(*sargs, **skwargs)

        for indcls, indargs, indkwargs in self.indicators:
            strat._addindicator(indcls, *indargs, **indkwargs)

        for multi, obscls, obsargs, obskwargs in self.observers:
            strat._addobserver(multi, obscls, *obsargs, **obskwargs)

        for ancls, anargs, ankwargs in self.analyzers:
            strat._addanalyzer(ancls, *anargs, **ankwargs)
        
        if self.p.stdstats:
            strat._addobserver(False, observers.Broker)
            strat._addobserver(True, observers.BuySell, barplot=True)
            strat._addobserver(False, observers.DataTrades)

        strat._start() # start strategy

        # Prepare timers
        for timer in self._pretimers:
            # preprocess tzdata if needed
            timer.start(self.datas[0])
            self._timers.append(timer)

        self._runnext(runstrats)

        for strat in runstrats:
            strat._stop()

        for data in self.datas:
            data.stop()

        self.store.stop()
        return runstrats

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

                if onlyresample or noresample:
                    dt0 = min((d for d in dts if d is not None))
                else:
                    dt0 = min((d for i, d in enumerate(dts)
                               if d is not None and i not in rsonly))
                dmaster = datas[dts.index(dt0)]

                # retry to get a bar if not returned
                for i, ret in enumerate(drets):
                    if ret:
                        continue
                    d = datas[i]
                    if d.next(datamaster=dmaster):
                        dts[i] = d.datetime[0]
                    else:
                        pass

                for i, dti in enumerate(dts):
                    if dti is not None:
                        di = datas[i]
                        if dti > dt0:
                            di.rewind()  # cannot deliver yet


            if self._event_stop:  # stop if requested
                return

            if d0ret:  # bars produced by data or filters
                self._check_timers(runstrats, dt0) # notify_timer to control next
                for strat in runstrats:
                    strat._next()

                    if self._event_stop:  # stop if requested
                        return

                    self._next_writers(runstrats)

        if self._event_stop:  # stop if requested
            return
        
    def runstop(self):
        '''If invoked from inside a strategy or anywhere else, including other
        threads the execution will stop as soon as possible.'''
        self._event_stop = True  # signal a stop has been requested

# -------------------------------------------------plot-----------------------------------------------------
    
    def plot(self, plotter=None, numfigs=1, iplot=True, start=None, end=None,
             width=16, height=9, dpi=300, tight=True, use=None,
             **kwargs):
        '''
        Plots the strategies inside cerebro

        If ``plotter`` is None a default ``Plot`` instance is created and
        ``kwargs`` are passed to it during instantiation.

        ``numfigs`` split the plot in the indicated number of charts reducing
        chart density if wished

        ``iplot``: if ``True`` and running in a ``notebook`` the charts will be
        displayed inline

        ``use``: set it to the name of the desired matplotlib backend. It will
        take precedence over ``iplot``

        ``start``: An index to the datetime line array of the strategy or a
        ``datetime.date``, ``datetime.datetime`` instance indicating the start
        of the plot

        ``end``: An index to the datetime line array of the strategy or a
        ``datetime.date``, ``datetime.datetime`` instance indicating the end
        of the plot

        ``width``: in inches of the saved figure

        ``height``: in inches of the saved figure

        ``dpi``: quality in dots per inches of the saved figure

        ``tight``: only save actual content and not the frame of the figure
        '''
        if self._exactbars > 0:
            return

        if not plotter:
            from . import plot
            # if self.p.oldsync:
            #     plotter = plot.Plot_OldSync(**kwargs)
            # else:
            #     plotter = plot.Plot(**kwargs)
            # plotter = plot.Plot(**kwargs)
            plotter = plot.Plot_OldSync(**kwargs)

        figs = []
        for stratlist in self.runstrats:
            for si, strat in enumerate(stratlist):
                rfig = plotter.plot(strat, figid=si * 100,
                                    numfigs=numfigs, iplot=iplot,
                                    start=start, end=end, use=use)
                # pfillers=pfillers2)

                figs.append(rfig)

            plotter.show()

        return figs
