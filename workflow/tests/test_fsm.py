import os
import json
import math
import asyncio
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import polars as pl

from dotenv import load_dotenv
from bt_sdk.core.protocol import *
from bt_sdk.core.client import FactorTopic
from workflow.function import _initialize_mdapi, calculate_dtw_params
from workflow.strategy.fsm import run_pipeline


mdapi = _initialize_mdapi() # result attach to loop not ray loop

def preload(start_date: int, end_date: int, benchmark: bytes, market: str):
    table = mdapi.get_instrument()
    mask = pc.starts_with(table["sid"], market) 
    universe = table.filter(mask).column("sid").cast(pa.binary()).to_pylist()
    
    # benchmark
    bench_body = QueryBody(start_date=start_date-20000, end_date=end_date, sid=[benchmark]) 
    bench_data = mdapi.get_benchmark(bench_body)
    return (universe, bench_data[benchmark])


def get_tick(start_date: int, end_date: int, sid: bytes):
    body = QueryBody(start_date=start_date, end_date=end_date, sid=[sid])
    tick_data = mdapi.get_subscribe( 
        body, 
        FactorTopic.Hfq # 0 1 2 / raw qfq hfq
    )
    return tick_data


def submit(sid:bytes, config_ref: dict, bench_ref: pa.Table):
    initial_date = config_ref["start_date"] - int(config_ref["config"]["loopback"]/252) * 10000
    tickdata = get_tick(initial_date, config_ref["end_date"], sid)
    print("tickdata ", tickdata)
    result = run_pipeline(
            sid, 
            config_ref,
            tickdata,
            bench_ref
            )
    return result


if __name__ == "__main__":

    load_dotenv()

    start_date=20000102
    end_date=20260228
    market="6"
    benchmark=b"000001"
    # load config
    with open("metric.json", "r") as f:
        trial_config = json.load(f)
    
    trial_config["start_date"] = start_date
    trial_config["end_date"] = end_date
    trial_config["output"] = "."

    config = trial_config["config"] 
    config["m"] = int(config["ndays"] * np.floor(4 * 60 / config["downsample"]))
    config["threshold_d"] = math.sqrt(2 * config["m"] * (1 - config["threshold_r"])) 
    config["dtw_window"] = calculate_dtw_params(config)

    universe, bench_data = preload(start_date, end_date, benchmark, market)
    results = submit(universe[0], trial_config, bench_data)
    print("results: ", results)
