#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest
from datetime import datetime
from bt_sdk.core.client import TdApi
from bt_sdk.constant import *
from bt_sdk.core.model import *


def get_data(q):
    data = []
    while True:
        msg = q.get()
        if msg == "eof":
            q.recycle()
            break
        data.append(msg)
    return data


class TestTdApi:

    @pytest.fixture
    def client_id(self):
        return "2038c248-abc6-4e40-b1d4-d77962ad94a8"

    @pytest.fixture
    def td_api(self, client_id):
        api = TdApi(addr=("127.0.0.1", 8888), client_id=client_id)
        return api
    
    @pytest.fixture
    def cashMeta(self):
        session = 19901210
        cash = 100000
        return CashMeta(session=session, cash=cash)
     
    @pytest.fixture
    def ordermeta(self):
        order_type = OrderType.Buy
        created_str = "2025-04-24 09:40:30"
        created_dt = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
        return OrderMeta(sid="002750", 
                         price=122,
                         size=1000,
                         sizer_cash=10000,
                         pricelimit=130,
                         created_at=created_dt.timestamp(), 
                         exec_type=ExecType.Open, # oco
                        #  exec_type=ExecType.Close, # oco
                        #  exec_type=ExecType.Market, # oco
                         order_type = order_type)

    @pytest.fixture
    def reqmeta(self):
        start_date = "20250425"
        end_date = "20250815"
        start_time = datetime.strptime(start_date, '%Y%m%d')
        end_time = datetime.strptime(end_date, '%Y%m%d')
        sid = ['002750']
        return ReqMeta(
                      start_date = start_time.timestamp(),
                      end_date = end_time.timestamp(),
                      sid = sid)

    # def test_set_cash(self, td_api, cashMeta):
    #     data = td_api.set_cash(cashMeta)
    #     print("test_set_cash: ", data)
    #     assert data is not None

    # def test_submit(self, td_api, ordermeta):
    #     data = td_api.submit(ordermeta)
    #     print("test_trade: ", data)
    #     assert data is not None

    # def test_chain(self, td_api, reqmeta):
    #     data = td_api.chain(reqmeta)
    #     print("test_chain: ", data)
    #     assert data is not None

    def test_getAccount(self, td_api):
        o = td_api.fetch("account")
        print("test account obj: ", o)
        assert o is not None

    def test_getPosition(self, td_api):
        o = td_api.fetch("position")
        print("test position obj: ", o)
        assert o is not None

    def test_subscirbe_order(self, td_api, reqmeta):
        with td_api.subscribe("order", reqmeta) as q:
            data = get_data(q)
            print("test_reqOrder: ", data)
            assert data is not None

    def test_subscribe_position(self, td_api, reqmeta):
        with td_api.subscribe("position", reqmeta) as q:
            data = get_data(q)
            print("test_reqPosition: ", data)
            assert data is not None

    def test_subscribe_account(self, td_api, reqmeta):
        with td_api.subscribe("account", reqmeta) as q:
            data = get_data(q)
            print("test_reqAccount: ", data)
            assert data is not None
    