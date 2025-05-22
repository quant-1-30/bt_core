#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest

from backtest.stores.btstore import BTStore

# to ensure metaclass __init__ automated executed
from backtest.brokers.btbroker import BTBroker
from backtest.feeds.mdapi import MdData
from bt_sdk.core.model import *
from bt_sdk.core.constant import *


def get_data(q):
    data = []
    while True:
        msg = q.get()
        if msg == "eof":
            break
        data.append(msg)
    return data


class TestBTStore:

    # @pytest.fixture(scope="session")  # 整个测试会话
    # @pytest.fixture(scope="module")   # 每个模块
    # @pytest.fixture(scope="class")    # 每个类
    # @pytest.fixture(scope="function") 

    # @pytest.fixture(scope="session")
    # def setup_once(self):
    #     print("Setup running once for the entire test session")
    #     # 设置代码
    #     yield
    #     # 清理代码
    #     print("Cleanup after all tests")

    @pytest.fixture(scope="session")
    def store(self):
        store = BTStore(user_id="test")
        store.start()
        return store
    
    @pytest.fixture
    def session(self):
        return 20240101
    
    @pytest.fixture
    def buyorder(self):
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
                       end_date=1728361060)
    
    def test_get_calendar(self, store):
        data = store.get_calendar()
        print("get_calendar: ", data)
        assert data is not None

    def test_get_instrument(self, store, session):
        data = store.get_instrument(session)
        print("get_instrument: ", data)
        assert data is not None

    def test_get_events(self, store, session):
        data = store.get_events(session)
        print("get_events: ", data)
        assert data is not None
    
    def test_get_position(self, store):
        data = store.get_position()
        print("get_position: ", data)
        assert data is not None

    def test_get_account(self, store):
        data = store.get_account()
        print("get_account: ", data)
        assert data is not None

    def test_reqOrder(self, store, reqmeta):
        q = store.reqOrder(reqmeta)
        data = get_data(q)
        print("reqOrder: ", data)
        assert data is not None

    def test_reqPosition(self, store, reqmeta):
        q = store.reqPosition(reqmeta)
        data = get_data(q)
        assert data is not None

    def test_reqAccount(self, store, reqmeta):
        q = store.reqAccount(reqmeta)
        data = get_data(q)
        assert data is not None
    
    def test_timer(self, store):
        data = store.on_timer(20241008)
        print("timer: ", data)
        assert data is not None
    
    # def test_reqdata(self, store, reqmeta):
    #     store.reqdata(reqmeta)
    #     store.preload()
    #     print("preload: ", store.datas.lines.open[0])
    #     assert store.datas.lines.open[0] is not None

    # def test_buy(self, store, buyorder):
    #     q = store.buy(**buyorder)
    #     data = get_data(q)
    #     print("buy: ", data)
    #     assert data is not None
    
    # def test_sell(self, store, sellorder):
    #     q = store.sell(order)
    #     data = get_data(q)
    #     assert data is not None
