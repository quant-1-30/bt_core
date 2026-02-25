cdef class Slippage:

    def __init__(self, 
                double slip_perc=0.0, 
                double slip_fixed=0.0):
        self.slip_fixed = slip_fixed
        self.slip_perc = slip_perc 

    cdef double _slip_up(self, double pmax, double price):
        cdef double pslip = 0.0
        if self.slip_perc > 0.0:
            pslip = price * (1 + self.slip_perc)
        elif self.slip_fixed > 0.0:
            pslip = price + self.slip_fixed
        else:
            pslip = price

        pslip = pslip if pslip < pmax else pmax
        return pslip # no price can be returned

    cdef double _slip_down(self, double pmin, double price):
        cdef double pslip
        if self.slip_perc > 0.0:
            pslip = price * (1 - self.slip_perc)
        elif self.slip_fixed > 0.0:
            pslip = price - self.slip_fixed
        else:
            pslip = price

        pslip = pslip if pslip > pmin else pmin
        return pslip
    
    def __call__(self, double price, double pmax, double pmin, bint isbuy):
        if isbuy:
            return self._slip_up(pmax, price)
        else:
            return self._slip_down(pmin, price)
