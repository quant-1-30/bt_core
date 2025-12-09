# Import the backtrader platform

import warnings
import numpy as np
from dotenv import load_dotenv

from bt_sdk.core.model import *
import backtest as bt
import backtest.indicators as btind

warnings.filterwarnings('ignore')


class TestStrategy(bt.Strategy):
    params = dict(period=10)

    def __init__(self):
        # data0 is a daily data
        sma0 = btind.SMA(self.data.close, period=25)  # 15 days sma
        sma1 = btind.SMA(sma0, period=5)  
        sma2 = btind.SMA(sma1, period=5) 
        sma3 = btind.SMA(sma2, period=10) 
        ema = btind.EMA(sma2, period=5)

        self.buysig = bt.operator.Cmp(ema, sma3)
    
    def next(self):
        if self.buysig[0] < 0.0:
            print("buysig: ", self.buysig[0])
            self.buy(plimit=2, execType=1, filler="trend") # default 
        else:
            print("sellsig: ", self.buysig[0])
            self.sell(plimit=2, execType=1, filler="trend")


if __name__ == '__main__':
    
    load_dotenv()

    cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219", stdstats=False) # configure ---> store="bt" # 2>/dev/null
    # cerebro = bt.Cerebro(client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80", stdstats=False) # ssh
    # Add a strategy
    cerebro.addstrategy(TestResample)

    data1 = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)

    data2 = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False, compression=1)

    data3 = cerebro.resampledata(timeframe=bt.TimeFrame.Months, adjbartime=False, compression=1)

    data4 = cerebro.resampledata(timeframe=bt.TimeFrame.Years, adjbartime=False, compression=1)

    datas = [data1, data2, data3, data4]
    cerebro.adddata(*datas)

    cerebro.run(cash=10000, sid=["603676"], fromdate=20200101, todate=20210101, benchmark="000001", out="out.csv") # localhost
    