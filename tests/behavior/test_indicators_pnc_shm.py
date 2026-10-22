"""Behavior tests for incremental indicators (UnBounded & QBuffer ring),
Strategy._getminperstatus, PeriodStats Welford, Pnc partial-sell intent,
SHM release/unregister, BatchWriterActor.reset, and Cerebro watchdog."""
import asyncio
import threading
import time
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import talib

import bt_core.indicators as btind
from bt_core.analyzers.periodstats import PeriodStats
from bt_core.cerebro import Cerebro
from bt_core.execution.actor.writer_actor import BatchWriterActor
from bt_core.feeds.pandafeed import PandasDirectData
from bt_core.pnc import Pnc
from bt_core.shm.shm_buffer import LogRingBuffer, SharedRingBuffer
from bt_core.sizer import Sizer
from bt_core.strategy import Strategy

N = 200
BJ = timezone(timedelta(hours=8))


def _make_market(seed=11):
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.2, N))
    high = close + np.abs(rng.normal(0.6, 0.35, N))
    low = close - np.abs(rng.normal(0.6, 0.35, N))
    return close, high, low


CLOSE, HIGH, LOW = _make_market()


def _make_feed():
    df = pd.DataFrame({
        "sid": b"000001",
        "open": CLOSE,
        "high": HIGH,
        "low": LOW,
        "close": CLOSE,
        "volume": 1e6,
        "amount": 1e8,
    }, index=pd.date_range("2020-01-01", periods=N))
    feed = PandasDirectData(dataname=df)
    feed._start()
    return feed


def _to_ring(feed, inds, ring_size):
    for ind in inds:
        ind.qbuffer(1)
    feed.qbuffer(1)
    feed.minbuffer(ring_size)


def _drive(feed, inds, capture):
    series = [[] for _ in capture]
    while feed.next():
        for ind in inds:
            ind._next()
        for j, ln in enumerate(capture):
            series[j].append(float(ln[0]))
    return [np.asarray(s, dtype=float) for s in series]


def _check_pair(factory, ring_size, refs):
    for ring in (False, True):
        feed = _make_feed()
        inds, capture = factory(feed)
        if ring:
            _to_ring(feed, inds, ring_size)
        outs = _drive(feed, inds, capture)
        for spec, out in zip(refs, outs):
            tag, ref, start = spec[0], spec[1], spec[2]
            atol = spec[3] if len(spec) > 3 else 1e-8
            rtol = spec[4] if len(spec) > 4 else 1e-7
            seg_m, seg_r = out[start:], np.asarray(ref, dtype=float)[start:]
            assert not np.isnan(seg_m).any(), f"{tag}(ring={ring}) NaN after {start}"
            assert np.allclose(seg_m, seg_r, atol=atol, rtol=rtol), \
                f"{tag}(ring={ring}) mismatch vs talib"


def test_all_incremental_indicators_unbounded_and_ring():
    p = 14
    idx = np.arange(N)
    _check_pair(lambda f: ([i := btind.SMA(f.close, period=p)], [i.lines.sma]),
                p, [("SMA", talib.SMA(CLOSE, p), p - 1)])
    _check_pair(lambda f: ([i := btind.Highest(f.close, period=p)], [i.lines.highest]),
                p, [("Highest", talib.MAX(CLOSE, p), p - 1)])
    _check_pair(lambda f: ([i := btind.Lowest(f.close, period=p)], [i.lines.lowest]),
                p, [("Lowest", talib.MIN(CLOSE, p), p - 1)])
    _check_pair(lambda f: ([i := btind.FindIndexHighest(f.close, period=p)], [i.lines.max]),
                p, [("MaxIndex", idx - talib.MAXINDEX(CLOSE, p), p - 1)])
    _check_pair(lambda f: ([i := btind.FindIndexLowest(f.close, period=p)], [i.lines.lowest]),
                p, [("MinIndex", idx - talib.MININDEX(CLOSE, p), p - 1)])
    _check_pair(lambda f: ([i := btind.WMA(f.close, period=p)], [i.lines.wma]),
                p, [("WMA", talib.WMA(CLOSE, p), p - 1)])
    _check_pair(lambda f: ([i := btind.StdDev(f.close, period=20)], [i.lines.stddev]),
                20, [("StdDev", talib.STDDEV(CLOSE, 20, 1.0), 19)])
    up, mid, low = talib.BBANDS(CLOSE, 20, 2.0, 2.0, matype=0)
    _check_pair(lambda f: ([i := btind.BBands(f.close, period=20)], [i.lines.up, i.lines.mid, i.lines.low]),
                20, [("BB.up", up, 19), ("BB.mid", mid, 19), ("BB.low", low, 19)])
    _check_pair(lambda f: ([i := btind.Momentum(f.close, period=12)], [i.lines.momentum]),
                13, [("MOM", talib.MOM(CLOSE, 12), 12)])
    _check_pair(lambda f: ([i := btind.PercentChange(f.close, period=12)], [i.lines.roc, i.lines.rocp, i.lines.rocr]),
                13, [("ROC", talib.ROC(CLOSE, 12), 12), ("ROCP", talib.ROCP(CLOSE, 12), 12), ("ROCR", talib.ROCR(CLOSE, 12), 12)])
    _check_pair(lambda f: ([i := btind.EMA(f.close, period=p)], [i.lines.ema]),
                p, [("EMA", talib.EMA(CLOSE, p), p - 1)])
    _check_pair(lambda f: ([i := btind.RSI(f.close, period=p)], [i.lines.rsi]),
                p + 1, [("RSI", talib.RSI(CLOSE, p), p)])
    _check_pair(lambda f: ([i := btind.ATR(f, period=p)], [i.lines.atr, i.lines.natr]),
                p + 1, [("ATR", talib.ATR(HIGH, LOW, CLOSE, p), p), ("NATR", talib.NATR(HIGH, LOW, CLOSE, p), p)])
    _check_pair(lambda f: ([i := btind.KAMA(f.close, period=30)], [i.lines.kama]),
                31, [("KAMA", talib.KAMA(CLOSE, 30), 30, 1e-6, 1e-6)])
    _check_pair(lambda f: ([i := btind.DEMA(f.close, period=p)], [i.lines.dema]),
                2 * p - 1, [("DEMA", talib.DEMA(CLOSE, p), 2 * p - 2)])
    _check_pair(lambda f: ([i := btind.TEMA(f.close, period=p)], [i.lines.tema]),
                3 * p - 2, [("TEMA", talib.TEMA(CLOSE, p), 3 * p - 3)])
    e12, e26 = talib.EMA(CLOSE, 12), talib.EMA(CLOSE, 26)
    m2 = e12 - e26
    s2 = np.full(N, np.nan)
    s2[25:] = talib.EMA(m2[25:], 9)
    h2 = m2 - s2
    _check_pair(lambda f: ([i := btind.MACD(f.close)], [i.lines.macd, i.lines.signal, i.lines.histo]),
                47, [("MACD", m2, 46), ("Signal", s2, 46), ("Histo", h2, 46)])
    _check_pair(lambda f: ([i := btind.AbsolutePriceOscillator(f.close, matype=0)], [i.lines.apo]),
                38, [("APO_SMA", talib.APO(CLOSE, 12, 26, 0), 37)])
    _check_pair(lambda f: ([i := btind.AbsolutePriceOscillator(f.close, matype=1)], [i.lines.apo]),
                38, [("APO_EMA", talib.APO(CLOSE, 12, 26, 1), 37)])
    _check_pair(lambda f: ([i := btind.CCI(f, period=p)], [i.lines.cci]),
                p, [("CCI", talib.CCI(HIGH, LOW, CLOSE, p), p - 1)])
    ref_dn, ref_up = talib.AROON(HIGH, LOW, p)
    _check_pair(lambda f: ([i := btind.AroonOscillator(f, period=p)], [i.lines.aroonup, i.lines.aroondown, i.lines.aroonosc]),
                p + 1, [("AroonUp", ref_up, p), ("AroonDn", ref_dn, p), ("AroonOsc", talib.AROONOSC(HIGH, LOW, p), p)])
    median = (HIGH + LOW) / 2.0
    ao_s = talib.SMA(median, 5) - talib.SMA(median, 34)
    _check_pair(lambda f: ([i := btind.AwesomeOscillator(f)], [i.lines.ao]),
                34, [("AO", ao_s, 33)])
    ac_ref = np.full(N, np.nan)
    for k in range(37, N):
        ac_ref[k] = ao_s[k] - ao_s[k - 4:k + 1].mean()
    _check_pair(lambda f: ([i := btind.AccelerationDecelerationOscillator(f)], [i.lines.accde]),
                38, [("AC", ac_ref, 37)])
    _check_pair(lambda f: ([i := btind.PlusDirectionalIndicator(f, period=p)], [i.lines.plusDI]),
                p + 1, [("PlusDI", talib.PLUS_DI(HIGH, LOW, CLOSE, p), p)])
    _check_pair(lambda f: ([i := btind.MinusDirectionalIndicator(f, period=p)], [i.lines.minusDI]),
                p + 1, [("MinusDI", talib.MINUS_DI(HIGH, LOW, CLOSE, p), p)])
    _check_pair(lambda f: ([i := btind.AverageDirectionalMovementIndex(f, period=p)], [i.lines.adx]),
                2 * p + 1, [("ADX", talib.ADX(HIGH, LOW, CLOSE, p), 2 * p)])
    _check_pair(lambda f: ([i := btind.AverageDirectionalMovementIndexRating(f, period=p)], [i.lines.adxr]),
                3 * p + 1, [("ADXR", talib.ADXR(HIGH, LOW, CLOSE, p), 3 * p)])


def test_strategy_minperstatus_passive_feed_exclusion():
    class FakeData:
        def __init__(self, n):
            self._n = n
        def __len__(self):
            return self._n

    class Shim:
        _getminperstatus = Strategy._getminperstatus
        def __init__(self, lens, mps):
            self.datas = [FakeData(n) for n in lens]
            self._minperiods = list(mps)

    assert Shim([0, 10], [1, 5])._getminperstatus() == -5
    assert Shim([0, 5], [1, 5])._getminperstatus() == 0
    assert Shim([0, 3], [1, 5])._getminperstatus() == 2
    assert Shim([0, 0], [1, 5])._getminperstatus() == 5


def test_periodstats_welford_online_stats():
    ps = PeriodStats.__new__(PeriodStats)
    ps.p = NS(zeroispos=False)
    PeriodStats.__init__(ps)
    ps.log_shm = NS(publish_metric=lambda k, v, dt: None)
    equities = [100.0, 102.0, 102.0, 99.96, 105.0, 103.5]
    for i, eq in enumerate(equities):
        ps.on_dt_over(20240101 + i, NS(account=NS(portfolio_value=eq, cash=0.0)))
    rets = np.diff(equities) / equities[:-1]
    assert np.isclose(ps._mean, np.mean(rets))
    assert np.isclose(np.sqrt(ps._m2 / (ps._n - 1)), np.std(rets, ddof=1))
    assert ps._pos_cnt == 2 and ps._neg_cnt == 2 and ps._nochange_cnt == 1


def test_pnc_partial_sell_intent_and_zero_share_guard():
    class HalfSizer(Sizer):
        def _getsizing(self, topk_info, snapshot, isbuy):
            if isbuy:
                return {sid: 0.2 for sid in topk_info}
            return {p.sid: 0.5 for p in snapshot.positions if p.size > 0}

    pnc = Pnc(HalfSizer(), days_held=5, stake=0.9, dd=0.25, max_positions=5)
    pnc._start([20240102 + i for i in range(20)])
    sid = b"600000"
    created = int(datetime(2024, 1, 2, 10, 0, tzinfo=BJ).timestamp())
    topk = {b"000001": 1.0}

    plan1 = pnc.generate_plan(20240110, topk, NS(positions=[NS(sid=sid, size=1000, available=1000, created_dt=created)], account=NS(cash=1e5)), 0, b"default")
    assert plan1[b"sell"][0]["weight"] == 0.5 and plan1[b"sell"][0]["size"] == 500

    pnc.on_execute({sid: [NS(executed_size=200)]})
    plan2 = pnc.generate_plan(20240111, topk, NS(positions=[NS(sid=sid, size=800, available=800, created_dt=created)], account=NS(cash=1e5)), 0, b"default")
    assert abs(plan2[b"sell"][0]["weight"] - 300.0 / 800.0) < 1e-12 and plan2[b"sell"][0]["size"] == 300

    class TinySizer(Sizer):
        def _getsizing(self, topk_info, snapshot, isbuy):
            return {p.sid: 0.001 for p in snapshot.positions} if not isbuy else {}

    pnc_tiny = Pnc(TinySizer(), days_held=5, stake=0.9, dd=0.25, max_positions=5)
    pnc_tiny._start([20240102 + i for i in range(10)])
    plan_tiny = pnc_tiny.generate_plan(20240108, topk, NS(positions=[NS(sid=sid, size=100, available=100, created_dt=created)], account=NS(cash=1e5)), 0, b"default")
    assert len(plan_tiny[b"sell"]) == 0

    # Macro drawdown risk control: once maxdd >= dd triggers in on_risk,
    # sells all available shares and halts subsequent buy plans (_last_trade_day = -1)
    pnc_dd = Pnc(HalfSizer(), days_held=5, stake=0.9, dd=0.25, max_positions=5)
    pnc_dd._start([20240102 + i for i in range(20)])
    pos_obj = NS(sid=sid, size=1000, available=1000, created_dt=created, pnl_ratio=0.0)
    s0 = pnc_dd.on_risk(NS(positions=[pos_obj]), {"drawdown": NS(maxdd=0.10)}, 20240103)
    assert len(s0) == 0
    s1 = pnc_dd.on_risk(NS(positions=[pos_obj]), {"drawdown": NS(maxdd=0.26)}, 20240104)
    assert len(s1) == 1 and s1[0]["sid"] == sid
    plan_halted = pnc_dd.generate_plan(20240104, topk, NS(positions=[pos_obj], account=NS(cash=1e5)), 0, b"default")
    assert len(plan_halted[b"buy"]) == 0


def test_shm_unregister_and_actor_reset():
    ring = LogRingBuffer(shm_name="t_beh_log", capacity=4, is_creator=True)
    try:
        for i in range(4):
            ring.publish_metric(b"m", 1.0, i)
        done = threading.Event()
        t = threading.Thread(target=lambda: (ring.publish_metric(b"m", 2.0, 99), done.set()), daemon=True)
        t.start()
        time.sleep(0.15)
        assert not done.is_set()
        ring.release_consumer()
        assert done.wait(timeout=3.0)
        t.join(timeout=3.0)
    finally:
        ring.close()
        ring.unlink()

    ering = SharedRingBuffer(shm_name="t_beh_evt", capacity=4, is_creator=True)
    spin = None
    try:
        c0 = ering.register_consumer()
        c1 = ering.register_consumer()
        for i in range(4):
            ering.publish_sentinel(i)
        ering.drain_events(c1)
        done2 = threading.Event()
        spin = threading.Thread(target=lambda: (ering.publish_sentinel(99), done2.set()), daemon=True)
        spin.start()
        time.sleep(0.15)
        assert not done2.is_set()
        ering.unregister_consumer(c0)
        assert done2.wait(timeout=3.0)
        spin.join(timeout=3.0)
        spin = None
        for _ in range(4):
            ering.drain_events(c1)

        # P0-3: full 16-byte UUID order_id (even with embedded \x00 and differing
        # only in the 16th byte) preserves all 128 bits via 32-char hex in SHM
        oid_a = b"\x01\x00\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\xaa"
        oid_b = b"\x01\x00\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\xbb"
        ering.publish_order(NS(sid=b"600000", order_id=oid_a, filler=b"default",
                               price=10.0, sizer_ratio=0.5, created_dt=100, order_type=0, exec_type=0))
        ering.publish_order(NS(sid=b"000001", order_id=oid_b, filler=b"default",
                               price=10.0, sizer_ratio=0.5, created_dt=100, order_type=0, exec_type=0))
        ering.publish_sentinel(101)
        evts = ering.drain_events(c1)
        assert len(evts) == 2
        assert evts[0]["data"]["order_id"] == oid_a.hex().encode("ascii")
        assert evts[1]["data"]["order_id"] == oid_b.hex().encode("ascii")
        assert evts[0]["data"]["order_id"] != evts[1]["data"]["order_id"]
    finally:
        ering.unregister_consumer(0)
        ering.unregister_consumer(1)
        if spin is not None:
            spin.join(timeout=1.0)
        ering.close()
        ering.unlink()

    async def _actor_lifecycle():
        a = BatchWriterActor(q_size=8, batch_size=100)
        await a.push([99])
        asyncio.get_running_loop().create_task(a.run())
        await asyncio.wait_for(a.wait_until_finished(), timeout=5)
        a.reset()
        asyncio.get_running_loop().create_task(a.run())
        await a.push([99])
        await asyncio.wait_for(a.wait_until_finished(), timeout=5)

    asyncio.run(_actor_lifecycle())

    c = Cerebro(client_id=b"\x00" * 16, fmt="parquet")
    try:
        assert c.p.timeout > 0
    finally:
        c._shutdown()


def test_datas0_benchmark_clock_with_datas1_indicators_adaptation():
    """Verify all adaptations when datas[0] is the high-freq benchmark master
    clock and indicators/signals operate on datas[1:] (resampled/slower feeds):
      1. Stateful recursive indicators (EMA, RSI, MACD) & LineActions on
         datas[1] only advance when datas[1] emits a new bar, NOT on every
         tick of datas[0] (exact match vs talib on datas[1]);
      2. _getminperstatus keeps strategy in prenext while datas[1] len==0
         even when datas[0] len > 0;
      3. Multiple indicators sharing datas[1] under QBuffer(savemem=1) do
         not shrink datas[1].close.maxlen back to 1;
      4. Indicator without explicit data inside a Strategy defaults to
         datas[1] (first user OHLCV feed) rather than datas[0] (benchmark)."""
    bench_feed = _make_feed()   # datas[0]: ticks every iteration
    stock_feed = _make_feed()   # datas[1]: ticks once every 5 iterations of datas[0]

    ema14 = btind.EMA(stock_feed.close, period=14)
    rsi14 = btind.RSI(stock_feed.close, period=14)
    low20 = btind.Lowest(stock_feed.close, period=20)
    expr_line = stock_feed.close / low20 - 1.0  # LineActions on datas[1]

    # Test QBuffer maxlen preservation when multiple indicators share datas[1]
    for ind in (ema14, rsi14, low20, expr_line):
        ind.qbuffer(1)
    stock_feed.qbuffer(1)
    assert stock_feed.close.maxlen >= 20, (
        f"shared datas[1] maxlen shrunk to {stock_feed.close.maxlen}")

    # Drive datas[0] 5x faster than datas[1]: recursive EMA/RSI on datas[1]
    # must still match talib on CLOSE exactly!
    ema_vals, rsi_vals = [], []
    step = 0
    while stock_feed.next():
        for _ in range(5):
            bench_feed.next()  # datas[0] ticks 5 times per datas[1] bar
            step += 1
            ema14._next()
            rsi14._next()
            low20._next()
            expr_line._next()
        ema_vals.append(float(ema14.lines.ema[0]))
        rsi_vals.append(float(rsi14.lines.rsi[0]))

    assert np.allclose(ema_vals[13:], talib.EMA(CLOSE, 14)[13:], atol=1e-8)
    assert np.allclose(rsi_vals[14:], talib.RSI(CLOSE, 14)[14:], atol=1e-8)

    # Verify _getminperstatus when datas[0] has len=10 but datas[1] (OHLCV) has len=0
    class FakeOHLCV:
        def __init__(self, n):
            self._n = n
            self.lines = NS(close=True, datetime=True)
        def __len__(self):
            return self._n

    class FakePatch:
        def __init__(self):
            self.lines = NS(datetime=True)  # no 'close'
        def __len__(self):
            return 0

    class Shim:
        _getminperstatus = Strategy._getminperstatus
        def __init__(self, datas, mps):
            self.datas = datas
            self._minperiods = mps

    # datas[0]=benchmark(len=10, mp=1), datas[1]=ddata(len=0, mp=5), datas[2]=patch(len=0, mp=1)
    # Must stay in prenext (status = 5 > 0) while datas[1] len==0!
    s_warm = Shim([FakeOHLCV(10), FakeOHLCV(0), FakePatch()], [1, 5, 1])
    assert s_warm._getminperstatus() == 5
    # Once datas[1] reaches len=5 -> status == 0 (nextstart), len=6 -> -1 (next)
    assert Shim([FakeOHLCV(1200), FakeOHLCV(5), FakePatch()], [1, 5, 1])._getminperstatus() == 0
    assert Shim([FakeOHLCV(1440), FakeOHLCV(6), FakePatch()], [1, 5, 1])._getminperstatus() == -1

    # Verify Strategy._periodset unwraps LineSeriesStub(self.datas[k].close)
    # to datas[k] rather than misattributing minperiod to datas[0]!
    from bt_core.lineiterator import LineIterator
    from bt_core.lineseries import LineSeriesMaker
    d0, d1, d2 = _make_feed(), _make_feed(), _make_feed()
    ind_d1 = btind.SMA(d1.close, period=15)
    ind_d2 = btind.SMA(d2.close, period=7)

    class PeriodSetShim:
        _periodset = Strategy._periodset
        def __init__(self):
            self.datas = [d0, d1, d2]
            self._minperiods = []
            self._lineiterators = {LineIterator.IndType: [ind_d1, ind_d2]}

    ps_shim = PeriodSetShim()
    ps_shim._periodset()
    assert ps_shim._minperiods == [1, 15, 7], (
        f"expected _minperiods [1, 15, 7] for [d0(bench), d1, d2], got {ps_shim._minperiods}")

    # Verify nested cross-timeframe composite indicator (e.g. WeekPriceSignal
    # taking (ddata, wdata) with an internal SMA(wdata.close, period=10)):
    # _periodset must attribute period=10 to wdata (index 2), NOT ddata (index 1)!
    class CrossTFSignal(btind.Indicator):
        lines = ('signal',)
        def __init__(self):
            self.sma_w = btind.SMA(self.data1.close, period=10)
        def next(self):
            self.lines.signal[0] = self.sma_w[0] / self.data0.close[0] - 1.0

    m0, d_day, d_week = _make_feed(), _make_feed(), _make_feed()
    ctf = CrossTFSignal(d_day, d_week)
    ps_cross = PeriodSetShim()
    ps_cross.datas = [m0, d_day, d_week]
    ps_cross._lineiterators = {LineIterator.IndType: [ctf]}
    ps_cross._periodset()
    assert ps_cross._minperiods == [1, 1, 10], (
        f"expected _minperiods [1, 1, 10] for cross-timeframe signal, got {ps_cross._minperiods}")

    # Verify deep-nesting (3-hop indicator chain) and cycle guard in _resolve_clock_feed
    from bt_core.lineiterator import _resolve_clock_feed
    cyc = NS(_clock=None, _owner=None)
    cyc._clock = cyc
    assert _resolve_clock_feed(cyc) is cyc
    assert _resolve_clock_feed(cyc, stop_ids={id(d_day)}) is None
    assert _resolve_clock_feed(None) is None

    # Verify HeikinAshi (MultiLogic Max/Min staticmethod), DivByZero(line, scalar),
    # and reverse-division zero-guard (1.0 / zero_line)
    import bt_core as bt
    f_logic = _make_feed()
    ha = btind.HeikinAshi(f_logic)
    hd_ema = btind.haDelta(f_logic, movav=btind.EMA)
    dbz = bt.DivByZero(f_logic.close, 0.0, zero=-1.0)
    zero_line = f_logic.close - f_logic.close
    rdiv = 1.0 / zero_line
    while f_logic.next():
        ha._next()
        hd_ema._next()
        dbz._next()
        zero_line._next()
        rdiv._next()
    assert np.isfinite(ha.lines.ha_high[0]) and np.isfinite(ha.lines.ha_low[0])
    assert np.isfinite(hd_ema.lines.smoothed[0])
    assert dbz[0] == -1.0 and rdiv[0] == 0.0


