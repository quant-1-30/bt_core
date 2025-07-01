#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest
from datetime import datetime
from bt_sdk.core.client import TdApi
from bt_sdk.core.model import *
from bt_sdk.core.constant import *


def get_data(q):
    data_list = []
    while True:
        data = q.get()
        if data == "eof":
            break
        data_list.append(data)
    return data_list


class TestTdApi:

    @pytest.fixture
    def client_id(self):
        return "2038c248-abc6-4e40-b1d4-d77962ad94a8"

    @pytest.fixture
    def td_api(self, client_id):
        api = TdApi(addr=("127.0.0.1", 8888), client_id=client_id)
        return api
    
    @pytest.fixture
    def ordermeta(self):
        order_type = OrderType.Buy
        created_str = "2021-03-01 09:40:30"
        created_dt = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
        return OrderMeta(sid="603676", 
                         price=97,
                         size=100,
                         sizer_cash=10000,
                         pricelimit=102,
                         created_at=created_dt.timestamp(), 
                         exec_type=ExecType.Open, # oco
                        #  exec_type=ExecType.Close, # oco
                        #  exec_type=ExecType.Market, # oco
                         order_type = order_type)
    
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
    def timer_msg(self):
        return {"timer": "end", "session": 20201206}
    
    # def test_set_cash(self, td_api):
    #     q = td_api.set_cash(19901210, 1000000)
    #     data = get_data(q)
    #     print("test_set_cash: ", data)
    #     assert data is not None

    # def test_trade(self, td_api, ordermeta):
    #     q = td_api.trade(ordermeta)
    #     data = get_data(q)
    #     print("test_placeOrder: ", data)
    #     assert data is not None
    
    # def test_pesudo_timer(self, td_api, timer_msg):
    #     q = td_api.pesudo_timer(timer_msg)
    #     data = get_data(q)
    #     print("test_pesudo_trade: ", data)
    #     assert data is not None
    
    def test_getAccount(self, td_api):
        q = td_api.getAccount()
        data = get_data(q)
        print("test_get_account: ", data)
        assert data is not None

    def test_getPosition(self, td_api):
        q = td_api.getPosition()
        data = get_data(q)
        print("test_get_position: ", data)
        assert data is not None

    def test_sub_Order(self, td_api, reqmeta):
        q = td_api.subscribe("order", reqmeta)
        data = get_data(q)
        print("test_reqOrder: ", data)
        assert data is not None

    def test_sub_Position(self, td_api, reqmeta):
        q = td_api.subscribe("position", reqmeta)
        data = get_data(q)
        print("test_reqPosition: ", data)
        assert data is not None

    def test_sub_Account(self, td_api, reqmeta):
        q = td_api.subscribe("account", reqmeta)
        data = get_data(q)
        print("test_reqAccount: ", data)
        assert data is not None
 