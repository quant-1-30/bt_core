# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++
# cython: language_level=3

from bt_core.execution.gateway.operator.schema import OrderBit

from bt_protocol._protocol import TradeBody, Resp


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
                bytes order_id, 
                int64_t executed_dt=0, 
                int64_t executed_size=0, 
                double executed_price=0.0, 
                double comm=0.0,
                bool isbuy=False):

        self.core.order_id = order_id
        self.core.executed_dt = <int64_t>executed_dt
        self.core.executed_price = executed_price
        self.core.executed_size = executed_size
        self.core.comm = comm
        self.core.isbuy = isbuy

    # property val:
    #     def __get__(self):
    #         return self.core.val

    cdef OrderExecutionBit clone(self):
        cdef OrderExecutionBit obj = OrderExecutionBit.__new__(OrderExecutionBit)
        obj.core.order_id = self.core.order_id
        obj.core.executed_dt = self.core.executed_dt
        obj.core.executed_size = self.core.executed_size
        obj.core.executed_price = self.core.executed_price
        obj.core.comm = self.core.comm
        obj.core.isbuy = self.core.isbuy
        return obj 
    
    cdef object serialize(self):
        cdef object body, resp
        body = TradeBody(order_id=self.core.order_id, executed_dt=self.core.executed_dt, executed_price=self.core.executed_price, 
                        executed_size=self.core.executed_size, comm=self.core.comm, isbuy=self.core.isbuy)   
        resp = Resp(body=body)
        return resp
    
    cdef object to_schema(self):
        return OrderBit(
            order_id=self.core.order_id,
            executed_dt=self.core.executed_dt,
            executed_price=self.core.executed_price,
            executed_size=self.core.executed_size,
            comm=self.core.comm,
            isbuy=self.core.isbuy
        )

    cdef OrderExbitData get_snapshot(self):
        return self.core
    
    def __reduce__(self): # class / args
        return (OrderExecutionBit, (self.core.order_id, self.core.executed_dt, self.core.executed_size, 
                                    self.core.executed_price, self.core.comm, self.core.isbuy))

    def __repr__(self):
        return f"OrderExecutionBit(order_id={self.core.order_id}, executed_dt={self.core.executed_dt}, executed_size={self.core.executed_size}, \
            executed_price={self.core.executed_price}, comm={self.core.comm}, isbuy={self.core.isbuy})"
