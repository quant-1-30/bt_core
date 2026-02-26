# distutils: language = c++
# cython: language_level=3

# C typedef / cython ctypedef

import numpy as np
import datetime
import pyarrow as pa

from libc.stdint cimport uint8_t, int64_t
from libc.time cimport gmtime, time_t, tm


cdef extern from "<uuid/uuid.h>" nogil:
    ctypedef uint8_t uuid_t[16]
    void uuid_generate(uuid_t out)
    void uuid_unparse_lower(const uuid_t uu, char *out)


# C typedef / cython ctypedef
cdef inline uuid128 fast_uuid4_c() nogil:
    cdef uuid128 uu
    uuid_generate(uu.data)
    return uu

cpdef inline bytes fast_uuid4_bytes():
    cdef uuid_t uu
    uuid_generate(uu)
    return (<char*>uu)[:16]


cpdef inline str fast_uuid4_str(): 
    cdef uuid_t uu
    cdef char out[37] # 36byte + \0
    with nogil:
        uuid_generate(uu)
        uuid_unparse_lower(uu, out)
    return out[:36].decode('ascii')


cdef inline object num2date(double x, bint native=True):
    """
    Unix 时间戳直接算术转换
    """
    cdef int64_t ix = <int64_t>x
    cdef int year, month, day, hour, minute, second, microsecond
    cdef double remainder
    cdef int64_t ts

    if np.isnan(x) or x <=0:
        return datetime.datetime.min

    if 10000000 < ix < 30000000:
        year = <int>(ix // 10000)
        month = <int>((ix % 10000) // 100)
        day = <int>(ix % 100)
        return datetime.datetime(year, month, day)

    if ix > 1000000000: # Unix Timestamp
        ts = <int64_t>ix - (SHANGHAI_OFFSET if native else 0 )
        return datetime.datetime.fromtimestamp(ts)

    # ordinal  0001-01-01 days 
    dt_base = datetime.datetime.fromordinal(<int>ix)
    remainder = x - ix
    # C ops --->  Python divmod
    remainder *= HOURS_PER_DAY
    hour = <int>remainder
    remainder = (remainder - hour) * MINUTES_PER_HOUR
    minute = <int>remainder
    remainder = (remainder - minute) * SECONDS_PER_MINUTE
    second = <int>remainder
    microsecond = <int>((remainder - second) * 1000000)
    
    if microsecond < 10: microsecond = 0
    elif microsecond > 999990:
        microsecond = 0
        second += 1 # 位运算
    return datetime.datetime(dt_base.year, dt_base.month, dt_base.day, 
                             hour, minute, second, microsecond)


cdef inline MarketTime market_utc(int64_t ts, bint native=True) nogil :
    cdef MarketTime mt
    cdef int64_t offset = SHANGHAI_OFFSET if native else 0
    cdef int64_t local_day_start_utc = ((ts + offset) // 86400) * 86400 - offset
    
    mt.open_ts = local_day_start_utc + OPEN_OFFSET
    mt.close_ts = local_day_start_utc + CLOSE_OFFSET
    return mt
           

cdef inline int64_t ts2intdt(int64_t ts, bint native=True) nogil: # only cdef nogil
    # C api / tzinfo="Asia/Shanghai" native
    cdef time_t rawtime = <time_t>(ts-28800) if native else <time_t>(ts) 
    cdef tm* info = gmtime(&rawtime)
    return (info.tm_year + 1900) * 10000 + (info.tm_mon + 1) * 100 + info.tm_mday

