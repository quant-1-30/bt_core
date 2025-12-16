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
        sma0 = btind.SMA(self.data.close, period=25)  # 15 days sma
        sma1 = btind.SMA(sma0, period=5)  
        sma2 = btind.SMA(sma1, period=5) 
        sma3 = btind.SMA(sma2, period=10) 
        ema = btind.EMA(sma2, period=5)
        self.macd = btind.MACDHisto(self.data.close)

        self.buysig = bt.operator.Cmp(sma1, ema)
    
    def next(self):
        if self.buysig[0] < 0.0 and self.macd.histo[0] > 0:
            print("buysig: ", self.buysig[0])
            self.buy(plimit=2, execType=1, filler="trend") # default 
        elif self.macd.histo[0] < 0 and self.buysig[0] > 0:
            print("sellsig: ", self.buysig[0])
            self.sell(plimit=2, execType=1, filler="trend")


if __name__ == '__main__':
    
    load_dotenv()
    # configure store sizer risk 
    cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219") # local
    # cerebro = bt.Cerebro(client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80") # ssh 
    
    cerebro.addstrategy(TestStrategy)

    path = "/Users/hengxinliu/startup/backtest/tests/test_cerebro/signal_demo.csv"
    cerebro.plot(out=path, num_data=3, num_ind=5, num_obs=7)  
