#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from bt_sdk.core.client import MdApi
from bt_sdk.core.model import *


def get_data(q):
    data = []
    while True:
        ele = q.get()
        if ele == "eof":
            break
        print(ele)
        data.append(ele)
    print("data: ", data)
    return data


class TestMdApi:
    
    @pytest.fixture
    def md_api(self):
        return MdApi(addr=("127.0.0.1", 8888))
    
    @pytest.fixture
    def session(self):
        return 20240101
    
    @pytest.fixture
    def reqMktDataMeta(self):
        return ReqMeta(
                      start_date = 1728351060,
                      end_date = 1728351060,
                      sid = ['603676'])
    
    @pytest.fixture
    def reqmeta(self):
        return ReqMeta(
                      start_date = 19900101,
                      end_date = 20241008,
                    #   sid = ['603676'])
                      sid =[]) 
    
    def test_connect(self, md_api):
        assert md_api.connected()

    def test_get_calendar(self, md_api):
        q = md_api.get_calendar()
        data = get_data(q)
        assert data is not None

    def test_get_instrument(self, md_api, session):
        q = md_api.get_instrument(session)
        data = get_data(q)
        assert data is not None

    def test_get_events(self, md_api, session):
        q = md_api.get_events(session)
        data = get_data(q)
        assert data is not None

    def test_reqmktdata(self, md_api, reqMktDataMeta):
        q = md_api.reqMktData(reqMktDataMeta)
        data = get_data(q)
        assert data is not None


