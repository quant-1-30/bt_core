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
import pprint as pp
import numpy as np
from collections import OrderedDict

import backtest as bt
from backtest.dataseries import TimeFrame
from backtest.metabase import with_metaclass, MetaParams, findowner
from backtest.utils.dt_cmp import get_dt_cmpkey


class MetaAnalyzer(MetaParams):
    def donew(cls, *args, **kwargs):
        '''
        Intercept the strategy parameter
        '''
        # Create the object and set the params in place
        _obj, args, kwargs = super(MetaAnalyzer, cls).donew(*args, **kwargs)

        _obj._children = list()

        # inherit from strategy
        _obj._owner = strategy = findowner(_obj, bt.Strategy)
        _obj.datas = strategy.datas
       
        # setup shm for analyzers
        _obj.log_shm = strategy.log_shm
        _obj.shm = strategy.shm_chan

        _obj._parent = findowner(_obj, Analyzer)
        # Register with a master observer if created inside one
        masterobs = findowner(_obj, bt.Observer)

        if masterobs is not None:
            masterobs._register_analyzer(_obj)

        # For each data add aliases: for first data: data and data0
        if _obj.datas:
            _obj.data = data = _obj.datas[0] # _clock

            for l, line in enumerate(data.lines):
                linealias = data._getlinealias(l)
                if linealias:
                    setattr(_obj, 'data_%s' % linealias, line)
                setattr(_obj, 'data_%d' % l, line)

            for d, data in enumerate(_obj.datas):
                setattr(_obj, 'data%d' % d, data)

                for l, line in enumerate(data.lines):
                    linealias = data._getlinealias(l)
                    if linealias:
                        setattr(_obj, 'data%d_%s' % (d, linealias), line)
                    setattr(_obj, 'data%d_%d' % (d, l), line)

        _obj.create_analysis()

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaAnalyzer, cls).dopostinit(_obj, *args, **kwargs)

        if _obj._parent is not None:
            _obj._parent._register(_obj) # analyzer with analyzer

        # Register to shm
        shm_id = _obj.shm.register_consumer()
        _obj.shm_id = shm_id
        return _obj, args, kwargs


class Analyzer(with_metaclass(MetaAnalyzer, object)):
    '''Analyzer base class. All analyzers are subclass of this one

    An Analyzer instance operates in the frame of a strategy and provides an
    analysis for that strategy.

    Automagically set member attributes:

      - ``self.strategy`` (giving access to the *strategy* and anything
        accessible from it)

      - ``self.datas[x]`` giving access to the array of data feeds present in
        the the system, which could also be accessed via the strategy reference

      - ``self.data``, giving access to ``self.datas[0]``

      - ``self.dataX`` -> ``self.datas[X]``

      - ``self.dataX_Y`` -> ``self.datas[X].lines[Y]``

      - ``self.dataX_name`` -> ``self.datas[X].name``

      - ``self.data_name`` -> ``self.datas[0].name``

      - ``self.data_Y`` -> ``self.datas[0].lines[Y]``

    This is not a *Lines* object, but the methods and operation follow the same
    design

      - ``__init__`` during instantiation and initial setup

      - ``start`` / ``stop`` to signal the begin and end of operations

      - ``prenext`` / ``nextstart`` / ``next`` family of methods that follow
        the calls made to the same methods in the strategy

    The mode of operation is open and no pattern is preferred. As such the
    analysis can be generated with the ``next`` calls, at the end of operations
    during ``stop`` and even with a single method like ``notify_trade``

    The important thing is to override ``get_analysis`` to return a *dict-like*
    object containing the results of the analysis (the actual format is
    implementation dependent)

    '''
    csv = True

    def _register(self, child):
        self._children.append(child)

    def _start(self):
        for child in self._children:
            child._start()

        self.start()

    def start(self):
        '''Invoked to indicate the start of operations, giving the analyzer
        time to setup up needed things'''
        pass

    def _prenext(self):
        for child in self._children:
            child._prenext()

        self.prenext()

    def _nextstart(self):
        for child in self._children:
            child._nextstart()

        self.nextstart() 

    def _next(self):
        for child in self._children:
            child._next()

        self.next()

    def prenext(self):
        '''Invoked for each prenext invocation of the strategy, until the minimum
        period of the strategy has been reached

        The default behavior for an analyzer is to invoke ``next``
        '''
        self.next()

    def nextstart(self):
        '''Invoked exactly once for the nextstart invocation of the strategy,
        when the minimum period has been first reached
        '''
        self.next()
    
    def next(self):
        '''Invoked for each next invocation of the strategy, once the minum
        preiod of the strategy has been reached'''
        pass

    def _stop(self):
        for child in self._children:
            child._stop()

        self.stop()

    def stop(self):
        '''Invoked to indicate the end of operations, giving the analyzer
        time to shut down needed things'''
        pass

    def create_analysis(self):
        '''Meant to be overriden by subclasses. Gives a chance to create the
        structures that hold the analysis.

        The default behaviour is to create a ``OrderedDict`` named ``rets``
        '''
        self.rets = OrderedDict()

    def get_analysis(self):
        '''Returns a *dict-like* object with the results of the analysis

        The keys and format of analysis results in the dictionary is
        implementation dependent.

        It is not even enforced that the result is a *dict-like object*, just
        the convention

        The default implementation returns the default OrderedDict ``rets``
        created by the default ``create_analysis`` method

        '''
        return self.rets

    def get_shm_events(self):
        '''Returns the events from the shared memory channel for this analyzer'''
        events  = self.shm.drain_events(self.shm_id)
        return events

    def print(self, *args, **kwargs):
        '''Prints the results returned by ``get_analysis`` via a standard
        ``Writerfile`` object, which defaults to writing things to standard
        output
        '''
        pass

    def pprint(self, *args, **kwargs):
        '''Prints the results returned by ``get_analysis`` using the pretty
        print Python module (*pprint*)
        '''
        pp.pprint(self.get_analysis(), *args, **kwargs)


class MetaTimeFrameAnalyzerBase(Analyzer.__class__):
    def __new__(meta, name, bases, dct):
        # Hack to support original method name
        if '_on_dt_over' in dct:
            dct['on_dt_over'] = dct.pop('_on_dt_over')  # rename method

        return super(MetaTimeFrameAnalyzerBase, meta).__new__(meta, name,
                                                              bases, dct)


class TimeFrameAnalyzerBase(with_metaclass(MetaTimeFrameAnalyzerBase,
                                           Analyzer)):
    params = (
        ('timeframe', TimeFrame.Days),
        ('compression', None),
    )

    def _start(self):
        # Override to add specific attributes
        self.timeframe = self.p.timeframe or self.data._timeframe
        self.compression = self.p.compression or self.data._compression

        self.dtcmp = 0 # boundary
        # self.dtkey = datetime.datetime.min

        super(TimeFrameAnalyzerBase, self)._start()
    
    def _prenext(self):
        for child in self._children:
            child._prenext()

        self.prenext()

    def _nextstart(self):
        for child in self._children:
            child._nextstart()

        self.nextstart()

    def _next(self):
        for child in self._children:
            child._next()

        # if self._dt_over():
        #     self.on_dt_over()
        self.next() 
    
    def notify_timer(self):
        pass

    def on_dt_over(self):
        pass

    def _dt_over(self):
        if self.timeframe == TimeFrame.NoTimeFrame:
            dtcmp = np.iinfo(np.int_).max
        else:
            dt = self._owner._clock.datetime[0] #
            dtcmp = get_dt_cmpkey(dt, self.timeframe, self.compression)

        # if self.dtcmp is None or dtcmp > self.dtcmp:
        if dtcmp > self.dtcmp:
            self.dtcmp, self.dtcmp1 = dtcmp, self.dtcmp
            return True
        return False
