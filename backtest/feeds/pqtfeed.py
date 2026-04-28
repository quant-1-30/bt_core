
import numpy as np
from backtest.feed import DataBase


class ParquetData(DataBase):

    
    params = (
        ("parquet_path", None),
        ("rtbar", False), 
        ("cols", ['tick', 'open', 'high', 'low', 'close', 'volume', 'amount'])
    )

    def _start(self, *args, **kwargs):
        super()._start(*args, **kwargs)

        lf = pl.scan_parquet(self.p.parquet_path)
        df = lf.sort("tick", descending=False).collect()

        arrays = [df[col].to_numpy() for col in self.p.cols]
        self._row_iter = zip(*arrays)

    def _load(self):
        try:
            row = next(self._row_iter)
        except StopIteration:
            return False

        if self.p.rtbar:
            return self._load_rtbar(row)
        else:
            return self._load_bar(row)

    def _load_bar(self, row):
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= row[0]:
            return False 
        
        self.lines.datetime[0] = row[0]
        self.lines.open[0]   = row[1]
        self.lines.high[0]   = row[2]
        self.lines.low[0]    = row[3]
        self.lines.close[0]  = row[4]
        self.lines.volume[0] = row[5]
        self.lines.amount[0] = row[6]
        return True

    def _load_rtbar(self, row): 
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= row[0]:
            return False  
        
        self.lines.datetime[0] = row[0]
        self.lines.open[0]   = row[1]
        self.lines.high[0]   = row[1]
        self.lines.low[0]    = row[1]
        self.lines.close[0]  = row[1]
        self.lines.volume[0] = row[2]
        self.lines.amount[0] = row[3]
        return True

    def stop(self):
        super().stop()
        self._row_iter = None 
