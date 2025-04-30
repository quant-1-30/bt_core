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


from backtest.feed import DataBase
from backtest.metabase import with_metaclass
from backtest.stores import ibstore
from backtest.utils import AutoDict, AutoOrderedDict

from backtest import (TimeFrame, num2date, date2num, BrokerBase)

from bt_sdk.core.client import TdApi
from bt_sdk.core.model import *


class MetaTdBroker(BrokerBase.__class__):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaTdBroker, cls).__init__(name, bases, dct)
        ibstore.BtStore.BrokerCls = cls


class TdBroker(with_metaclass(MetaTdBroker, BrokerBase)):
    '''Broker implementation for Interactive Brokers.

    This class maps the orders/positions from Interactive Brokers to the
    internal API of ``backtrader``.

    Notes:

      - ``tradeid`` is not really supported, because the profit and loss are
        taken directly from IB. Because (as expected) calculates it in FIFO
        manner, the pnl is not accurate for the tradeid.

      - Position

        If there is an open position for an asset at the beginning of
        operaitons or orders given by other means change a position, the trades
        calculated in the ``Strategy`` in cerebro will not reflect the reality.

        To avoid this, this broker would have to do its own position
        management which would also allow tradeid with multiple ids (profit and
        loss would also be calculated locally), but could be considered to be
        defeating the purpose of working with a live broker
    '''
    params = ()
    # order type / order status 
    # Order.Market: bytes('MKT'),
    # Order.Limit: bytes('LMT'),
    # Order.Close: bytes('MOC'),
    # Order.Stop: bytes('STP'),
    # Order.StopLimit: bytes('STPLMT'),
    # Order.StopTrail: bytes('TRAIL'),
    # Order.StopTrailLimit: bytes('TRAIL LIMIT')
    
    (SUBMITTED, FILLED, CANCELLED, INACTIVE,
     PENDINGSUBMIT, PENDINGCANCEL, PRESUBMITTED) = (
        'Submitted', 'Filled', 'Cancelled', 'Inactive',
         'PendingSubmit', 'PendingCancel', 'PreSubmitted',)

    # slippage / commission / filler / replay  

    def __init__(self, **kwargs):
        super(TdBroker, self).__init__()

        self.ib = ibstore.TdStore(**kwargs)

        self.startingcash = self.cash = 0.0
        self.startingvalue = self.value = 0.0

        self._lock_orders = threading.Lock()  # control access
        self.notifs = queue.Queue()  # holds orders which are notified
        self.tonotify = collections.deque()  # hold oids to be notified

    def start(self):
        super(TdBroker, self).start()
        self.ib.start(broker=self)

        if self.ib.connected():
            self.ib.reqAccountUpdates()
            self.startingcash = self.cash = self.ib.get_acc_cash()
            self.startingvalue = self.value = self.ib.get_acc_value()
        else:
            self.startingcash = self.cash = 0.0
            self.startingvalue = self.value = 0.0

    def stop(self):
        super(TdBroker, self).stop()
        self.ib.stop()

    def getcash(self):
        # This call cannot block if no answer is available from ib
        self.cash = self.td.get_acc_cash()
        return self.cash

    def getvalue(self, datas=None):
        self.value = self.td.get_acc_value()
        return self.value

    def getposition(self, data, clone=True):
        return self.td.getposition(data.tradecontract, clone=clone)

    def cancel(self, m_orderId):
        self.td.cancelOrder(m_orderId)

    def submit(self, order_msg: OrderMsg):

        order_id = self.td.submit(order_msg)
        return order_id

    # set coo / coc and so on
    def buy(self, owner, data,
            size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0,
            **kwargs):

        msg = OrderMsg(
            'BUY',
            owner, data, size, price, plimit, exectype, valid, tradeid,
            **kwargs)

        return self.submit(msg)

    def sell(self, owner, data,
             size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0,
             **kwargs):

        msg = OrderMsg(
            'SELL',
            owner, data, size, price, plimit, exectype, valid, tradeid,
            **kwargs)

        return self.submit(msg)

    def notify(self, order):
        self.notifs.put(order.clone())

    def get_notification(self, msg):
        # msg.errorCode
        # Cancelled and Submitted with Filled = 0 can be pushed immediately
        try:
            return self.notifs.get(False)
        except queue.Empty:
            pass
