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

    def log(self, txt, dt=None):
        ''' Logging function for this strategy'''
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt, txt))

    def __init__(self):

        # data0 is a daily data
        sma0 = btind.SMA(self.data.close, period=25)  # 15 days sma
        sma1 = btind.SMA(sma0, period=5)  
        sma2 = btind.SMA(sma1, period=5) 
        sma3 = btind.SMA(sma2, period=10) 
        ema = btind.EMA(sma2, period=5)

        self.buysig = bt.operators.Cmp(ema, sma3)
    
    def next(self):
        if self.buysig[0] < 0.0:
            print("buysig: ", self.buysig[0])
            self.buy(plimit=2, execType=1, filler="trend") # default 
        else:
            print("sellsig: ", self.buysig[0])
            # import pdb; pdb.set_trace()
            self.sell(plimit=2, execType=1, filler="trend")


if __name__ == '__main__':
    
    load_dotenv()
    # configure store sizer risk 
    cerebro = bt.Cerebro(out="out.csv", client_id="1001fe63-3d5d-42b3-89d5-d96218617219") # local
    # cerebro = bt.Cerebro(out="out.csv", client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80") # ssh 

    # Add a strategy
    cerebro.addstrategy(TestStrategy)

    cerebro.run(cash=10000, sid=["603676"], fromdate=20200101, todate=20210101, benchmark="000001") 
    cerebro.plot() 
