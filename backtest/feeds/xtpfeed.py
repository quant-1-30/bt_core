import numpy as np
import datetime
from bt_sdk.core.client import GetMdApi


class XtpMarketGateway:
    def __init__(self, universe, ndays=3):
        self.universe = universe
        self.ndays = ndays
        self.m_length = ndays * 240
        
        # 🌟 预分配全市场连续内存池 (5000股票 x 720分钟)
        # 行主序，极度缓存友好
        self.market_matrix = np.zeros((len(universe), self.m_length), dtype=np.float32)
        self.sid_2_idx = {sid: i for i, sid in enumerate(universe)}
        
        # 每日数据分界线
        self.today_start_idx = (ndays - 1) * 240 

    def pre_market_warmup(self):
        """ 09:15 盘前调用：拉取历史，填满前半截 """
        print("📥 开始盘前预热：拉取过去 N-1 天分钟数据...")
        md_api = _initialize_mdapi()
        
        # 伪代码：通过 gRPC 获取过去的数据
        history_data = md_api.get_history_minutes(self.universe, days=self.ndays-1)
        
        for sid, mins_array in history_data.items():
            idx = self.sid_2_idx[sid]
            # 填入矩阵前半部分 (0 ~ 479)
            self.market_matrix[idx, :self.today_start_idx] = mins_array

    def on_xtp_minute_bar_closed(self, sid: str, minute_time: datetime.time, close_price: float):
        """ 盘中 09:30-14:55 XTP 回调更新 """
        # 计算今天过去了多少分钟
        minutes_passed = self._time_to_minutes(minute_time)
        
        idx = self.sid_2_idx.get(sid)
        if idx is not None:
            # 🌟 原地涂写：填入矩阵当天的格子中 (480 ~ 719)
            self.market_matrix[idx, self.today_start_idx + minutes_passed] = close_price

    def get_1455_snapshot(self):
        """ 14:55 获取全市场拼接好的完整曲线！ """
        # 获取 0 到 14:55 (第 235 分钟) 的所有数据
        # 此时返回的是形状为 (5000, 715) 的二维矩阵！
        end_idx = self.today_start_idx + 235
        return self.market_matrix[:, :end_idx]

