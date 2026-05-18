# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
from libc.time cimport time_t, localtime_r, mktime, tm
from libc.math cimport floor
from cpython.datetime cimport datetime_new, import_datetime


# 初始化 CPython datetime API
import_datetime()


cpdef int64_t get_dt_cmpkey(double dt_ts, int64_t timeframe, int64_t compression=1):
    """
    :param dt_ts: 输入的时间戳 (float/double), 替代原来的 datetime 对象
    :param timeframe: 周期类型 (int64_t)
    :param compression: 压缩倍数 (int64_t)
    :return: (int_timestamp, datetime_object)
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

    # t_ptr = gmtime(&ts_sec) # utc
    # if t_ptr == NULL: return 0
    # t_struct = t_ptr[0] 

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
