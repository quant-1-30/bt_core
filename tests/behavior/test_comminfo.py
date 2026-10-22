import uuid

from bt_core.execution.core.finance.order import Order, OrderType
from bt_core.execution.core.finance.comminfo import CommInfo_Stocks

EID = uuid.uuid4().bytes
OID = uuid.uuid4().bytes

STAMP_CKPT = 1693180800           # 2023-08-28 印花税 1‰ -> 0.5‰
TRANSFER_CKPT = 1651180800        # 2022-04-29 过户费 0.02‰ -> 0.01‰
TRANSFER_UNIFY_CKPT = 1438387200  # 2015-08-01 沪深统一 0.02‰（此前沪面值 0.06‰×size，深 0）
RATIO_CKPT = 1433813400           # 2015-06-09 佣金 3‰ -> 0.5‰

D_2014 = 1400000000
D_2015_SUMMER = 1437000000
D_2016 = 1451606400
D_2021 = 1609459200
D_2023_WINTER = 1672531200


def make_order(sid, created_dt, is_sell):
    return Order(
        EID, sid, OID, 1.0, 10.0,
        OrderType.Sell if is_sell else OrderType.Buy,
        0, created_dt, b"default",
    )


def expect(created_dt, is_sell, size, price, sse):
    amount = abs(size) * price
    comm_rate = 3e-3 if created_dt < RATIO_CKPT else 5e-4
    comm = max(amount * comm_rate, 5.0)
    stamp = 0.0
    if is_sell:
        stamp = amount * (5e-4 if created_dt >= STAMP_CKPT else 1e-3)
    if created_dt >= TRANSFER_CKPT:
        tf_fee = amount * 1e-5
    elif created_dt >= TRANSFER_UNIFY_CKPT:
        tf_fee = amount * 2e-5
    else:
        tf_fee = (6e-5 * abs(size)) if sse else 0.0
    return comm + stamp + tf_fee


def check(sid, created_dt, is_sell, size, price):
    o = make_order(sid, created_dt, is_sell)
    sse = sid.startswith(b"60")
    got = CommInfo_Stocks()(o, size, price)
    exp = expect(created_dt, is_sell, size, price, sse)
    assert abs(got - exp) <= 1e-9 * max(1.0, exp), \
        f"{sid} @{created_dt} sell={is_sell}: got {got!r} != {exp!r}"


def test_fee_checkpoint_matrix():
    dates = [
        D_2014, RATIO_CKPT - 1, RATIO_CKPT,
        D_2015_SUMMER, TRANSFER_UNIFY_CKPT - 1, TRANSFER_UNIFY_CKPT,
        D_2016, D_2021, TRANSFER_CKPT - 1, TRANSFER_CKPT,
        D_2023_WINTER, STAMP_CKPT - 1, STAMP_CKPT,
    ]
    for dt in dates:
        for sid in (b"600519", b"000001", b"300308"):
            for is_sell in (False, True):
                check(sid, dt, is_sell, 10000, 20.0)


def test_min_commission_only_applies_to_brokerage():
    check(b"600519", D_2023_WINTER, False, 100, 10.0)
    check(b"600519", D_2023_WINTER, True, 100, 10.0)
    check(b"000001", D_2014, True, 100, 10.0)
    check(b"600519", D_2014, True, 100, 10.0)


def test_sse_transfer_fee_par_value_price_independent_and_szse_exempt():
    check(b"300308", D_2014, False, 5000, 15.0)
    check(b"600519", D_2014, False, 5000, 15.0)
    check(b"600519", D_2014, False, 5000, 50.0)
