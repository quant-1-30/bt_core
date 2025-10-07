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
            break
        data.append(msg)
    return data


class TestTdApi:

    @pytest.fixture
    def client_id(self):
        return "fc9dac14-b6bb-4a2a-a716-741fa73aa5ca"
    
    @pytest.fixture
    def experiment_id(self):
        return "5889b29e-2760-41c2-90db-e3614031bbd4"

    @pytest.fixture
    def td_api(self, client_id, experiment_id):
        api = TdApi(addr=("localhost", 8888), client_id=client_id, timeout=20)
        # api = TdApi(addr=("192.168.2.100", 8888), client_id=client_id, timeout=20)
        api.experiment_id = experiment_id
        return api
    
    @pytest.fixture
    def expMeta(self, client_id):
        strategy = "test"
        assets='002750'
        return ExpMeta(client_id=client_id, strategy=strategy, assets=assets)
    
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
                         sizer_ratio=0.5,
                         pricelimit=130,
                         created_at=created_dt.timestamp(),
                         # ExecType.Close / ExecType.Market 
                         exec_type=ExecType.Open, # oco
                         order_type = order_type)
    
    @pytest.fixture(scope="function")
    def reqmeta(self):
        start_date = "20250424"
        end_date = "20250815"
        start_time = datetime.strptime(start_date, '%Y%m%d')
        end_time = datetime.strptime(end_date, '%Y%m%d')
        sid = ['002750']
        return ReqMeta(
                      start_date = start_time.timestamp(),
                      end_date = end_time.timestamp(),
                      sid = sid)
    
    # def test_register(self, td_api, expMeta):
    #     td_api.register(expMeta)
    #     assert td_api.experiment_id is not None

    # def test_set_cash(self, td_api, cashMeta):
    #     data = td_api.set_cash(cashMeta)
    #     print("test_set_cash: ", data)
    #     assert data is not None

    # def test_submit(self, td_api, ordermeta):
    #     data = td_api.submit(ordermeta)
    #     print("test_submit: ", data)
    #     assert data is not None

    def test_getAccount(self, td_api):
        o = td_api.fetch("account")
        print("test get_account: ", o)
        assert o is not None

    def test_getPosition(self, td_api):
        o = td_api.fetch("position")
        print("test get_position: ", o)
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
    
    def test_on_dt_over(self, td_api, reqmeta):
        status = td_api.on_dt_over(reqmeta)
        print("test_on_dt_over: ", status)
        assert status is not None
