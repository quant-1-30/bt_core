# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++

import numpy as np

cimport numpy as cnp
cnp.import_array() # initialzie numpy C-API

from bt_core.execution.core.finance.common cimport Exchange
from bt_core.execution.core.finance.order cimport OrderCoreData
from bt_core.execution.core.finance.position cimport PositionCoreData

# A 股手续费时间分界点 (unix 秒)
cdef const int64_t STAMP_TAX_CKPT = 1693180800     # 2023-08-28 印花税 1‰ -> 0.5‰
cdef const int64_t TRANSFER_FEE_CKPT = 1651180800  # 2022-04-29 过户费 0.02‰ -> 0.01‰
cdef const int64_t TRANSFER_FEE_UNIFY_CKPT = 1438387200  # 2015-08-01 沪深统一按成交金额 0.02‰ (此前沪市按面值 0.06‰, 深市免收)
cdef const int64_t RatioCkpt = 1433813400          # 2015 佣金 3‰ -> 0.5‰ (万分之5)
cdef const double PAR_TRANSFER_RATE = 6e-5         # 2015-08-01 前沪市过户费面值费率 (每股面值 1 元)


cdef class CommInfoBase:

    def __init__(self,
                 double commission = 0.0,
                 double fixed = 0.0,
                 int32_t commtype = 0):

        self.commission = commission / 100.0
        self.commtype = commtype
        self.fixed = fixed

    cdef double calculate(self, Order order):
        return self.commission

    cdef double getcommission(self, Order order, int32_t size, double price):
        cdef double comm_rate = self.calculate(order)
        cdef double comm 
        
        comm = abs(size) * comm_rate

        if self.commtype == CommType.COMM_PERC:
            comm = abs(size) * comm_rate * price
        return comm
    
    def __call__(self, Order order, int32_t size, double price):
        '''Calculates the commission of an operation at a given price'''
        return self.getcommission(order, size, price)
    
    cdef double get_comm_rate(self, Order order):
        return self.calculate(order)


cdef class CommInfo_Stocks(CommInfoBase):

    cdef (double, double, double) _fee_rates(self, Order order):
        """
            # stamp_rate: 2023-08-28 前 1‰ 卖出, 之后 0.5‰ 卖出; 买入不收
            # transfer_rate: 2022-04-29 前沪深双向 0.02‰, 之后 0.01‰
            
            # commission: 2015-06-09 前 3‰, 之后 0.5‰, 最低 5 元
        """
        cdef bint is_buy = order.isbuy
        cdef OrderCoreData core = order.core

        # 1. stamp_rate
        cdef double stamp_rate = 0.0
        if not is_buy:
            stamp_rate = 5e-4 if core.created_dt >= STAMP_TAX_CKPT else 1e-3

        # 2. transfer_fee (0.01‰ = 1e-5 / 0.02‰ = 2e-5)
        cdef double transfer_rate
        if core.created_dt >= TRANSFER_FEE_CKPT:
            transfer_rate = 1e-5
        elif core.created_dt >= TRANSFER_FEE_UNIFY_CKPT:
            transfer_rate = 2e-5  # 2015-08-01 0.02‰
        else:
            transfer_rate = PAR_TRANSFER_RATE if order.exchange == Exchange.SSE else 0.0

        # 3. commission_rate
        cdef double commission_rate = 3e-3 if core.created_dt < RatioCkpt else 5e-4

        return stamp_rate, transfer_rate, commission_rate

    cdef double calculate(self, Order order):
        cdef double stamp_rate, transfer_rate, commission_rate
        stamp_rate, transfer_rate, commission_rate = self._fee_rates(order)
        return stamp_rate + transfer_rate + commission_rate

    cdef double getcommission(self, Order order, int32_t size, double price):
        """
            A 股手续费 = 印花税 + 过户费 + 佣金
            其中佣金有 5 元最低红线, 印花税/过户费无最低门槛;
            2015-08-01 前沪市过户费按面值 (每股 1 元) 0.06‰ 计, 深市免收
        """
        cdef OrderCoreData core = order.core
        cdef double stamp_rate, transfer_rate, commission_rate
        stamp_rate, transfer_rate, commission_rate = self._fee_rates(order)
        cdef double trade_value = abs(size) * price

        cdef double commission = trade_value * commission_rate
        if commission < 5.0:
            commission = 5.0

        cdef double transfer_fee
        if core.created_dt >= TRANSFER_FEE_UNIFY_CKPT:
            transfer_fee = trade_value * transfer_rate
        else:
            # size * 0.06‰ 
            transfer_fee = PAR_TRANSFER_RATE * abs(size) if order.exchange == Exchange.SSE else 0.0

        return trade_value * stamp_rate + transfer_fee + commission


cdef class CommInfo_Futures(CommInfoBase):
    
    cdef double calculate(self, Order order):
        return self.commission

    cdef double getcommission(self, Order order, int32_t size, double price):
        cdef double comm = size * self.fixed 
        return comm