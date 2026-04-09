#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import json
import ray
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from typing import List, Any, Dict
from ray import tune

from workflow.function import _initialize_mdapi
from workflow.strategy.astc import *
from workflow.visual import plot_tune_landscape_3d
from bt_sdk.core.client import FactorTopic
from bt_sdk.core.protocol import QueryBody


def preload(start_date: int, end_date: int, benchmark: bytes, market: str, frac:float, adj=1): # 0 1 2 / raw qfq hfq
    md_api = _initialize_mdapi()

    # universe
    table = md_api.get_instrument() 
    mask = pc.and_(
        pc.less(table["first_trading"], end_date),
        # pc.greater(table["delist"], start_date)
        pc.starts_with(table["sid"], market)
    )
    filter_table = table.filter(mask)

    num_rows = filter_table.num_rows
    num_samples = int(frac * num_rows)
    result = filter_table.take(np.random.choice(num_rows, size=num_samples, replace=False))
    universe = result.column("sid").cast(pa.binary()).to_pylist() # view(pa.uint8())
    # benchmark
    bench_body = QueryBody(start_date=start_date, end_date=end_date, sid=[benchmark]) 
    bench_data = md_api.get_benchmark(bench_body)
    # tick
    body = QueryBody(start_date=start_date, end_date=end_date, sid=universe)
    tick_data = md_api.get_subscribe(body, adj)
    return {"benchmark": bench_data[benchmark], "tick": tick_data}


def train(start_date=20100101, end_date=20111231, benchmark=b"000001", market="6", frac:float=0.05, stats_window=[5,10,20], 
                num_samples:int =200): 

    print("🚀 初始化 Ray 分布式集群...")

    env_config = {}
    # env_vars = { # numpy auto use all cpus
    #   "OMP_NUM_THREADS": "1",
    #   "MKL_NUM_THREADS": "1",
    #   "OPENBLAS_NUM_THREADS": "1",
    #   "VECLIB_MAXIMUM_THREADS": "1",
    #   "NUMEXPR_NUM_THREADS": "1"
    # }

    ray.init(address="auto", 
            namespace="backtest", 
            # runtime_env={"env_vars": json.dumps(env_config)}, # 
            ignore_reinit_error=True)

    data = preload(
        start_date=start_date - 10000, 
        end_date=end_date, 
        benchmark=benchmark,
        market=market, # 6/688/0/3
        frac=frac,
        adj=FactorTopic.Hfq
    )
    print("finish preload data")

    config = {"signal_type": "vwap",
              "downsample": 20,
              "ndays": 2,
              "threshold_r": 0.1,
              "dtw_window_frac": 0.1,
              "penalty_m": 20,
              "loopback": 252,
              "gpd_quantiles": [0.10, 0.30, 0.70, 0.90],
              "gpd_freq_month": 3
            } 

    result = run_pipeline(config, data_ref=data, stats_window=stats_window,actual_date=start_date)
    
    class CustomEncoder(json.JSONEncoder):
        
        def default(self, obj):
            if isinstance(obj, np.ndarray):
                return list(obj)
            
            if isinstance(obj, np.float64):
                return float(obj)

    with open("metric.json", "w+") as f:
        json.dump(result, f, indent=4, cls=CustomEncoder, ensure_ascii=False) 


if __name__ == "__main__":

    train() 
