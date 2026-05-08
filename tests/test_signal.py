# Import the backtrader platform
import os
import uuid
import numpy as np

from dotenv import load_dotenv

import backtest as bt
import backtest.indicators as btind


os.environ["GRPC_POLL_STRATEGY"] = "poll"


class WeekPriceSignal(btind.Indicator): 
    lines = ('signal',)
    params = (("period", 10),) 

    def __init__(self):
        # self.data0 ddata), self.data1 wdata)
        self.sma_weekly = btind.SMA(self.data1.close, period=self.p.period)

    def next(self):
        if len(self.sma_weekly) == 0 or len(self.data0) == 0:
            return

        # =============================================================
        # Look-ahead Bias
        # =============================================================
        if self.data1.datetime.datetime() == self.data0.datetime.datetime():
            if len(self.sma_weekly) < 2: 
                return
            last_week_sma = self.sma_weekly[-1]
        else:
            last_week_sma = self.sma_weekly[0]

        self.lines.signal[0] = last_week_sma / self.data0.close[-1] - 1.0

        print("WeekPriceSignal ", self.lines.signal[0])
        if self.lines.signal[0] > 10.0:
            # print("WeekPriceSignal ", self.lines.signal[0])
            raise ValueError("WeekPriceSignal corrupted")
            

class DailyPriceSignal(btind.Indicator): 

    lines = ('signal',)
    params = (("period", 120),) 

    def __init__(self):
        low_ind = btind.Lowest(self.data0.close, period=self.p.period) 
        self.lines.signal = self.data0.close / low_ind  - 2.0
    
    def next(self):
        signal = self.lines.signal[0]
        print("DailyPriceSignal ", signal)
        if signal > 10.0:
            # print("DailyPriceSignal ", signal)
            raise


class MACDSignal(btind.Indicator): 

    lines = ('signal',)
    params = (('period_me1', 12), ('period_me2', 26), ('period_signal', 9),) # daily

    def __init__(self):
        macd = btind.MACDHisto(self.data0.close, 
                            period_me1=self.p.period_me1, 
                            period_me2=self.p.period_me2, 
                            period_signal=self.p.period_signal) 
        self.lines.signal = macd 

    def next(self):
        signal = self.lines.signal[0] # histo
        if not np.isnan(signal):
            print("MacdSignal :", signal)


class VolSignal(btind.Indicator):

    lines = ("signal",)
    params = (("period", 10), ("thres", 1.1)) 

    def __init__(self):
        vsma = btind.SMA(self.data0.volume, period=self.p.period)
        self.lines.signal = vsma / (self.data0.volume * self.p.thres) - 1.0

    def next(self):
        signal = self.lines.signal[0]
        print("VolSignal ", signal)
        if signal > 10.0: # 71  2022年
            # print("VolSignal ", signal)
            import pdb; pdb.set_trace()
            # raise
            pass


class SellSignal(btind.Indicator): 

    lines = ("signal",)
    params = (("period", 10), ("thres", 0.85)) # daily

    def __init__(self): 
        high_ind = btind.Highest(self.data0.close, period=self.p.period) # inherit from PeriodN(addminperiod(self.p.period)) 
        self.lines.signal = self.data0.close / (high_ind * self.p.thres) - 1.0
    
    def next(self):
        signal = self.lines.signal[0]
        print("SellSignal ", signal)
        if signal > 10.0:
            # print("SellSignal ", signal)
            # raise
            pass


class DrawDownSignal(btind.Indicator): 

    lines = ('signal',)
    params = (("thres", 0.25),)

    def __init__(self):
        self.thres = self.p.thres
        import pdb; pdb.set_trace()

    def next(self):
        self.dd = self._owner.stats["drawdown"]  
        signal = self.thres - self.dd.lines.drawdown[0]
        # self.lines.signal[0] = np.nan_to_num(signal) # used for array not scalar
        self.lines.signal[0] = 0.0 if np.isnan(signal) else signal
        print("DrawDownSignal ", signal)


if __name__ == '__main__':
    
    load_dotenv()
    cerebro = bt.Cerebro(client_id=uuid.UUID("e9f8cd38-e73c-453f-8a47-55beda640ae6").bytes, writer=True) 
    cerebro.addstore() 
    cerebro.addpnc("fixed", days_held=5, stake=0.9)

    ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
    wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

    # data0作为主时钟
    cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, ddata, wdata)
    cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, ddata) 
    cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal) 

    # 600036/ 300308
    cerebro.run(cash=100000, sid=[b"300308"], fromdate=20230101, todate=20260201, benchmark=[b"000001"], out="signal.csv")

    # 22年数据有问题重新入库 导致 vol > 70 /  resample volume ohlcv 聚合 / stats计算为空

