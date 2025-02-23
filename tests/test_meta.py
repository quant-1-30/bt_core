#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import pdb
from feeds.pandafeed import PandasData
from meta.dataseries import TimeFrame


sample_data = pd.read_csv('~/startup/backtest/samples/tick_sample.csv')

data = PandasData(dataname=sample_data, timeframe=TimeFrame.Days)

# test_resample
data.resample(timeframe=TimeFrame.Days,
              compression=2)

# test_preload
data._start()
data.preload()

pdb.set_trace()

# test_replayer

# test_indicator

# test_strategy
