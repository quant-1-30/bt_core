import uuid
import numpy as np
import polars as pl
import backtest as bt
import backtest.indicators as btind
from backtest.utils.dateintern import ts2intdt

from typing import Dict, Any
from collections import defaultdict
from dotenv import load_dotenv


class PanelRanker(bt.Indicator):
    lines = ('dummy',) 

    params = (
        ("parquet_path", None),
        ('thres', 0.0), 
        ('top_k', 5),
    )

    def __init__(self):
        self.context_info = defaultdict(dict)

        lf = pl.scan_parquet(self.p.parquet_path)
        
        # ==========================================
        # group by day and struct columns
        # ==========================================
        agg_df = (
            lf
            .with_columns(
                pl.col("sid").cast(pl.Binary)
            )
            .filter(pl.col("score") > self.p.thres)
            .group_by("day")
            .agg(
                pl.struct(["sid", "score", "distance", "macro_state"])
                .sort_by("score", descending=True)
                .head(self.p.top_k)
                .alias("topk_info")
            )
        ).collect()

        for row in agg_df.iter_rows(named=True):
            day = row["day"]
            self.context_info[day] = {
                item["sid"]: item for item in row["topk_info"]
            }

    def next(self):
        current_day = ts2intdt(self.data.datetime[0])

        # self.lines.dummy[0] = 0.0 # dummy line to trigger next

        if current_day in self.context_info:
            info = self.context_info[current_day]
            self._owner.topk_info = info 


class FsmStrategy(bt.Strategy):

    params = (
        ("parquet_path", "/Users/hengxinliu/startup/backtest/workflow/data/fsm/*"),
    )

    def __init__(self):
        self.pr = PanelRanker(parquet_path=self.p.parquet_path)

    def next(self):
        current_tick = self.data.datetime[0]
        current_day = ts2intdt(current_tick)
        # print("FsmStrategy current_day ", current_day)
        seconds_in_day = int(current_tick) % 86400 # utc 28800
        snapshot = self.get_snapshot()
        psids = [p.sid for p in snapshot.positions]
        # print("psids ", psids)

        pending_sells = self.pnc.get_pending_sells()

        # =========================================================
        # stage1 09:30 —— Pending Sells
        # =========================================================
        if seconds_in_day == 34200:
            # mode eager
            self.sell(pending_sells.values())

        # =========================================================
        # stage2 14:55 —— FSM 
        # =========================================================
        elif seconds_in_day == 53700:
            topk_info = self.topk_info 
            if not topk_info: return
            current_prices = self.store.get_snapshot_tick(psids, int(current_tick))
            plan = self.pnc.generate_plan(topk_info, current_prices, snapshot, self.stats)
            # print("plan ", plan)

            # 【卖出指令生成】
            self.sell(plan["sell"])

            # 【买入指令生成】 可以重复建仓
            self.buy(plan["buy"])


if __name__ == '__main__':
    
    load_dotenv()
    cerebro = bt.Cerebro(client_id=uuid.UUID("e9f8cd38-e73c-453f-8a47-55beda640ae6").bytes, writer=False) 
    cerebro.addstore() 
    cerebro.addcontrol(5, "fixed", stake=0.9)

    # ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
    # wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)
    
    cerebro.addstrategy(FsmStrategy)

    # 600036/ 300308
    cerebro.run(cash=100000, sid=[b"000001"], fromdate=20100101, todate=20121231, benchmark=[b"000001"], out="signal.csv")
