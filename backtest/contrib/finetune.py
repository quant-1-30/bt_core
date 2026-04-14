#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import json
import ray
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from typing import List, Any, Dict
from ray import tune
from ray.tune.search.optuna import OptunaSearch

from workflow.function import _initialize_mdapi
from workflow.strategy.astc import run_pipeline
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
    # tick
    body = QueryBody(start_date=start_date, end_date=end_date, sid=universe)
    tick_data = md_api.get_subscribe(body, adj)
    # benchmark
    bench_body = QueryBody(start_date=start_date-10000, end_date=end_date, sid=[benchmark]) 
    bench_data = md_api.get_benchmark(bench_body)
    return {"benchmark": bench_data[benchmark], "tick": tick_data}


def train_hpo(start_date=20100101, end_date=20111231, benchmark=b"000001", market="6", frac:float=0.1, stats_window=[5,10,20], 
                num_samples:int =200, max_concurrency:int=10, topK=5):
     
    data = preload(
        start_date=start_date, 
        end_date=end_date, 
        benchmark=benchmark,
        market=market, # 6/688/0/3
        frac=frac,
        adj=FactorTopic.Hfq
    )
    print("finish preload data")
    
    # Object store and publish to worker
    data_ref = ray.put(data) 

    search_space = {
        # extract median
        "signal_type": tune.choice(["vwap", "vpt"]),

        # m <= 50 
        "downsample": tune.choice([15, 20, 30, 60]), 
        "ndays": tune.choice([1, 2, 3]), 

        # dtw / linalg_norm
        "threshold_r": tune.uniform(0.70, 0.95),
        "dtw_window_frac": tune.choice([0.05, 0.10, 0.15, 0.20]), 

        # metrics
        "penalty_m": tune.choice([20, 30, 40]), 

        # rolling
        "loopback": tune.choice([126, 252]),
        "gpd_quantiles": tune.choice([[0.10, 0.30, 0.70, 0.90], [0.20, 0.40, 0.60, 0.80], [0.05, 0.25, 0.75, 0.95]]),
        "gpd_freq_month": tune.choice([3, 6]), # update frequency 
    }

    # --- 配置 ASHA 算法 (早停) 避免score -np.inf ---
    # metric: 优化目标, mode:最大化 / grace_period: 至少跑多久才开始判断 / reduction_factor: 每轮淘汰比例
    asha_scheduler = tune.schedulers.ASHAScheduler( 
        metric="metrics_score", # target
        mode="max", 
        grace_period=1, # util when to criterior
        reduction_factor=4 # 
    )
    
    # --- 启动 Tuner ---
    wrapped_trainable = tune.with_resources(
        tune.with_parameters(
            run_pipeline,
            data_ref=data_ref,
            stats_window=stats_window,
            actual_date=start_date  
        ),
        resources={"cpu": 1, "gpu": 0} # intend for every trial
    )
    search_alg = HyperOptSearch()

    tuner = tune.Tuner( 
        wrapped_trainable, 

        param_space=search_space,
        
        tune_config=tune.TuneConfig(
            # search_alg=search_alg,
            num_samples=num_samples,            
            max_concurrent_trials=max_concurrency,    
            scheduler=asha_scheduler

        ),
        
        run_config=tune.RunConfig(
            name="my_strategy_hpo",
            storage_path="/tmp/ray_tune_results",
        ),
    )
    results = tuner.fit()
    # search_alg.save("./my-checkpoint.pkl")
    # search_alg2.restore("./my-checkpoint.pkl")

    # --- 分析结果 ---
    best_trial = results.get_best_result(metric="metrics_score", mode="max")
    print("="*30)
    print("Best trial config: {}".format(best_trial.config))
    print("Best trial final: {}".format(best_trial.metrics))
    
    class CustomEncoder(json.JSONEncoder):
        
        def default(self, obj):
            if isinstance(obj, np.ndarray):
                return list(obj)
            
            if isinstance(obj, np.float64):
                return float(obj)
            return super().default(obj)
 

    with open("metric.json", "w+") as f:
        json.dump(best_trial.metrics, f, indent=4, cls=CustomEncoder, ensure_ascii=False) 

    df = results.get_dataframe()
    df.to_csv("finetune.csv")
    # 3D Visual
    plot_tune_landscape_3d(df, "config/threshold_r", "config/downsample")
    # topk
    topK=5
    print(f"========== Top {topK} Trials ==========")
    valid = df[df["metrics_score"] > -np.inf].copy()
    top_k_df = valid.sort_values(by="metrics_score", ascending=False).head(topK)
    
    for idx, row in top_k_df.iterrows():
        cfg = {k.replace("config/", ""): v for k, v in row.items() if k.startswith("config/")}
        print(f"Trial: {row['trial_id']} | Status: {row['status']} | Score: {row['metrics_score']:.4f} | Config: {cfg}")


if __name__ == "__main__":

    env_vars = { 
      "OMP_NUM_THREADS": "1",
      "MKL_NUM_THREADS": "1",
      "OPENBLAS_NUM_THREADS": "1",
      "VECLIB_MAXIMUM_THREADS": "1",
      "NUMEXPR_NUM_THREADS": "1"
    }

    ray.init(address="auto", 
             namespace="backtest", 
             runtime_env={"env_vars": env_vars}, # 
            ignore_reinit_error=True
    )
    train_hpo() 
