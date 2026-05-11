# cython: language_level=3
from libc.stdint cimport int64_t, int32_t, uint8_t

cdef enum EventType:
    EACCOUNT = 1
    EPOSITION = 2
    ETRADE = 3
    EORDER = 4
    EDTOVER = 5

cdef struct AccountData:
    int64_t datetime
    double portfolio_value
    double cash
    double pnl
    double leverage
    double margin

cdef struct PositionData:
    char sid[16]          # bytes char数组 
    int64_t datetime
    double cost_basis
    double pnl
    int32_t size
    int32_t available

cdef struct TradeData:
    char order_id[32]
    int64_t executed_dt
    double executed_price
    double comm
    int32_t executed_size
    int32_t isbuy     

cdef struct OrderData:
    char sid[16]
    char filler[16]
    double pricelimit
    double sizer_ratio
    int64_t created_dt
    int32_t order_type
    int32_t exec_type

cdef struct DtOverData:
    int64_t datetime


cdef union EventData:
    AccountData account # 48
    PositionData position # 48
    TradeData trade # 64
    OrderData order #
    DtOverData dtover 


cdef struct EventMsg:
    int32_t type
    uint8_t _pad1[4]
    int64_t dt_over_time
    EventData data         
    # 末尾对齐到 64 字节的倍数（比如总长 128）
    uint8_t _pad2[56]      


cdef struct RingHeader:
    # 强制 volatile 保证内存可见性
    volatile int64_t head             
    volatile int64_t tails[32]     
    int32_t capacity                  
    uint8_t _pad[4]      
    
    volatile int32_t active_consumers[32] # 32 * 4 = 128
    
    uint8_t _pad1[48] # (400 + 63) & ~63 = 448


cdef class SharedRingBuffer:
    cdef RingHeader* header
    cdef EventMsg* buffer
    cdef int32_t capacity
    cdef object _shm          # Python SharedMemory 对象的引用防止被GC

    cpdef int register_consumer(self)
    
    cdef void _wait_if(self, RingHeader* h) noexcept nogil# nogil 函数不能接收 self必须接收 C 指针

    cpdef publish_account(self, object py_account)
    
    cpdef publish_position(self, object py_pos)

    cpdef publish_order(self, object py_order)

    cpdef publish_dt_over(self, int64_t tick)

    cpdef get_events(self, int consumer_id)

    cdef close(self)

    cdef unlink(self)
