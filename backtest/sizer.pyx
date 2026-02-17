# cython: language_level=3, boundscheck=False, wraparound=False

from libc.stdint cimport int32_t
from libcpp.vector cimport vector


cdef class Sizer:
    cpdef int32_t getsizing(self, bint is_buy):
        return 0

    cpdef void reset(self):
        pass


cdef class Fixed(Sizer):
    '''This is the default sizer used by ``backtrader`` if no other sizer is
    set

    It will simply return a size of ``1`` for each operation
    '''
    cpdef int32_t getsizing(self, bint isbuy):
        return 100


cdef class Pyramid(Sizer):

    def __init__(self, list ratios=None):
        if ratios is None:
            ratios = [40, 40, 20]  
        
        self.max_step = len(ratios)
        self.step = 0
        
        for r in ratios:
            self.ratios.push_back(r)

    cpdef int32_t getsizing(self, bint is_buy):
        cdef int32_t r

        if is_buy:
            if self.step >= self.max_step:
                return 0
            
            r = self.ratios[self.step]
            
            self.step += 1
            return r
        else:
            return 100

    cpdef void reset(self):
        self.step = 0


# cdef class Kelly(Sizer):
#     '''This sizer will return a size based on the Kelly Criterion
# 
#     The Kelly Criterion is a formula used to determine the optimal size of a
#     series of bets in order to maximize the logarithm of wealth. It is often
#     used in gambling and investing to help manage risk and maximize returns.
# 
#     The formula for the Kelly Criterion is:
# 
#     f* = (bp - q) / b
# 
#     where:
# 
#       - f* is the fraction of the current bankroll to wager
# 
#       - b is the net odds received on the wager (i.e., "b to 1") - this is
#         calculated as (1 / (price - 1)) for buy operations and (1 / price) for
#         sell operations
# 
#       - p is the probability of winning (i.e., the probability that the bet
#         will pay off)
# 
#       - q is the probability of losing, which is equal to 1 - p
# 
#     The Kelly Criterion suggests that you should bet a fraction of your
#     bankroll equal to f* in order to maximize your long-term growth rate. If
#     f* is negative, it means that you should not place the bet at all.
# 
#     Note that the Kelly Criterion assumes that you have an edge over the house
#     or market, meaning that your probability of winning (p) is greater than
#     your probability of losing (q). If you do not have an edge, then betting
#     according to the Kelly Criterion may lead to losses over time.
# 
#     This sizer requires that ``self.strategy`` has two methods implemented:
# 
#       - ``kelly_p(self, data)``: returns the probability of winning for the
#         given data
# 
#       - ``kelly_q(self, data)``: returns the probability of losing for the
#         given data
# 
#     '''

