# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# distutils: language = c++

import numpy as np
cimport numpy as cnp

from libcpp.algorithm cimport binary_search
from libc.stdint cimport int32_t, int64_t


cdef class Lines:
    
    def __init__(self):
        self._size = 0

    cdef void batch_load(self, double[:, :] arr):
        cdef int32_t n = arr.shape[0]
        cdef int32_t i

        # pre-reserve memory
        self._v_tick.reserve(self._size + n)
        self._v_open.reserve(self._size + n)
        self._v_high.reserve(self._size + n)
        self._v_low.reserve(self._size + n)
        self._v_close.reserve(self._size + n)
        self._v_volume.reserve(self._size + n)
        self._v_amount.reserve(self._size + n)

        for i in range(n):
            self._v_tick.push_back(<int64_t>arr[i, 0])
            self._v_open.push_back(arr[i, 1])
            self._v_high.push_back(arr[i, 2])
            self._v_low.push_back(arr[i, 3])
            self._v_close.push_back(arr[i, 4])
            self._v_volume.push_back(arr[i, 5])
            self._v_amount.push_back(arr[i, 6])

        self._size += n

        # ==========================================================
        # critical C-ptr
        # ==========================================================
        self.tick = self._v_tick.data()
        self.open = self._v_open.data()
        self.high = self._v_high.data()
        self.low = self._v_low.data()
        self.close = self._v_close.data()
        self.volume = self._v_volume.data()
        self.amount = self._v_amount.data()

    # -----------------------------------------------------------
    # nogil
    # -----------------------------------------------------------
    cdef double max(self) nogil:
        if self._size == 0: return 0.0
        
        cdef double m = self.high[0] 
        cdef int32_t i
        for i in range(1, self._size):
            if self.high[i] > m:
                m = self.high[i]
        return m

    cdef double min(self) nogil:
        if self._size == 0: return 0.0

        cdef double m = self.low[0]
        cdef int32_t i
        for i in range(1, self._size):
            if self.low[i] < m:
                m = self.low[i]
        return m

    # =========================================================
    # 🌟 C++ Vector replace np.searchsorted
    # =========================================================

    cdef bint is_in(self, int64_t tick_val) nogil:
        if self._size == 0: return False
        # C++ vector 
        return binary_search(self._v_tick.begin(), self._v_tick.end(), tick_val)

    cdef int32_t get_loc(self, int64_t target_tick) nogil:
        if self._size == 0:
            return 0
            
        cdef vector[int64_t].iterator it = lower_bound(self._v_tick.begin(), self._v_tick.end(), target_tick)
        return <int32_t>(it - self._v_tick.begin())

    cdef Bar getvalue(self, int32_t idx) nogil:
        cdef Bar bar
        bar.tick = self.tick[idx]
        bar.open = self.open[idx]
        bar.high = self.high[idx]
        bar.low = self.low[idx]
        bar.close = self.close[idx]
        bar.volume = self.volume[idx]
        bar.amount = self.amount[idx]
        return bar

    def __len__(self):
        return self._size

    cpdef clear(self):
        self._v_tick.clear()
        self._v_open.clear()
        self._v_high.clear()
        self._v_low.clear()
        self._v_close.clear()
        self._v_volume.clear()
        self._v_amount.clear()
        self._size = 0
