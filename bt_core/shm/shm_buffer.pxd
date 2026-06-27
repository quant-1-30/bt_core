# cython: language_level=3
from libc.stdint cimport int64_t, int32_t, uint8_t

cdef enum EventType:
    eACCOUNT = 1
    ePOSITION = 2
    eTRADE = 3
    eORDER = 4
    eSENTINEL = 5

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
    int64_t created_dt
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
    char order_id[16]
    char filler[16]
    double price
    double sizer_ratio
    int64_t created_dt
    int32_t order_type
    int32_t exec_type

cdef struct SENTINEL:
    int64_t datetime

cdef union EventData:
    AccountData account # 48
    PositionData position # 48
    TradeData trade # 64
    OrderData order #
    SENTINEL sentinel

cdef struct EventMsg:
    int32_t type
    uint8_t _pad1[4]
    int64_t dt_over_time
    EventData data         
    uint8_t _pad2[56] # 末尾对齐到 64 字节

cdef struct RingHeader:
    volatile int64_t head # 编译器不优化访问 / 内存可见性        
    volatile int64_t tails[32]     
    int32_t capacity                  
    uint8_t _pad[4]      
    volatile int32_t active_consumers[32] # 32 * 4 = 128
    uint8_t _pad1[48] # (400 + 63) & ~63 = 448

cdef struct MetricMsg:
    int64_t datetime    
    double value    
    char metrics[64] # 63 bytes + '\0' char align 1 byte 

cdef struct LogRingHeader:
    # memory visable / avoid register cache
    volatile int64_t head 
    volatile int64_t tail  
    int32_t capacity
    uint8_t _pad[4]          


cdef class SharedRingBuffer:
    cdef RingHeader* header
    cdef EventMsg* buffer
    cdef int32_t capacity
    cdef object _shm  # Python SharedMemory avoid gc

    cpdef int32_t register_consumer(self)
    
    cdef void _advance(self) noexcept nogil
    
    cdef void _wait_if(self, RingHeader* h) noexcept nogil # nogil 函数不能接收 self必须接收 C 指针
   
    cdef EventMsg* _get_msg(self) noexcept nogil
    
    cpdef void publish_sentinel(self, int64_t tick)
    
    cdef void publish_account(self, object py_account)
    
    cdef void publish_position(self, object py_pos)

    cdef void publish_trade(self, object py_trade)
    
    cpdef void publish_snapshot(self, object py_snapshot)
    
    cpdef void publish_order(self, object py_order)

    cpdef list drain_events(self, int32_t consumer_id)

    cpdef void close(self)

    cpdef void unlink(self)


cdef class LogRingBuffer: # MPSC
    cdef LogRingHeader* header
    cdef MetricMsg* buffer
    cdef int32_t capacity
    cdef object _shm

    cdef void _wait_if_full(self) noexcept nogil

    cpdef void publish_metric(self, bytes metrics, double value, int64_t dt)

    cpdef object drain_metrics(self, int32_t batch=*)

    cpdef void close(self)

    cpdef void unlink(self)
