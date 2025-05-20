#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest
from bt_sdk.core.client import TdApi
from bt_sdk.core.model import ReqMeta, OrderMeta, TimerMeta
from bt_sdk.core.constant import OrderType, ExecType


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
    
    @pytest.fixture
    def timermeta(self):
        # open / close
        return TimerMeta(timer="open", session=20241008)
    
    def test_trade(self, td_api, ordermeta):
        q= td_api.on_trade(ordermeta)
        data = q.get()
        assert data is not None

    # def test_order(self, td_api, reqmeta):
    #     q = td_api.reqOrder(reqmeta)
    #     data = q.get()
    #     assert data is not None

    # def test_position(self, td_api, reqmeta):
    #     q = td_api.reqPosition(reqmeta)
    #     data = q.get()
    #     assert data is not None

    # def test_account(self, td_api, reqmeta):
    #     q = td_api.reqAccount(reqmeta)
    #     data = q.get()
    #     assert data is not None

    # def test_sync(self, td_api, timermeta):
    #     q = td_api.on_sync(timermeta)
    #     data = q.get()
    #     assert data is not None
