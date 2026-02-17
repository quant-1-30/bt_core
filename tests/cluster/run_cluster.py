import os

# numpy auto use all cpus so to restricted
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import ray
import gc
import uuid
import traceback
import numpy as np
import backtest as bt
import ray.util.scheduling_strategies

from itertools import compress
from functools import partial
from joblib import Parallel, delayed
from typing import Dict, Any
from tests.sample.ind import *


env_vars = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1"
}


@ray.remote(num_cpus=2, max_calls=1) # delete python process after finish
def run_backtest(config_ref, sid_map, store_agent=None):
    sid = sid_map["sid"]
    try:
        cerebro = bt.Cerebro(client_id=uuid.UUID(config_ref["client_id"]).bytes, writer=False)  
        cerebro.addstore("ray", agent=store_agent) 
        print("run_backtest calendar and markets ", len(cerebro.calendar_days), len(cerebro.markets))
        # try:
        ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
        wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

        cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, ddata) 
        cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal) 

        print("run_backtest")
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
        result = {
                "sid": sid,
                "status": 1,
                "error": str(e)
            }
    if cerebro:
        del cerebro
    # gc.collect()
    return result


def get_assets(rq_config):
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
    if cerebro:
        del cerebro
    return avaiables[500:600]


def main():
    rq_config = {
        "cash": 100000,
        "client_id": "e9f8cd38-e73c-453f-8a47-55beda640ae6", 
        "fromdate": 20000101,
        "todate": 20260101,
        "benchmark": b"000001"
    }
    # pending = results = [] # bug ref to same ptr
    pending = []
    results = []
    ray_window = 4 # to avoid put all tasks
    assets = get_assets(rq_config)
    
    ray.init(address="auto", 
             namespace="backtest", 
             ignore_reinit_error=True,
             runtime_env={"env_vars": env_vars}  # <--- 关键！自动分发到所有节点
            ) 

    agents = []
    pool_idx = 0
    while True:
        try:
            actor = ray.get_actor(f"StoreAgent_Local_{pool_idx}")
            agents.append(actor)
            pool_idx += 1
        except ValueError:
            break
    
    if not agents:
        print("No Global Pool agents found. Switching to Binding/Auto mode (store_agent=None).")
        use_explicit_agent = False
    else:
        print(f"Found {len(agents)} Global Pool agents. Using Round-Robin distribution.")
        use_explicit_agent = True

    pending = []
    results = []
    agent_counter = 0
    ray_window = 2
    assets = get_assets(rq_config) # 假设有 1000 个 assets
    total_assets = len(assets)
    
    config_ref = ray.put(rq_config)

    def submit():
        nonlocal agent_counter
        if not assets:
            return None
        
        sid_map = assets.pop()
        
        current_agent = None
        if use_explicit_agent:
            current_agent = agents[agent_counter % len(agents)]
        
        agent_counter += 1
        
        return run_backtest.remote(
            config_ref, 
            sid_map, 
            store_agent=current_agent)

    for _ in range(ray_window): 
        if assets:
            pending.append(submit()) # partial(submit_task, nodes=node_ids, rq_config=rq_config) 

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
                traceback.print_exc()

        if assets:
            pending.append(submit())

    print("All done!")
    # ray.shutdown()


if __name__ == '__main__':
    main()
