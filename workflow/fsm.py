# Best trial config: {'rolling_freq': 28, 'ewm_span': 27, 'downsample': 16, 'ndays': 1, 'threshold_r': 0.9365181748464984}

#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os
import ray
import math
import numpy as np
import pyarrow as pa
import polars as pl
from typing import List, Any, Dict

from bt_sdk.core.client import FactorTopic
from bt_sdk.core.protocol import QueryBody


class BayesianOnlineFSM:
    def __init__(self, prior_matrix):
        # Postperior Dirichlet
        self.prior_matrix = prior_matrix # np.ones((num_macro_states, num_micro_bins))
        # to cache pending state
        self.pending_update = None 

    def update_posterior(self, realized_ret, gpd_edges):
        if self.pending_update is not None and len(gpd_edges) > 0:
            pre_macro_state = self.pending_update["macro_state"]
            
            real_bin = np.digitize(realized_ret, gpd_edges)
            real_bin = min(max(real_bin, 0), self.num_micro - 1) # to avoid surpass
            
            self.prior_matrix[pre_macro_state, real_bin] += 1.0
            
            self.pending_update = None

    def predict_expected_return(self, macro_state, gpd_centers):
        row_counts = self.prior_matrix[macro_state, :]
        probs = row_counts / np.sum(row_counts)
        return float(np.sum(probs * gpd_centers))

    def track_state(self, macro_state):
        self.pending_update = {"macro_state": macro_state}


# ==========================================
# Ray Worker
# ==========================================
@ray.remote(num_cpus=0.2)
def run_pipeline(
    sid: bytes, 
    start_date: int, 
    end_date: int, 
    config: dict, 
    learned_motif: ray.ObjectRef, 
    fsm_prior: ray.ObjectRef,
    macro_state_ref: ray.ObjectRef, 
    bench_ref: ray.ObjectRef
    ):
    output_dir = "/tmp/backtest_results/parquet"
    os.makedirs(output_dir, exist_ok=True)
    parquet_path = f"{output_dir}/{sid.decode('utf-8')}.parquet"
    
    md_api = _initialize_mdapi()
    tick_data = md_api.get_subscribe(QueryBody(start_date=start_date, end_date=end_date, sid=[sid]), adj=FactorTopic.Hfq)
    
    if sid not in tick_data or tick_data[sid].num_rows == 0:
        return {"sid": sid, "status": "no_data"}
        
    hf_df = extract_from_beta_with_freq(
        raw=pl.from_arrow(tick_data[sid]), bench_ref=bench_ref, 
        rolling_freq=config["rolling_freq"], ewm_span=config["ewm_span"]
    )
    
    m = int(config["ndays"] * np.floor(4 * 60 / config["downsample"]))
    eod_data = extract_asset_feature(hf_df=hf_df, downsample=config["downsample"], m=m, amplify=1000)
    
    if len(eod_data) < 2: return {"sid": sid, "status": "insufficient_data"}
    
    threshold_d = math.sqrt(2 * m * (1 - config["threshold_r"]))
    z_motif = robust_z_normalize(learned_motif)
    fsm = BayesianOnlineFSM(prior_matrix=fsm_prior)

    records =[]
    history_returns =[] 
    current_gpd_edges = np.array([])
    current_gpd_centers = np.array([])
    current_quarter = 0
    
    for today in eod_data:
        date_int = today["date_int"]
        curve_m = today["curve"]
        daily_ret = today["daily_ret"]
        daily_beta = today["last_beta"] 
        
        history_returns.append(daily_ret)
        
        quarter = (date_int % 10000 // 100 - 1) // 3 + 1
        if quarter != current_quarter or len(current_gpd_edges) == 0:
            current_gpd_edges, current_gpd_centers = calculate_gpd(history_returns[-1000:])
            current_quarter = quarter
            
        fsm.update_posterior(realized_ret=daily_ret, gpd_edges=current_gpd_edges)
            
        z_today = robust_z_normalize(curve_m)
        dist = np.linalg.norm(z_today - z_motif)
        
        if dist < threshold_d:
            macro_state = macro_state_ref.get(date_int, 1) 
            
            pred_score = fsm.predict_expected_return(macro_state, current_gpd_centers)
            
            records.append({
                "date": date_int, "sid": sid.decode("utf-8"),
                "distance": float(dist), "beta": float(daily_beta),
                "macro_state": int(macro_state), "pred_score": float(pred_score)
            })
            
            fsm.track_state(macro_state)
            
    if records:
        pl.DataFrame(records).write_parquet(parquet_path)
        return {"sid": sid, "status": "success", "triggers": len(records), "path": parquet_path}
    return {"sid": sid, "status": "no_triggers"}
