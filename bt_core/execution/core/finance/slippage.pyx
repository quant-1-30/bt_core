# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++
# cython: language_level=3


cdef class Slippage:

    cdef double _slip_up(self, double pmax, double price):
        return price

    cdef double _slip_down(self, double pmin, double price):
        return price
    
    def __call__(self, double price, double pmax, double pmin, bint isbuy):
        if isbuy:
            return self._slip_up(pmax, price)
        else:
            return self._slip_down(pmin, price)


cdef class PercSlip(Slippage):

    def __init__(self, 
                double slip_perc=0.005):
        self.slip_perc = slip_perc 

    cdef double _slip_up(self, double pmax, double price):
        cdef double pslip = 0.0
        
        pslip = price * (1 + self.slip_perc)
        pslip = pslip if pslip < pmax else pmax
        return pslip # no price can be returned

    cdef double _slip_down(self, double pmin, double price):
        cdef double pslip

        pslip = price * (1 - self.slip_perc)
        pslip = pslip if pslip > pmin else pmin
        return pslip
    
    def __call__(self, double price, double pmax, double pmin, bint isbuy):
        if isbuy:
            return self._slip_up(pmax, price)
        else:
            return self._slip_down(pmin, price)


cdef class FixedSlip(Slippage):

    def __init__(self, 
                double slip_fixed=10):
        self.slip_fixed = slip_fixed

    cdef double _slip_up(self, double pmax, double price):
        cdef double pslip = 0.0
        
        pslip = price + self.slip_fixed
        pslip = pslip if pslip < pmax else pmax
        return pslip # no price can be returned

    cdef double _slip_down(self, double pmin, double price):
        cdef double pslip
        
        pslip = price - self.slip_fixed
        pslip = pslip if pslip > pmin else pmin
        return pslip
    
    def __call__(self, double price, double pmax, double pmin, bint isbuy):
        if isbuy:
            return self._slip_up(pmax, price)
        else:
            return self._slip_down(pmin, price)
