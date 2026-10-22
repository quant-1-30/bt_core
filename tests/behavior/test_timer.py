import datetime as dt

from bt_core.timer import Timer
from bt_core.utils.dateintern import date2num


def bars(day, times):
    return [date2num(dt.datetime.combine(day, t)) for t in times]


def make_timer(**kwargs):
    t = Timer(**kwargs)
    t.start(object())
    return t


def test_nonrepeat_fires_once_per_day():
    t = make_timer(when=dt.time(10, 0))
    day = dt.date(2024, 6, 3)
    got = [t.check(x) for x in bars(
        day, [dt.time(9, 30), dt.time(9, 45), dt.time(10, 0),
              dt.time(10, 15), dt.time(11, 0)])]
    assert got == [False, False, True, False, False], got
    assert t.check(date2num(dt.datetime.combine(dt.date(2024, 6, 4), dt.time(10, 0))))


def test_nonrepeat_before_target_does_not_fire():
    t = make_timer(when=dt.time(14, 30))
    day = dt.date(2024, 6, 3)
    got = [t.check(x) for x in bars(
        day, [dt.time(9, 30), dt.time(11, 0), dt.time(14, 0)])]
    assert got == [False, False, False], got


def test_negative_offset_shifts_trigger_earlier():
    t = make_timer(when=dt.time(15, 0), offset=dt.timedelta(minutes=-10))
    day = dt.date(2024, 6, 3)
    assert not t.check(date2num(dt.datetime.combine(day, dt.time(14, 49))))
    assert t.check(date2num(dt.datetime.combine(day, dt.time(14, 50))))
    assert not t.check(date2num(dt.datetime.combine(day, dt.time(14, 51))))


def test_allow_filter_blocks_whole_day():
    t = make_timer(when=dt.time(9, 40), allow=lambda d: d.day != 4)
    assert t.check(date2num(dt.datetime.combine(dt.date(2024, 6, 3), dt.time(9, 40))))
    assert not t.check(date2num(dt.datetime.combine(dt.date(2024, 6, 4), dt.time(9, 30))))
    assert not t.check(date2num(dt.datetime.combine(dt.date(2024, 6, 4), dt.time(9, 40))))
    assert t.check(date2num(dt.datetime.combine(dt.date(2024, 6, 5), dt.time(9, 40))))


def test_intraday_repeat_every_45min():
    t = make_timer(when=dt.time(9, 30), repeat=dt.timedelta(minutes=45))
    day = dt.date(2024, 6, 3)
    base = dt.datetime.combine(day, dt.time(9, 30))
    times = [(base + dt.timedelta(minutes=15 * i)).time() for i in range(7)]
    got = [t.check(x) for x in bars(day, times)]
    expected = [tt in (dt.time(9, 30), dt.time(10, 15), dt.time(11, 0)) for tt in times]
    assert got == expected, got
