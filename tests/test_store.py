#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest
from datetime import datetime

import backtest as bt
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
        store = bt.BTStore(user_id="test")
        store.start()
        return store
    
    @pytest.fixture
    def session(self):
        return 20240101
    
    @pytest.fixture
    def event_type(self):
        return "adjustment"
    
    @pytest.fixture
    def order(self):
        return OrderMeta(sid="603676", 
                price=97,
                size=100,
                sizer_cash=10000,
                pricelimit=102,
                created_at=1728351060, 
                exec_type=ExecType.Open,
                order_type=OrderType.Buy)
    
    @pytest.fixture
    def reqmeta(self):
        start_date = "20210101"
        end_date = "20230101"
        start_time = datetime.strptime(start_date, '%Y%m%d')
        end_time = datetime.strptime(end_date, '%Y%m%d')
        sid = ['603676']
        return ReqMeta(
                      start_date = start_time.timestamp(),
                      end_date = end_time.timestamp(),
                      sid = sid)
    
    @pytest.fixture
    def subMeta(self):
        start_date = "20210101"
        end_date = "20210301"
        start_time = datetime.strptime(start_date, '%Y%m%d')
        end_time = datetime.strptime(end_date, '%Y%m%d')
        sid = ['600000']
        return ReqMeta(
                      start_date = start_time.timestamp(),
                      end_date = end_time.timestamp(),
                      sid = sid)
    
    @pytest.fixture
    def timer_msg(self):
        return {"timer": "end", "session": 20201206}
    
    def test_getcalendar(self, store):
        data = store.getCalendar()
        print("getcalendar: ", data)
        assert data is not None

    def test_getinstrument(self, store, session):
        data = store.getInstrument(session)
        print("getinstrument: ", data)
        assert data is not None

    def test_getevent(self, store, session, event_type):
        data = store.getEvent(session, event_type)
        print("getevents: ", data)
        assert data is not None
    
    def test_getposition(self, store):
        data = store.getPosition()
        print("getposition: ", data)
        assert data is not None

    def test_getaccount(self, store):
        data = store.getAccount()
        print("getaccount: ", data)
        assert data is not None

    def test_reqOrder(self, store, reqmeta):
        q = store.on_request("order", reqmeta)
        data = get_data(q)
        print("reqOrder: ", data)
        assert data is not None

    def test_reqPosition(self, store, reqmeta):
        q = store.on_request("position", reqmeta)
        data = get_data(q)
        print("reqPosition: ", data)
        assert data is not None

    def test_reqAccount(self, store, reqmeta):
        q = store.on_request("account", reqmeta)
        data = get_data(q)
        print("reqAccount: ", data)
        assert data is not None
    
    def test_submit(self, store, order):
        q = store.submit(order)
        data = get_data(q)
        print("submit: ", data)
        assert data is not None
    
    def test_subscribe(self, store, subMeta):
        store.subscribe(subMeta)
        store._feed.preload()
        print("preload: ", store._feed.lines.buflen())
        assert store._feed.lines.buflen() > 0
    
    def test_timer(self, store, timer_msg):
        data = store.on_timer(timer_msg)
        print("timer: ", data)
        assert data is not None
