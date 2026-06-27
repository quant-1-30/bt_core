# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++
# cython: language_level=3


cdef class Slippage:

    cdef double get_slip_price(self, double order_price, double open, double high, double low, double close, bint is_buy) noexcept nogil:
        return order_price
    

cdef class FixedPercSlip(Slippage):

    def __init__(self, 
                double slip_perc=0.005):
        self.slip_perc = slip_perc 

    cdef double get_slip_price(self, double order_price, double open, double high, double low, double close, bint is_buy) noexcept nogil:
        cdef double pslip

        if is_buy:
            pslip = order_price * (1 + self.slip_perc)
            pslip = pslip if pslip < high else high
            return pslip
        else:
            pslip = order_price * (1 - self.slip_perc)
            pslip = pslip if pslip > low else low
            return pslip


cdef class SmoothSlip(Slippage):
    
    def __init__(self, double slip_perc=0.005):
        self.slip_perc = slip_perc
        
    cdef double get_slip_price(self, double order_price, double b_open, double b_high, double b_low, double b_close, bint is_buy) noexcept nogil:
        cdef double smooth_price = (b_open + b_high + b_low + b_close) / 4.0, pslip

        if is_buy:
            pslip = smooth_price * (1.0 + self.slip_perc)
            return pslip if pslip < b_high else b_high
        else:
            pslip = smooth_price * (1.0 - self.slip_perc)
            return pslip if pslip > b_low else b_low


cdef class LikehoodSlip(Slippage):
    
    def __init__(self, double slip_perc=0.005):
        self.slip_perc = slip_perc

    cdef double get_slip_price(self, double order_price, double b_open, double b_high, double b_low, double b_close, bint is_buy) noexcept nogil:
        cdef double pslip
        
        pslip = b_high if is_buy else b_low
        return pslip * self.slip_perc


_slip = {
    "default": FixedPercSlip,
    "smooth": SmoothSlip,
    "progressive": Likehood
}
