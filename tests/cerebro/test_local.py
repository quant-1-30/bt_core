import os
import uuid
import backtest as bt
from itertools import chain
from dotenv import load_dotenv
from typing import List, Any, Dict

from bt_sdk.core.client import GetMdApi
from bt_sdk.core.protocol import QueryBody
from deploy.strategy.test_signal import *
from backtest.runner.async_runner import AsyncRunner


def _initialize_mdpai():
    md_addr = os.getenv("MD_ADDR", "127.0.0.1:50051").split(":")
    mdapi = GetMdApi(addr=(md_addr[0], int(md_addr[1])))
    _runner = AsyncRunner()
    _runner.start() # new_event_loop
    _loop = _runner.get_loop()
    mdapi.start(_loop)
    return mdapi


def preload(start_date: int, end_date: int, sid: List[str], benchmark):
    md_api = _initialize_mdpai()

    body = QueryBody(start_date=start_date, end_date=end_date, sid=sid)
    bench_body = QueryBody(start_date=body.start_date, end_date=body.end_date, sid=[benchmark]) 

    # calendar
    datas = md_api.get_calendar()
    calendar = list(chain(*datas))
    # instrument
    table = md_api.get_instrument() 
    # ctable = pa.concat_tables(tables, promote_options="permissive") # zero_copy , but combine_chunk is heavy memory ops
    instrument = table.to_pylist() # row-wise dict list / table.to_pandas() and df.to_dict('records') # Arrow --> Pandas
    # benchmark
    bench_data = md_api.get_benchmark(bench_body)
    bench = bench_data[benchmark]
    # adj
    adj_data = md_api.get_factor(body)
    adj = adj_data[sid[0]]
    factors = adj.raw_factors if adj else {} # adj_factors
    adj_factors = dict(sorted(factors.items())) # sort by key
    # tick
    tick_data = md_api.get_subscribe(body)
    return {"calendar": calendar, "instrument": instrument, "benchmark": bench, "adj": adj_factors, "tick": tick_data[sid[0]], "sid": sid}


def run_backtest(config: Dict[str, Any], data_ref: Dict[str, Any]):
    # try:
        # --- 初始化 Cerebro ---
        cerebro = bt.Cerebro(client_id=uuid.UUID(config["client_id"]).bytes, writer=False)
        cerebro.addstore("local", ref=data_ref, config=config) 

        ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
        wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)
        
        # --- 添加信号/策略，并注入 Tune 参数 ---
        cerebro.add_signal(bt.SIGNAL_LONG, WeekPriceSignal, 
                            wdata, 
                            ddata,
                            period=config["week"])
        cerebro.add_signal(bt.SIGNAL_LONG_INV, DailyPriceSignal, 
                            ddata,
                            period=config["daily"])
        cerebro.add_signal(bt.SIGNAL_LONG, MACDSignal, 
                            ddata,
                            period_me1=config["macd_me1"], 
                            period_me2=config["macd_me2"], 
                            period_signal=config["macd"])
        cerebro.add_signal(bt.SIGNAL_LONG, VolSignal, 
                            ddata,
                            period=config["vol"], 
                            thres=config["vol_thres"])
        cerebro.add_signal(bt.SIGNAL_SHORT, SellSignal, 
                            ddata,
                            period=config["sell"], 
                            thres=config["sell_thres"]) 
        cerebro.add_signal(bt.SIGNAL_SHORT, DrawDownSignal, 
                            thres=config["dd_thres"]) 
        # --- 运行 ---
        results = cerebro.run(cash=config["cash"], 
                            sid=config["sid"], 
                            fromdate=config["fromdate"], 
                            todate=config["todate"], 
                            benchmark=config["benchmark"]
                            )
        # --- 获取指标 ---
        pnl = results.get('pnl', -9999)
        sharpe = results.get('sharpe', -9999)
        tune.report({"pnl": pnl, "sharpe": sharpe})
    # except Exception as e:
    #     tune.report({"pnl": -9999, "sharpe": -9999, "error": str(e)})


def train_hpo():
    print("Preloading data...")
    data = preload(
        start_date=20100101, 
        end_date=20230101, 
        sid=[b"600036"], 
        benchmark=b"000001"
    )

    search_space = {
        "client_id": "e9f8cd38-e73c-453f-8a47-55beda640ae6",
        "cash": 100000,
        "sid": [b"600036"], 
        "fromdate": 20040101, 
        "todate": 20260201, 
        "benchmark": b"000001", 
        
        # WeekPriceSignal
        "week": 10,

        # DailyPriceSignal
        "daily": 120,

        # MACDSignal
        "macd_me1": 12,
        "macd_me2": 26,
        "macd": 10,

        # VolSignal
        "vol": 10,
        "vol_thres": 1.1,
        
        # VolSignal
        "sell": 10,
        "sell_thres": 0.85 ,

        # DrawDownSignal
        "dd_thres": 0.2,
    }
    run_backtest(search_space, data)


if __name__ == '__main__':
    load_dotenv()
    train_hpo()
