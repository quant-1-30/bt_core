#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

import collections
import io
import itertools
import sys
import pandas as pd


class LogConsumerThread(threading.Thread):
    def __init__(self, log_shm, filepath):
        super().__init__()
        self.log_shm = log_shm
        self.filepath = filepath
        self._running = True
        self.daemon = True  

    def run(self):
        print("LogConsumerThread started.")
        # with open(self.filepath, 'w', newline='') as f:
        #     writer = csv.DictWriter(f, fieldnames=["datetime", "sid", "metric_id", "value"])
        #     writer.writeheader()
            
        while self._running:
            batch = self.log_shm.drain_metrics(max_batch=5000)
            df = pd.DataFrame(batch)

            df.to_parquet(f, index=False, engine='pyarrow', compression='snappy', append=True)
            
            # 2. 如果读到了数据，落盘
            if batch:
                writer.writerows(batch)
            else:
                # 3. 没数据时，休眠 1 毫秒，让出 CPU
                # 由于是独立线程，这里的 sleep 绝对不会阻塞 Cerebro 主线
                time.sleep(0.001)
                
        # --- 退出时的清理工作 ---
        # 确保主程序通知停止后，把残留的 Log 彻底吸干净
        while True:
            batch = self.log_shm.drain_metrics(max_batch=5000)
            if not batch:
                break
            writer.writerows(batch)
                
        print("LogConsumerThread stopped.")

    def stop(self):
        self._running = False
