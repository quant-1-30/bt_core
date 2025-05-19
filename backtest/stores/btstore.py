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

import collections
import threading
import queue
from datetime import datetime, timedelta

import backtest as bt
from backtest.metabase import MetaParams, with_metaclass
# from backtest.utils import AutoDict
from bt_sdk.core.client import MdApi, TdApi

# Extend the exceptions to support extra cases
# error
# er = dict(code=599, message='Request Error', description='')
# er = dict(code=598, message='Failed Streaming', description=content)
# er = dict(code=597, message='Not supported TimeFrame', description='')
# er = dict(code=596, message='Network Error', description='')


class MetaSingleton(MetaParams):
    '''Metaclass to make a metaclassed class a singleton'''
    def __init__(cls, name, bases, dct):
        super(MetaSingleton, cls).__init__(name, bases, dct)
        cls._singleton = None

    def __call__(cls, *args, **kwargs):
        if cls._singleton is None:
            cls._singleton = (
                super(MetaSingleton, cls).__call__(*args, **kwargs))
        return cls._singleton


class BtStore(with_metaclass(MetaSingleton, object)):
    '''Singleton class wrapping to control the connections to Oanda.

    Params:

      - ``token`` (default:``None``): API access token

      - ``client_id`` (default: ``None``): client_id

      - ``timerefresh`` (default: ``10.0``): refresh period
    '''

    DataCls = None  # data class will auto register

    params = (
        ('addr', ("localhost", 8888)),
        ('client_id', ''),
        ('timerefresh', 60.0),  # How often to refresh the timeoffset
    )

    _DTEPOCH = datetime(1970, 1, 1)

    # @classmethod
    # def getdata(cls, *args, **kwargs):
    #     '''Returns ``DataCls`` with args, kwargs'''
    #     return cls.DataCls(*args, **kwargs)
    
    def getdata(self, **kwargs):
        '''Returns ``DataCls`` with args, kwargs'''
        return self.DataCls(self.mdapi, **kwargs)

    def __init__(self):
        super(BtStore, self).__init__()

        self.notifs = collections.deque()  # store notifications for cerebro

        self._env = None  # reference to cerebro for general notifications
        self.datas = None  # datas that have registered over start

        self._orders = collections.defaultdict(collections.deque)

        self._cash = 0.0
        self._value = 0.0
        self._evt_acct = threading.Event()
        
        self.mdapi, self.tdapi = btopt.ibConnection(
            host=self.p.host, port=self.p.port, clientId=self.clientId)

    def start(self, data=None, broker=None):
        # connect to mdapi and tdapi
        # Datas require some processing to kickstart data reception
        self.broker_threads()

    def stop(self):
        self.mdapi.stop()
        self.tdapi.stop()

    def put_notification(self, msg, *args, **kwargs):
        self.notifs.append((msg, args, kwargs))

    def get_notifications(self):
        '''Return the pending "store" notifications'''
        self.notifs.append(None)  # put a mark / threads could still append
        return [x for x in iter(self.notifs.popleft, None)]
    
    def get_calendar(self):
        cals = self.DataCls.get_calendar(self.p.client_id)
        return cals
    
    def get_instrument(self, dataname="stock"):
        insts = self.DataCls.get_instruments(self.p.cliend_id, constract=dataname)
        return insts
    
    def reqEventData(self, sid, session):
        events = self.DataCls.get_event(sid, session)
        return events
   
    def get_positions(self):
        positions = self.tdapi.get_positions(self.p.client_id)
        poslist = positions.get('positions', [])
        return poslist

    def get_cash(self):
        return self._cash

    def get_value(self):
        return self._value
    
    def put_notification(self, msg, *args, **kwargs):
        self.notifs.append((msg, args, kwargs))

    def get_notification(self):
        if not self.notifs:
            return None
        return self.notifs.popleft()

    def broker_threads(self):
        t = threading.Thread(target=self._account)
        t.daemon = True
        t.start()

        # Wait once for the values to be set
        self._evt_acct.wait(self.p.account_tmout)

    def _account(self):
        while True:
            try:
                accinfo = self.oapi.get_account(self.p.client_id)
            except Exception as e:
                self.put_notification(e)
                continue
            try:
                self._cash = accinfo['marginAvail']
                self._value = accinfo['balance']
            except KeyError:
                pass

            self._evt_acct.set()

    def buy(self, owner, data,
            size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            parent=None, transmit=True,
            **kwargs):
        msg = OrderMsg(owner=owner, data=data,
                         size=size, price=price, pricelimit=plimit,
                         exectype=exectype, valid=valid, tradeid=tradeid,
                         trailamount=trailamount, trailpercent=trailpercent,
                         parent=parent, transmit=transmit)
        q = self.tdapi.on_trade(msg)
        return q

    def sell(self, owner, data,
             size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             parent=None, transmit=True,
             **kwargs):
        order = OrderMsg(owner=owner, data=data,
                          size=size, price=price, pricelimit=plimit,
                          exectype=exectype, valid=valid, tradeid=tradeid,
                          trailamount=trailamount, trailpercent=trailpercent,
                          parent=parent, transmit=transmit)
        q = self.tdapi.on_trade(order)
        return q

    def cancel(self, order_id):
        q = self.tdapi.on_cancel(order_id)
        return q
    
    # rebalance
