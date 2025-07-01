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

from backtest.dataseries import TimeFrame
from bt_sdk.core.model import ReqMeta, OrderMeta
from bt_sdk.core.client import MdApi, TdApi
from backtest.store import Store


class BTStore(Store):
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
    )

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

# -------------------------------------------------get components-----------------------------------------------------

    @classmethod
    def getdata(cls, *args, **kwargs):
        '''Returns ``DataCls`` with args, kwargs'''
        return cls.DataCls(*args, **kwargs)

    @classmethod
    def getbroker(cls, *args, **kwargs):
        '''Returns broker with *args, **kwargs from registered ``BrokerCls``'''
        return cls.BrokerCls(*args, **kwargs)
    
# -------------------------------------------------public api-----------------------------------------------------

    def __init__(self, user_id="", **kwargs):
        super(BTStore, self).__init__()
    
        self._cash = 0.0
        self._fundvalue = 0.0
        self.calendar = None
        self.notifs = collections.deque()  # store notifications for cerebro
        self.datas = []
        
        self._feed, self.broker = self.on_connect(user_id, **kwargs)

        self._evt_acct = threading.Event()
        self._evt_cal = threading.Event()

    def on_connect(self, user_id, **kwargs):
        client_id = self.getToken(user_id)
        print("client_id ", client_id)
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
    
    def get_notification(self):
        '''Return the pending "store" notifications'''
        notifs = self.broker.notifs
        notifs.put(None)  # put a mark / threads could still append
        # None is sentinel
        return [x for x in iter(notifs.get, None)]
    
    # def notify(self, order):
    #     self.notifs.put(copy.deepcopy(order))
    
    # def put_notification(self, msg, *args, **kwargs):
    #     self.notifs.append((msg, args, kwargs))
    
    # def get_notification(self):
    #     try:
    #         return self.broker.notifs.get(False)
    #     except queue.Empty:
    #         pass
    #     return None
    
# -------------------------------------------------initialize-----------------------------------------------------

    def _start(self):
        self._feed._start()
        self.broker._start()

    def start(self):
        self._start()
        self.data_threads()
        self.broker_threads()

    def data_threads(self):
        t = threading.Thread(target=self._t_cal)
        t.daemon = True
        t.start()
        self._evt_cal.wait()

    def _t_cal(self):
        msg = self._feed.getCalendar()
        self.calendar = msg
        self._evt_cal.set()

    def broker_threads(self):
        t = threading.Thread(target=self._t_account)
        t.daemon = True
        t.start()
        self._evt_acct.wait() # wait for account data to be set

    def _t_account(self):
        data = self.broker.getAccount()
        print('_t_account', data)
        if data:
            msg = data[0]["msg"]
            self._cash = msg["cash"]
            self._fundvalue = msg["fundvalue"]
            self._evt_acct.set()

# -------------------------------------------------broker api-----------------------------------------------------
    
    def getcash(self):
        return self.broker._cash

    def getvalue(self):
        return self.broker._fundvalue
    
    def getPosition(self):
        return self.broker.getPosition()
    
    def getAccount(self):
        self._t_account()
        return (self._cash, self._fundvalue)
    
    def on_request(self, topic, reqmeta):
        return self.broker.subscribe(topic, reqmeta)

    def submit(self, order_meta: OrderMeta):
        return self.broker.submit(order_meta)
    
    def cancel(self, order_id):
        return self.broker.cancel(order_id)
    
    def on_timer(self, timermeta):
        return self.broker.on_timer(timermeta)

# -------------------------------------------------order api-----------------------------------------------------
    
    def getCalendar(self):
        return self.calendar
    
    def getInstrument(self, session):
        return self._feed.getInstrument(session)
    
    def getEvent(self, session, event_type):
        return self._feed.getEvent(session, event_type)
     
    def subscribe(self, reqmeta):
        return self._feed.subscribe(reqmeta)
    
    def cancelData(self):
        return self._feed.cancel()

    def stop(self):
        # signal end of thread
        self.broker.stop()
        self._feed.stop()