#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest
from datetime import datetime

import backtest as bt
from bt_sdk.constant import *

def get_data(q):
    data = []
    while True:
        msg = q.get()
        if msg == "eof":
            break
        data.append(msg)
    return data


class TestBTStore:

    # @pytest.fixture(scope="session")
    # def setup_once(self):
    #     print("Setup running once for the entire test session")
    #     yield
    #     print("Cleanup after all tests")

    @pytest.fixture # scope="function" / "class" / "module" / "session" 
    def client_id(self):
        return "2160a316-b483-4fd1-8f0e-ff1fbe06ea80"

    # @pytest.fixture(scope="session")
    @pytest.fixture
    def store(self, client_id):
        store = bt.BTStore(
            md_addr=("192.168.2.100", 9000),
            td_addr=("192.168.2.100", 8888),
            client_id=client_id)
        return store
    
    @pytest.fixture
    def ordermeta(self):
        created_str = "2025-04-22 09:40:30"
        created_dt = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
        return {"sid":"002750", 
                "price":97,
                "size":100,
                "sizer_cash":10000,
                "pricelimit":102,
                "created_at":created_dt.timestamp(), 
                "exec_type":ExecType.Open,
                "order_type":OrderType.Buy}
    
    @pytest.fixture
    def reqmeta(self):
        topic = "position"
        start_date = "20240423"
        end_date = "20250801"
        start_time = int(datetime.strptime(start_date, '%Y%m%d').timestamp())
        end_time = int(datetime.strptime(end_date, '%Y%m%d').timestamp())
        sid = ['002750']
        return (topic, start_time, end_time, sid)
    
    # def test_set_cash(self, store):
    #         cash = 100000
    #         session = "20240101"
    #         data = store.set_cash(session=session, cash=cash)
    #         print("account_cash: ", data)
    #         assert data is not None

    # def test_submit(self, store, ordermeta):
    #     data = store.submit(**ordermeta)
    #     print("submit: ", data)
    #     assert data is not None
    
    # def test_chain(self, store, reqmeta):
    #     data = store.chain(*reqmeta[1:3])
    #     print("test_check: ", data)
    #     assert data is not None

    def test_getCalendar(self, store):
        data = store.get_calendar()
        print("getcalendar: ", data)
        assert data is not None

    def test_getInstrument(self, store):
        data = store.get_instrument()
        print("getinstrument: ", data)
        assert data is not None 

    def test_getAccount(self, store):
        data = store.get_account()
        print("get_acct: ", data)
        assert data is not None

    def test_getPosition(self, store):
        data = store.get_position()
        print("get_position: ", data)
        assert data is not None
    
    def test_subscribe(self, store, reqmeta):
        _iter = store.subscribe(*reqmeta) # broker
        res = []
        while True:
            try:
                data = next(_iter)
                res.append(data)
            except StopIteration:
                break
        print("test_req: ", res)
        assert res is not None
    