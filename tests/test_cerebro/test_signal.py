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
# PeriodN __init__ already addimperiod self.p.period
# signal scale to 0 - 1 / bool(self.delta[0] > 0) # np.False_ ---> bool 


class WeekPriceSignal(btind.Indicator): 

    lines = ('signal',)
    params = (("period", 10),) # week

    def __init__(self):
        sma = btind.SMA(self.data0.close, period=self.p.period)
        self.lines.signal = sma / self.data1.close - 1.0

    def next(self):
        signal = self.lines.signal[0]
        if signal > 10.0:
            import pdb; pdb.set_trace()
        print("WeekPriceSignal delta: ", signal)


class DailyPriceSignal(btind.Indicator): 

    lines = ('signal',)
    params = (("period", 120),) # daily

    def __init__(self):
        low_ind = btind.Lowest(self.data0.close, period=self.p.period) 
        self.lines.signal = self.data0.close / low_ind  - 2.0
    
    def next(self):
        signal = self.lines.signal[0]
        if signal > 10.0:
            import pdb; pdb.set_trace()
        print("DailyPriceSignal ", signal )


class MACDSignal(btind.Indicator): 

    lines = ('signal',)
    params = (('period', 12), ('period1', 26), ('period2', 9),) # daily

    def __init__(self):
        macd = btind.MACDHisto(self.data0.close, 
                            period_me1=self.p.period, 
                            period_me2=self.p.period1, 
                            period_signal=self.p.period2) 
        self.lines.signal = macd.histo

    def next(self):
        signal = self.lines.signal[0]
        print("MACDSignal ", signal )


class VolSignal(btind.Indicator):

    lines = ("signal",)
    params = (("period", 10), ("thres", 1.1)) # daily

    def __init__(self):
        vsma = btind.SMA(self.data0.volume, period=self.p.period)
        self.lines.signal = vsma / (self.data0.volume * self.p.thres) - 1.0

    def next(self):
        # signal =  self.vsma[0] / (self.data0.volume[0] * self.p.thres) - 1.0
        signal = self.lines.signal[0]
        if signal > 10.0:
            import pdb; pdb.set_trace()
        print("VolSignal ", signal )


class SellSignal(btind.Indicator): 

    lines = ("signal",)
    params = (("period", 10), ("thres", 0.85)) # daily

    def __init__(self): 
        # self.lines[0].addminperiod(self.p.period)
        high_ind = btind.Highest(self.data0.close, period=self.p.period) 
        self.lines.signal = self.data0.close / (high_ind * self.p.thres) - 1.0
    
    def next(self):
        signal = self.lines.signal[0]
        if signal > 10.0:
            import pdb; pdb.set_trace()
        print("SellSignal ", signal )


class DrawDownSignal(btind.Indicator): 

    lines = ('signal',)
    params = (("thres", 0.25),)

    def next(self):
        obs = self._owner.stats.getbyname("drawdown") # lowercase
        signal = self.p.thres - obs.lines.drawdown[0]
        self.lines.signal[0] = signal
        print("DrawDownSignal ", signal )


if __name__ == '__main__':
    
    load_dotenv()
    
    # configure store sizer risk 
    # cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219") # local
    cerebro = bt.Cerebro(client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80") # ssh 

    ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
    wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

    cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, ddata) 
    cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal) 

    cerebro.addrisk("tl", thres=0.75) # tl means tolerance 
    cerebro.run(cash=100000, sid=["300308"], fromdate=20210101, todate=20250925, benchmark="000001")

