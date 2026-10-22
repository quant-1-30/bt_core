import logging
from bisect import bisect_left
import polars as pl

from bt_core.feed import DataBase
from bt_core.utils import resolve_scan_source

logger = logging.getLogger(__name__)

__all__ = ["ParquetPatch", "ParquetPatch"]


class ParquetPatch(DataBase):
    
    lines = ('datetime',)
    params = (
        ("parquet_path", None),
        # Causal lag in trading days: set lag=1 when parquet scores are
        # computed from end-of-day (15:00 close) features so a 14:50 TRADE
        # timer on day T only sees T-1's scores (no look-ahead bias).
        ("lag", 0),
    )

    def _start(self, *args, **kwargs):
        super()._start(*args, **kwargs)

        self.global_scores = {}
        self._sorted_days = []

        src = resolve_scan_source(self.p.parquet_path)
        if src is not None:
            raw_lf = pl.scan_parquet(src).with_columns(
                (pl.col("day").dt.year() * 10000 +
                 pl.col("day").dt.month() * 100 +
                 pl.col("day").dt.day()).alias("day_id")
            )
            if int(self.p.lag or 0) > 0:
                all_days_df = raw_lf.select("day_id").unique().collect()
                self._sorted_days = sorted(int(d) for d in all_days_df["day_id"].to_list())

            res_dict = (
                raw_lf
                .filter(pl.col("fsm_score") > 0.0)
                .group_by("day_id")
                .agg([pl.col("sid"), pl.col("fsm_score")])
                .collect()
                .to_dict(as_series=False)
            )

            if "day_id" in res_dict and len(res_dict["day_id"]) > 0:
                self.global_scores = {
                    int(day_id): {
                        (s.encode() if isinstance(s, str) else bytes(s)): float(sc)
                        for s, sc in zip(sids, scores)
                    }
                    for day_id, sids, scores in zip(
                        res_dict["day_id"], res_dict["sid"], res_dict["fsm_score"]
                    )
                }

            logger.info("[bt_core] %d trading_days signal (lag=%d)",
                        len(self.global_scores), int(self.p.lag or 0))
        else:
            logger.warning("[bt_core] parquet not found: %s (empty signal)",
                           self.p.parquet_path)

    def _load(self):
        return False

    def get_topk(self, current_day: int) -> dict:
        lag = int(self.p.lag or 0)
        if lag <= 0:
            return self.global_scores.get(current_day, {})
        idx = bisect_left(self._sorted_days, current_day) - lag
        if idx < 0:
            return {}
        return self.global_scores.get(self._sorted_days[idx], {})

    def notify_metrics(self, dts: int):
        pass

    def stop(self):
        super().stop()
        self.global_scores.clear()
        self._sorted_days.clear()
