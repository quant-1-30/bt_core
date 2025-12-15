# Import the backtrader platform

import warnings
import numpy as np
from dotenv import load_dotenv

from bt_sdk.core.model import *
import backtest as bt
import backtest.indicators as btind

warnings.filterwarnings('ignore')

# 涉及 linebuffer __init__ /  具体值计算比较 next  __getitem__
# basciops to implement next method and use linebuffer instead of __getitem__
# self define need to addminpeeriod and define dmaster

class WeekPriceSignal(btind.Indicator): 

    lines = ('signal',)
    params = (("wperiod", 10),)

    def __init__(self):
        sma = btind.SMA(self.data0.close, period=self.p.wperiod) # PeriodN __init__ already addimperiod self.p.period
        self.lines.signal = sma - self.data1.close # bool(self.delta[0] > 0) # np.False_ ---> bool 

    def next(self):
        delta = self.lines.signal[0]
        print("WeekPriceSignal delta: ", delta)


class DailyPriceSignal(btind.Indicator): 

    lines = ('signal',)
    params = (("dperiod", 120),)

    def __init__(self):
        self.min_ind = btind.Lowest(self.data0.close, period=self.p.dperiod) # PeriodN __init__ already addimperiod self.p.period
        self.delta = self.data0.close - self.min_ind * 2 # bool(delta < 0) # np.False_ ---> bool


class MACDSignal(btind.Indicator): 

    lines = ('signal',)
    params = (('period1', 12), ('period2', 26), ('period3', 9),)

    def __init__(self):
        macd = btind.MACDHisto(self.data0.close, period_me1=self.p.period1, period_me2=self.p.period2, period_signal=self.p.period3) # 12 / 26 / 9
        self.lines.signal = macd.histo

    def next(self):
        signal = bool(self.lines.signal[0] > 0)
        print("MACDSignal ", signal )


class VolSignal(btind.Indicator):

    _mindatas = 2
    lines = ('signal',)
    params = (("period", 10), ("thres", 1.05))

    def __init__(self):
        vsma = btind.SMA(self.data0.volume, period=self.p.period)
        self.lines.signal = vsma - self.data0.volume 


class SellSignal(btind.Indicator): 

    lines = ("signal",)
    params = (("period", 10), ("thres", 0.95), ("thres2", 0.85))

    def __init__(self): 
        self.lines[0].addminperiod(self.p.period)

    def next(self):
        # return < 0.15  ---> close < max(10 week close) * 0.98
        # return >= 0.15 ---> close < max(10 day close) * 0.95
        cdata = self.data.close.get(size=self.p.period)
        self.lines.breakthrough[0] = cdata[0] - self.p.thres * max(cdata)


if __name__ == '__main__':
    
    load_dotenv()
    # configure store sizer risk 
    cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219") # local
    # cerebro = bt.Cerebro(client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80") # ssh 

    ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
    wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

    cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
    # cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal) 

    cerebro.run(cash=100000, sid=["600089"], fromdate=20220101, todate=20250925, benchmark="000001", out="signal.csv") 
