#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import pdb
import pytest
import pandas as pd
from backtest.feeds.pandafeed import PandasData
from backtest.dataseries import TimeFrame
from backtest.feeds.mdapi import MdData
from bt_sdk.core.model import ReqMeta


class TestFeed:

    # def test_pandas(self):
    #     sample_data = pd.read_csv('./samples/tick_sample.csv')
    #     data = PandasData(dataname=sample_data, timeframe=TimeFrame.Days)
    #     # # test_resample
    #     # data.resample(timeframe=TimeFrame.Days,
    #     #               compression=2)
    #     # test_preload
    #     data._start()
    #     data.preload()
        
    def test_mdapi(self):
        req = ReqMeta(start_date = 1728351060,
                      end_date = 1728361060,
                      sid = ['603676'])
        mdData = MdData()
        mdData._start()
        mdData.reqdata(req)
        mdData.preload()
