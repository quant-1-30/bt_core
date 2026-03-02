#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from backtest.execution.gateway.operator.schema import OrderBit
from bt_sdk.core.protocol import TradeBody, Resp


cdef class OrderExecutionBit:
    '''
    Intended to hold information about order execution. A "bit" does not
    determine if the order has been fully/partially executed, it just holds
    information.

    Member Attributes:

      - executed_dt: datetime (float) execution time
      - executed_size: how much was executed
      - executed_price: execution price
      - comm: commission for the entire bit execution

    '''
    def __init__(self,
                bytes vtorder_id, 
                int executed_dt=0, 
                int executed_size=0, 
                double executed_price=0.0, 
                double comm=0.0,
                bool isbuy=False):

        self.vtorder_id = vtorder_id
        self.core.executed_dt = <int64_t>executed_dt
        self.core.executed_price = executed_price
        self.core.executed_size = executed_size
        self.core.comm = comm

        if isbuy:
            self.core.cash = -1 * executed_price * executed_size - comm
        else:
            self.core.cash = executed_price * executed_size - comm

        self.isbuy = isbuy

    property cash:
        def __get__(self):
            return self.core.cash

    cdef OrderExecutionBit clone(self):
        cdef OrderExecutionBit obj = OrderExecutionBit.__new__(OrderExecutionBit)
        obj.vtorder_id = self.vtorder_id
        obj.core.executed_dt = self.core.executed_dt
        obj.core.executed_size = self.core.executed_size
        obj.core.executed_price = self.core.executed_price
        obj.core.comm = self.core.comm
        obj.core.cash = self.core.cash
        obj.isbuy = self.isbuy
        return obj 
    
    cdef object to_schema(self):
        return OrderBit(
            order_id=self.vtorder_id,
            executed_dt=self.core.executed_dt,
            executed_price=self.core.executed_price,
            executed_size=self.core.executed_size,
            comm=self.core.comm,
            isbuy=self.isbuy
        )
    
    cdef object serialize(self):
        cdef object body, resp
        body = TradeBody(vtorder_id=self.vtorder_id, executed_dt=self.core.executed_dt, executed_price=self.core.executed_price, 
                        executed_size=self.core.executed_size, comm=self.core.comm, isbuy=self.isbuy)   
        resp = Resp(body=body)
        return resp
    
    def __reduce__(self): # class / args
        return (OrderExecutionBit, (self.vtorder_id, self.core.executed_dt, self.core.executed_price, 
                                    self.core.executed_size, self.core.comm))

    def __repr__(self):
        return f"OrderExecutionBit(vtorder_id={self.vtorder_id}, executed_dt={self.core.executed_dt}, executed_size={self.core.executed_size}, \
            executed_price={self.core.executed_price}, comm={self.core.comm}, isbuy={self.isbuy})"