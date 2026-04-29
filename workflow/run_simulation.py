import numpy as np
import polars as pl
import backtest as bt
import backtest.indicators as btind
from backtest.utils.dateintern import ts2intdt

from typing import Dict, Any
from collections import defaultdict


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
            self.notify(info) # strategy


class FsmMasterStrategy(bt.Strategy):

    def next(self):
        current_tick = self.data.datetime[0]
        seconds_in_day = int(current_tick) % 86400 # utc 28800

        # =========================================================
        # 时钟 1: 早盘 09:31 —— 肃清遗留死单 (Pending Sells)
        # =========================================================
        if seconds_in_day == 34260:
            pending = self.taskplan.pending_sells
            if pending:
                # mode eager
                self.sell(sids=sids_to_kill, execType=0, filler=b"open")

        # =========================================================
        # 时钟 2: 尾盘 14:55 —— FSM 换仓核心逻辑
        # =========================================================
        elif seconds_in_day == 53700:
            topk_info = self.get_notify_info()  # 从 Indicator 的 notify 里拿到的全局视野数据    
            if not topk_info: return

            sell_plan, buy_plan = self.taskplan.generate_plan(topk_info, snapshot, rish_tl)  
            
            # 【卖出指令生成】
            if sell_plan:
                self.sell(sids=sell_plan, execType=0, filler=b"close")

            # 【买入指令生成】 可以重复建仓
            if buy_plan:
                self.buy(sids=buy_plan, execType=0, filler=b"close")

    def notify_trade(self, trades):
        """真实成交回报 推进taskplan状态"""
        self.taskplan.on_filled(sid, trades)

