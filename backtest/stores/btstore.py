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
import httpx
import collections
import threading

from backtest.metabase import MetaParams, with_metaclass
from backtest.dataseries import TimeFrame
from bt_sdk.core.model import ReqMeta
from bt_sdk.core.client import MdApi, TdApi


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
    

class BTStore(with_metaclass(MetaSingleton, object)):
    '''Singleton class wrapping to control the connections to Oanda.

    Params:

      - ``token`` (default:``None``): API access token

      - ``account`` (default: ``None``): account id

      - ``practice`` (default: ``False``): use the test environment

      - ``account_tmout`` (default: ``10.0``): refresh period for account
        value/cash refresh
    '''
    
    # get_method is blocking method / req_method is non-blocking method

    BrokerCls = None  # broker class will autoregister
    DataCls = None  # data class will auto register

    params = (
        ("token", ""),
        ('account', ''),
        ('md_addr', ("127.0.0.1", 8888)),
        ('td_addr', ("127.0.0.1", 8888)),
        ('account_tmout', -1),  # account balance refresh timeout
        ('cal_tmout', -1),  # calendar refresh timeout
    )

    # _DTEPOCH = datetime(1970, 1, 1)
    # _ENVLIVE = 'live'

    @classmethod
    def getdata(cls, *args, **kwargs):
        '''Returns ``DataCls`` with args, kwargs'''
        return cls.DataCls(*args, **kwargs)

    @classmethod
    def getbroker(cls, *args, **kwargs):
        '''Returns broker with *args, **kwargs from registered ``BrokerCls``'''
        return cls.BrokerCls(*args, **kwargs)

    def __init__(self, user_id="", **kwargs):
        super(BTStore, self).__init__()

        self.datas, self.broker = self.on_login(user_id, **kwargs)
    
        # self._env = self.datas._env
        self._cash = 0.0
        self._value = 0.0
        self.calendar = None
        self.notifs = collections.deque()  # store notifications for cerebro

        # self._orders = collections.OrderedDict()  # map order.ref to oid
        # self._ordersrev = collections.OrderedDict()  # map oid to order.ref
        # self._transpend = collections.defaultdict(collections.deque)

        self._evt_acct = threading.Event()
        self._evt_cal = threading.Event()

    def on_login(self, user_id, **kwargs):
        client_id = self.getToken(user_id)
        md_addr = kwargs.get('md_addr', self.p.md_addr)
        td_addr = kwargs.get('td_addr', self.p.td_addr)
        mdapi = MdApi(md_addr, client_id=client_id)
        tdapi = TdApi(td_addr, client_id=client_id)
        return (self.DataCls(mdapi), self.BrokerCls(tdapi))

    @staticmethod
    def getToken(user_id):
        headers = {
            "Authorization": f"Bearer test"
        }
        response = httpx.post("http://localhost:10000/auth/login", json={"user_id": user_id}, headers=headers)
        data = response.json()
        if data["status"] == 1:
            raise Exception(data["data"])
        return data["data"]
    
    def _start(self):
        self.datas._start()
        self.broker._start()

    def start(self, data=None, broker=None):
        self._start()
        self.data_threads()
        self.broker_threads()

    def data_threads(self):
        t = threading.Thread(target=self._t_cal)
        t.daemon = True
        t.start()
        # self._evt_cal.wait(self.p.account_tmout)
        self._evt_cal.wait()

    def _t_cal(self):
        msg = self.datas.get_calendar()
        self.calendar = msg
        self._evt_cal.set()

    def broker_threads(self):
        t = threading.Thread(target=self._t_account)
        t.daemon = True
        t.start()
        self._evt_acct.wait(self.p.account_tmout)

    def _t_account(self):
        msg = self.broker.get_account()
        if msg:
            self._cash = msg[0][0]
            self._value = msg[0][1]
        self._evt_acct.set()
    
    def get_cash(self):
        return self._cash

    def get_value(self):
        return self._value
    
    def get_calendar(self):
        return self.calendar
    
    def get_position(self):
        return self.broker.get_position()
    
    def get_account(self):
        self._t_account()
        return (self._cash, self._value)
    
    def get_instrument(self, session):
        return self.datas.get_instrument(session)
    
    def get_events(self, session):
        return self.datas.get_events(session)
    
    def put_notification(self, msg, *args, **kwargs):
        self.notifs.append((msg, args, kwargs))

    def get_notifications(self):
        '''Return the pending "store" notifications'''
        self.notifs.append(None)  # put a mark / threads could still append
        # None is sentinel
        return [x for x in iter(self.notifs.popleft, None)]

    # supported granularities
    _GRANULARITIES = {
        (TimeFrame.Seconds, 5): 'S5',
        (TimeFrame.Seconds, 10): 'S10',
        (TimeFrame.Seconds, 15): 'S15',
        (TimeFrame.Seconds, 30): 'S30',
        (TimeFrame.Minutes, 1): 'M1',
        (TimeFrame.Minutes, 2): 'M3',
        (TimeFrame.Minutes, 3): 'M3',
        (TimeFrame.Minutes, 4): 'M4',
        (TimeFrame.Minutes, 5): 'M5',
        (TimeFrame.Minutes, 10): 'M5',
        (TimeFrame.Minutes, 15): 'M5',
        (TimeFrame.Minutes, 30): 'M5',
        (TimeFrame.Minutes, 60): 'H1',
        (TimeFrame.Minutes, 120): 'H2',
        (TimeFrame.Minutes, 180): 'H3',
        (TimeFrame.Minutes, 240): 'H4',
        (TimeFrame.Minutes, 360): 'H6',
        (TimeFrame.Minutes, 480): 'H8',
        (TimeFrame.Days, 1): 'D',
        (TimeFrame.Weeks, 1): 'W',
        (TimeFrame.Months, 1): 'M',
    }
    def get_granularity(self, timeframe, compression):
        return self._GRANULARITIES.get((timeframe, compression), None)

    def buy(self, sid='', size=0, sizer_cash=0, price=None, plimit=None,
            exec_type=None, **kwargs):
        return self.broker.buy(sid, size, sizer_cash=sizer_cash, price=price, plimit=plimit,
            exec_type=exec_type, **kwargs)
    
    def sell(self, sid='', size=0, sizer_cash=0, price=None, plimit=None,
             exec_type=None, **kwargs):
        return self.broker.sell(sid, size, sizer_cash=sizer_cash, price=price, plimit=plimit,
            exec_type=exec_type, **kwargs)
     
    def reqdata(self, reqmeta):
        return self.datas.reqdata(reqmeta)
    
    def preload(self):
        return self.datas.preload()
    
    def reqOrder(self, reqmeta):
        return self.broker.reqOrder(reqmeta)
    
    def reqPosition(self, reqmeta):
        return self.broker.reqPosition(reqmeta) 
    
    def reqAccount(self, reqmeta):
        return self.broker.reqAccount(reqmeta)
    
    def cancel(self, order_id):
        return self.broker.cancel(order_id)
    
    def cancelData(self):
        return self.datas.cancelData()

    def stop(self):
        # signal end of thread
        self.broker.stop()
        self.datas.stop()

    def on_timer(self, tick):
        return self.broker.on_timer(tick)
