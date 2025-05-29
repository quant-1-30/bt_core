# Import the backtrader platform

import backtest as bt
import backtest.indicators as btind

from bt_sdk.core.model import *


class MyStrategy(bt.Strategy):
    params = dict(period=20)

    def __init__(self):

        sma = btind.SimpleMovingAverage(self.datas[0], period=self.params.period)

    def next(self):
        print("sma: ", self.sma[0])


# class MyStrategy(Strategy):
#     params = dict(period=20)

#     def __init__(self):

#         self.movav = btind.SimpleMovingAverage(self.data, period=self.p.period)
#         self.cmpval = self.data.close(-1) > self.sma

#     def next(self):
#         if self.cmpval[0]:
#             print('Previous close is higher than the moving average')


# class MyStrategy(Strategy):
#     params = dict(period=20)

#     def __init__(self):

#         # data0 is a daily data
#         sma0 = btind.SMA(self.data0, period=15)  # 15 days sma
#         # data1 is a weekly data
#         sma1 = btind.SMA(self.data1, period=5)  # 5 weeks sma

#         self.buysig = sma0 > sma1()

#     def next(self):
#         if self.buysig[0]:
#             print('daily sma is greater than weekly sma1')


if __name__ == '__main__':

    # Create a cerebro entity
    cerebro = bt.Cerebro()

    # Add a strategy
    cerebro.addstrategy(MyStrategy, period=5)
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

    # Print out the final result
    print('Final Portfolio Value and Cash: %.2f, %.2f' % (cerebro.store.getvalue(), cerebro.store.getcash()))

