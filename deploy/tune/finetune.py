import ray
import os
import tempfile
from itertools import chain
from dotenv import load_dotenv
from typing import List, Any, Dict
from ray import tune, train

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
    tick = md_api.get_subscribe(body)
    return {"calendar": calendar, "instrument": instrument, "benchmark": bench, "adj": adj_factors, "tick": tick}


def run_backtest(config: Dict[str, Any], data_ref: Dict[str, Any]):
    try:
        # --- 初始化 Cerebro ---
        cerebro = bt.Cerebro(client_id=uuid.UUID(config["client_id"]).bytes, writer=False)
        cerebro.addstore("local", data_ref) 
        # cerebro.adddata(feed)

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
                            period_signal=config["macd_period"])
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
        train.report({"pnl": pnl, "sharpe": sharpe})
    except Exception as e:
        train.report({"pnl": -9999, "sharpe": -9999, "error": str(e)})


def train_hpo():
    # --- 启动 Ray ---
    ray.init(address="auto", namespace="backtest", ignore_reinit_error=True)
    # --- 数据预加载 (在 Driver 端执行一次) ---
    print("Preloading data...")
    data = preload(
        start_date=20100101, 
        end_date=20230101, 
        sid=[b"600036"], 
        benchmark=b"000001"
    )
    data_ref = ray.put(data) # Object store and publish to worker

    search_space = {
        # 通用回测配置
        "client_id": "e9f8cd38-e73c-453f-8a47-55beda640ae6",
        "cash": 100000,
        "sid": [b"600036"], 
        "fromdate": 20040101, 
        "todate": 20260201, 
        "benchmark": b"000001", 

        # MACD 信号的参数
        "macd_fast": tune.randint(5, 15),
        "macd_slow": tune.randint(20, 35),

        # Sell 信号的参数
        "sell_period": tune.choice([10, 15, 20]),
        "sell_thres": tune.uniform(0.80, 0.95),
    }

    # --- 配置 ASHA 算法 (早停) ---
    # metric: 优化目标, mode: 最大化, grace_period: 至少跑多久才开始判断
    # reduction_factor: 每轮淘汰比例（例如淘汰后 1/4 的 Trial）
    asha_scheduler = tune.schedulers.ASHAScheduler(
        metric="sharpe",
        mode="max",
        grace_period=1, 
        reduction_factor=4
    )
    
    # --- 启动 Tuner ---
    tuner = tune.Tuner(
        tune.with_parameters(run_backtest, data=data_ref), # big data ref
        
        param_space=search_space,
        
        tune_config=tune.TuneConfig(
            num_samples=200,             # 尝试 200 组参数
            max_concurrent_trials=12,    # 最大并发数
            scheduler=asha_scheduler     # 启用 ASHA 剪枝
        ),
        
        run_config=tune.RunConfig(
            name="my_strategy_hpo",
            storage_path="/tmp/ray_tune_results"
        )
    )

    results = tuner.fit()

    # --- 分析结果 ---
    best_trial = results.get_best_result(metric="sharpe", mode="max")
    print("="*30)
    print("Best trial config: {}".format(best_trial.config))
    print("Best trial final sharpe: {}".format(best_trial.metrics["sharpe"]))


if __name__ == '__main__':
    train_hpo()
