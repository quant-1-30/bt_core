# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from multiprocessing import shared_memory

cimport cython
from libc.string cimport strncpy, memset
from libc.stdint cimport int64_t, uint32_t


cdef extern from *: # 引入内存屏障防止 CPU 或编译器重排指令保证无锁队列的安全性
    """
    #define mem_barrier() __sync_synchronize() 
    """
    void mem_barrier() nogil


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
    #include <unistd.h>
    #include <sched.h>
    """
    void mem_barrier() nogil

    void cpu_relax() nogil
    int sched_yield() nogil
    void usleep(unsigned int usec) nogil


cdef class SharedRingBuffer:

    def __cinit__(self, str shm_name, int capacity, bint is_creator=False):
        """
        初始化共享内存环形队列
        :param shm_name: 共享内存在 OS 层的全局唯一名称
        :param capacity: 队列容量
        :param is_creator: 是否为创建者(主线 Strategy)消费者传 False
        """
        self.capacity = capacity
        
        # 计算 C 结构体需要的总字节数
        cdef size_t header_size = sizeof(RingHeader)
        cdef size_t buffer_size = capacity * sizeof(EventMsg)
        cdef size_t total_size = header_size + buffer_size

        # Python 标准库向操作系统申请/打开真正的共享内存
        if is_creator:
            try:
                self._shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
            except FileExistsError:
                # 如果上次崩溃导致内存未清理先挂载并强行销毁再重新创建
                old_shm = shared_memory.SharedMemory(name=shm_name, create=False)
                old_shm.unlink()
                self._shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
        else:
            # 根据名字挂载已存在的共享内存
            self._shm = shared_memory.SharedMemory(name=shm_name, create=False)

        # 底层内存视图强制转换为无符号字符数组 (Zero-Copy 核心)
        cdef unsigned char[:] mem_view = self._shm.buf

        # 绑定 C 指针到这块共享内存对应的物理偏移量
        self.header = <RingHeader*> &mem_view[0]
        self.buffer = <EventMsg*> &mem_view[header_size]

        # 创建者对内存进行零初始化清理 OS 分配时的脏数据
        if is_creator:
            memset(&mem_view[0], 0, total_size)
            self.header.capacity = capacity
            self.header.head = 0
            # tails 和 active_consumers 数组会被 memset 自动置为 0 / False

    cpdef int register_consumer(self):
        cdef RingHeader* h = self.header

        for i in range(32):
            if not h.active_consumers[i]:
                h.active_consumers[i] = True
                h.tails[i] = h.head # reset
                return i
        raise RuntimeError("共享内存槽位已满")

    cdef void _wait_if(self, RingHeader* h) noexcept nogil: 

        cdef int64_t min_tail
        cdef int32_t i, counter=0

        while True:
            min_tail = h.head
            for i in range(32):
                if h.active_consumers[i]:
                    if h.tails[i] < min_tail:
                        min_tail = h.tails[i]
            
            # slot avoid spin
            if h.head - min_tail < h.capacity:
                break

            # self spin cpu_relax
            counter += 1 

            if counter < 1000:
                cpu_relax()
            else:
                sched_yield()
    
    cdef void publish_account(self, object py_account):
        cdef RingHeader* h = self.header
        cdef EventMsg* buf = self.buffer

        with nogil:
            self._wait_if(h)

        cdef int64_t pos = h.head % self.header.capacity
        cdef EventMsg* msg = &buf[pos]
        
        # union avoi data corruption
        memset(msg, 0, sizeof(EventMsg))

        # Zero-Copy
        msg.type = EACCOUNT
        msg.data.account.datetime = py_account.datetime
        msg.data.account.portfolio_value = py_account.portfolio_value
        msg.data.account.cash = py_account.cash
        msg.data.account.pnl = py_account.pnl
        msg.data.account.leverage = py_account.leverage
        msg.data.account.margin = py_account.margin
        msg.data.account.experiment_id = py_account.experiment_id

    cdef void publish_position(self, object py_pos):
        cdef RingHeader* h = self.header
        cdef EventMsg* buf = self.buffer
        cdef int32_t cap = self.capacity
        
        with nogil:
            self._wait_if(h)
            
        cdef int64_t pos = h.head % cap
        cdef EventMsg* msg = &buf[pos]

        # union avoi data corruption
        memset(msg, 0, sizeof(EventMsg))

        msg.type = EPOSITION
        strncpy(msg.data.position.sid, <bytes>py_pos.sid, 15) # bytes ---> char[]
        msg.data. position.datetime = py_pos.datetime
        msg.data.position.size = py_pos.size
        msg.data.position.available = py_pos.available
        msg.data.position.cost_basis = py_pos.cost_basis
        msg.data.position.pnl = py_pos.pnl
        msg.data.position.created_dt = py_pos.created_dt
        
        self.header.head += 1
    
    cdef void publish_order(self, object py_order):
        cdef RingHeader* h = self.header
        cdef EventMsg* buf = self.buffer
        cdef int32_t cap = self.capacity

        with nogil:
            self._wait_if(h)
            
        cdef int64_t pos = h.head % cap
        cdef EventMsg* msg = &buf[pos]

        # union avoi data corruption
        memset(msg, 0, sizeof(EventMsg))

        msg.type = EORDER
        strncpy(msg.data.order.sid, <bytes>py_order.sid, 16) # bytest -> char[] 
        strncpy(msg.data.order.filler, <bytes>py_order.filler, 16) 

        msg.data.order.pricelimit = py_order.pricelimit
        msg.data.order.sizer_ratio = py_order.sizer_ratio
        msg.data.order.created_dt = py_order.created_dt
        msg.data.order.order_type = py_order.order_type
        msg.data.order.exec_type = py_order.exec_type
        
        self.header.head += 1

    cdef void publish_dt_over(self, int64_t tick):
        cdef RingHeader* h = self.header
        cdef EventMsg* buf = self.buffer
        cdef int32_t cap = self.capacity
        
        with nogil:
            self._wait_if(h)

        cdef int64_t pos = h.head % cap
        cdef EventMsg* msg = &buf[pos]
        
        memset(msg, 0, sizeof(EventMsg))

        msg.type = EDTOVER
        msg.data.dtover.datetime = tick

        self.header.head += 1


    cpdef publish_snapshot(self, object py_snapshot, object py_order):
        self.publish_order(py_order)

        if py_snapshot.trades:
            for trade in py_snapshot.trades:
                self.publish_trade(trade)
        
        for pos in py_snapshot.positions:
            self.publish_position(pos)
        
        self.publish_account(py_snapshot.account)

    cpdef get_events(self, int32_t consumer_id):
        cdef RingHeader* h = self.header
        cdef EventMsg* buf = self.buffer

        cdef int64_t event_tail
        cdef EventMsg* msg
        cdef list events =[]  

        while True:
            event_tail = h.tails[consumer_id]
            
            if event_tail >= self.header.head:
                continue 

            msg = &buf[event_tail % self.header.capacity]
            
            if msg.type == EDTOVER:
                self.header.tails[consumer_id] += 1
                return events
            
            elif msg.type == EACCOUNT:
                events.append({
                    "type": "account",
                    "data": msg.data.account 
                })
            elif msg.type == EPOSITION:
                events.append({
                    "type": "position",
                    "data": msg.data.position
                })
            elif msg.type == ETRADE:
                events.append({
                    "type": "trade",
                    "data": msg.data.trade,
                })
            elif msg.type == EORDER:
                events.append({
                    "type": "order",
                    "data": msg.data.order,
                })

            self.header.tails[consumer_id] += 1
            return events

    cdef close(self):
        if self._shm is not None:
            self._shm.close()

    cdef unlink(self):
        if self._shm is not None:
            self._shm.unlink()
