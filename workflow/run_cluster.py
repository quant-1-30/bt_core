#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os

# numpy auto use all cpus so to restricted
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import ray
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from functools import partial
from typing import List, Any, Dict

from bt_sdk.core.protocol import QueryBody
from workflow.strategy.fsm import run_pipeline
from workflow.preprocess import _initialize_mdapi


def preload(start_date: int, end_date: int, benchmark: bytes, market: str):
     # 0 1 2 / raw qfq hfq
    print("📡 获取全市场股票池...")
    md_api = _initialize_mdapi()
    table = md_api.get_instrument()
    mask = pc.starts_with(table["sid"], market) 
    universe = table.filter(mask).column("sid").cast(pa.binary()).to_pylist()
    
    # benchmark
    bench_body = QueryBody(start_date=start_date-20000, end_date=end_date, sid=[benchmark]) 
    bench_data = md_api.get_benchmark(bench_body)
    return (universe, bench_data[benchmark])


# ==========================================
# Orchestration
# ==========================================
def dipatch(start_date, end_date, market, benchmark):
    print("🚀 初始化 Ray 分布式集群...")

    # env_vars = { # numpy auto use all cpus
    #   "OMP_NUM_THREADS": "1",
    #   "MKL_NUM_THREADS": "1",
    #   "OPENBLAS_NUM_THREADS": "1",
    #   "VECLIB_MAXIMUM_THREADS": "1",
    #   "NUMEXPR_NUM_THREADS": "1"
    # }

    ray.init(
        ignore_reinit_error=True,
        # runtime_env={"env_vars": json.dumps(env_vars)}, # 
    )

    # object_ref ---> zero_copy and read  
    universe, bench_data = preload(start_date, end_date, benchmark, market)
    bench_ref = ray.put(bench_data)

    # load agents
    agents = []
    node_id = 0
    while True:
        try:
            actor = ray.get_actor(f"MdapiAgent_Local_{node_id}" )
            agents.append(actor)
            node_id += 1
        except ValueError:
            break
    
    if not agents:
        # use_explicit_agent = True
        raise ValueError("No Global Pool agents found. Switching to Binding/Auto mode (store_agent=None).")
    print(f"Agent Num {len(agents)}") 

    # load config
    config = {}
    config["start_date"] = start_date
    config["end_date"] = end_date
    config_ref = ray.put(config)

    print(" Dispatcher Ray Worker...")
    results = []

    # Head Node: N RayAgent 
    pending = [agents[i % 10].submit.remote(sid, config_ref, bench_ref) for i, sid in enumerate(universe[:10])]

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
    success_cnt = sum(1 for r in results if r["status"] == "success")
    total_triggers = sum(r.get("triggers", 0) for r in results)
    print("=========================================")
    print(f"success rate : {success_cnt}/{len(universe)}")
    print(f"📁 {total_triggers} writer /tmp/backtest_results/parquet")
    print("=========================================")
    # ray.shutdown()


if __name__ == "__main__":

    start_date=20200102
    end_date=20260228
    market="6"
    benchmark=b"000001"

    dipatch(start_date, end_date, market, benchmark)
