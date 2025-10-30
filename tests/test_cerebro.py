# Import the backtrader platform

import backtest as bt
import backtest.indicators as btind

from bt_sdk.core.model import *


# class MyStrategy(bt.Strategy):

#     def log(self, txt, dt=None):
#         ''' Logging function for this strategy'''
#         # dt = dt or self.datas[0].datetime.date(0)
#         # print('%s, %s' % (dt.isoformat(), txt))
#         # dt = dt or self.datas[0].datetime.date(0)
#         dt = str(self.datas[0].datetime.date(0))
#         print('%s, %s' % (dt, txt))

#     def __init__(self):
#         # Keep a reference to the "close" line in the data[0] dataseries
#         self.dataclose = self.datas[0].close

#     def next(self):
#         # Simply log the closing price of the series from the reference
#         self.log('Close, %.2f' % self.dataclose[0])


# class MyStrategy(bt.Strategy):
#     params = dict(period=10)

#     def log(self, txt, dt=None):
#         ''' Logging function for this strategy'''
#         # dt = dt or self.datas[0].datetime.date(0)
#         # print('%s, %s' % (dt.isoformat(), txt))
#         dt = dt or self.datas[0].datetime.date(0)
#         print('%s, %s' % (dt, txt))

#     def __init__(self):

#         self.sma = btind.SimpleMovingAverage(self.datas[0], period=self.p.period)

#     def next(self):
#         self.log('sma: %.2f' % self.sma[0])


# class MyStrategy(bt.Strategy):
#     params = dict(period=5)

#     def __init__(self):

#         self.movav = btind.SimpleMovingAverage(self.data, period=self.p.period)
#         self.cmpval = self.data.close > self.movav.lines.sma

#     def next(self):
#         print("cmpval: ", self.cmpval[0])
#         print("previous close: ", self.data.close[0])
#         if self.cmpval[0]:
#             print('Previous close is higher than the moving average')


class MyStrategy(bt.Strategy):
    params = dict(period=20)

    def __init__(self):

        # data0 is a daily data
        sma0 = btind.SMA(self.data.close, period=15)  # 15 days sma
        # data1 is a weekly data
        sma1 = btind.SMA(sma0, period=5)  # 5 weeks sma
        sma2 = btind.SMA(sma1, period=5)  # 5 weeks sma
        sma3 = btind.SMA(sma2, period=10)  # 5 weeks sma
        ema = btind.EMA(sma2, period=10)

        self.buysig = ema > sma3 # linesoperation
        # self.buysig = sma0 > sma1 # linesoperation

    def next(self):
        print("buysig: ", self.buysig[0])
        if self.buysig[0]:
            print('daily sma is greater than weekly sma1')

# # LineSeriesStub
# class MyStrategy(bt.Strategy):

#     def __init__(self):

#         sma1 = btind.SimpleMovingAverage(self.data.close)
#         ema1 = btind.ExponentialMovingAverage(self.data.close)

#         close_over_sma = self.data.close > sma1 # line ---> LineSeries
#         close_over_ema = self.data.close > ema1 # line ---> LineSeries
#         sma_ema_diff = sma1 - ema1

#         self.buy_sig = bt.And(close_over_sma, close_over_ema, sma_ema_diff > 0)

#     def next(self):
#         print("buy_sig: ", self.buy_sig[0])
#         if self.buy_sig[0]:
#             print('buy')


if __name__ == '__main__':

    cerebro = bt.Cerebro()
    # Add a strategy
    cerebro.addstrategy(MyStrategy)
    cerebro.addstore(bt.BTStore)
    cerebro.run(sid=["603676"], start_date=20200101, end_date=20200201, client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80")

    # plot
    cerebro.plot()
