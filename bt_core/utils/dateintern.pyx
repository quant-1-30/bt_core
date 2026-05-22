# distutils: language = c++
# cython: language_level=3

import pytz
import numpy as np
import datetime as py_datetime

# from cpython.datetime cimport import_datetime, PyDateTime_DateTime # invisable
from libc.stdint cimport uint8_t, int64_t 
from libc.time cimport gmtime, time_t, tm

from cpython.datetime cimport datetime, import_datetime, \
    PyDateTime_DATE_GET_HOUR, \
    PyDateTime_DATE_GET_MINUTE, \
    PyDateTime_DATE_GET_SECOND, \
    PyDateTime_DATE_GET_MICROSECOND

import_datetime()

cpdef object num2date(double x, bint native=True): # inline only used in cdef
    """
    Unix 时间戳直接算术转换
    """
    cdef int64_t ix = <int64_t>x
    cdef int year, month, day, hour, minute, second, microsecond
    cdef double remainder
    cdef int64_t ts

    if np.isnan(x) or x <=0:
        return py_datetime.datetime.min

    if 10000000 < ix < 30000000:
        year = <int>(ix // 10000)
        month = <int>((ix % 10000) // 100)
        day = <int>(ix % 100)
        return py_datetime.datetime(year, month, day)

    if ix > 1000000000: # Unix Timestamp
        ts = <int64_t>ix - (SHANGHAI_OFFSET if native else 0 )
        return py_datetime.datetime.fromtimestamp(ts)

    # ordinal  ---> matplotlib 0001-01-01 days 
    dt_base = py_datetime.datetime.fromordinal(<int>ix)
    remainder = x - ix
    # C ops --->  Python divmod
    remainder *= HOURS_PER_DAY
    hour = <int>remainder
    remainder = (remainder - hour) * MINUTES_PER_HOUR
    minute = <int>remainder
    remainder = (remainder - minute) * SECONDS_PER_MINUTE
    second = <int>remainder
    microsecond = <int>((remainder - second) * 1000000)
    
    if microsecond < 10: 
        microsecond = 0
    elif microsecond > 999990:
        microsecond = 0
        second += 1 # 位运算
    return py_datetime.datetime(dt_base.year, dt_base.month, dt_base.day, 
                             hour, minute, second, microsecond)

# cpdef double date2num(object dt): # adapt matplotlib ordinal days
#     # python datetime to struct c datetime
#     # data[0-1]: year, data[2]: month, data[3]: day
#     # data[4]: hour, data[5]: minute, data[6]: second
#     # data[7-9]: microsecond (3 byte)
#     cdef int hour = PyDateTime_DATE_GET_HOUR(dt)
#     cdef int minute = PyDateTime_DATE_GET_MINUTE(dt)
#     cdef int second = PyDateTime_DATE_GET_SECOND(dt)
#     cdef int microsecond = PyDateTime_DATE_GET_MICROSECOND(dt)
# 
#     return dt.toordinal() + (hour / 24.0 + minute / 1440.0 + 
#                             second / 86400.0 + microsecond / 86400000000.0)


cpdef double date2num(object dt):
    return dt.timestamp()


cpdef int64_t ts2intdt(double ts, bint native = True): # only cdef nogil
    # tzinfo="Asia/Shanghai" native
    if np.isnan(ts) or ts <= 0:
        return 0
    cdef time_t rawtime = <time_t>(ts - 28800) if native else <time_t>(ts) 
    cdef tm* info = gmtime(&rawtime)
    return (info.tm_year + 1900) * 10000 + (info.tm_mon + 1) * 100 + info.tm_mday


cpdef object tzparse(str tz):
    # If no object has been provided by the user and a timezone can be
    # found via contractdtails, then try to get it from pytz, which may or
    # may not be available.
    if not tz:
        return py_datetime.timezone.utc

    tzinfo = pytz.timezone(tz)
    return tzinfo


cdef inline MarketTime market_utc(int64_t ts, bint native=True) nogil :
    cdef MarketTime mt
    cdef int64_t offset = SHANGHAI_OFFSET if native else 0
    cdef int64_t local_day_start_utc = ((ts + offset) // 86400) * 86400 - offset
    
    mt.open_ts = local_day_start_utc + OPEN_OFFSET
    mt.close_ts = local_day_start_utc + CLOSE_OFFSET
    return mt
