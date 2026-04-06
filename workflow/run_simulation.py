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


def run_backtest(config_ref, sid_map, store_agent=None):
    sid = sid_map["sid"]
    print("run_backtest sid ", sid)
    try:
        cerebro = bt.Cerebro(client_id=uuid.UUID(config_ref["client_id"]).bytes, writer=False)  
        cerebro.addstore("ray", agent=store_agent) 
        ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
        wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

        cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)

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


def calculate_gpd_cvar(returns, confidence_level=0.99):
    """基于 GPD 计算 99% 极值条件在险价值 (CVaR)"""
    # ====== 在仓位管理中的应用 ======
    # position_rate = tolerance / GPD_CVaR = 5% / 12% = 41.6% 
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

