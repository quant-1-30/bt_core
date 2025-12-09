# Import the backtrader platform

import warnings
import numpy as np
from dotenv import load_dotenv

from bt_sdk.core.model import *
import backtest as bt
import backtest.indicators as btind

warnings.filterwarnings('ignore')



if __name__ == '__main__':
    
    load_dotenv()
    # configure store sizer risk 
    cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219") # local
    # cerebro = bt.Cerebro(client_id="2160a316-b483-4fd1-8f0e-ff1fbe06ea80") # ssh 

    path = "/Users/hengxinliu/startup/backtest/tests/test_cerebro/out.csv"
    cerebro.plot(out=path) # independent 
