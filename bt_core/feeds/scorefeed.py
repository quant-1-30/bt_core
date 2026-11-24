import logging
from bisect import bisect_left
import polars as pl

from bt_core.feed import DataBase
from bt_core.utils import resolve_scan_source

logger = logging.getLogger(__name__)

__all__ = ["ParquetPatch"]

_EXTRA_META_COLS = ("expected_return", "preclose", "entry_close")


def _build_day_map(row: dict, extra_cols: tuple) -> dict:
    day_map = {}

    for k, sid in enumerate(row["sid"]):
        sid_b = sid.encode() if isinstance(sid, str) else bytes(sid)
        info = {"fsm_score": float(row["fsm_score"][k])}
        for col in extra_cols:
            val = row[col][k]
            if val is not None:
                info[col] = float(val)
        day_map[sid_b] = info
    return day_map


class ParquetPatch(DataBase):
    lines = ("datetime",)
    params = (
        ("parquet_path", None),
        ("lag", 0),
    )

    def _start(self, *args, **kwargs):
        super()._start(*args, **kwargs)

        self.global_scores = {}
        self._sorted_days = []

        src = resolve_scan_source(self.p.parquet_path)
        if src is not None:
            raw_lf = pl.scan_parquet(src).with_columns(
                (
                    pl.col("day").dt.year() * 10000
                    + pl.col("day").dt.month().cast(pl.Int32) * 100
                    + pl.col("day").dt.day()
                ).alias("day_id")
            )
            if int(self.p.lag or 0) > 0:
                all_days_df = raw_lf.select("day_id").unique().collect()
                self._sorted_days = sorted(int(d) for d in all_days_df["day_id"].to_list())

            schema_names = set(raw_lf.collect_schema().names())
            # Always pass rich metadata; columns absent from the parquet are
            # simply omitted per row (graceful degradation).
            extra_cols = [c for c in _EXTRA_META_COLS if c in schema_names]
            agg_exprs = [pl.col("sid"), pl.col("fsm_score")] + [pl.col(c) for c in extra_cols]

            res_df = (
                raw_lf.filter(pl.col("fsm_score") > 0.0)
                .group_by("day_id")
                .agg(agg_exprs)
                .collect()
            )
            for row in res_df.iter_rows(named=True):
                self.global_scores[int(row["day_id"])] = _build_day_map(row, extra_cols)

            logger.info(
                "[bt_core] %d trading_days signal (lag=%d)",
                len(self.global_scores),
                int(self.p.lag or 0),
            )
        else:
            logger.warning("[bt_core] parquet not found: %s (empty signal)", self.p.parquet_path)

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
