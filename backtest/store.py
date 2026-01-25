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
import backtest as bt
from backtest.metabase import MetaParams, with_metaclass, findowner


class MetaStore(MetaParams):
    '''Metaclass to make a metaclassed class a singleton'''
    def __init__(cls, name, bases, dct):
        super(MetaStore, cls).__init__(name, bases, dct)
        cls._singleton = None

    def donew(cls, *args, **kwargs):
        _obj, args, kwargs = super(MetaStore, cls).donew(*args, **kwargs)
        _obj.owner = env =  findowner(_obj, bt.cerebro.Cerebro)
        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStore, cls).dopostinit(_obj, *args, **kwargs)
        
        _obj._orderspending = list()    
        _obj._tradespending = list() 

        _obj._start(*args, **kwargs) 
        return _obj, args, kwargs

    def __call__(cls, *args, **kwargs):
        if cls._singleton is None:
            cls._singleton = (
                super(MetaStore, cls).__call__(*args, **kwargs))
        return cls._singleton


class Store(with_metaclass(MetaStore, object)):
    '''Base class for all Stores'''

    _singleton = None
    
    # to ensure metaclass __init__ automated executed
    BrokerCls = None  # broker class will autoregister
    DataCls = None  # data class will auto register

    params = (
        ("timeout", 10),
    )
    
    def _start(self, *args, **kwargs):
        self.start(*args, **kwargs)
    
    def on_dt_over(self, last=False):
        # determin whether T + 0 or T + 1
        pass
    
    def stop(self):
        self._feed.stop()
        self.broker.stop()
