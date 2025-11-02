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
from collections import OrderedDict
from pytz import timezone

from . import observers
from .writer import WriterFile
from backtest.metabase import MetaParams, with_metaclass
from backtest.sizers import sizers
from backtest.timer import Timer
from backtest.errors import *
from backtest.stores import _stores


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

        Broker notifications are delivered right before the delivery of the
        *next* prices. For backtesting this has no implications, but with live
        brokers a notification can take place long before the bar is
        delivered. When set to ``True`` notifications will be delivered as soon
        as possible (see ``qcheck`` in live feeds)

        Set to ``False`` for compatibility. May be changed to ``True``

    '''
    params = (
        ('stdstats', True),
        ("cash", 100000),
        ('savemem', 1),
        ('writer', False),
        ("sizer", "fixed"),
        ("store", "bt"),
        ('tz', None),
    )

    def __init__(self):

        self.datas = list()
        self.strats = list()
        
        self.observers = list()
        self.indicators = list()
        self.writers = list()
        self.storecbs = list()
        self.optcbs = list()  # holds a list of callbacks for opt strategies
        
        self.store = None

        self._pretimers = list()

    def set_cash(self, *args, **kwargs):
        self.cash = kwargs.pop("cash", self.p.cash)

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

    def addwriter(self, wrtcls, *args, **kwargs):
        '''Adds an ``Writer`` class to the mix. Instantiation will be done at
        ``run`` time in cerebro
        '''
        self.writers.append((wrtcls, args, kwargs))

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
        return self._add_timer(
            owner=self, when=when, offset=offset, repeat=repeat,
            weekdays=weekdays, weekcarry=weekcarry,
            monthdays=monthdays, monthcarry=monthcarry,
            allow=allow,
            tzdata=tzdata)
    
    def _check_timers(self, runstrats, dt0):
        # timers = self._timers if not cheat else self._timerscheat
        for t in self._pretimers:
            if not t.check(dt0):
                continue

            # via store notify_timer
            t.params.owner.notify_timer(t, t.lastwhen, *t.args, **t.kwargs) 

            if t.params.strats:
                for strat in runstrats:
                    strat.notify_timer(t, t.lastwhen, *t.args, **t.kwargs)

# ------------------------------------------------------------------ store --------------------------------------------------------------

    def addstore(self, *args, **kwargs):
        '''Adds an ``Store`` instance to the if not already present'''
        storecls = _stores[kwargs.pop("store", self.p.store)]
        # import pdb; pdb.set_trace
        self.store = storecls(*args, **kwargs)
        _feed = self.store.get_feed()
        self.datas.append(_feed)
 
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

# ---------------------------------------------------------------- strategy ------------------------------------------------------------

    def optcallback(self, cb):
        '''
        Adds a *callback* to the list of callbacks that will be called with the
        optimizations when each of the strategies has been run

        The signature: cb(strategy)
        '''
        self.optcbs.append(cb)

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

    def addsizer(self, *args, **kwargs):
        '''Adds a ``Sizer`` class (and args) which is the default sizer for any
        strategy added to cerebro
        '''
        sizer_type = kwargs.pop("sizer", self.p.sizer)
        self.sizer = sizers[sizer_type](*args, **kwargs)

    def _init_stcount(self):
        self.stcount = itertools.count(0)

    # unique id for each strategy
    def _next_stid(self): 
        return next(self.stcount)
    
# ---------------------------------------------------------------- run-------------------------------------------------------------------

    def __call__(self, iterstrat):
        '''
        Used during optimization to pass the cerebro over the multiprocesing
        module without complains
        '''
        return self.runstrategies(iterstrat)
    
    def _start(self, *args, **kwargs):
        self.set_cash(*args, **kwargs) # pop cash
        self.addstore(*args, **kwargs) # pop client_id fromdate todate 
        self.addsizer(*args, **kwargs)

    def run(self, *args, **kwargs):
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
        self._start(*args, **kwargs)

        # initialize feed
        for data in self.datas:
            data._start(**kwargs)

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
            wr = WriterFile()
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

        iterstrats = itertools.product(*self.strats)
        for iterstrat in iterstrats: # let's skip process "spawning" when mp
            runstrat = self.runstrategies(iterstrat, **kwargs)
            self.runstrats.append(runstrat)
            for cb in self.optcbs:
                cb(runstrat)  # callback receives finished strategy
    
        return self.runstrats
     
    def runstrategies(self, iterstrat, **kwargs):
        '''
        Internal method invoked by ``run``` to run a set of strategies
        '''
        self._init_stcount()

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
                # if self.p.stdstats:
                #     strat._addobserver(False, observers.Broker)
                #     strat._addobserver(True, observers.BuySell, barplot=True)
                #     strat._addobserver(False, observers.Trades)

                for multi, obscls, obsargs, obskwargs in self.observers:
                    strat._addobserver(multi, obscls, *obsargs, **obskwargs)

                for indcls, indargs, indkwargs in self.indicators:
                    strat._addindicator(indcls, *indargs, **indkwargs)
        
                for writer in self.runwriters:
                    if writer.p.csv:
                        writer.addheaders(strat.getwriterheaders())
                
                strat._start(**kwargs)
                strat.qbuffer(savemem=self.p.savemem)
                
            for writer in self.writers:
                writer.start()

            # Prepare timers
            self._timers = []
            self._timerscheat = []
            for timer in self._pretimers:
                # preprocess tzdata if needed
                timer.start(self.datas[0])

                if timer.params.cheat:
                    self._timerscheat.append(timer)
                else:
                    self._timers.append(timer) 

            self._runnext(runstrats)

            for strat in runstrats:
                strat._stop()
            print("strat stop")

        for data in self.datas:
            data.stop()
        print("feed data stop")

        self.stop_writers(runstrats) 

        print("stop writer")      

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
            print("dOret ", d0ret)

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

            if d0ret:  # bars produced by data or filters
                # self._check_timers(runstrats, dt0) # notify_timer to control next
                for strat in runstrats:
                    strat._next()

                    if self._event_stop:  # stop if requested
                        return
                    
                    self._next_writers(runstrats)
                
        self._next_writers(runstrats)
        
    def runstop(self):
        '''If invoked from inside a strategy or anywhere else, including other
        threads the execution will stop as soon as possible.'''
        self._event_stop = True  # signal a stop has been requested

# ---------------------------------------------------------------------- writer ------------------------------------------------------------

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
            writer.writedict(dict(Cerebro=cerebroinfo))
            writer.stop()
    
# ---------------------------------------------------------------------- plot ------------------------------------------------------------
    
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
