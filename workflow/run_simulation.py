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
        ('thres', 0.3), 
        ('top_k', 5),
    )

    def __init__(self):
        self.context_info = defaultdict(dict)
        self.notify = self._owner.notify  

        lf = pl.scan_parquet(self.p.parquet_path)
        
        # ==========================================
        # group by day and struct columns
        # ==========================================
        agg_df = (
            lf.filter(pl.col("score") > self.p.thres)
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
        current_day = ts2intdt(self.data.datetime.date(0))

        if current_day in self.context_info:
            info = self.context_info[current_day]
            self._onwner.topk_info = info 


class FsmMasterStrategy(bt.Strategy):

    def next(self):
        current_tick = self.data.datetime[0]
        seconds_in_day = int(current_tick) % 86400 # utc 28800
        snapshot = self.get_snapshot()

        pending_sells = self.taskplan.get_pending_sells()

        # =========================================================
        # stage1 09:31 —— Pending Sells
        # =========================================================
        if seconds_in_day == 34260:
            pending = self.taskplan.pending_sells
            # mode eager
            super().sell(pending_sells)

        # =========================================================
        # stage2 14:55 —— FSM 
        # =========================================================
        elif seconds_in_day == 53700:
            topk_info = self.get_notify_info()  # how to get info from PanelRanker? 通过 strategy.notify() 传递信息? 
            if not topk_info: return

            self.pnc.generate_plan(topk_info, snapshot, rish_tl) 
            plan = self.pnc.to_plan()

            # 【卖出指令生成】
            super().sell(plan["sell"])

            # 【买入指令生成】 可以重复建仓
            super().buy(plan["buy"])


if __name__ == '__main__':
    
    load_dotenv()
    cerebro = bt.Cerebro(client_id=uuid.UUID("e9f8cd38-e73c-453f-8a47-55beda640ae6").bytes, writer=False) 
    cerebro.addstore() 
    cerebro.addcontrol(5, "fixed", stake=0.9)

    ddata = cerebro.resampledata(timeframe=bt.TimeFrame.Days, adjbartime=False)
    wdata = cerebro.resampledata(timeframe=bt.TimeFrame.Weeks, adjbartime=False)
    
    cerebro.addstrategy(FsmMasterStrategy)

    # 600036/ 300308
    cerebro.run(cash=100000, sid=[b"000001"], fromdate=20200101, todate=20260201, benchmark=[b"000001"], out="signal.csv")
