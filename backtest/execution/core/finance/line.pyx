# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
#cython.boundscheck(False) # 关闭边界检查
#cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++

cnp.import_array() # 必须调用以初始化 numpy C-API
import numpy as np

from libcpp.algorithm cimport binary_search
from libcpp.algorithm cimport lower_bound 
from libc.stddef cimport size_t


cdef class LineAlias:

    def __init__(self, str name):
        self.name = name

    cdef void append(self, double value):
        self._data.push_back(value)

    cdef void extend(self, double[:] arr): # memoryview
        cdef int32_t i
        for i in range(arr.shape[0]):
            self._data.push_back(arr[i])

    cdef double[:] get_array(self):  # cpdef double[:, ::1] get_array(self):  
        cdef double[:] buffer_view = np.empty(self._data.size(), dtype=np.float64)
        cdef Py_ssize_t n = self._data.size() # unsigned long
        cdef Py_ssize_t i  # Py_ssize_t 是 Python 和 Cython 中处理容器索引的标准类型与 size_t 比较
        for i in range(n):
            buffer_view[i] = self._data[i]
        return buffer_view

    def __len__(self):
        return self._data.size()

    def __gt__(self, value): #  via numpy 
        return self.get_array() > value

    def clear(self):
        self._data.clear() # memory keep / shrink_to_fit


cdef class Lines:

    def __init__(self):
        self._size = 0

    cdef void batch_load(self, double[:, :] arr): 
        """
            Memoryview (double[:, :]) numpy array zero_copy
        """
        cdef int32_t n = arr.shape[0]
        cdef int32_t i
        
        for i in range(n):
            self.tick.push_back(<int64_t>arr[i, 0])
            self.open.push_back(arr[i, 1])
            self.high.push_back(arr[i, 2])
            self.low.push_back(arr[i, 3])
            self.close.push_back(arr[i, 4])
            self.volume.push_back(arr[i, 5])
            self.amount.push_back(arr[i, 6])
        
        self._size += n

    cdef Bar getvalue(self, int32_t idx):
        """返回 C 结构体包装的 Bar 或者纯 Python 字典/元组"""
        cdef Bar bar
        if idx < 0 or idx >= self._size:
            raise IndexError("Line index out of range")
        
        bar.tick = self.tick[idx]
        bar.open = self.open[idx]
        bar.high = self.high[idx]
        bar.low = self.low[idx]
        bar.close = self.close[idx]
        bar.volume = self.volume[idx]
        bar.amount = self.amount[idx]
        return bar

    property open:
        def __get__(self):
            cdef double[:] arr = <double[:self._size]>self.open.data() # C++ vector ---> return Memoryview 
            return np.asarray(arr)# .data means memory ptr

    property high:
        def __get__(self):
            cdef double[:] arr = <double[:self._size]>self.high.data()
            return np.asarray(arr)

    property low:
        def __get__(self):
            cdef double[:] arr = <double[:self._size]>self.low.data()
            return np.asarray(arr)
    
    property close:
        def __get__(self):
            cdef double[:] arr = <double[:self._size]>self.close.data()
            return np.asarray(arr)

    property volume:
        def __get__(self):
            cdef double[:] arr = <double[:self._size]>self.volume.data()
            return np.asarray(arr)

    property amount:
        def __get__(self):
            cdef double[:] arr = <double[:self._size]>self.amount.data()
            return np.asarray(arr) 

    cdef double max(self): 
        if self._size == 0: return 0.0
        cdef double m = self.high[0]
        cdef int32_t i
        for i in range(1, self._size):
            if self.high[i] > m: m = self.high[i]
        return m

    cdef double min(self):
        if self._size == 0: return 0.0
        cdef double m = self.low[0]
        cdef int32_t i
        for i in range(1, self._size):
            if self.low[i] < m: m = self.low[i]
        return m

    cdef bint is_in(self, int64_t tick):
        cdef vector[int64_t]* vec = &self.tick
        # return binary_search(vec.begin(), vec.end(), tick)
        return binary_search(vec[0].begin(), vec[0].end(), tick) # deref(vec).begin # ptr[0] means ptr

    def __len__(self):
        return self._size

    def __iter__(self):
        cdef int32_t i
        for i in range(self._size):
            yield self.getvalue(i) 
