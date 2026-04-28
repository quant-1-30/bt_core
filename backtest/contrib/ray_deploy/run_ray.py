#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os

# numpy auto use all cpus so to restricted
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import json
import ray
import traceback
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from functools import partial
from typing import List, Any, Dict

from dotenv import load_dotenv
from bt_sdk.core.protocol import QueryBody
from workflow.strategy.fsm import run_pipeline
from workflow.function import _initialize_mdapi


def preload(start_date: int, end_date: int, benchmark: bytes, market: str):
    md_api = _initialize_mdapi()
    table = md_api.get_instrument()
    mask = pc.starts_with(table["sid"], market) 
    universe = table.filter(mask).column("sid").cast(pa.binary()).to_pylist()
    # benchmark
    bench_body = QueryBody(start_date=start_date-10000, end_date=end_date, sid=[benchmark]) 
    bench_data = md_api.get_benchmark(bench_body)
    return (universe, bench_data[benchmark])


# ==========================================
# Orchestration
# ==========================================
def dipatch(start_date, end_date, market, benchmark, output):
    # object_ref ---> zero_copy and read  
    universe, bench_data = preload(start_date, end_date, benchmark, market)
    bench_ref = ray.put(bench_data)

    # load agents
    agents = []
    node_id = 0
    max_retries = 5  

    while node_id < 10:  
        actor_name = f"MdapiAgent_Local_{node_id}"
        retries = 0
        actor = None
        
        while retries < max_retries:
            try:
                actor = ray.get_actor(actor_name, namespace="backtest")
                agents.append(actor)
                node_id += 1
                break  
            except ValueError:
                retries += 1
                print(f"[{retries}/{max_retries}] 未找到 {actor_name}，等待 GCS 注册...")
                time.sleep(1)  # used for ray gcs register

    if not agents:
        # use_explicit_agent = True
        raise ValueError("No Global Pool agents found. Switching to Binding/Auto mode (store_agent=None).")
    print(f"Agent Num {len(agents)}") 

    # load config
    with open("metric.json", "r") as f:
        config = json.load(f)
    
    config["start_date"] = start_date
    config["end_date"] = end_date
    config["output"] = output
    config_ref = ray.put(config)

    print(" Dispatcher Ray Worker...")
    # Head Node: N RayAgent
    pending = [agents[i % 10].submit.remote(sid, config_ref, bench_ref) for i, sid in enumerate(universe)]
    results = []

    while pending:
        done, pending = ray.wait(pending, num_returns=1)
        for ref in done:
            try:
                res = ray.get(ref)
                print("result: ",res)
                results.append(res)
                if len(results) % 5 == 0:
                    print(f"Progress: {len(results)}/{len(assets)}")
            except Exception as e:
                print(f"Task failed: {e}")
                traceback.print_exc()

    print("All done!")
    success_cnt = sum(1 for r in results if r["status"] == "success")
    total_triggers = sum(r.get("triggers", 0) for r in results)
    print("=========================================")
    print(f"success rate : {success_cnt}/{len(universe)}")
    print(f"📁 {total_triggers} writer /tmp/backtest_results/parquet")
    print("=========================================")


if __name__ == "__main__":

    load_dotenv()

    start_date=20000102
    end_date=20260228
    market="6"
    benchmark=b"000001"
    dipatch(start_date, end_date, market, benchmark)
