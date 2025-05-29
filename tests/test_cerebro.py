# Import the backtrader platform

import backtest as bt
import backtest.indicators as btind

from bt_sdk.core.model import *


# # Create a Stratey
# class MyStrategy(bt.Strategy):

#     def log(self, txt, dt=None):
#         ''' Logging function for this strategy'''
#         # dt = dt or self.datas[0].datetime.date(0)
#         # print('%s, %s' % (dt.isoformat(), txt))
#         dt = dt or self.datas[0].datetime.date(0)
#         print('%s, %s' % (dt, txt))

#     def __init__(self):
#         # Keep a reference to the "close" line in the data[0] dataseries
#         self.dataclose = self.datas[0].close

#     def next(self):
#         import pdb; pdb.set_trace()
#         # Simply log the closing price of the series from the reference
#         self.log('Close, %.2f' % self.dataclose[0])



# class MyStrategy(bt.Strategy):
#     params = dict(period=20)

#     def log(self, txt, dt=None):
#         ''' Logging function for this strategy'''
#         # dt = dt or self.datas[0].datetime.date(0)
#         # print('%s, %s' % (dt.isoformat(), txt))
#         dt = dt or self.datas[0].datetime.date(0)
#         print('%s, %s' % (dt, txt))

#     def __init__(self):

#         self.sma = btind.SimpleMovingAverage(self.datas[0], period=self.params.period)

#     def next(self):
#         import pdb; pdb.set_trace()
#         self.log('sma: %.2f' % self.sma[0])
#         print("sma: ", self.sma[0])


# class MyStrategy(bt.Strategy):
#     params = dict(period=5)

#     def __init__(self):

#         self.movav = btind.SimpleMovingAverage(self.data, period=self.p.period)
#         self.cmpval = self.data.close(-1) > self.movav.lines.sma

#     def next(self):
#         # import pdb; pdb.set_trace()
#         print("cmpval: ", self.cmpval[0])
#         if self.cmpval[0]:
#             print('Previous close is higher than the moving average')


class MyStrategy(bt.Strategy):
    params = dict(period=20)

    def __init__(self):

        # data0 is a daily data
        sma0 = btind.SMA(self.data, period=15)  # 15 days sma
        # data1 is a weekly data
        sma1 = btind.SMA(self.data, period=5)  # 5 weeks sma
        self.buysig = sma0 > sma1

    def next(self):
        print("buysig: ", self.buysig[0])
        if self.buysig[0]:
            print('daily sma is greater than weekly sma1')


# class MyStrategy(bt.Strategy):

#     def __init__(self):

#         sma1 = btind.SimpleMovingAverage(self.data)
#         ema1 = btind.ExponentialMovingAverage()

#         close_over_sma = self.data.close > sma1
#         close_over_ema = self.data.close > ema1
#         sma_ema_diff = sma1 - ema1

#         self.buy_sig = bt.And(close_over_sma, close_over_ema, sma_ema_diff > 0)

#     def next(self):
#         # import pdb; pdb.set_trace()
#         print("buy_sig: ", self.buy_sig[0])
#         if self.buy_sig[0]:
#             print('buy')


if __name__ == '__main__':

    # Create a cerebro entity
    cerebro = bt.Cerebro()
    # Add a strategy
    cerebro.addstrategy(MyStrategy)
    # add data
    store = bt.BTStore(user_id="test")
    # import pdb; pdb.set_trace()
    cerebro.addstore(store)

    # data = btfeeds.MyFeed(...)
    # cerebro.adddata(data)
    print("backtest calendar: ", len(cerebro.store.getCalendar()))
    # Print out the starting conditions
    print('Starting Portfolio Value and Cash: %.2f, %.2f' % (cerebro.store.getvalue(), cerebro.store.getcash()))
    reqmeta = ReqMeta(sid=["603676"], start_date=1728351060, end_date=1728384000)
    # Run over everything
    cerebro.run(reqmeta)

    # plot
    cerebro.plot()
    # Print out the final result
    print('Final Portfolio Value and Cash: %.2f, %.2f' % (cerebro.store.getvalue(), cerebro.store.getcash()))
