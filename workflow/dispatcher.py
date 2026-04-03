#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import ray
import numpy as np
import pyarrow.compute as pc
from typing import List, Any, Dict

from bt_sdk.core.protocol import QueryBody
from workflow.fsm import run_pipeline


def preload(start_date: int, end_date: int, benchmark: bytes, market: str):
     # 0 1 2 / raw qfq hfq
    print("📡 获取全市场股票池...")
    md_api = _initialize_mdapi()
    table = md_api.get_instrument()
    mask = pc.starts_with(table["sid"], market) 
    universe = table.filter(mask).column("sid").cast(pa.binary()).to_pylist()
    print(f"✅ 找到标的数量: {len(universe)}")
    
    # benchmark
    bench_body = QueryBody(start_date=start_date, end_date=end_date, sid=[benchmark]) 
    bench_data = md_api.get_benchmark(bench_body)
    
    # macro_benchmark
    print("📊 Head Node Benchmark rolling 252 macro state")
    bench_252_body = QueryBody(start_date=start_date - 20000, end_date=end_date, sid=[benchmark])
    bench_252_data = md_api.get_benchmark(bench_252_body)
    return (universe, bench_data[benchmark], bench_252_data[benchmark])


# ==========================================
# Orchestration
# ==========================================
def dipatch(start_date, end_date, market, benchmark=b"000001"):
    print("🚀 初始化 Ray 分布式集群...")
    ray.init(ignore_reinit_error=True)

    universe, bench_data, bench_252_data = preload(start_date, end_date, market, benchmark)

    # object_ref ---> zero_copy and read  
    bench_ref = ray.put(bench_data)

    macro_state = compute_rolling_macro_states(bench_252_data)
    macro_ref = ray.put(macro_state) 
    
    print(" Dispatcher Ray Worker...")
    # config / vec_m / fsm read from file

    futures =[]
    for sid in universe: 
        future = run_pipeline.remote(
            sid=sid,
            start_date=start_date,
            end_date=end_date,
            config=BEST_CONFIG,
            learned_motif=HYPOTHETICAL_MOTIF,
            fsm_prior=INITIAL_FSM_PRIOR,
            macro_state_ref=macro_ref,
            bench_ref=bench_ref
        )
        futures.append(future)
    
    results = ray.get(futures)
    
    success_cnt = sum(1 for r in results if r["status"] == "success")
    total_triggers = sum(r.get("triggers", 0) for r in results)
    print("=========================================")
    print(f"success rate : {success_cnt}/{len(universe)}")
    print(f"📁 {total_triggers} writer /tmp/backtest_results/parquet")
    print("=========================================")


if __name__ == "__main__":

    start_date=20200102
    end_date=20260228
    market="6"

    dispatcher(start_date, end_date, market)
