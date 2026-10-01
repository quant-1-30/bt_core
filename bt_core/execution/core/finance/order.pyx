# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++

import uuid
import numpy as np
cimport numpy as cnp
# initialize numpy C-API
cnp.import_array()

from libcpp.vector cimport vector
from cpython.object cimport Py_EQ

from bt_core.execution.core.finance.common cimport Exchange
from bt_core.utils.util cimport fast_uuid4_bytes


cdef class Order:

    def __init__(self, 
                 bytes experiment_id,
                 bytes sid,
                 bytes order_id,
                 double sizer_ratio,
                 double price,
                 int32_t order_type,
                 int32_t exec_type,
                 int32_t created_dt,
                 bytes filler):

        self.core.experiment_id = experiment_id
        self.core.sid = sid
        self.core.size = 0
        self.core.sizer_ratio = sizer_ratio  
        self.core.price = price
        self.core.order_type = order_type
        self.core.exec_type = exec_type
        self.core.created_dt = created_dt

        self.status = 0
        self.filler = filler
        self.info = AssetCore()

        self._exchange = Exchange.SSE if sid.startswith(b"60") else (
            Exchange.SZSE if not (sid.startswith(b"4") or sid.startswith(b"8") or sid.startswith(b"92"))
            else Exchange.BSE)
        # self.core.order_id = fast_uuid4_bytes() # uuid.uuid4().bytes
        self.core.order_id = order_id

        # cache
        self._exbits = []
        self._cum_filled = 0
        self.cached_uuid = uuid.UUID(bytes=experiment_id)

        self.core.limit_ratio = float('inf')

    property alive:
        def __get__(self):
            '''Returns True if the order is in a status in which it can still be
            executed
            '''
            return self.status in [OrderStatus.Created, OrderStatus.Submitted,
                               OrderStatus.Partial, OrderStatus.Accepted]

    property isbuy:
        def __get__(self):
            '''Returns True if the order is a Buy order'''
            return self.core.order_type == OrderType.Buy

    property exchange:
        def __get__(self):
            return self._exchange            
    
    property exbits:
        def __get__(self):
            '''Returns True if the order is a Buy order'''
            return self._exbits

    cdef void addinfo(self, Asset asset):
        '''Add the keys, values of kwargs to the internal info dictionary to
        hold custom information in the order
        include: preclose / asset info 
        '''
        self.info = asset.core

    cdef void execute(self, int32_t size, OrderExecutionBit order_bit, double order_price): # except *
        cdef OrderExbitData core = order_bit.core
        cdef int32_t exbit_size = core.executed_size

        if exbit_size <= 0:
            return

        self._exbits.append(order_bit)

        # completed/partial must be judged on cumulative filled size,
        # not on the size of this single bit (multi-fill orders would
        # otherwise never reach Completed). Incremental O(1) counter —
        # an exbits rescan here made multi-fill orders O(n^2).
        self._cum_filled += exbit_size

        if self._cum_filled < abs(size):
            self.partial()
        else:
            # fully filled
            self.completed()

        # update core.size
        self.core.size = size
        self.core.price = order_price
   
    cdef void submit(self):
        '''Marks an order as submitted and stores the broker to which it was
        submitted'''
        self.status = OrderStatus.Submitted
    
    cdef void accept(self):
        '''Marks an order as submitted and stores the broker to which it was
        submitted'''
        self.status = OrderStatus.Accepted
    
    cdef void reject(self):
        '''Marks an order as rejected'''
        self.status = OrderStatus.Rejected

    cdef void partial(self):
        '''Marks an order as partially filled'''
        self.status = OrderStatus.Partial

    cdef void expire(self):
        '''Marks an order as expired. Returns True if it worked'''
        self.status = OrderStatus.Expired

    cdef void completed(self):
        '''Marks an order as completely filled'''
        self.status = OrderStatus.Completed
    
    cdef void cancel(self):
        '''Marks an order as cancelled'''
        self.status = OrderStatus.Canceled

    cdef object serialize(self):
        cdef data_body = []
        cdef OrderExecutionBit exbit

        for exbit in self._exbits:
            data_body.append(exbit.serialize().body)
        return data_body

    cdef OrderCoreData get_snapshot(self):
        return self.core

    def __len__(self):
        return len(self._exbits)
        
    def __eq__(self, other):
        if other is None:
            return False
        
        if not isinstance(other, Order):
            return False
        
        cdef Order o = <Order>other # cast
        return self.core.order_id == o.core.order_id

    def __hash__(self):
        # defining __eq__ without __hash__ makes Order unhashable in Python;
        # identity follows order_id (same field __eq__ compares)
        return hash(self.core.order_id)

    # def __richcmp(x, y, int op):
    #     cdef:
    #         Order r
    #         str v_id
        
    #     r, y = (x, y) if isinstance(x, Order) else (y, x)
    #     v_id = r.order_id

    #     if op = Py_EQ:
    #         return v_id == y

    def __reduce__(self): # class / args
        return (Order, (self.core.experiment_id, self.core.sid, self.core.order_id,
                        self.core.sizer_ratio, self.core.price, self.core.order_type,
                        self.core.exec_type, self.core.created_dt, self.filler)
        )
    
    def __repr__(self):
        return f"Order(experiment_id={self.core.experiment_id}, sid={self.core.sid}, \
            created_dt={self.core.created_dt}, sizer_ratio={self.core.sizer_ratio}, \
            order_type={self.core.order_type}, exec_type={self.core.exec_type}, filler={self.filler})"
