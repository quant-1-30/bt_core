"""Stateless delivery-time backward adjustment (apply_factor) & ParquetPatch tests."""
import os
import tempfile
import types
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

from bt_core.feed import AbstractDataBase
from bt_core.feeds import ParquetPatch, ParquetPatch
from bt_core.linebuffer import LineBuffer


def ts_of(ymd):
    y, m, d = ymd // 10000, (ymd // 100) % 100, ymd % 100
    return datetime(y, m, d, 2, 0, tzinfo=timezone.utc).timestamp()


def make_line(values):
    lb = LineBuffer()
    for v in values:
        lb.forward(v)
    return lb


class Stub:
    def __init__(self, adj_factors, current_ts, close_val=10.0, vol_val=1000.0, clone=False):
        self.lines = types.SimpleNamespace(
            datetime=make_line([current_ts]),
            close=make_line([close_val]),
        )
        self.open = make_line([close_val])
        self.high = make_line([close_val + 1.0])
        self.low = make_line([close_val - 1.0])
        self.close = self.lines.close
        self.volume = make_line([vol_val])
        self.adj_factors = adj_factors
        self._clone = clone


def test_delivery_backward_adjustment():
    # scale(bar@D) = prod(1/r for ex_date <= D); price *= scale, volume /= scale
    d1, d2 = 20240110, 20240605
    factors = {d1: 0.8, d2: 0.5}  # 累计 scale = 1 / (0.8 * 0.5) = 2.5

    # 在 d1 当日: 仅 d1 生效 -> scale = 1.25, 未来 d2 被排除(无前视)
    s1 = Stub(factors, ts_of(d1), close_val=10.0, vol_val=1000.0)
    AbstractDataBase.apply_factor(s1)
    assert abs(s1.close[0] - 12.5) < 1e-9
    assert abs(s1.volume[0] - 800.0) < 1e-9

    # 在 d2 当日(或停牌跨越 d1..d2 后复牌首根 bar): 复合 scale = 2.5
    s2 = Stub(factors, ts_of(d2), close_val=10.0, vol_val=1000.0)
    AbstractDataBase.apply_factor(s2)
    assert abs(s2.close[0] - 25.0) < 1e-9
    assert abs(s2.volume[0] - 400.0) < 1e-9


def test_dataclone_short_circuits_ohlcv():
    d1, d2 = 20240110, 20240605
    factors = {d1: 0.8, d2: 0.5}
    sc = Stub(factors, ts_of(d1), close_val=12.5, vol_val=800.0, clone=True)
    AbstractDataBase.apply_factor(sc)
    assert abs(sc.close[0] - 12.5) < 1e-9, "DataClone must not double-scale OHLCV"


def test_parquet_score_feed_aliases_3d_schema_and_causal_lag():
    assert ParquetPatch is ParquetPatch
    with tempfile.TemporaryDirectory() as tmpd:
        df = pl.DataFrame({
            "day": [date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "sid": ["600000", "688001", "600000", "600000"],
            "fsm_score": [1.0, 1.0, -0.5, 1.2],
        })
        df.write_parquet(os.path.join(tmpd, "scores_202401.parquet"))

        pf0 = ParquetPatch(parquet_path=Path(tmpd), lag=0)
        pf0._start()
        tk = pf0.get_topk(20240102)
        assert tk[b"600000"] == 1.0 and tk[b"688001"] == 1.0

        pf1 = ParquetPatch(parquet_path=Path(tmpd), lag=1)
        pf1._start()
        assert pf1.get_topk(20240102) == {}
        assert pf1.get_topk(20240103) == tk
        # 20240103 全为负分 -> 20240104 查 T-1 必须返回空字典而非复用 20240102 陈旧信号
        assert pf1.get_topk(20240104) == {}
        assert pf1.get_topk(20240105)[b"600000"] == 1.2


def test_remote_data_unified_benchmark_master_clock():
    import pyarrow as pa
    import pytest
    from bt_protocol.constant import RpcTopic
    from bt_core.feeds.rpcfeed import RemoteData

    def _make_close_table(sid_bytes=b"1A0001"):
        tbl = pa.table({"day": [20240102, 20240103], "close": [3000.0, 3015.0]})
        return tbl.replace_schema_metadata({b"sid": sid_bytes})

    class DummyObservable:
        def __init__(self, items=()):
            self._items = list(items)
        def pipe(self, *args):
            return self
        def subscribe(self, **kwargs):
            on_next = kwargs.get("on_next")
            if on_next:
                for it in self._items:
                    on_next(it)
            if "on_completed" in kwargs:
                kwargs["on_completed"]()

    class MockMdApi:
        def __init__(self, close_items=None):
            self.subscribed_topics = []
            self.factor_calls = 0
            self.close_items = close_items if close_items is not None else [_make_close_table()]
        def get_factor(self, body, topic):
            self.factor_calls += 1
            return {}
        def subscribe(self, body, topic):
            self.subscribed_topics.append((topic, list(body.sid), body.start_date, body.end_date))
            if topic == RpcTopic.Close:
                return DummyObservable(self.close_items)
            return DummyObservable()

    # 1. Single-sid validation (rpcfeed, len(sid) == 1): Tick & get_factor use [b"300308"],
    #    while benchmark Close uses [b"1A0001"]
    api1 = MockMdApi()
    rd1 = RemoteData(mdapi=api1)
    rd1._start(sid=[b"300308"], fromdate=20040101, todate=20260531)
    assert rd1.benchmark == [b"1A0001"]
    assert api1.factor_calls == 1
    assert (RpcTopic.Close, [b"1A0001"], 20040101, 20260531) in api1.subscribed_topics
    assert (RpcTopic.Tick, [b"300308"], 20040101, 20260531) in api1.subscribed_topics

    # 2. Multi-sid run (scorefeed, len(sid) > 1): datas[0] Tick & Close both subscribe [b"1A0001"]
    api2 = MockMdApi()
    rd2 = RemoteData(mdapi=api2)
    rd2._start(sid=[b"300308", b"600000", b"000001"], fromdate=20120101, todate=20260531, benchmark=[b"1A0001"])
    assert api2.factor_calls == 0
    assert all(sids == [b"1A0001"] for _, sids, _, _ in api2.subscribed_topics)

    # 3. Missing benchmark Close data raises explicit RuntimeError at startup (E3)
    api_empty = MockMdApi(close_items=[])
    rd_empty = RemoteData(mdapi=api_empty)
    with pytest.raises(RuntimeError, match="Benchmark Close data missing or empty"):
        rd_empty._start(sid=[b"300308"], fromdate=20040101, todate=20260531)


