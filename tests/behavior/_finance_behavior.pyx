# cython: language_level=3
# distutils: language = c++

import datetime as dtm
import math
import pickle
import uuid
import numpy as np
cimport numpy as cnp

from libcpp.vector cimport vector
from libc.stdint cimport int32_t, int64_t

from bt_core.execution.core.finance.position cimport Position
from bt_core.execution.core.finance.asset cimport Asset
from bt_core.execution.core.finance.order cimport Order, OrderStatus
from bt_core.execution.core.finance.trade cimport OrderExecutionBit
from bt_core.execution.core.finance.account cimport Account
from bt_core.execution.core.finance.cache cimport AssetCache
from bt_core.execution.core.finance.simulate cimport TrackerActor
from bt_core.execution.core.finance.common cimport AdjustmentData, RightData, EventItem, ExecPrep
from bt_core.execution.core.finance.line cimport Lines
from bt_core.execution.core.finance.filler cimport PseudoFiller, AlgoFiller, VWAPFiller, TWAPFiller
from bt_core.execution.actor.writer_actor cimport BatchWriterActor
from bt_core.timer cimport Timer
from bt_core.utils.dateintern cimport ts2intdt

EID = uuid.uuid4().bytes
OID = uuid.uuid4().bytes

# 北京时间 2024-06-03 10:00 / 10:30 / 15:00 的 unix ts
TS_MORNING = 1717380000
TS_NOON = 1717398000
TS_CLOSE = 1717417200


cdef Asset _asset(bytes sid, int32_t first_trading=0, int32_t delist=0,
                  bytes merger=b"", float ratio=0.0, bytes name=b"tst"):
    return Asset(sid, name, first_trading, delist, merger, ratio)


cdef OrderExecutionBit _bit(bint isbuy, int64_t dt, int32_t size, double price,
                            double comm=0.0):
    return OrderExecutionBit(OID, dt, size, price, comm, isbuy)


cdef int64_t _ts(int y, int m, int d):
    cdef double ts = dtm.datetime(y, m, d, 2, 0, tzinfo=dtm.timezone.utc).timestamp()
    return <int64_t>ts


def _assert_close(double got, double exp, str what, double tol=1e-9):
    assert abs(got - exp) <= tol * max(1.0, abs(exp)), \
        f"{what}: got {got!r} != {exp!r}"


cpdef Lines _create_mock_lines(double[:, :] arr):
    cdef Lines l = Lines()
    l.batch_load(arr)
    return l


# =====================================================================
# 1. T+1 与日内/日终时间表示不变量
# =====================================================================

def test_t1_lock_and_unlock():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 0, 0, 0.0)

    p.update(_bit(True, TS_MORNING, 100, 10.0))
    assert p.core.size == 100
    assert p.core.available == 0
    _assert_close(p.core.cost_basis, 10.0, "open cost")

    try:
        p.update(_bit(False, TS_NOON, 100, 10.5))
        raise AssertionError("same-day sell must raise T+1 violation")
    except ValueError:
        pass
    assert p.core.size == 100

    p.on_dt_over(20240603, 10.2)
    assert p.core.available == 100
    p.update(_bit(False, TS_MORNING + 86400, 60, 10.8))
    assert p.core.size == 40
    assert p.core.available == 40

    p.update(_bit(False, TS_CLOSE + 86400, 40, 11.0))
    assert p.core.size == 0
    assert p.core.available == 0


def test_t1_sell_over_available_raises():
    cdef Asset a = _asset(b"000001")
    cdef Position p = Position(EID, b"000001", a, 0, 0, 100, 100, 10.0)
    try:
        p.update(_bit(False, TS_MORNING, 101, 10.0))
        raise AssertionError("sell > available must raise")
    except ValueError:
        pass


def test_intraday_dt_stays_ts_and_settles_to_ymd():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 0, 0, 0.0)

    p.update(_bit(True, TS_MORNING, 100, 10.0))
    p.update(_bit(True, TS_NOON, 100, 12.0))
    assert p.core.datetime == TS_NOON

    p.on_dt_over(20240603, 12.0)
    assert p.core.datetime == 20240603


def test_short_position_rejected():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 0, 0, 0.0)
    try:
        p.update(_bit(False, TS_MORNING, 100, 10.0))
        raise AssertionError("sell from empty must raise")
    except ValueError:
        pass


def test_cost_averaging_realized_pnl_ratio():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 0, 0, 0.0)

    p.update(_bit(True, TS_MORNING, 100, 10.0))
    p.on_dt_over(20240603, 10.0)
    p.update(_bit(True, TS_MORNING + 86400, 100, 12.0))
    _assert_close(p.core.cost_basis, 11.0, "weighted cost")
    assert p.core.available == 100

    p.on_dt_over(20240604, 11.5)
    assert p.core.available == 200
    p.update(_bit(False, TS_MORNING + 2 * 86400, 150, 11.5))
    assert p.core.size == 50 and p.core.available == 50
    _assert_close(p.core.realized_pnl, 150 * (11.5 - 11.0), "realized pnl")
    _assert_close(p.core.pnl, 50 * (11.5 - 11.0), "unrealized pnl")
    _assert_close(p.core.pnl_ratio,
                  (p.core.pnl + p.core.realized_pnl) / (50 * 11.0), "pnl_ratio")


# =====================================================================
# 2. 分红送转 / 配股 / 滚动现金判定
# =====================================================================

cdef EventItem _adj(double bonus_share, double transfer, double bonus):
    cdef EventItem item
    item.event_type = 0
    item.adj = AdjustmentData(bonus_share, transfer, bonus)
    return item


cdef EventItem _rgt(double ratio, double price):
    cdef EventItem item
    item.event_type = 1
    item.rgt = RightData(ratio, price)
    return item


def test_event_bonus_transfer_10_2_1_5():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 100, 100, 10.0)
    cdef vector[EventItem] events
    events.push_back(_adj(2.0, 1.0, 5.0))

    cdef double cash = p.process_events(events, 1e18)
    assert p.core.size == 130
    assert p.core.available == 130
    _assert_close(cash, 50.0, "bonus cash = size * bonus/10")
    _assert_close(p.core.cost_basis, 10.0 / 1.3, "cost / sizer_ratio")


def test_event_rights_10_3_at_8():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 100, 100, 10.0)
    cdef vector[EventItem] events
    events.push_back(_rgt(3.0, 8.0))

    cdef double cash = p.process_events(events, 1e18)
    assert p.core.size == 130
    _assert_close(cash, -240.0, "rights cash = -rights_size * price")
    _assert_close(p.core.cost_basis, (10.0 * 100 + 8.0 * 30) / 130.0, "weighted")
    assert p.core.available == 100


def test_rights_abandoned_when_cash_insufficient():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 100, 100, 10.0)
    cdef vector[EventItem] events
    events.push_back(_rgt(3.0, 8.0))

    cdef double cash = p.process_events(events, 239.99)
    assert p.core.size == 100
    assert p.core.available == 100
    _assert_close(cash, 0.0, "abandoned rights pays nothing")
    _assert_close(p.core.cost_basis, 10.0, "abandoned rights keeps cost")


def test_rights_boundary_cash_exactly_enough():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 100, 100, 10.0)
    cdef vector[EventItem] events
    events.push_back(_rgt(3.0, 8.0))

    cdef double cash = p.process_events(events, 240.0)
    assert p.core.size == 130
    _assert_close(cash, -240.0, "exact cash still subscribes")


def test_batch_dividend_funds_rights_same_settlement():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 100, 100, 10.0)
    cdef vector[EventItem] events
    events.push_back(_adj(0.0, 0.0, 24.0))
    events.push_back(_rgt(3.0, 8.0))

    cdef double cash = p.process_events(events, 0.0)
    assert p.core.size == 130
    _assert_close(cash, 0.0, "net cash flow = +240 - 240")


def test_batch_rights_abandoned_then_later_dividend_still_paid():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 100, 100, 10.0)
    cdef vector[EventItem] events
    events.push_back(_rgt(3.0, 8.0))
    events.push_back(_adj(0.0, 0.0, 5.0))

    cdef double cash = p.process_events(events, 0.0)
    assert p.core.size == 100
    _assert_close(cash, 50.0, "later dividend still paid")


def test_event_odd_share_floor_and_available_le_size():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 105, 60, 10.0)
    cdef vector[EventItem] events
    events.push_back(_adj(2.0, 1.0, 0.0))
    p.process_events(events, 1e18)
    assert p.core.size == 136
    assert p.core.available == 78
    assert p.core.available <= p.core.size

    cdef Position p2 = Position(EID, b"600519", a, 0, 0, 5700, 5700, 10.0)
    cdef vector[EventItem] events2
    events2.push_back(_adj(2.0, 2.0, 0.0))
    p2.process_events(events2, 1e18)
    assert p2.core.size == 7979

    # Tiered dividend tax (<=20 trading days: 20%, 21..240: 10%, >240: 0% post-20150908)
    from bt_core.tradingcal import DataTradingCalendar, get_calendar, set_calendar
    old_cal = get_calendar()
    cal_days = [20230100 + d for d in range(1, 28)] + [20230200 + d for d in range(1, 28)]
    for m in range(3, 13):
        cal_days.extend([20230000 + m * 100 + d for d in range(1, 28)])
    for m in range(1, 7):
        cal_days.extend([20240000 + m * 100 + d for d in range(1, 28)])
    cdef EventItem ev_tax
    cdef Position p_t1, p_t2, p_t3
    cdef vector[EventItem] v_t1, v_t2, v_t3
    set_calendar(DataTradingCalendar(cal_days))
    try:
        ev_tax.event_type = 0
        ev_tax.adj = AdjustmentData(bonus_share=0.0, transfer=0.0, bonus=10.0)  # 1.0 yuan/share pre-tax

        # Tier 1: <= 20 trading days -> 20% tax (net 80.0 on 100 shares)
        p_t1 = Position(EID, b"600519", a, 0, 20230102, 100, 100, 10.0)
        ev_tax.ex_date = 20230116
        v_t1.push_back(ev_tax)
        _assert_close(p_t1.process_events(v_t1, 1e18), 80.0, "tier 1 (<=20d) 20% dividend tax")

        # Tier 2: 21..240 trading days -> 10% tax (net 90.0 on 100 shares)
        p_t2 = Position(EID, b"600519", a, 0, 20230102, 100, 100, 10.0)
        ev_tax.ex_date = 20230601
        v_t2.push_back(ev_tax)
        _assert_close(p_t2.process_events(v_t2, 1e18), 90.0, "tier 2 (21..240d) 10% dividend tax")

        # Tier 3: > 240 trading days -> 0% tax post-2015-09-08 (net 100.0 on 100 shares)
        p_t3 = Position(EID, b"600519", a, 0, 20230102, 100, 100, 10.0)
        ev_tax.ex_date = 20240603
        v_t3.push_back(ev_tax)
        _assert_close(p_t3.process_events(v_t3, 1e18), 100.0, "tier 3 (>240d) 0% dividend tax")
    finally:
        set_calendar(old_cal)


# =====================================================================
# 3. 退市 / 吸并零股补偿与幂等 / 停牌保市值
# =====================================================================

def test_delist_and_restart_preserve_realized_buckets():
    cdef Asset a = _asset(b"600519", 0, 20240605)
    cdef Position p = Position(EID, b"600519", a, 0, 0, 50, 50, 10.0,
                               50.0, 250.0)
    body = p.serialize().body
    _assert_close(body.pnl, 50.0, "snapshot pnl is unrealized bucket")
    _assert_close(body.realized_pnl, 250.0, "realized bucket carried separately")

    p.on_dt_over(20240603, 11.0)
    cdef Position restored = Position(EID, b"600519", a, 0, 0,
                                      50, 50, 10.0,
                                      p.core.pnl, p.core.realized_pnl)
    restored.on_dt_over(20240606, 5.0)
    assert restored.core.size == 0
    _assert_close(restored.core.realized_pnl, 250.0 - 500.0,
                  "historical realized survives restart+delist")


def test_merger_converts_sid_and_fractional_cash_idempotent():
    cdef Asset a = _asset(b"600519", 0, 20240605, b"600000", 0.5)
    cdef Position p = Position(EID, b"600519", a, 0, 0, 101, 101, 10.0)
    # 101 * 0.5 = 50.5 -> 50 shares + 0.5 * (8.0 / 0.5) = 8.0 fractional cash
    cdef double comp = p.on_dt_over(20240606, 8.0)
    assert p.core.sid == b"600000"
    assert p.core.size == 50
    assert p.core.available == 50
    _assert_close(comp, 8.0, "fractional share cash compensation")
    _assert_close(p.core.cost_basis, 10.0 / 0.5, "cost_basis = old_cost / ratio")

    # 幂等守卫: sid == merger 时再次结算不得重复换股
    cdef double comp2 = p.on_dt_over(20240607, 16.0)
    assert p.core.size == 50 and comp2 == 0.0


def test_suspend_close_zero_keeps_position_and_account_market_value():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 20240603, TS_MORNING,
                               1000, 1000, 10.0, 2500.0, 0.0)
    p.on_dt_over(20240606, 0.0)
    assert p.core.size == 1000
    _assert_close(p.core.pnl, 2500.0, "unrealized pnl preserved during suspension")

    cdef Account acct = Account(EID, 20240603, 12500.0, 50000.0, 2500.0)
    acct.sync(TS_CLOSE, {(EID, b"600519"): p})
    _assert_close(acct.core.portfolio_value, 12500.0,
                  "Account.sync preserves suspended position market value")


# =====================================================================
# 4. 订单状态机 / Pickle / Account 守卫
# =====================================================================

def test_order_multifill_exchange_hash_and_pickle():
    cdef Order o = Order(EID, b"600519", OID, 1.0, 10.0, 0, 0, TS_MORNING, b"default")
    o.execute(300, _bit(True, TS_MORNING, 100, 10.0), 10.0)
    assert o.status == OrderStatus.Partial
    o.execute(300, _bit(True, TS_NOON, 100, 10.1), 10.0)
    assert o.status == OrderStatus.Partial
    o.execute(300, _bit(True, TS_CLOSE, 100, 10.2), 10.0)
    assert o.status == OrderStatus.Completed

    cdef Order o2 = pickle.loads(pickle.dumps(o))
    assert o2.core.sid == b"600519" and o2.core.order_id == o.core.order_id
    assert len({o, o2}) == 1

    cdef Order o_sh = Order(EID, b"600519", OID, 1.0, 10.0, 0, 0, TS_MORNING, b"default")
    cdef Order o_star = Order(EID, b"688001", OID, 1.0, 10.0, 0, 0, TS_MORNING, b"default")
    cdef Order o_sz = Order(EID, b"300308", OID, 1.0, 10.0, 0, 0, TS_MORNING, b"default")
    cdef Order o_bse = Order(EID, b"920001", OID, 1.0, 10.0, 0, 0, TS_MORNING, b"default")
    assert o_sh.exchange == 0 and o_star.exchange == 0 and o_sz.exchange == 1 and o_bse.exchange == 2


def test_account_cashflow_negative_guard_and_ymd_sync():
    cdef Account acct = Account(EID, 0, 0.0, 100000.0)
    acct.update([
        _bit(True, TS_MORNING, 100, 10.0, 7.0),
        _bit(False, TS_NOON, 50, 11.0, 6.0),
    ])
    _assert_close(acct.core.cash, 100000.0 - 1000.0 - 7.0 + 550.0 - 6.0, "cash flow")
    assert acct.core.datetime == TS_NOON

    try:
        acct.add_cash(-200000.0)
        raise AssertionError("negative cash must raise")
    except ValueError:
        pass

    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 100, 100, 10.0)
    p.on_dt_over(20240603, 12.0)
    acct.sync(TS_CLOSE, {b"k": p})
    assert acct.core.datetime == 20240603

    # 已是 ymd 输入时严禁二次 ts2intdt 转换
    acct.sync(0, {b"k": p})
    assert acct.core.datetime == 20240603


# =====================================================================
# 5. Asset.restricted 板块 / 新股豁免 / ST / 北交所
# =====================================================================

def test_asset_restricted_all_boards_and_st():
    from bt_core.tradingcal import DataTradingCalendar, set_calendar
    set_calendar(DataTradingCalendar([
        20110104, 20150105, 20150106,
        20200102, 20200103, 20200106, 20200107, 20200108, 20200109,
        20200821, 20200824, 20200825,
        20240102, 20240103, 20240104, 20240105, 20240108, 20240109,
        20240603, 20240604,
        20240830, 20240902, 20240903, 20240904, 20240905, 20240906,
    ]))
    cdef Asset main_norm = _asset(b"600519")
    _assert_close(main_norm.restricted(TS_MORNING), 0.1, "main 10%")

    cdef Asset main_st = _asset(b"600001", 20100101, 0, b"", 0.0, b"*ST_MAIN")
    _assert_close(main_st.restricted(TS_MORNING), 0.05, "main ST 5%")

    cdef Asset cyb_st = _asset(b"300001", 20100101, 0, b"", 0.0, b"ST_CYB")
    _assert_close(cyb_st.restricted(_ts(2020, 8, 21)), 0.05, "old CYB ST 5%")
    _assert_close(cyb_st.restricted(_ts(2020, 8, 25)), 0.20, "new CYB ST 20%")

    cdef Asset star = _asset(b"688001", first_trading=20240830)
    assert math.isinf(star.restricted(_ts(2024, 9, 2)))
    assert math.isinf(star.restricted(_ts(2024, 9, 5)))  # 跨周末第 5 个交易日
    _assert_close(star.restricted(_ts(2024, 9, 6)), 0.20, "STAR day 6 -> 20%")

    cdef Asset main_reg_ipo = _asset(b"601099", first_trading=20240102)
    assert math.isinf(main_reg_ipo.restricted(_ts(2024, 1, 8)))
    _assert_close(main_reg_ipo.restricted(_ts(2024, 1, 9)), 0.10, "Reg IPO day 6 -> 10%")

    cdef Asset main_old_ipo = _asset(b"601088", first_trading=20200102)
    _assert_close(main_old_ipo.restricted(_ts(2020, 1, 2)), 0.44, "approval IPO day 1 -> 44%")
    _assert_close(main_old_ipo.restricted(_ts(2020, 1, 3)), 0.10, "approval IPO day 2 -> 10%")

    cdef Asset bse = _asset(b"920001", first_trading=20240102)
    assert bse.core.board == 3
    assert math.isinf(bse.restricted(_ts(2024, 1, 2)))
    _assert_close(bse.restricted(_ts(2024, 1, 3)), 0.30, "BSE day 2 -> 30%")


# =====================================================================
# 6. Filler: 卖出 T+1 clamp / std 封板拒单 / 流动性与限价排队折减 / Cache
# =====================================================================

def test_filler_sell_clamp_and_zero_avail_reject():
    cdef Asset a = _asset(b"600000")
    cdef Position pos = Position(EID, b"600000", a, 0, 1700000000,
                                 500, 300, 10.0, 0.0, 0.0)
    cdef PseudoFiller filler = PseudoFiller()
    cdef cnp.ndarray[cnp.float64_t, ndim=2] arr = np.array([
        [1700000000.0, 10.0, 10.5, 9.5, 10.2, 1.0e6, 1.02e7],
    ], dtype=np.float64)
    cdef Lines lines = _create_mock_lines(arr)

    cdef Order o1 = Order(EID, b"600000", b"oid1", 1.0, 0.0, 1, 0, 1700000000, b"default")
    o1.core.size = 1000
    cdef ExecPrep prep1 = filler._prepare_execute(o1, pos, 100000.0, lines)
    assert prep1.total_size == 300 and prep1.start_loc == 0

    cdef Position pos0 = Position(EID, b"600000", a, 0, 1700000000,
                                  500, 0, 10.0, 0.0, 0.0)
    cdef Order o2 = Order(EID, b"600000", b"oid2", 1.0, 0.0, 1, 0, 1700000000, b"default")
    o2.core.size = 800
    cdef ExecPrep prep2 = filler._prepare_execute(o2, pos0, 100000.0, lines)
    assert prep2.start_loc == -1 and o2.status == OrderStatus.Rejected


def test_filler_limit_seal_and_microstructure_discounts():
    cdef Asset a = _asset(b"600000")
    cdef Position pos = Position(EID, b"600000", a, 0, 1700000000,
                                 0, 0, 0.0, 0.0, 0.0)
    cdef PseudoFiller filler = PseudoFiller()
    cdef double base = 1700000000.0

    # (a) One-print board fallback rejection when pre_close is absent
    rows = []
    for i in range(5):
        px = 10.0 + 0.1 * i
        rows.append([base + i * 60, px, px + 0.2, px, px + 0.1, 20000.0, 2e5])
    sealed_tick = base + 5 * 60
    rows.append([sealed_tick, 10.6, 10.61, 10.60, 10.61, 20000.0, 2e5])
    rows.append([base + 6 * 60, 10.6, 10.8, 10.5, 10.7, 20000.0, 2e5])
    cdef Lines lines = _create_mock_lines(np.array(rows, dtype=np.float64))
    cdef Order order = Order(EID, b"600000", b"lim1", 1.0, 0.0, 0, 0,
                             <int64_t>base, b"default")
    order.info = a.core
    order.core.limit_ratio = 0.1
    filler._execute(order, pos, 10000000.0, lines)
    ticks = [b['executed_dt'] for b in [xb.core for xb in order.exbits]]
    assert sealed_tick not in ticks and base in ticks and (base + 6 * 60) in ticks

    # (b) Quiet flat bar (high == low == 10.02, +0.2% vs pre_close=10.00) must NOT
    #     be falsely rejected when limit_up=11.00 is known from pre_close!
    cdef Lines l_quiet = _create_mock_lines(np.array([
        [base - 86400, 9.95, 10.05, 9.90, 10.00, 50000.0, 5.0e5],
        [base, 10.02, 10.02, 10.02, 10.02, 20000.0, 2.004e5],
    ], dtype=np.float64))
    cdef Order o_quiet = Order(EID, b"600000", b"quiet1", 1.0, 0.0, 0, 0,
                               <int64_t>base, b"default")
    o_quiet.info = a.core
    o_quiet.core.limit_ratio = 0.1
    filler._execute(o_quiet, pos, 100000.0, l_quiet)
    assert o_quiet.exbits[0].core['executed_size'] == 1000


def test_asset_cache_negative_cache_and_unknown_sid_reject():
    cdef AssetCache ac = AssetCache()
    ac._missing_sids.add(b"999999")
    assert ac.get_cache_info(b"999999", None) is None

    cdef BatchWriterActor w_actor = BatchWriterActor(8, 10)
    cdef TrackerActor t_actor = TrackerActor(EID, w_actor, ac, 8, 10, None)
    cdef Order o_unk = Order(EID, b"999999", b"unk1", 0.5, 0.0, 0, 0,
                             1700000000, b"default")
    resp = t_actor.process_order(o_unk)
    assert o_unk.status == OrderStatus.Rejected
    assert resp is not None and resp.body is not None


def test_timer_user_tzdata_preserved():
    tz = dtm.timezone(dtm.timedelta(hours=8))

    class FakeData:
        pass

    fd = FakeData()
    t1 = Timer(when=dtm.time(9, 30), tzdata=tz)
    t1.start(fd)
    assert t1._tzdata is tz and t1._isdata is False

    t2 = Timer(when=dtm.time(9, 30))
    t2.start(fd)
    assert t2._tzdata is fd


def test_filler_caches_and_algo_vwap_twap_causality():
    cdef Asset a = _asset(b"600519")
    cdef Position p = Position(EID, b"600519", a, 0, 0, 0, 0, 0.0)
    cdef int i

    # 1. AlgoFiller._current_vhat_dt independent cache invalidation
    cdef VWAPFiller vf = VWAPFiller(impact=0.05, slip_perc=0.0)
    vf._current_vhat_dt = 20240603
    vf._vhat_cache[(b"600519", 20240603)] = 500000.0
    assert (b"600519", 20240603) in vf._vhat_cache
    # Simulate date rollover in _current_vhat_dt
    if vf._current_vhat_dt != 20240604:
        vf._vhat_cache.clear()
        vf._current_vhat_dt = 20240604
    assert len(vf._vhat_cache) == 0 and vf._current_vhat_dt == 20240604

    # 2. TWAPFiller equal slicing & VWAPFiller causal volume clock
    cdef cnp.ndarray[cnp.float64_t, ndim=2] data = np.zeros((10, 7), dtype=np.float64)
    for i in range(10):
        data[i, 0] = <double>(TS_MORNING + i * 60)
        data[i, 1] = 10.0
        data[i, 2] = 10.2
        data[i, 3] = 9.8
        data[i, 4] = 10.0
        data[i, 5] = 50000.0
        data[i, 6] = 500000.0
    cdef Lines lines = _create_mock_lines(data)
    cdef Order ord_twap = Order(EID, b"600519", OID, 0.1, 10.0, 0, 0, TS_MORNING, b"twap")
    ord_twap.addinfo(a)
    cdef TWAPFiller tf = TWAPFiller(impact=0.0, slip_perc=0.0)
    tf._execute(ord_twap, p, 100500.0, lines)
    assert ord_twap.status == OrderStatus.Completed
    assert len(ord_twap._exbits) == 10


def test_round2_ashare_compliance_fixes():
    import polars as pl
    from bt_core.execution.core.finance.slippage import FixedPercSlip

    cdef Asset a_sh = _asset(b"600519")
    cdef Position pos = Position(EID, b"600519", a_sh, 0, 1700000000,
                                 1000, 1000, 10.0, 0.0, 0.0)
    cdef PseudoFiller filler = PseudoFiller(impact=0.05, slip_perc=0.0)
    cdef double base = 1700000000.0
    cdef Lines lines = _create_mock_lines(np.array([
        [base, 10.0, 10.5, 9.5, 10.2, 100000.0, 1.02e6],
    ], dtype=np.float64))

    # B2: _sync_event global chronological sorting across Rightment & Adjustment
    # Rights on 20160501 (10配3@8 on 105 shares -> 31 shares, -248 cash),
    # followed by Bonus/Transfer on 20160801 (10送2转1 on 136 shares -> 176 shares).
    # Without global sort, Adjustment ran first (105->136) and Rights took
    # floor(136*0.3)=40 shares (-320 cash)!
    cdef AssetCache ac = AssetCache()
    cdef BatchWriterActor w_actor = BatchWriterActor(8, 10)
    cdef TrackerActor t_actor = TrackerActor(EID, w_actor, ac, 8, 10, None)
    t_actor.cash_manager.get_account(EID).core.cash = 10000.0
    cdef Position p_corp = Position(EID, b"300308", _asset(b"300308"),
                                    20160310, 1457593200, 105, 105, 10.0)
    t_actor.positions[(EID, b"300308")] = p_corp
    adj_df = pl.DataFrame({
        "ex_date": [20160801],
        "bonus_share": [2.0],
        "transfer": [1.0],
        "bonus": [0.0],
    })
    rgt_df = pl.DataFrame({
        "ex_date": [20160501],
        "ratio": [3.0],
        "price": [8.0],
    })
    t_actor._sync_event(EID, t_actor.positions,
                        {b"300308": adj_df}, {b"300308": rgt_df})
    assert p_corp.core.size == 176
    _assert_close(t_actor.cash_manager.get_account(EID).core.cash,
                  10000.0 - 248.0, "chronological rights-then-adj cash delta")

    # B3: Pre-2015-08-01 SSE transfer fee in filler._fill uses par value (6e-5 * size)
    cdef int64_t ts_2014 = 1400000000
    cdef Lines l_2014 = _create_mock_lines(np.array([
        [<double>ts_2014, 20.0, 20.5, 19.5, 20.0, 100000.0, 2.0e6],
    ], dtype=np.float64))
    cdef Order o_2014 = Order(EID, b"600519", b"b3_sse", 0.5, 0.0, 0, 0,
                              ts_2014, b"default")
    o_2014.info = a_sh.core
    filler._execute(o_2014, pos, 100000.0, l_2014)
    cdef int32_t sz_2014 = o_2014.exbits[0].core['executed_size']
    cdef double got_comm = o_2014.exbits[0].core['comm']
    cdef double exp_comm = (20.0 * sz_2014) * 3e-3 + 6e-5 * sz_2014
    _assert_close(got_comm, exp_comm, "pre-2015 SSE bit comm uses par-value transfer fee")

    # B4: ChiNext approval-era IPO day 1 (2014..2020-08-23) -> 44%
    cdef Asset cyb_2015 = _asset(b"300400", first_trading=20150105)
    _assert_close(cyb_2015.restricted(_ts(2015, 1, 5)), 0.44, "2015 CYB IPO day 1 -> 44%")
    _assert_close(cyb_2015.restricted(_ts(2015, 1, 6)), 0.10, "2015 CYB IPO day 2 -> 10%")

    # B7: Slippage tick rounding to 0.01
    slip = FixedPercSlip(0.005)
    # 10.03 * 1.005 = 10.08015 -> rounded to 10.08
    cdef Order o_slip = Order(EID, b"600519", b"b7_slp", 0.2, 0.0, 0, 0,
                              <int64_t>base, b"default")
    o_slip.info = a_sh.core
    cdef PseudoFiller filler_slip = PseudoFiller(impact=0.05, slip_perc=0.005)
    cdef Lines l_slip = _create_mock_lines(np.array([
        [base, 10.03, 10.20, 10.00, 10.10, 100000.0, 1.01e6],
    ], dtype=np.float64))
    filler_slip._execute(o_slip, pos, 100000.0, l_slip)
    _assert_close(o_slip.exbits[0].core['executed_price'], 10.08, "slipped price rounded to 0.01 tick")

    # B8: Low-price bank stock (4.00 yuan) normal bar fills
    cdef Lines l_bank = _create_mock_lines(np.array([
        [base - 86400, 3.98, 4.02, 3.96, 4.00, 100000.0, 4.0e5],
        [base, 4.00, 4.01, 4.00, 4.01, 100000.0, 4.0e5],
    ], dtype=np.float64))
    cdef Order o_bank = Order(EID, b"601398", b"b8_bnk", 0.2, 0.0, 0, 0,
                              <int64_t>base, b"default")
    o_bank.info = _asset(b"601398").core
    o_bank.core.limit_ratio = 0.10
    filler._execute(o_bank, pos, 100000.0, l_bank)
    assert len(o_bank.exbits) == 1, "low-price bank 1-cent bar must not be falsely rejected"

    # B9: Pre-close resolved directly from multi-day Lines (pre_dt + int_dt):
    # yesterday closes at 10.00 (base - 86400), today's limit band is [9.00, 11.00].
    from bt_core.tradingcal import prev_trading_day
    assert prev_trading_day(20240902) == 20240830
    assert prev_trading_day(20110104) == 20110104  # first calendar day clamps to index 0
    try:
        prev_trading_day(19900101)
        raise AssertionError("out-of-range ymd must raise ValueError")
    except ValueError:
        pass
    cdef Lines l_two_days = _create_mock_lines(np.array([
        [base - 86400, 9.90, 10.10, 9.85, 10.00, 100000.0, 1.0e6],
        # today bar 0: wide range (10.30..11.00) closing sealed at limit_up=11.00 -> rejected
        [base, 10.40, 11.00, 10.30, 11.00, 100000.0, 1.08e6],
        # today bar 1: opened board (close=10.95) -> fills, slip_price clamped <= 11.00
        [base + 60, 10.98, 11.20, 10.80, 10.95, 100000.0, 1.09e6],
    ], dtype=np.float64))
    cdef Order o_high_lim = Order(EID, b"600519", b"b1_hi", 0.5, 11.50, 0, 3,
                                  <int64_t>base, b"default")
    o_high_lim.info = a_sh.core
    o_high_lim.core.limit_ratio = 0.10
    filler._execute(o_high_lim, pos, 100000.0, l_two_days)
    assert o_high_lim.status == OrderStatus.Rejected

    cdef Order o_wseal = Order(EID, b"600519", b"wseal_ref", 0.2, 0.0, 0, 0,
                               <int64_t>base, b"default")
    o_wseal.info = a_sh.core
    o_wseal.core.limit_ratio = 0.10
    filler_slip._execute(o_wseal, pos, 100000.0, l_two_days)
    w_ticks = [b['executed_dt'] for b in [xb.core for xb in o_wseal.exbits]]
    assert base not in w_ticks, "wide bar closing sealed at limit_up=11.00 must not fill"
    assert (base + 60) in w_ticks, "opened-board bar must fill"
    _assert_close(o_wseal.exbits[0].core['executed_price'], 11.00, "slip_price clamped to limit_up=11.00")

    # B11: Missing RPC tail bars (e.g. 14:59 / 15:00 missing, last available bar is 14:48):
    # order created at 14:50 on the same trading day falls back to the last available
    # bar (14:48) instead of expiring, and VWAP converges frac=1.0 on the final available bar.
    cdef int64_t t_1448 = 1717397280
    cdef int64_t t_1450 = 1717397400
    cdef Lines l_miss = _create_mock_lines(np.array([
        [<double>t_1448, 10.00, 10.10, 9.95, 10.05, 500000.0, 5.0e6],
    ], dtype=np.float64))
    cdef Order o_miss = Order(EID, b"600519", b"miss_tail", 0.2, 0.0, 0, 0,
                              t_1450, b"vwap")
    o_miss.info = a_sh.core
    cdef AlgoFiller vwap_f = VWAPFiller(impact=0.5, slip_perc=0.0)
    vwap_f._vhat_cache[(b"600519", ts2intdt(t_1450))] = 1000000.0
    vwap_f._execute(o_miss, pos, 100000.0, l_miss)
    assert o_miss.status == OrderStatus.Completed and len(o_miss.exbits) == 1

    # P1-10: STAR board (688, tick_size=200, increment=False):
    # minimum 200 shares, 1-share increments above 200 (e.g. 257 shares allowed, <200 rejected)
    cdef Asset a_star = _asset(b"688001", first_trading=20200101)
    assert a_star.core.tick_size == 200 and not a_star.core.increment
    cdef Order o_star = Order(EID, b"688001", b"star_inc", 0.0, 0.0, 0, 0,
                              t_1448, b"default")
    o_star.info = a_star.core
    o_star.core.size = 257
    filler._execute(o_star, pos, 100000.0, l_miss)
    assert o_star.exbits[0].core['executed_size'] == 257





