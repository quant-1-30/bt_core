#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest

from backtest.stores.btstore import BTStore
from backtest.brokers.btbroker import BTBroker
from backtest.feeds.mdapi import MdData
from bt_sdk.core.model import *
from bt_sdk.core.constant import *


def get_data(q):
    data_list = []
    while True:
        data = q.get()
        if data == "eof":
            break
        print("data: ", data)
        data_list.append(data)
    return data_list


class TestTdApi:

    @pytest.fixture
    def store(self):
        store = BTStore(user_id="test")
        return store
    
    @pytest.fixture
    def order(self):
        return {"sid": "603676", 
                "price": 97,
                "size": 100,
                "sizer_cash": 10000,
                "pricelimit": 102,
                "created_at": 1728351060, 
                "exec_type": ExecType.Open}
    
    @pytest.fixture 
    def reqmeta(self):
        return ReqMeta(sid=["603676"], 
                       start_date=1728351060, 
                       end_date=1728351060)
    
    def test_get_calendar(self, store):
        store.start()
        q = store.get_calendar()
        data = get_data(q)
        assert data is not None

    # def test_get_instrument(self, store, reqmeta):
    #     store.start()
    #     q = store.get_instrument(reqmeta)
    #     data = get_data(q)
    #     assert data is not None
    
    # def test_get_account(self, store):
    #     store.start()
    #     q = store.get_account()
    #     data = get_data(q)
    #     assert data is not None

    # def test_get_position(self, store):
    #     q = store.get_position()
    #     data = get_data(q)
    #     assert data is not None

    # def test_placeOrder(self, store, ordermeta):
    #     q = store.on_trade(ordermeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_reqOrder(self, store, reqmeta):
    #     q = store.reqOrder(reqmeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_reqPosition(self, store, reqmeta):
    #     q = store.reqPosition(reqmeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_reqAccount(self, store, reqmeta):
    #     q = store.reqAccount(reqmeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_timer(self, store):
    #     q = store.on_timer(20241008)
    #     data = q.get()
    #     assert data is not None
