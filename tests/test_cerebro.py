# Import the backtrader platform
from backtest.cerebro import Cerebro
from backtest.stores.btstore import BTStore
from backtest.strategy import Strategy
from bt_sdk.core.model import *


# Create a Stratey
class TestStrategy(Strategy):

    def log(self, txt, dt=None):
        ''' Logging function for this strategy'''
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        # Keep a reference to the "close" line in the data[0] dataseries
        self.dataclose = self.datas[0].close

    def next(self):
        # Simply log the closing price of the series from the reference
        self.log('Close, %.2f' % self.dataclose[0])


if __name__ == '__main__':

    # Create a cerebro entity
    cerebro = Cerebro()
    # Add a strategy
    cerebro.addstrategy(TestStrategy)
    # add data
    store = BTStore(user_id="test")
    # import pdb; pdb.set_trace()
    cerebro.addstore(store)
    print("backtest calendar: ", len(cerebro.store.getCalendar()))
    # Print out the starting conditions
    print('Starting Portfolio Value and Cash: %.2f, %.2f' % (cerebro.store.getvalue(), cerebro.store.getcash()))

    reqmeta = ReqMeta(sid=["603676"], start_date=1728351060, end_date=1728371060)

    # Run over everything
    cerebro.run(reqmeta)

    # Print out the final result
    print('Final Portfolio Value and Cash: %.2f, %.2f' % (cerebro.store.getvalue(), cerebro.store.getcash()))
