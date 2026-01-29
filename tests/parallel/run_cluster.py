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
    cerebro.addstore("ray") # RayBtStore() light proxy store
    print("run_backtest 1", cerebro.calendar_days, cerebro.markets)
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

    print("run_backtest 2")
    # Parallel(n_jobs=pool_size)(delayed(rpc)(meta) for meta in batches) # Parallel(n_jobs=2, return_as="generator")
    cerebro.run(
        cash = rq_config["cash"],
        sid = [sid],
        fromdate = rq_config["fromdate"], 
        todate = rq_config["todate"], 
        benchmark = rq_config["benchmark"],
        out="%s.csv" % sid
    )
    print("run_backtest 3")
    # result =  {"sid": sid, "status": 0}
    # # except Exception as e:
    # #     result = {
    # #             "sid": sid,
    # #             "status": 1,
    # #             "error": str(e)
    # #         }
    # return result


def get_avaiable(rq_config):
    cerebro = bt.Cerebro(client_id=uuid.UUID(rq_config["client_id"]).bytes, writer=False)  
    cerebro.addstore()

    ranges = [rq_config["fromdate"], rq_config["todate"]]
    market_assets = cerebro.markets

    if not market_assets:
        return []

    delist = [m['delist'] if m['delist'] else np.inf for m in market_assets]
    first = [m['first_trading'] for m in market_assets]

    arr_delist = np.array(delist) # dtype='datetime64[D]'
    arr_first = np.array(first)

    keep_mask = (arr_first <= ranges[1]) & (arr_delist >= ranges[0])
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
    jobs = []
    results = []
    assets = get_avaiable(rq_config)
    
    ray.init(address="auto", namespace="backtest", ignore_reinit_error=True) # --address auto # connect exist cluster

    active_nodes = [
        n for n in ray.nodes() 
        # if n["Alive"] and "node:127.0.0.1" not in n["Resources"] 
        if n["Alive"] 
    ]
    
    node_ids = [n["NodeID"] for n in active_nodes]
    node_count = len(node_ids)
    print(f"Found {node_count} worker nodes ready for dispatch.")

    
    for i, sid_map in enumerate(assets): # Round-Robin
        dispatcher_node = node_ids[i % node_count]
        strategy = ray.util.scheduling_strategies.NodeAffinitySchedulingStrategy( # force binding
            node_id=dispatcher_node,
            soft=False # wait util node is avaiable 
        )
        job = run_backtest.options(
            scheduling_strategy=strategy,
            num_cpus=1 
        ).remote(rq_config, sid_map)
        
        jobs.append(job)

    print(f"Submitted {len(jobs)} tasks. Waiting for results...")

    pending = jobs

    print("All jobs submitted")
    
    while pending:
        done, pending = ray.wait(pending, num_returns=min(10, len(pending)))
        
        for ref in done:
            try:
                res = ray.get(ref)
                results.append(res)
                if len(results) % 100 == 0:
                    print(f"Progress: {len(results)}/{len(all_sids)}")
            except Exception as e:
                print(f"Task failed: {e}")

    print("All done!")
    # ray.shutdown()


if __name__ == '__main__':
    main()
