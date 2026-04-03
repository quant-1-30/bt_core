#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import ray
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from typing import List, Any, Dict
from ray import tune

import backtest as bt

from bt_sdk.core.client import GetMdApi, FactorTopic
from bt_sdk.core.protocol import QueryBody
from backtest.workflow.preprocess import _initialize_mdpai
from backtest.workflow.strategy.astc import *


def preload(start_date: int, end_date: int, benchmark: bytes, market: str, frac:float, adj=1): # 0 1 2 / raw qfq hfq
    md_api = _initialize_mdpai()

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


def train_hpo(start_date=20100101, end_date=20200101, benchmark=b"000001", market="6", frac:float=0.01, stats_window=[5,10,20], 
                num_samples:int =200, max_concurrency:int=10, topK=5): 
    # # --- 启动 Ray ---
    env_config = {}

    ray.init(address="auto", 
            namespace="backtest", 
            # runtime_env={"env_vars": json.dumps(env_config)}, # 
            ignore_reinit_error=True)

    print("preload data")
    data = preload(
        start_date=start_date, 
        end_date=end_date, 
        benchmark=benchmark,
        market=market, # 6/688/0/3
        frac=frac,
        adj=FactorTopic.Hfq
    )
    data_ref = ray.put(data) # Object store and publish to worker
    
    print("📊 Head Node Benchmark rolling 252 macro state")
    global_macro_dict = compute_rolling_macro_states(start_date, end_date, benchmark_sid=benchmark)
    macro_ref = ray.put(global_macro_dict)

    search_space = {
        # extract from beta
        "rolling_freq": tune.randint(5, 30), # m
        "ewm_span": tune.randint(5, 30), # ewm_span

        # downsample for stumpy 
        "downsample": tune.randint(10, 60),# minute
        "ndays":  tune.randint(1, 14),

        # stumpy tsc and filter
        "threshold_r": tune.uniform(0.8, 0.99),
    }

    # --- 配置 ASHA 算法 (早停) ---
    # metric: 优化目标, mode:最大化 / grace_period: 至少跑多久才开始判断 / reduction_factor: 每轮淘汰比例
    asha_scheduler = tune.schedulers.ASHAScheduler(
        metric="metrics_score",
        mode="max", 
        grace_period=1, 
        reduction_factor=4 
    )
    
    # --- 启动 Tuner ---
    wrapped_trainable = tune.with_resources(
        tune.with_parameters(
            run_pipeline,
            data_ref=data_ref,
            macro_ref=macro_ref,
            stats_window=stats_window  
        ),
        resources={"cpu": 8, "gpu": 0}
    )

    tuner = tune.Tuner( 
        wrapped_trainable, 

        param_space=search_space,
        
        tune_config=tune.TuneConfig(
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

    # --- 分析结果 ---
    best_trial = results.get_best_result(metric="metrics_score", mode="max")
    print("="*30)
    print("Best trial config: {}".format(best_trial.config))
    print("Best trial final sharpe: {}".format(best_trial.metrics)) 

    # Best trial config: {'rolling_freq': 28, 'ewm_span': 27, 'downsample': 16, 'ndays': 1, 'threshold_r': 0.9365181748464984}

    # # topk
    # print(f"========== Top {K} Trials ==========")
    # df = results.get_dataframe()
    # valid = df[df["metrics_score"] > -np.inf].copy()
    # top_k_df = valid.sort_values(by="metrics_score", ascending=False).head(topK)
    
    # top_k_configs =[]
    # for idx, row in top_k_df.iterrows():
    #     # Ray Tune 会把 config 平铺为 config/xxx
    #     cfg = {k.replace("config/", ""): v for k, v in row.items() if k.startswith("config/")}
    #     top_k_configs.append({
    #         "config": cfg,
    #         "metrics_score": row["metrics_score"],
    #         "fsm_prior_matrix": row.get("fsm_prior_matrix"), 
    #         "trial_id": row["trial_id"] 
    #     })
    #     print(f"Trial: {row['trial_id']} | Score: {row['metrics_score']:.4f} | Config: {cfg}")
        

if __name__ == "__main__":

    train_hpo() 
