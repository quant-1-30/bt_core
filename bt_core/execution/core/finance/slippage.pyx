# cython: boundscheck=False
# cython: wraparound=False
# distutils: language = c++
# cython: language_level=3

from bt_core.execution.core.finance.function cimport round_tick as _round_tick


cdef class Slippage:

    cdef double get_slip_price(self, double order_price, Bar bar, bint is_buy) noexcept nogil:
        return order_price
    

cdef class FixedPercSlip(Slippage):

    def __init__(self, 
                double slip_perc=0.005):
        self.slip_perc = slip_perc 

    cdef double get_slip_price(self, double order_price, Bar bar, bint is_buy) noexcept nogil:
        cdef double pslip

        if is_buy:
            pslip = _round_tick(order_price * (1 + self.slip_perc))
            pslip = pslip if pslip < bar.high else bar.high
            return pslip
        else:
            pslip = _round_tick(order_price * (1 - self.slip_perc))
            pslip = pslip if pslip > bar.low else bar.low
            return pslip


cdef class SmoothSlip(Slippage):
    
    def __init__(self, double slip_perc=0.005):
        self.slip_perc = slip_perc
        
    cdef double get_slip_price(self, double order_price, Bar bar, bint is_buy) noexcept nogil:
        cdef double smooth_price = (bar.open + bar.high + bar.low + bar.close) / 4.0, pslip

        if is_buy:
            pslip = _round_tick(smooth_price * (1.0 + self.slip_perc))
            return pslip if pslip < bar.high else bar.high
        else:
            pslip = _round_tick(smooth_price * (1.0 - self.slip_perc))
            return pslip if pslip > bar.low else bar.low


cdef class LikelihoodSlip(Slippage):
    """
    最悲观成交价滑点模型:
    买入按 bar 最高价成交 (追高代价)
    卖出按 bar 最低价成交 (砸盘代价)
    """

    def __init__(self, double slip_perc=0.005):
        self.slip_perc = slip_perc

    cdef double get_slip_price(self, double order_price, Bar bar, bint is_buy) noexcept nogil:
        cdef double bound
        if is_buy:
            # 买入: 为保证能成交, 按区间最高价但不超过 order_price*(1+slip_perc)容忍上限
            bound = _round_tick(order_price * (1.0 + self.slip_perc))
            return bar.high if bar.high < bound else bound
        else:
            # 卖出: 按区间最低价但不低于 order_price*(1-slip_perc)容忍下限
            bound = _round_tick(order_price * (1.0 - self.slip_perc))
            return bar.low if bar.low > bound else bound


_slip = {
    "default": FixedPercSlip,
    "smooth": SmoothSlip,
    "progressive": LikelihoodSlip,
}