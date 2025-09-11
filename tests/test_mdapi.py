#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from datetime import datetime

from bt_sdk.core.client import MdApi
from bt_sdk.core.model import *


def get_data(q):
    data = []
    while True:
        msg = q.get()
        print("get_data msg :", msg)
        if msg == "eof":
            break
        data.append(msg)
    return data


class TestMdApi:
    
    @pytest.fixture
    def md_api(self):
        return MdApi(addr="tcp://127.0.0.1:9000")
    
    @pytest.fixture
    def session(self):
        return 20241008
    
    @pytest.fixture
    def event_type(self):
        # return "adjustment"
        return "rightment"

    @pytest.fixture
    def reqMeta(self):
        start_date = "20250707 9:30:00"
        end_date = "20250830 15:00:00"
        start_time = datetime.strptime(start_date, '%Y%m%d %H:%M:%S').timestamp()
        end_time = datetime.strptime(end_date, '%Y%m%d %H:%M:%S').timestamp()
        sid = ['603676']
        return ReqMeta(start_date = start_time ,end_date = end_time, sid = sid)
    
    def test_getCalendar(self, md_api):
        data = md_api.get_calendar()
        print("test_getCalendar: ", data)
        assert data is not None

    def test_getInstrument(self, md_api):
        data = md_api.get_instrument()
        print("test_getInstrument: ", data)
        assert data is not None
    
    def test_subscribe(self, md_api, reqMeta):
        with md_api.subscribe(reqMeta) as q:
            data = get_data(q)
        # print("subscribe data: ",data)
        assert data is not None
    
    def test_get_close(self, md_api, reqMeta):
        data = md_api.get_close(reqMeta)
        print("test_getClose: ", data)
        assert data is not None

    def test_adjust_event(self, md_api, reqMeta):
        data = md_api.get_event("adjustment", reqMeta)
        print("test_getEvent: ", data)
        assert data is not None
    
    def test_right_event(self, md_api, reqMeta):
        data = md_api.get_event("rightment", reqMeta)
        print("test_getEvent: ", data)
        assert data is not None

    def test_factor(self, md_api, reqMeta):
        data = md_api.factor(reqMeta)
        print("test_getClose: ", data)
        assert data is not None
