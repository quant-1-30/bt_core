# Import the backtrader platform

import warnings
import numpy as np
from dotenv import load_dotenv

from bt_sdk.core.model import *
import backtest as bt
import backtest.indicators as btind

warnings.filterwarnings('ignore')


class TestResample(bt.Strategy):

    def log(self, txt, dt=None):
        ''' Logging function for this strategy'''
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt, txt))

    def __init__(self):

        # data0 is a daily data
        sma0 = btind.SMA(self.data.close, period=25)  # 15 days sma


if __name__ == '__main__':
    
    load_dotenv()

    # configure store sizer
    # cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219", stdstats=False) # 2>/dev/null
    cerebro = bt.Cerebro(client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80", stdstats=False) # ssh
    # Add a strategy
    cerebro.addstrategy(TestResample)

    data1 = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)

    data2 = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False, compression=1)

    data3 = cerebro.resampledata(timeframe=bt.TimeFrame.Months, adjbartime=False, compression=1)

    data4 = cerebro.resampledata(timeframe=bt.TimeFrame.Years, adjbartime=False, compression=1)

    cerebro.run(cash=10000, sid=["603676"], fromdate=20200101, todate=20210101, benchmark="000001", out="resample.csv") # localhost
    