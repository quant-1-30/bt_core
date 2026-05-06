#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import uuid
import numpy as np
from backtest.execution.gateway.operator.schema import vtOrder

from libcpp.vector cimport vector
from cpython.object cimport Py_EQ

from backtest.execution.core.finance.common cimport Exchange
from backtest.execution.utils.util cimport fast_uuid4_bytes

cimport numpy as cnp
cnp.import_array() # 必须调用以初始化 numpy C-API


cdef class Order:

    def __init__(self, 
                 bytes experiment_id,
                 bytes sid,
                 double sizer_ratio,
                 double pricelimit,
                 int32_t order_type,
                 int32_t exec_type,
                 int32_t created_dt,
                 bytes filler):

        self.core.experiment_id = experiment_id
        self.core.sid = sid
        self.core.size = 0
        self.core.sizer_ratio = sizer_ratio  #  sizer_ratio / 100
        self.core.price = 0.0
        self.core.pricelimit = pricelimit # pricelimit / 100
        self.core.order_type = order_type
        self.core.exec_type = exec_type
        self.core.created_dt = created_dt

        self.status = 0
        self.filler = filler
        self.info = AssetCore(0, 0, 0, False)

        self._exchange = Exchange.SSE if sid.startswith(b"60") else Exchange.SZSE
        self.core.vtorder_id = fast_uuid4_bytes() # uuid.uuid4().bytes

        # cache  
        self._exbits = []
        self._exbits_schema = []
        self.cached_uuid = uuid.UUID(bytes=experiment_id)

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

    cdef void addinfo(self, dict asset_info):
        '''Add the keys, values of kwargs to the internal info dictionary to
        hold custom information in the order
        include: preclose / asset info 
        '''
        self.info = AssetCore(asset_info["first_trading"], asset_info["delist"], asset_info["tick_size"], asset_info["increment"])

    cdef on_fix(self, double price):
        self.core.price = price

    cdef void execute(self, int32_t size, double price, OrderExecutionBit order_bit): # except * 
        cdef OrderExbitData core = order_bit.core
        cdef int32_t exbit_size = core.executed_size

        if exbit_size <= 0:
            return

        self._exbits.append(order_bit)
        self._exbits_schema.append(order_bit.to_schema())

        # partial = abs(self.core.size) - abs(exbit_size)
        partial = abs(size) - abs(exbit_size)
        if partial > 0:
            self.partial()
        else: 
            # partial == 0
            self.completed()
        
        # update core.size
        self.core.size = size
        self.core.price = price 
     
    cdef Order clone(self):
        cdef Order obj = Order.__new__(Order) # only allocate memory
        cdef OrderCoreData core 

        core.experiment_id = self.core.experiment_id
        core.sid = self.core.sid
        core.size = self.core.size
        core.sizer_ratio = self.core.sizer_ratio
        core.price = self.core.price
        core.pricelimit = self.core.pricelimit
        core.order_type = self.core.order_type
        core.exec_type = self.core.exec_type
        core.created_dt = self.core.created_dt
        core.vtorder_id = self.core.vtorder_id

        obj.filler = self.filler
        obj.info = self.info
        obj.status = self.status
        # obj._exbits = self._exbits # reference copy / clone exbit
        obj._exbits = list(self._exbits)  
        obj._exchange = self._exchange
        obj.core = core
        return obj 

    cdef list serialize(self):
        cdef data = []
        cdef OrderExecutionBit exbit

        for exbit in self._exbits:
            data.append(exbit.serialize())
        return data
    
    cdef object to_schema(self):
        # cdef OrderExecutionBit exbit
        # cdef object experiment_id = uuid.UUID(self.core.experiment_id.decode("utf-8"))
        # cdef object experiment_id = uuid.UUID(bytes=self.core.experiment_id)

        vtorder = vtOrder(
            # experiment_id=experiment_id,
            experiment_id=self.cached_uuid,
            sid=self.core.sid,
            order_id=self.core.vtorder_id,
            price=self.core.price,
            size=self.core.size,
            order_type=self.core.order_type,
            exec_type = self.core.exec_type,
            created_dt=self.core.created_dt
        )
        # orderBits = [exbit.to_schema() for exbit in self._exbits] # complex object need to be serialized used for insert into pg
        # vtorder.order_bits.extend(orderBits)

        vtorder.order_bits.extend(self._exbits_schema)
        return vtorder

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
    
    def __len__(self):
        return len(self._exbits)
        
    def __eq__(self, other):
        if other is None:
            return False
        
        if not isinstance(other, Order):
            return False
        
        cdef Order o = <Order>other # cast
        return self.core.vtorder_id == o.core.vtorder_id

    # def __richcmp(x, y, int op):
    #     cdef:
    #         Order r
    #         str v_id
        
    #     r, y = (x, y) if isinstance(x, Order) else (y, x)
    #     v_id = r.vtorder_id

    #     if op = Py_EQ:
    #         return v_id == y

    def __reduce__(self): # class / args
        return (Order, (self.core.experiment_id, self.core.sid, self.core.sizer_ratio, self.core.pricelimit, 
                        self.core.order_type, self.core.exec_type, self.core.created_dt, self.filler)      
        )
    
    def __repr__(self):
        return f"Order(experiment_id={self.core.experiment_id}, sid={self.core.sid}, \
            created_dt={self.core.created_dt}, sizer_ratio={self.core.sizer_ratio}, pricelimit={self.core.pricelimit}, \
            order_type={self.core.order_type}, exec_type={self.core.exec_type}, filler={self.filler})"
