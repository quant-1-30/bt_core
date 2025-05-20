#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest
from bt_sdk.core.client import TdApi
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
    def td_api(self):
        api = TdApi(addr=("127.0.0.1", 8888))
        return api
    
    @pytest.fixture
    def ordermeta(self):
        order_type = OrderType.Sell
        return OrderMeta(sid="603676", 
                         price=97,
                         size=100,
                         sizer_cash=10000,
                         pricelimit=102,
                         created_at=1728351060, 
                         exec_type=ExecType.Open,
                         order_type = order_type)
    
    @pytest.fixture 
    def reqmeta(self):
        return ReqMeta(sid=["603676"], 
                       start_date=1728351060, 
                       end_date=1728351060)
    
    def test_get_account(self, td_api):
        q = td_api.get_account()
        data = get_data(q)
        assert data is not None

    def test_get_position(self, td_api):
        q = td_api.get_position()
        data = get_data(q)
        assert data is not None

    # def test_placeOrder(self, td_api, ordermeta):
    #     q = td_api.on_trade(ordermeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_reqOrder(self, td_api, reqmeta):
    #     q = td_api.reqOrder(reqmeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_reqPosition(self, td_api, reqmeta):
    #     q = td_api.reqPosition(reqmeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_reqAccount(self, td_api, reqmeta):
    #     q = td_api.reqAccount(reqmeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_timer(self, td_api):
    #     q = td_api.on_timer(20241008)
    #     data = q.get()
    #     assert data is not None
