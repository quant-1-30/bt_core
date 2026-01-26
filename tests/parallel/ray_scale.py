import os
import ray
import uuid
import numpy as np

from itertools import compress
from dotenv import load_dotenv
from functools import partial
from joblib import Parallel, delayed
from typing import Dict, Any

import backtest as bt
from tests.parallel.sample import *


# ------------------------------------------------------------------- scale ----------------------------------------------------------------

def run_strategy(meta, config):
    cerebro = bt.Cerebro(client_id=uuid.UUID(config["client_id"]).bytes, writer=False)  
    try:
        ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
        wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)

        cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, ddata) 
        cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal) 

        cerebro.addsizer() # default fixed 
        cerebro.addrisk(thres=0.75) # default tl
        sid = meta["sid"]
        benchmark = config["benchmark"]

        cerebro.run(
            cash = config["cash"],
            sid = [sid],
            fromdate = config["fromdate"], 
            todate = config["todate"], 
            benchmark = benchmark,
            out="%s.csv" % sid
        )
        result =  {"sid": sid, "status": 0}
    except Exception as e:
        result = {
                "sid": sid,
                "status": 1,
                "error": str(e)
            }
    return result

# ==========================================
# Ray + Multiprocessing 混合并行层
# ==========================================

@ray.remote
def dispatcher(batches, config):
    
    pool_size = min(len(batches), os.cpu_count() - 1)
    
    # with multiprocessing.Pool(processes=pool_size) as pool: # apply_async / imap_unordered / submit 
    #     results = pool.map(run_strategy, tasks)

    rpc = partial(run_strategy, config=config)
    results = Parallel(n_jobs=pool_size)(delayed(rpc)(meta) for meta in batches) # Parallel(n_jobs=2, return_as="generator")
    return results


def filter_markets(markets, ranges):
    if not markets:
        return []

    delist = [m['delist'] if m['delist'] else np.inf for m in markets]
    first = [m['first_trading'] for m in markets]

    arr_delist = np.array(delist) # dtype='datetime64[D]'
    arr_first = np.array(first)

    keep_mask = (arr_first <= ranges[1]) & (arr_delist >= ranges[0])
    return list(compress(markets, keep_mask))


def main():
    load_dotenv()
    ray.init(address="auto", ignore_reinit_error=True) # --address auto # connect exist cluster 

    BATCH_SIZE = 4 
    rq_config = {
        "cash": 10000,
        "client_id": "e9f8cd38-e73c-453f-8a47-55beda640ae6", 
        "fromdate": 20080101,
        "todate": 20260101,
        "benchmark": b"000001"
    }
    cerebro = bt.Cerebro(client_id=uuid.UUID(rq_config["client_id"]).bytes, writer=False)  
    cerebro._preload()

    ranges = [rq_config["fromdate"], rq_config["todate"]]
    avaiables = filter_markets(cerebro.markets, ranges)

    ray_task = dispatcher.options(num_cpus=BATCH_SIZE) # schedule based on task cpu

    ray_futures = []
    for i in range(0, len(avaiables), BATCH_SIZE):
        batch = avaiables[i : i + BATCH_SIZE]

        future = ray_task.remote(batch, rq_config)
        ray_futures.append(future)

    print(f"Submitted {len(ray_futures)} Ray tasks processing {len(avaiables)} SIDs...")

    batch_results = ray.get(ray_futures)
    
    from itertools import chain
    output = list(chain(*batch_results))

    success_count = 0
    for res in output:
        if res['status'] == 0:
            success_count += 1
        else:
            print(f"SID: {res['sid']} Failed: {res['error']}")

    print(f"Done. Success: {success_count}/{len(output)}")
    
    ray.shutdown()

if __name__ == '__main__':
    main()