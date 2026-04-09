import gc
import uuid
import traceback
import backtest as bt

from typing import Dict, Any
from workflow.strategy.ind import *


def run_backtest(config_ref, sid_map, store_agent=None):
    sid = sid_map["sid"]
    print("run_backtest sid ", sid)
    try:
        cerebro = bt.Cerebro(client_id=uuid.UUID(config_ref["client_id"]).bytes, writer=False)  
        cerebro.addstore("generic") 
        ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
        wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

        cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)

        cerebro.run(
            cash = config_ref["cash"],
            sid = [sid],
            fromdate = config_ref["fromdate"], 
            todate = config_ref["todate"], 
            benchmark = config_ref["benchmark"],
            out="%s.csv" % sid
        )
        result =  {"sid": sid, "status": 0}
    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"Worker Error on {sid}: {err_msg}") 
        result = {
                "sid": sid,
                "status": 1,
                "error": str(e)
            }
    if cerebro:
        del cerebro
        gc.collect()
    return result

