#! /usr/bin/env python3
# -*- coding: utf-8 -*- 

import pytest
import pytz
import uuid
from dotenv import load_dotenv
from datetime import datetime
from backtest.execution.trade_api import TdApi, SubTopic
from backtest.protocol import RegisterBody, CashBody, OrderBody, QueryBody


class TestTdApi:

    @pytest.fixture(scope="session")
    def client_id(self): # \x16 --> 2
        return uuid.UUID("e9f8cd38-e73c-453f-8a47-55beda640ae6").bytes
    
    @pytest.fixture(scope="session")
    def experiment_id(self): # bytes.fromhex()
        return b'!\xa9\x95\xb2\xf0gCT\xa1\xbf\xa9)<\xca\xab\xb3'

    @pytest.fixture(scope="session")
    def td_api(self, client_id):
        load_dotenv()
        api = TdApi(client_id=client_id)
        api.start()
        yield api     
        # ===== teardown =====
        api.stop()    
    
    @pytest.fixture
    def register(self, client_id):
        strategy = "test_cython"
        extra_info= "300308"
        return RegisterBody(client_id=client_id, strategy=strategy, extra_info=extra_info)
    
    @pytest.fixture
    def cash(self):
        session = 19901210
        cash = 100000
        return CashBody(session=session, cash=cash)
      
    @pytest.fixture
    def order(self):
        created_str = "2025-04-23 9:31:00" # pytz timezone default to UTC
        created_dt = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
        created_dt = pytz.UTC.localize(created_dt)
        return OrderBody(
                sid=b"300308", 
                pricelimit=2, # / 100
                sizer_ratio=80, #  /100
                created_dt=int(created_dt.timestamp()),
                order_type=0,
                exec_type=0,
                filler=b"likehood") # oco / occ / smooth / likehood
    
    @pytest.fixture(scope="function")
    def query(self):
        start_date = 0
        end_date = 1745400660
        sid = [b'300308']
        return QueryBody(start_date=start_date, end_date=end_date, sid=sid)
    
    @pytest.fixture(scope="function")
    def dt_over_query(self):
        start_date = 1745400660
        end_date = 1746500660
        sid = [b'300308']
        return QueryBody(start_date=start_date, end_date=end_date, sid=sid)
    
    # def test_register(self, td_api, register):
    #     with td_api as client:
    #         resp = client.register(register)
    #         print("resp ", resp)
    #         assert resp is not None

    # def test_set_cash(self, td_api, experiment_id, cash):
    #     with td_api as client:
    #         resp = client.set_cash(experiment_id, cash)
    #         print("test_set_cash: ", resp)
    #         assert resp is not None
    
    # def test_submit(self, td_api, experiment_id, order):
    #     with td_api as client:
    #         resp = client.submit(experiment_id, order)
    #         print("test_submit: ", resp)
    #         assert resp is not None

    def test_getValue(self, td_api, experiment_id):
        with td_api as client:
            resp = client.getvalue(experiment_id)
            print("test getValue: ", resp)
            assert resp is not None

    def test_subscribe_position(self, td_api, experiment_id, query):
        with td_api as client:
            resp = client.subscribe(SubTopic.Position, experiment_id, query)
            print("test_reqPosition: ", resp)
            assert resp is not None

    def test_subscribe_account(self, td_api, experiment_id, query):
        with td_api as client:
            resp = client.subscribe(SubTopic.Account, experiment_id, query)
            print("test_reqAccount: ", resp)
            assert resp is not None
    
    def test_subscirbe_order(self, td_api, experiment_id, query):
        with td_api as client:
            resp = client.subscribe(SubTopic.Order, experiment_id, query)
            print("test_reqOrder: ", resp)
            assert resp is not None
    
    # def test_on_dt_over(self, td_api, experiment_id, dt_over_query):
    #     with td_api as client:
    #         resp = client.on_dt_over(experiment_id, dt_over_query)
    #         print("test_on_dt_over: ", resp)
    #         assert resp is not None
