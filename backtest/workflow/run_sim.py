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
import backtest as bt
import ray.util.scheduling_strategies

from itertools import compress
from functools import partial
from joblib import Parallel, delayed
from typing import Dict, Any
from tests.sample.ind import *

env_vars = { # numpy auto use all cpus
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1"
}
import numpy as np

agent_counter = 0 # used to locate rayagent


@ray.remote(num_cpus=0.2, max_calls=1) # max_calls --- delete python process after finish
def run_backtest(config_ref, sid_map, store_agent=None):
    sid = sid_map["sid"]
    print("run_backtest sid ", sid)
    try:
        cerebro = bt.Cerebro(client_id=uuid.UUID(config_ref["client_id"]).bytes, writer=False)  
        cerebro.addstore("ray", agent=store_agent) 
        print("run_backtest calendar and markets ", len(cerebro.calendar_days), len(cerebro.markets))
        ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
        wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

        cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, ddata) 
        cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal) 

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
        print(f"Worker Error on {sid}: {err_msg}") # 这会在 Ray Driver 终端打印
        result = {
                "sid": sid,
                "status": 1,
                "error": str(e)
            }
    if cerebro:
        del cerebro
        gc.collect()
    return result


def submit(assets: dict, rq_config: dict, agents):
    # nonlocal agent_counter
    global agent_counter
    if not assets:
        return None
    
    current_agent = agents[agent_counter % len(agents)]
    print(f"Found Using Round-Robin distribution.")
    agent_counter += 1
    sid = assets.pop()
    return run_backtest.remote(
            rq_config,
            sid, 
            store_agent=current_agent
    )


def retrieve_assets(rq_config):
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
    if not avaiables:
        raise ValueError("assets Empty")
    if cerebro:
        del cerebro
        gc.collect()
    return avaiables[2000:3000]


def calculate_gpd_cvar(returns, confidence_level=0.99):
    """基于 GPD 计算 99% 极值条件在险价值 (CVaR)"""
    # ====== 在仓位管理中的应用 ======
    # 假设您的总资金是 100 万，您能承受的单日极限回撤是 5 万 (5%)
    # 正态分布可能告诉您全仓买入没事。但 GPD 告诉您 99% CVaR 是 12%！
    # 您的严格仓位上限 = 极限承受力 / GPD_CVaR = 5% / 12% = 41.6% (绝不满仓！)
    losses = -np.array(returns)
    threshold_percentile = 95
    u = np.percentile(losses, threshold_percentile)
    
    tail_losses = losses[losses > u] - u
    # c 是形状参数 (xi), loc 是位置参数(固定为0), scale 是尺度参数 (beta)
    shape_xi, loc, scale_beta = genpareto.fit(tail_losses, floc=0)
    
    # GPD CVar 相比于正态分布的 VaR
    tail_prob = 1.0 - (threshold_percentile / 100.0)
    alpha = 1.0 - confidence_level
    
    cvar_gpd = u + (scale_beta / (1 - shape_xi)) * ( ((tail_prob / alpha) ** shape_xi) - 1 )
    return cvar_gpd


def main(rq_config):
    ray.init(address="auto", 
             namespace="backtest", 
             ignore_reinit_error=True,
             runtime_env={"env_vars": env_vars}  # <--- key auto-dispatcher
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
        # use_explicit_agent = True
        raise ValueError("No Global Pool agents found. Switching to Binding/Auto mode (store_agent=None).")
    print(f"Agent Num {len(agents)}") 

    assets = retrieve_assets(rq_config)
    ray_submit = partial(submit, assets=assets, rq_config=rq_config, agents=agents)
    
    pending = []
    results = []
    ray_window = 100 # to avoid put all tasks
    for _ in range(ray_window): 
        pending.append(ray_submit()) 

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
            pending.append(ray_submit())

    print("All done!")
    # ray.shutdown()


if __name__ == '__main__':
    rq_config = {
        "cash": 100000,
        "client_id": "e9f8cd38-e73c-453f-8a47-55beda640ae6", 
        "fromdate": 20200101,
        "todate": 20260101,
        "benchmark": b"000001"
    }

    main(rq_config)
