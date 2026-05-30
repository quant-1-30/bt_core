import numpy as np
import datetime
from bt_sdk.core.client import GetMdApi


class XtpMarketGateway:
    def __init__(self, universe, ndays=3):
        self.universe = universe
        self.ndays = ndays
        self.m_length = ndays * 240
        
        self.market_matrix = np.zeros((len(universe), self.m_length), dtype=np.float32)
        self.sid_2_idx = {sid: i for i, sid in enumerate(universe)}
        
        # 每日数据分界线
        self.today_start_idx = (ndays - 1) * 240 

    def pre_market_warmup(self):
        """ 09:15 盘前调用拉取历史填满"""
        # md_api = _initialize_mdapi()
        md_api = None
        
        history_data = md_api.get_history_minutes(self.universe, days=self.ndays-1)
        
        for sid, mins_array in history_data.items():
            idx = self.sid_2_idx[sid]
            self.market_matrix[idx, :self.today_start_idx] = mins_array

    def on_xtp_minute_bar_closed(self, sid: str, minute_time: datetime.time, close_price: float):
        """ 盘中 09:30-14:55 XTP 回调更新 """
        minutes_passed = self._time_to_minutes(minute_time)
        
        idx = self.sid_2_idx.get(sid)
        if idx is not None:
            self.market_matrix[idx, self.today_start_idx + minutes_passed] = close_price

    def get_1455_snapshot(self):
        """ 14:55 获取全市场拼接好的完整曲线！ """
        end_idx = self.today_start_idx + 235
        return self.market_matrix[:, :end_idx]

