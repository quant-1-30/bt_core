# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

import numpy as np
cimport numpy as cnp
# np create array / cnp cdef 

import multiprocessing as mp
from multiprocessing import shared_memory

cimport cython
from libc.string cimport strncpy, memset
from libc.stdint cimport int64_t, uint32_t


mp.set_start_method('spawn', force=True)


cdef extern from *: 
    """
    #if defined(__i386__) || defined(__x86_64__)
        #include <immintrin.h>
        #define cpu_relax() _mm_pause()
    #elif defined(__aarch64__) || defined(__arm__)
        #define cpu_relax() __asm__ volatile("yield" ::: "memory")
    #else
        #define cpu_relax() ((void)0)
    #endif
    #define mem_barrier() __sync_synchronize()
    #include <sched.h>
    """
    void mem_barrier() nogil # 引入内存屏障防止CPU或编译器重排指令保证无锁队列安全性
    void cpu_relax() nogil
    int sched_yield() nogil


cdef class SharedRingBuffer: # SPMC

    def __cinit__(self, str shm_name, int64_t capacity, bint is_creator=False):
        """
        初始化共享内存环形队列
        :param shm_name: 共享内存在 OS 层的全局唯一名称
        :param capacity: 队列容量
        :param is_creator: 是否为创建者(主线 Strategy)消费者传 False
        """
        # C Struct bytes
        cdef size_t header_size = sizeof(RingHeader)
        cdef size_t buffer_size = capacity * sizeof(EventMsg)
        cdef size_t total_size = header_size + buffer_size

        if is_creator:
            try:
                self._shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
            except FileExistsError:
                shared_memory.SharedMemory(name=shm_name, create=False).unlink()
                self._shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
        else:
            self._shm = shared_memory.SharedMemory(name=shm_name, create=False)

        cdef unsigned char[:] mem_view = self._shm.buf # zero_copy core

        # C binding offset
        self.header = <RingHeader*> &mem_view[0]
        self.buffer = <EventMsg*> &mem_view[header_size]

        if is_creator:
            memset(&mem_view[0], 0, total_size)
            self.header.capacity = capacity
            self.header.head = 0
            # tails 和 active_consumers 数组会被 memset 自动置为 0 / False

    cpdef int32_t register_consumer(self):
        cdef RingHeader* h = self.header
        cdef int32_t i

        for i in range(32):
            if not h.active_consumers[i]:
                h.active_consumers[i] = True
                # h.tails[i] = h.head # reset
                h.tails[i] = 0
                return i
        raise RuntimeError("共享内存槽位已满")

    cdef void _wait_if(self, RingHeader* h) noexcept nogil: 

        cdef int64_t min_tail
        cdef int32_t i, counter = 0

        while True:
            min_tail = h.head
            for i in range(32):
                if h.active_consumers[i]:
                    if h.tails[i] < min_tail:
                        min_tail = h.tails[i]
            
            # slot avoid spin
            if h.head - min_tail < h.capacity:
                break

            counter += 1
            if counter < 1000:
                cpu_relax() # self spin cpu_relax
            else:
                sched_yield() # layoff cpu 
    
    cdef void _advance(self) noexcept nogil:
        mem_barrier()
        self.header.head += 1

    cdef EventMsg* _get_msg(self) noexcept nogil:
        cdef EventMsg* msg
        cdef RingHeader* h = self.header
        cdef int32_t pos, cap = self.header.capacity

        self._wait_if(h)
        pos = self.header.head % cap
        msg = &self.buffer[pos]
        memset(msg, 0, sizeof(EventMsg))
        return msg
 
    cpdef void publish_sentinel(self, int64_t tick):
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = eSENTINEL
        msg.data.sentinel.datetime = tick

        self._advance()
    
    cdef void publish_account(self, object py_account):
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        # Zero-Copy
        msg.type = eACCOUNT
        msg.data.account.datetime = py_account.datetime
        msg.data.account.portfolio_value = py_account.portfolio_value
        msg.data.account.cash = py_account.cash
        msg.data.account.pnl = py_account.pnl
        msg.data.account.leverage = py_account.leverage
        msg.data.account.margin = py_account.margin
        
        self._advance()

    cdef void publish_position(self, object py_pos):
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = ePOSITION
        strncpy(msg.data.position.sid, <bytes>py_pos.sid, 15) # bytes ---> char[]
        msg.data.position.sid[15] = 0

        msg.data. position.datetime = py_pos.datetime
        msg.data.position.size = py_pos.size
        msg.data.position.available = py_pos.available
        msg.data.position.cost_basis = py_pos.cost_basis
        msg.data.position.pnl = py_pos.pnl
        msg.data.position.created_dt = py_pos.created_dt
        
        self._advance()

    cdef void publish_trade(self, object py_trade):
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = eORDER
        strncpy(msg.data.trade.order_id, <bytes>py_trade.order_id, 16) # bytest -> char[] 
        msg.data.trade.order_id[15] = 0  

        msg.data.trade.executed_dt = py_trade.executed_dt
        msg.data.trade.executed_price = py_trade.executed_price
        msg.data.trade.comm = py_trade.comm
        msg.data.trade.executed_size = py_trade.executed_size
        msg.data.trade.isbuy = py_trade.isbuy
        
        self._advance()
    
    cpdef void publish_order(self, object py_order):
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = eORDER
        strncpy(msg.data.order.sid, <bytes>py_order.sid, 16) # bytest -> char[]
        msg.data.order.sid[15] = 0  
        strncpy(msg.data.order.filler, <bytes>py_order.filler, 16) 
        msg.data.order.filler[15] = 0  

        msg.data.order.pricelimit = py_order.pricelimit
        msg.data.order.sizer_ratio = py_order.sizer_ratio
        msg.data.order.created_dt = py_order.created_dt
        msg.data.order.order_type = py_order.order_type
        msg.data.order.exec_type = py_order.exec_type
        
        self._advance()
    
    cpdef void publish_snapshot(self, object py_snapshot):
        if py_snapshot.trades:
            for trade in py_snapshot.trades:
                self.publish_trade(trade)
        
        for pos in py_snapshot.positions:
            self.publish_position(pos)
        
        self.publish_account(py_snapshot.account)
    
    cpdef list drain_events(self, int32_t consumer_id):
        cdef RingHeader* h = self.header
        cdef EventMsg* buf = self.buffer
        cdef EventMsg* msg
        cdef int32_t event_tail, cap = self.header.capacity
        cdef list events = []  
        
        cdef int32_t counter = 0

        while True:
            event_tail = h.tails[consumer_id]
            
            if event_tail >= h.head:
                counter += 1
                with nogil: # handover gil
                    if counter < 1000:
                        cpu_relax() 
                    else:
                        sched_yield() 
                continue 
            
            counter = 0
            msg = &buf[event_tail % cap]
 

            msg = &buf[event_tail % cap]
            
            if msg.type == eSENTINEL:
                h.tails[consumer_id] += 1
                break 
            
            elif msg.type == eACCOUNT:
                events.append({"type": "account", "data": msg.data.account})
            elif msg.type == ePOSITION:
                events.append({"type": "position", "data": msg.data.position})
            elif msg.type == eTRADE:
                events.append({"type": "trade", "data": msg.data.trade})
            elif msg.type == eORDER:
                events.append({"type": "order", "data": msg.data.order})

            h.tails[consumer_id] += 1
        return events

    cpdef void close(self):
        if self._shm is not None:
            self._shm.close()

    cpdef void unlink(self):
        if self._shm is not None:
            self._shm.unlink() # incase shm is corruption


cdef class LogRingBuffer: # MPSC

    def __cinit__(self, str shm_name, int32_t capacity, bint is_creator=False):
        # cdef size_t header_size = (sizeof(LogRingHeader) + 63) & ~63
        cdef size_t header_size = sizeof(LogRingHeader)
        cdef size_t total_size = header_size + (capacity * sizeof(MetricMsg))
        self.capacity = capacity

        if is_creator:
            try:
                self._shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
            except FileExistsError:
                shared_memory.SharedMemory(name=shm_name).unlink()
                self._shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
        else:
            self._shm = shared_memory.SharedMemory(name=shm_name, create=False)

        cdef unsigned char[:] mem_view = self._shm.buf
        self.header = <LogRingHeader*> &mem_view[0]
        self.buffer = <MetricMsg*> &mem_view[header_size]

        if is_creator:
            memset(&mem_view[0], 0, total_size)
            self.header.capacity = capacity
            self.header.head = 0
            self.header.tail = 0

    cdef void _wait_if_full(self) noexcept nogil:
        cdef LogRingHeader* h = self.header
        cdef int32_t counter = 0

        while h.head - h.tail >= h.capacity:
            counter += 1
            if counter < 1000:
                cpu_relax()
            else:
                sched_yield()

    cpdef void publish_metric(self, bytes metrics, double value, int64_t dt):
        cdef LogRingHeader* h = self.header
        cdef int64_t pos = h.head % self.capacity
        cdef MetricMsg* msg
        
        with nogil:
            self._wait_if_full()
            
        msg = &self.buffer[pos]
        
        msg.datetime = dt
        msg.value = value
        
        strncpy(msg.metrics, <char*>metrics, 15)
        msg.metrics[15] = b'\0'
        
        with nogil:
            mem_barrier()
            h.head += 1

    cpdef object drain_metrics(self, int32_t min_batch, int32_t max_batch=50000):
        cdef LogRingHeader* h = self.header
        cdef int64_t current_tail = h.tail
        cdef int64_t current_head = h.head
        cdef int32_t i

        cdef int64_t available = current_head - current_tail
        cdef int64_t count = min(available, <int64_t>max_batch)

        if available < min_batch: # avoid 0 to accumulate
            return None
            
        # dtype ---> numpy Structured Arrays C struct
        # 'i8' = int64, 'f8' = float64, 'S16' = 16 bytes
        dtype = cnp.dtype([
            ('datetime', 'i8'), 
            ('value', 'f8'), 
            ('metrics', 'S16')
        ])
        
        cdef cnp.ndarray arr = np.empty(count, dtype=dtype)  
        cdef MetricMsg* dest = <MetricMsg*>arr.data
        cdef MetricMsg* src = self.buffer
        
        for i in range(count):
            dest[i] = src[(current_tail + i) % self.capacity] # C struct ---> slot of array`
            
        h.tail = current_tail + count
        return arr
    
    cpdef bint has_data(self):
        return self.header.head > self.header.tail
    
    cpdef void close(self):
        if self._shm is not None:
            self._shm.close()

    cpdef void unlink(self):
        if self._shm is not None:
            self._shm.unlink()
