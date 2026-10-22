from libc.stdint cimport int32_t, int64_t


cdef struct CashData:
    double cash
    int session

    
cdef struct AdjustmentData:
    double bonus_share
    double transfer
    double bonus


cdef struct RightData:
    double ratio # not divide by 10
    double price


cdef struct EventItem:
    int32_t ex_date
    int event_type  # 0 为 adjustment, 1 为 right
    AdjustmentData adj
    RightData rgt


cdef struct ExecPrep:
    int32_t start_loc
    int32_t total_size
    double target_price
    double order_price
    double limit_down
    double limit_up
    double cash


cdef enum Exchange:
    SSE = 0              # Shanghai Stock Exchange
    SZSE = 1             # Shenzhen Stock Exchange
    BSE = 2              # Beijing Stock Exchange


cdef enum:
    TS_MAGNITUDE = 100000000  # unix ts (~1.7e9) vs ymd int (~2e7) threshold


