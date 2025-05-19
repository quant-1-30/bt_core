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
        print('ele: ', ele)
        data.append(ele)
    return data


class TestMdApi:
    
    @pytest.fixture
    def md_api(self):
        return MdApi(addr=("127.0.0.1", 8888))
    
    @pytest.fixture
    def reqmeta(self):
        return ReqMeta(
                      start_date = 1728351060,
                      end_date = 1728361060,
                      sid = ['603676'])
    
    @pytest.fixture
    def reqCalendarmeta(self):
        return ReqMeta(
                      start_date = 19900101,
                      end_date = 20241008,
                      sid = ['603676'])

    def test_reqmktdata(self, md_api, reqmeta):
        q = md_api.reqMktData(reqmeta)
        data = get_data(q)
        assert data is not None

    # def test_reqcalendar(self, md_api, reqCalendarmeta):
    #     q = md_api.reqCalendar(reqCalendarmeta)
    #     data = get_data(q)
    #     assert data is not None

    # def test_reqevents(self, md_api, reqmeta):
    #     q = md_api.reqEvents(reqmeta)
    #     data = get_data(q)
    #     assert data is not None
