import os
import ray
import uuid
import numpy as np
import backtest as bt
import ray.util.scheduling_strategies

from itertools import compress
from functools import partial
from joblib import Parallel, delayed
from typing import Dict, Any

from tests.sample.ind import *

# ------------------------------------------------------------------- scale ----------------------------------------------------------------

@ray.remote
def run_backtest(rq_config, sid_map):
    cerebro = bt.Cerebro(client_id=uuid.UUID(rq_config["client_id"]).bytes, writer=False)  
    cerebro.addstore("ray") 
    print("run_backtest calendar and markets ", len(cerebro.calendar_days), len(cerebro.markets))
    sid = sid_map["sid"]
    # try:
    ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
    wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

    cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
    cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, ddata) 
    cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal) 

    cerebro.addsizer() # default fixed 
    cerebro.addrisk(thres=0.75) # default tl

    print("run_backtest")
    cerebro.run(
        cash = rq_config["cash"],
        sid = [sid],
        fromdate = rq_config["fromdate"], 
        todate = rq_config["todate"], 
        benchmark = rq_config["benchmark"],
        out="%s.csv" % sid
    )
    # result =  {"sid": sid, "status": 0}
    # # except Exception as e:
    # #     result = {
    # #             "sid": sid,
    # #             "status": 1,
    # #             "error": str(e)
    # #         }
    # return result


def submit_task(nodes, rq_config, sid_map):
    node_count = len(nodes)
    # dispatcher_node = nodes[i % node_count]
    # strategy = ray.util.scheduling_strategies.NodeAffinitySchedulingStrategy( # force binding / local unneccessary
    #     node_id=dispatcher_node,
    #     soft=True # wait util node is avaiable 
    # )
    job = run_backtest.options(
        # scheduling_strategy=strategy,
        num_cpus=1 
    ).remote(rq_config, sid_map) 
    return job


def get_avail(rq_config):
    cerebro = bt.Cerebro(client_id=uuid.UUID(rq_config["client_id"]).bytes, writer=False)  
    cerebro.addstore()

    market_assets = cerebro.markets
    if not market_assets:
        return []

    delist = [m['delist'] if m['delist'] else np.inf for m in market_assets]
    first = [m['first_trading'] for m in market_assets]
    arr_delist = np.array(delist) # dtype='datetime64[D]'
    arr_first = np.array(first)

    intervals = [rq_config["fromdate"], rq_config["todate"]]
    keep_mask = (arr_first <= intervals[1]) & (arr_delist >= intervals[0])
    avaiables = list(compress(market_assets, keep_mask))
    print("avaiables :", len(avaiables))
    del cerebro
    return avaiables[10:14]


def main(): # distribute on driver script
    rq_config = {
        "cash": 10000,
        "client_id": "e9f8cd38-e73c-453f-8a47-55beda640ae6", 
        "fromdate": 20200101,
        "todate": 20260101,
        "benchmark": b"000001"
    }
    pending = results = []
    ray_window = 6 # to avoid put all tasks
    assets = get_avail(rq_config)
    
    ray.init(address="auto", namespace="backtest", ignore_reinit_error=True) # --address auto # connect exist cluster
    active_nodes = [
        n for n in ray.nodes() 
        # if n["Alive"] and "node:127.0.0.1" not in n["Resources"] 
        if n["Alive"] 
    ]
    node_ids = [n["NodeID"] for n in active_nodes]

    submit = partial(submit_task, nodes=node_ids, rq_config=rq_config)
    
    for _ in range(ray_window): # initialize
        if assets:
            pending.append(submit(sid_map=assets.pop()))

    while pending:
        done, pending = ray.wait(pending, num_returns=1)
        
        for ref in done:
            try:
                res = ray.get(ref)
                results.append(res)
                if len(results) % ray_window == 0:
                    print(f"Progress: {len(results)}/{len(assets)}")
            except Exception as e:
                print(f"Task failed: {e}")
        if assets:
            pending.append(submit(sid_map=assets.pop()))

    print("All done!")
    # ray.shutdown()


if __name__ == '__main__':
    main()
