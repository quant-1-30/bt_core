# Import the backtrader platform

import warnings
import uuid
import numpy as np
from dotenv import load_dotenv

import backtest as bt
import backtest.indicators as btind

warnings.filterwarnings('ignore')


if __name__ == '__main__':
    
    load_dotenv()
    # cerebro = bt.Cerebro(client_id="1001fe63-3d5d-42b3-89d5-d96218617219") # local
    cerebro = bt.Cerebro(client_id=uuid.UUID("e9f8cd38-e73c-453f-8a47-55beda640ae6").bytes, writer=False) # ssh 
    
    path = "/Users/hengxinliu/startup/backtest/tests/test_cerebro/signal.csv"
    cerebro.plot(num_data=3, num_ind=6, num_obs=7, source=path)  
