import uuid
import numpy as np
import os
import multiprocessing
import ray
from dotenv import load_dotenv
from datetime import datetime

import backtest as bt
import backtest.indicators as btind


class WeekPriceSignal(btind.Indicator): 
    lines = ('signal',)
    params = (("period", 10),)

    def __init__(self):
        sma = btind.SMA(self.data0.close, period=self.p.period)
        self.lines.signal = sma / self.data1.close - 1.0


class DailyPriceSignal(btind.Indicator): 
    lines = ('signal',)
    params = (("period", 120),)

    def __init__(self):
        low_ind = btind.Lowest(self.data0.close, period=self.p.period) 
        self.lines.signal = self.data0.close / low_ind  - 2.0
    

class MACDSignal(btind.Indicator): 
    lines = ('signal',)
    params = (('period', 12), ('period1', 26), ('period2', 9),)

    def __init__(self):
        macd = btind.MACDHisto(self.data0.close, 
                            period_me1=self.p.period, 
                            period_me2=self.p.period1, 
                            period_signal=self.p.period2) 
        self.lines.signal = macd.histo


class VolSignal(btind.Indicator):
    lines = ("signal",)
    params = (("period", 10), ("thres", 1.1))

    def __init__(self):
        vsma = btind.SMA(self.data0.volume, period=self.p.period)
        self.lines.signal = vsma / (self.data0.volume * self.p.thres) - 1.0


class SellSignal(btind.Indicator): 
    lines = ("signal",)
    params = (("period", 10), ("thres", 0.85))

    def __init__(self): 
        high_ind = btind.Highest(self.data0.close, period=self.p.period) 
        self.lines.signal = self.data0.close / (high_ind * self.p.thres) - 1.0


class DrawDownSignal(btind.Indicator): 
    lines = ('signal',)
    params = (("thres", 0.25),)

    def next(self):
        obs = self._owner.stats.getbyname("drawdown") # ensure drawdown analyzer already added
        signal = self.p.thres - obs.lines.drawdown[0]
        self.lines.signal[0] = signal


def run_strategy(cerebro, args):

    sid, cash, start_date, end_date, benchmark = args
    
    try:
        # cerebro = bt.Cerebro(client_id=client_id)

        ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False, dataname=sid)
        wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False, dataname=sid)

        cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, wdata, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, ddata)
        cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, ddata) 
        cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal) 

        cerebro.addrisk("tl", thres=0.75)

        result = cerebro.run(
            cash=cash, 
            sid=[sid], 
            fromdate=start_date, 
            todate=end_date, 
            benchmark=benchmark,
            out=None 
        )
        
    except Exception as e:
        return {
            "sid": sid,
            "status": "failed",
            "error": str(e)
        }

# ==========================================
# 3. Ray + Multiprocessing 混合并行层
# ==========================================

@ray.remote
def on_submit(batch_sids, config):
    
    pool_size = min(len(batch_sids), multiprocessing.cpu_count() - 1)

    tasks = []
    for sid in batch_sids:
        tasks.append((
            sid, 
            config["cash"],
            config["client_id"], 
            config["start_date"], 
            config["end_date"], 
            config["benchmark"]
        ))
    
    # multiple_results = [pool.apply_async(os.getpid, ()) for i in range(4)]
    # for i in pool.imap_unordered(f, range(10))
    with multiprocessing.Pool(processes=pool_size) as pool:
        results = pool.map(run_strategy, tasks)

    # with ProcessPoolExecutor(max_worker=self.n_jobs) as pool:
    #     for jb in iterable:
    #         results = pool.submit(jb[0], *jb[1], **jb[2])
    #         results.add_done_callback(when_done)
    return results

# ==========================================
# 4. 主程序入口
# ==========================================

def main():
    load_dotenv()
    
    # address='auto' 用于连接现有集群，如果只是单机跑则不填
    ray.init(ignore_reinit_error=True) 

    client_uuid = uuid.UUID("e9f8cd38-e73c-453f-8a47-55beda640ae6")
    config = {
        'cash': 10000,
        'client_id': client_uuid.bytes,
        'start_date': 20200101,
        'end_date': 20260101,
        'benchmark': b"000001"
    }

    sids = 
    all_sids = [b"300308"] * 20 + [b"600000"] * 20 + [b"000001"] * 20
    
    BATCH_SIZE = 4 
    ray_task = on_submit.options(num_cpus=BATCH_SIZE) # ray schedule based on task cpu

    ray_futures = []
    for i in range(0, len(all_sids), BATCH_SIZE):
        batch = all_sids[i : i + BATCH_SIZE]

        future = ray_task.remote(batch, config)
        ray_futures.append(future)

    print(f"Submitted {len(ray_futures)} Ray tasks processing {len(all_sids)} SIDs...")

    batch_results = ray.get(ray_futures)
    
    from itertools import chain
    final_results = list(chain(*batch_results))

    success_count = 0
    for res in final_results:
        if res['status'] == 'success':
            success_count += 1
            # print(f"SID: {res['sid']}, Value: {res['final_value']:.2f}")
        else:
            print(f"SID: {res['sid']} Failed: {res['error']}")

    print(f"Done. Success: {success_count}/{len(final_results)}")
    
    ray.shutdown()

if __name__ == '__main__':
    main()