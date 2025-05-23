# Import the backtrader platform
from backtest.cerebro import Cerebro
from backtest.stores.btstore import BTStore
from backtest.strategy import Strategy


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
    cerebro.addstore(store)
    # Print out the starting conditions
    print('Starting Portfolio Value: %.2f' % cerebro.stores[0].getvalue())

    # Run over everything
    cerebro.run()

    # Print out the final result
    print('Final Portfolio Value: %.2f' % cerebro.stores[0].getvalue())
