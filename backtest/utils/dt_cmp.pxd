from libc.time cimport time_t, localtime, mktime, tm
from libc.stdint cimport int64_t

cdef enum:
    TF_TICK=0
    TF_MicroSeconds = 1
    MilliSecond = 2
    TF_Seconds = 3
    TF_Minutes = 4
    TF_Days = 5
    TF_Weeks = 6
    TF_Months = 7
    TF_Years = 8
    TF_NoTimeFrame = 9


cpdef int64_t get_dt_cmpkey(double dt_ts, int64_t timeframe, int64_t compression=?)

cdef double _get_subday_cmpkey_c(double dt_ts, tm* tm_ptr, int64_t timeframe, int64_t compression)