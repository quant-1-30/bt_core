# distutils: language = c++
# cython: language_level=3

import pytz
import numpy as np
import datetime as py_datetime

from libc.stdint cimport uint8_t, int64_t 

from libc.time cimport time_t, localtime_r, mktime, tm, gmtime
from libc.math cimport floor

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
    cdef time_t rawtime = <time_t>(ts - 28800) if native else <time_t>(ts) 
    cdef tm* info = gmtime(&rawtime)
    return (info.tm_year + 1900) * 10000 + (info.tm_mon + 1) * 100 + info.tm_mday


cdef inline MarketTime market_utc(int64_t ts, bint native=True) nogil :
    cdef MarketTime mt
    cdef int64_t offset = SHANGHAI_OFFSET if native else 0
    cdef int64_t local_day_start_utc = ((ts + offset) // 86400) * 86400 - offset
    
    mt.open_ts = local_day_start_utc + OPEN_OFFSET
    mt.close_ts = local_day_start_utc + CLOSE_OFFSET
    return mt
 

cpdef int64_t get_dt_cmpkey(double dt_ts, int64_t timeframe, int64_t compression=1):
    """
    :param dt_ts: float/double
    :param timeframe: int64_t
    :param compression: int64_t
    :return: int64_t
    """
    cdef:
        time_t ts_sec
        tm t_struct # C struct_tm / tm in cython
        double result_ts
        int64_t tm_year, tm_mon, tm_mday, tm_wday
        int64_t days_to_sunday
        
    if timeframe == TF_NoTimeFrame:
        return <int64_t>dt_ts

    # timestamp ---> C struct tm 
    ts_sec = <time_t>dt_ts

    # replace localtime(&ts_sec)[0] to thread safe localtime_r
    localtime_r(&ts_sec, &t_struct) 

    if timeframe == TF_Years:
        t_struct.tm_mon = 11    # 12月 (0-11)
        t_struct.tm_mday = 31   # 31日
        t_struct.tm_hour = 23
        t_struct.tm_min = 59
        t_struct.tm_sec = 59
        # mktime DST and re
        result_ts = <double>mktime(&t_struct)

    elif timeframe == TF_Months: # 逻辑技巧 下个月第 0 天 mktime 会自动回退到本月最后一天
        t_struct.tm_mon += 1    
        t_struct.tm_mday = 0    
        t_struct.tm_hour = 23
        t_struct.tm_min = 59
        t_struct.tm_sec = 59
        result_ts = <double>mktime(&t_struct)

    elif timeframe == TF_Weeks: # C tm_wday: 0=Sun, 1=Mon, ..., 6=Sat
        days_to_sunday = (7 - t_struct.tm_wday) % 7
        
        t_struct.tm_mday += days_to_sunday
        t_struct.tm_hour = 23
        t_struct.tm_min = 59
        t_struct.tm_sec = 59
        result_ts = <double>mktime(&t_struct)

    elif timeframe == TF_Days:
        t_struct.tm_hour = 23
        t_struct.tm_min = 59
        t_struct.tm_sec = 59
        result_ts = <double>mktime(&t_struct)
    else:
        result_ts = _get_subday_cmpkey_c(dt_ts, &t_struct, timeframe, compression)

    return <int64_t>result_ts


cdef double _get_subday_cmpkey_c(double dt_ts, tm* tm_ptr, int64_t timeframe, int64_t compression):
    cdef:
        long point = 0
        long ph=0, pm=0, ps=0, pus=0
        long extradays = 0
        double result_ts
        
    # Calculate intraday position (Point)
    point = tm_ptr.tm_hour * 60 + tm_ptr.tm_min

    if timeframe < TF_Minutes: # Seconds or Micros
        point = point * 60 + tm_ptr.tm_sec

    if timeframe < TF_Seconds: # Micros 1e6
        pus = <long>((dt_ts - floor(dt_ts)) * 1e6)
        point = point * 1000000 + pus 

    # 关键向上取整 
    point = point // compression  
    point += 1
    point *= compression

    # Decode back to H:M:S:us
    # ---------------------------------------
    if timeframe == TF_Minutes:
        ph = point // 60
        pm = point % 60
        ps = 0
        pus = 0
        
    elif timeframe == TF_Seconds:
        ph = point // 3600
        pm = (point % 3600) // 60
        ps = point % 60
        pus = 0
        
    elif timeframe == TF_MicroSeconds:
        ph = point // 3600000000
        pass

    # Handle Day Overflow
    # ---------------------------------------
    extradays = 0
    if ph > 23:
        extradays = ph // 24
        ph = ph % 24

    # Update Struct TM
    # ---------------------------------------
    tm_ptr.tm_hour = <int64_t>ph
    tm_ptr.tm_min = <int64_t>pm
    tm_ptr.tm_sec = <int64_t>ps
    
    if extradays > 0:
        tm_ptr.tm_mday += <int64_t>extradays

    # Make Timestamp (Canonicalize)
    # ---------------------------------------
    result_ts = <double>mktime(tm_ptr)

    # Apply tadjust 
    # ---------------------------------------
    if timeframe == TF_Minutes:
        result_ts -= 60.0
    elif timeframe == TF_Seconds:
        result_ts -= 1.0
    elif timeframe == TF_MicroSeconds:
        result_ts -= 0.000001

    return result_ts


cpdef object tzparse(str tz):
    # If no object has been provided by the user and a timezone can be
    # found via contractdtails, then try to get it from pytz, which may or
    # may not be available.
    if not tz:
        return py_datetime.timezone.utc

    tzinfo = pytz.timezone(tz)
    return tzinfo
