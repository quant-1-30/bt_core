import array as pyarray

import numpy as np

from bt_core.linebuffer import LineBuffer, QBuffer


def unbounded(values):
    lb = LineBuffer()
    for v in values:
        lb.forward(v)
    return lb


def ring(values, maxlen):
    lb = LineBuffer()
    lb.mode = QBuffer
    lb.maxlen = maxlen
    lb.reset()
    for v in values:
        lb.forward()
        lb[0] = v
    return lb


def test_unbounded_get_windows():
    lb = unbounded([1.0, 2.0, 3.0, 4.0])
    assert list(lb.get(0, 1)) == [4.0]
    assert list(lb.get(0, 2)) == [3.0, 4.0]
    assert list(lb.get(0, 4)) == [1.0, 2.0, 3.0, 4.0]
    assert list(lb.get(-1, 2)) == [2.0, 3.0]


def test_ring_get_exact_size_and_order():
    lb = ring([1, 2, 3, 4, 5, 6], 4)
    assert lb[0] == 6.0 and lb[-1] == 5.0
    assert list(lb.get(0, 1)) == [6.0]
    assert list(lb.get(0, 2)) == [5.0, 6.0]
    assert list(lb.get(0, 3)) == [4.0, 5.0, 6.0]
    assert list(lb.get(0, 4)) == [3.0, 4.0, 5.0, 6.0]
    assert list(lb.get(-1, 2)) == [4.0, 5.0]


def test_ring_get_no_wrap_phase():
    lb = ring([1, 2, 3], 4)
    assert list(lb.get(0, 3)) == [1.0, 2.0, 3.0]
    assert list(lb.get(0, 2)) == [2.0, 3.0]


def test_ring_get_future_wrap_exact_size():
    lb = ring([1, 2, 3, 4, 5, 6], 4)
    r = lb.get(3, 2)
    assert len(r) == 2 and list(r) == [4.0, 5.0]
    r2 = lb.get(2, 2)
    assert list(r2) == [3.0, 4.0] and len(r2) == 2
    r3 = lb.get(6, 3)
    assert len(r3) == 3


def test_reset_rewinds_indices():
    lb = ring([1, 2, 3], 4)
    lb.reset()
    assert lb.idx == -1 and lb._cur_idx == -1 and lb.lencount == 0
    assert np.all(np.isnan(lb.array))

    lb2 = unbounded([1.0, 2.0])
    lb2.reset()
    assert lb2.idx == -1 and lb2._cur_idx == -1 and len(lb2.array) == 0


def test_apply_factor_unbounded_and_ring():
    lb = unbounded([10.0, 11.0, 12.0])
    lb.apply_factor(0.5)
    assert list(lb.array) == [5.0, 5.5, 6.0]
    assert isinstance(lb.array, pyarray.array)

    lb2 = ring([10.0, 20.0, 30.0, 40.0], 4)
    lb2.apply_factor(0.1)
    assert list(lb2.array) == [1.0, 2.0, 3.0, 4.0]
