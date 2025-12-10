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
# self define need to addminpeeriod

class PriceSignal(btind.Indicator):  # 分钟重采样日线 --- 60日均线

    lines = ('breakthrough',)
    params = (("period", 60),)

    def __init__(self):
        sma = btind.SMA(self.data.close, period=self.p.period) # PeriodN __init__ already addimperiod self.p.period
        self.lines.breakthrough = sma - self.data.close
    

class VolSignal(btind.Indicator): # 分钟重采样 --- 日成交量突破

    lines = ('breakthrough',)
    params = (("period", 70), ("thres", 1.05))

    def __init__(self):
        vsma = btind.SMA(self.data.volume, period=self.p.period)
        self.lines.breakthrough = vsma - self.data.volume 


class MACDSignal(btind.Indicator): # 分钟重采样 --- MACD dif / def 背离

    lines = ('breakthrough',)
    params = (("period", 20), ("thres", 1.05))

    def __init__(self):
        macd = btind.MACD(self.data.close) # 12 / 26 / 9
        self.lines.breakthrough = macd.signal 


class DDSignal(btind.Indicator): # 分钟重采用 --- maxdrawdown 0.4

    lines = ("breakthrough",)
    params = (("period", 90), ("drawdown", 0.4))

    def __init__(self): # self._dd = DDI(period=self.p.period, drawdown=self.p.drawdown)
        self.lines[0].addminperiod(self.p.period)

    def next(self):
        cdata = self.data.close.get(size=self.p.period)
        self.lines.breakthrough[0] = cdata[0] / max(cdata) + self.p.drawdown - 1


if __name__ == '__main__':
    
    load_dotenv()
    # configure store sizer risk 
    # cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219") # local
    cerebro = bt.Cerebro(client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80") # ssh 

    data1 = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
    cerebro.adddata(data1)

    cerebro.add_signal(bt.SIGNAL_LONG, PriceSignal, data1)
    cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, data1)
    cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, data1)
    cerebro.add_signal(bt.SIGNAL_LONG, DDSignal, data1)

    cerebro.run(cash=100000, sid=["603676"], fromdate=20200101, todate=20210101, benchmark="000001", out="signal.csv") 
