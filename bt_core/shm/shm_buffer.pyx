# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

import numpy as np
cimport numpy as cnp

from multiprocessing import shared_memory

cimport cython
from libc.string cimport strncpy, memcpy, memset
from libc.stdint cimport int64_t, uint32_t

cdef enum:
    # ~100ms spin ceiling when producer has exited without publishing sentinel
    MAX_DRAIN_SPIN = 1000000

cdef const char* _HEX = "0123456789abcdef"

cdef inline void _write_order_id(char* dst, bytes py_oid) noexcept:
    cdef const unsigned char* src = <const unsigned char*>(<char*>py_oid)
    cdef Py_ssize_t n = len(py_oid)
    cdef Py_ssize_t i
    cdef unsigned char b
    if n == 16:
        for i in range(16):
            b = src[i]
            dst[i * 2] = _HEX[b >> 4]
            dst[i * 2 + 1] = _HEX[b & 0x0f]
        dst[32] = 0
    else:
        if n > 32:
            n = 32
        memcpy(dst, src, n)
        dst[n] = 0


# dtype ---> numpy Structured Arrays C struct
# 'i8' = int64, 'f8' = float64, 'S16' = 16 bytes
dtype = cnp.dtype([
    ('datetime', 'i8'), 
    ('value', 'f8'), 
    ('metrics', 'S64')
])


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
    #define mem_barrier() __atomic_thread_fence(__ATOMIC_ACQ_REL)
    #define acquire_barrier() __atomic_thread_fence(__ATOMIC_ACQUIRE)
    #define release_barrier() __atomic_thread_fence(__ATOMIC_RELEASE)
    #include <sched.h>
    """
    void mem_barrier() nogil
    void acquire_barrier() nogil
    void release_barrier() nogil
    void cpu_relax() nogil
    int sched_yield() nogil


cdef inline object _open_shm(str shm_name, size_t total_size, bint is_creator):
    if is_creator:
        try:
            return shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
        except FileExistsError:
            shared_memory.SharedMemory(name=shm_name, create=False).unlink()
            return shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
    return shared_memory.SharedMemory(name=shm_name, create=False)


cdef inline void _unlink_shm(object shm):
    if shm is not None:
        try:
            shm.unlink()
        except FileNotFoundError:
            pass


cdef class SharedRingBuffer: # SPMC

    def __cinit__(self, str shm_name, int64_t capacity, bint is_creator=False):
        """
        :param shm_name: str
        :param capacity: int64_t
        :param is_creator: whether to create shm
        """
        # C Struct bytes
        cdef size_t header_size = sizeof(RingHeader)
        cdef size_t buffer_size = capacity * sizeof(EventMsg)
        cdef size_t total_size = header_size + buffer_size

        self._shm = _open_shm(shm_name, total_size, is_creator)
        cdef unsigned char[:] mem_view = self._shm.buf # zero_copy core

        # C binding offset
        self.header = <RingHeader*> &mem_view[0]
        self.buffer = <EventMsg*> &mem_view[header_size]

        if is_creator:
            memset(&mem_view[0], 0, total_size) # empty memory
            self.header.capacity = capacity
            self.header.head = 0
            # tails 和 active_consumers 数组会被 memset 自动置为 0 / False

    cpdef int32_t register_consumer(self):
        cdef RingHeader* h = self.header
        cdef int32_t i

        for i in range(32):
            if not h.active_consumers[i]:
                h.active_consumers[i] = True
                # start at current head: tail=0 would replay the entire ring
                # (stale/garbage slots) to a late-registered consumer
                h.tails[i] = h.head
                return i
        raise RuntimeError("共享内存槽位已满")

    cpdef void unregister_consumer(self, int32_t consumer_id):
        """Release a consumer slot so its frozen tail can no longer stall
        the producer (``_wait_if`` only waits on ACTIVE consumers).

        Call when a consumer is permanently gone (crashed / retired):
        without this the producer would spin forever in nogil once the
        ring wraps to that consumer's last-read position."""
        cdef RingHeader* h = self.header
        if h == NULL:
            return
        if 0 <= consumer_id < 32:
            h.active_consumers[consumer_id] = False

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
        release_barrier()
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
        if self.header == NULL:
            return
        
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = eSENTINEL
        msg.data.sentinel.datetime = tick

        self._advance()
    
    cdef void publish_account(self, object py_account):
        if self.header == NULL:
            return
        
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
        if self.header == NULL:
            return
        
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = ePOSITION
        strncpy(msg.data.position.sid, <bytes>py_pos.sid, 16) # bytes ---> char[]
        msg.data.position.sid[15] = 0

        msg.data. position.datetime = py_pos.datetime
        msg.data.position.size = py_pos.size
        msg.data.position.available = py_pos.available
        msg.data.position.cost_basis = py_pos.cost_basis
        msg.data.position.pnl = py_pos.pnl
        msg.data.position.created_dt = py_pos.created_dt
        
        self._advance()

    cdef void publish_trade(self, object py_trade):
        if self.header == NULL:
            return
        
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = eTRADE
        _write_order_id(msg.data.trade.order_id, <bytes>py_trade.order_id)

        msg.data.trade.executed_dt = py_trade.executed_dt
        msg.data.trade.executed_price = py_trade.executed_price
        msg.data.trade.comm = py_trade.comm
        msg.data.trade.executed_size = py_trade.executed_size
        msg.data.trade.isbuy = py_trade.isbuy
        
        self._advance()

    cpdef void publish_snapshot(self, object py_snapshot):
        if py_snapshot.trades:
            for trade in py_snapshot.trades:
                self.publish_trade(trade)
        
        for pos in py_snapshot.positions:
            self.publish_position(pos)
        
        self.publish_account(py_snapshot.account)
    
    cpdef void publish_order(self, object py_order):
        if self.header == NULL:
            return
        
        cdef EventMsg* msg

        with nogil:
            msg = self._get_msg()

        msg.type = eORDER
        strncpy(msg.data.order.sid, <bytes>py_order.sid, 16)
        msg.data.order.sid[15] = 0 
        
        _write_order_id(msg.data.order.order_id, <bytes>py_order.order_id)

        strncpy(msg.data.order.filler, <bytes>py_order.filler, 16) 
        msg.data.order.filler[15] = 0  

        msg.data.order.price = py_order.price
        msg.data.order.sizer_ratio = py_order.sizer_ratio
        msg.data.order.created_dt = py_order.created_dt
        msg.data.order.order_type = py_order.order_type
        msg.data.order.exec_type = py_order.exec_type
        
        self._advance()
     
    cpdef list drain_events(self, int32_t consumer_id):
        cdef RingHeader* h = self.header
        if h == NULL:
            return []  # already closed: avoid NULL deref
        cdef EventMsg* buf = self.buffer
        cdef EventMsg* msg
        # int64: total published events can exceed 2^31 over long runs
        cdef int64_t event_tail = h.tails[consumer_id]
        cdef int64_t cur_head = event_tail
        cdef int32_t cap = h.capacity
        cdef list events = []
        cdef int32_t spin_count = 0

        while True:
            if self.header == NULL:
                break
            if event_tail >= cur_head:
                cur_head = h.head
                if event_tail >= cur_head:
                    spin_count += 1
                    if spin_count > MAX_DRAIN_SPIN:
                        break
                    with nogil:
                        if spin_count < 1000:
                            cpu_relax()
                        else:
                            sched_yield()
                    continue
                spin_count = 0
                acquire_barrier()  # single acquire barrier per batch of newly observed head

            msg = &buf[event_tail % cap]
            event_tail += 1
            if msg.type == eSENTINEL:
                break
            elif msg.type == eACCOUNT:
                events.append({"type": "account", "data": msg.data.account})
            elif msg.type == ePOSITION:
                events.append({"type": "position", "data": msg.data.position})
            elif msg.type == eTRADE:
                events.append({"type": "trade", "data": msg.data.trade})
            elif msg.type == eORDER:
                events.append({"type": "order", "data": msg.data.order})

        release_barrier()
        h.tails[consumer_id] = event_tail
        return events

    cpdef void close(self):
        # avoid suspending ptr
        self.header = NULL 
        self.buffer = NULL
        
        if self._shm is not None:
            self._shm.close()

    cpdef void unlink(self):
        _unlink_shm(self._shm)


cdef class LogRingBuffer: # MPSC

    def __cinit__(self, str shm_name, int32_t capacity, bint is_creator=False):
        # cdef size_t header_size = (sizeof(LogRingHeader) + 63) & ~63
        cdef size_t header_size = sizeof(LogRingHeader)
        cdef size_t total_size = header_size + (capacity * sizeof(MetricMsg))
        self.capacity = capacity

        self._shm = _open_shm(shm_name, total_size, is_creator)
        cdef unsigned char[:] mem_view = self._shm.buf
        self.header = <LogRingHeader*> &mem_view[0]
        self.buffer = <MetricMsg*> &mem_view[header_size]
        self._consumer_alive = True

        if is_creator:
            memset(&mem_view[0], 0, total_size)
            self.header.capacity = capacity
            self.header.head = 0
            self.header.tail = 0

    cpdef void release_consumer(self):
        """Mark the drain side as gone: the producer stops waiting for it
        (backpressure disabled - it overwrites the oldest slots instead of
        spinning forever in nogil). Data loss beats a hung process; only
        safe because this buffer is single-process (bt_core internal)."""
        self._consumer_alive = False

    cdef void _wait_if_full(self) noexcept nogil:
        cdef LogRingHeader* h = self.header
        cdef int32_t counter = 0

        while self._consumer_alive and h.head - h.tail >= h.capacity:
            counter += 1
            if counter < 1000:
                cpu_relax()
            else:
                sched_yield()

    cpdef void publish_metric(self, bytes metrics, double value, int64_t dt):
        if self.header == NULL:
            return

        cdef LogRingHeader* h = self.header
        cdef int64_t pos = h.head % self.capacity
        cdef MetricMsg* msg
        
        with nogil:
            self._wait_if_full()
            
        msg = &self.buffer[pos]
        
        msg.datetime = dt
        msg.value = value
        
        strncpy(msg.metrics, <char*>metrics, 64)
        msg.metrics[63] = '\0' # auto add \0 in end for safety
        
        with nogil:
            release_barrier()
            h.head += 1

    cpdef object drain_metrics(self, int32_t batch=10000):
        cdef LogRingHeader* h = self.header
        if h == NULL:
            return np.array([])  # already closed: avoid NULL deref
        cdef int64_t current_tail = h.tail
        cdef int64_t current_head = h.head
        cdef MetricMsg* src = self.buffer
        cdef int32_t i

        cdef int64_t available = current_head - current_tail
        if available <= 0:
            return np.array([]) 

        acquire_barrier()
        cdef int64_t count = min(available, <int64_t>batch)
        
        cdef cnp.ndarray[cnp.uint8_t, ndim=1] raw_arr = np.empty(count * sizeof(MetricMsg), dtype=np.uint8) 
        cdef MetricMsg* dest = <MetricMsg*> &raw_arr[0]

        for i in range(count):
            dest[i] = src[(current_tail + i) % self.capacity]
            
        release_barrier()
        h.tail = current_tail + count
        return raw_arr.view(dtype)
    
    cpdef void close(self):
        self.header = NULL
        self.buffer = NULL
        
        if self._shm is not None:
            self._shm.close()

    cpdef void unlink(self):
        _unlink_shm(self._shm)
