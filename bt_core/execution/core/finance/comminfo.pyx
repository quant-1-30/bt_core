# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
cnp.import_array() # 必须调用以初始化 numpy C-API

import numpy as np

#from libc.stdint cimport int64_t

from bt_core.execution.core.finance.common cimport Exchange
from bt_core.execution.core.finance.order cimport OrderCoreData
from bt_core.execution.core.finance.position cimport PositionCoreData

cdef const int64_t RatioCkpt = 1433813400 # 2015年 万分之5


cdef class CommInfoBase:
    '''Base Class for the Commission Schemes.
    Params:

      - ``commission`` (def: ``0.0``): base commission value in percentage or
        monetary units

      - ``mult`` (def ``1.0``): multiplier applied to the asset for
        value/profit

      - ``margin`` (def: ``None``): amount of monetary units needed to
        open/hold an operation. It only applies if the final ``_stocklike``
        attribute in the class is set to ``False``

      - ``automargin`` (def: ``False``): Used by the method ``get_margin``
        to automatically calculate the margin/guarantees needed with the
        following policy

          - Use param ``margin`` if param ``automargin`` evaluates to ``False``

          - Use param ``mult`` * ``price`` if ``automargin < 0``

          - Use param ``automargin`` * ``price`` if ``automargin > 0``

      - ``commtype`` (def: ``None``): Supported values are
        ``CommType.COMM_PERC`` (commission to be understood as %) and
        ``CommType.COMM_FIXED`` (commission to be understood as monetary
        units)

        The default value of ``None`` is a supported value to retain
        compatibility with the legacy ``CommissionInfo`` object. If
        ``commtype`` is set to None, then the following applies:

          - ``margin`` is ``None``: Internal ``_commtype`` is set to
            ``COMM_PERC`` and ``_stocklike`` is set to ``True`` (Operating
            %-wise with Stocks)

          - ``margin`` is not ``None``: ``_commtype`` set to ``COMM_FIXED`` and
            ``_stocklike`` set to ``False`` (Operating with fixed rount-trip
            commission with Futures)

        If this param is set to something else than ``None``, then it will be
        passed to the internal ``_commtype`` attribute and the same will be
        done with the param ``stocklike`` and the internal attribute
        ``_stocklike``

      - ``stocklike`` (def: ``False``): Indicates if the instrument is
        Stock-like or Futures-like (see the ``commtype`` discussion above)

      - ``percabs`` (def: ``False``): when ``commtype`` is set to COMM_PERC,
        whether the parameter ``commission`` has to be understood as XX% or
        0.XX

        If this param is ``True``: 0.XX
        If this param is ``False``: XX%

      - ``interest`` (def: ``0.0``)

        If this is non-zero, this is the yearly interest charged for holding a
        short selling position. This is mostly meant for stock short-selling

        The formula: ``days * price * abs(size) * (interest / 365)``

        It must be specified in absolute terms: 0.05 -> 5%

        .. note:: the behavior can be changed by overriding the method:
                 ``_get_credit_interest``

      - ``interest_long`` (def: ``False``)

        Some products like ETFs get charged on interest for short and long
        positions. If ths is ``True`` and ``interest`` is non-zero the interest
        will be charged on both directions

      - ``leverage`` (def: ``1.0``)

        Amount of leverage for the asset with regards to the needed cash

    Attributes:

      - ``_stocklike``: Final value to use for Stock-like/Futures-like behavior
      - ``_commtype``: Final value to use for PERC vs FIXED commissions

      This two are used internally instead of the declared params to enable the
      compatibility check described above for the legacy ``CommissionInfo``
      object

    '''
    def __init__(self, 
                 double commission = 0.0,
                 double interest = 0.0,
                 int32_t commtype = 0):

        self.commission = commission / 100.0
        self.creditrate = interest / 365.0
        self.commtype = commtype
        self._stocklike = False

    property stocklike:
        def __get__(self):
            return self._stocklike 

    def __call__(self, Order order, int32_t size, double price):
        '''Calculates the commission of an operation at a given price
        '''
        return self.getcommission(order, size, price)

    cdef double calculate(self, Order order):
        return self.commission

    cdef double getcommission(self, Order order, int32_t size, double price):
        cdef double comm_rate = self.calculate(order)
        
        if self.commtype == CommType.COMM_PERC:
            return abs(size) * comm_rate * price
        return abs(size) * comm_rate

    cdef double get_credit_interest(self, Position pobj, int64_t dt):
        cdef PositionCoreData core = pobj.core

        cdef long days = (dt - core.datetime) // 86400
        if days <= 0:
            return 0.0
        
        return days * self.creditrate * abs(core.size) * core.price


cdef class CommInfo_Stocks(CommInfoBase):

    def __init__(self):
        self._stocklike = True

    cdef double calculate(self, Order order):
        """
            # 印花税 1‰(卖的时候才收取 全国统一)
            # 过户费：深圳交易所无 / 上海交易所万分之1 买卖
            # 交易佣金:最高收费为3‰ / 2015 5/10000
        """
        cdef bint is_buy = order.isbuy
        cdef OrderCoreData core = order.core

        stamp_commission = 0 if is_buy else 1e-3
        transfer_commission = 1e-4 if order.exchange == Exchange.SSE else 0
        trade_commission = 3e-3 if core.created_dt < RatioCkpt else 5e-4

        comm = stamp_commission + transfer_commission + trade_commission
        return comm


cdef class CommInfo_Futures(CommInfoBase):
    
    def __init__(self, 
                 double commission = 0.0,
                 double interest=0.0,
                 int32_t commtype = CommType.COMM_FIXED):
        super(CommInfo_Futures, self).__init__(commission,
                                               interest,
                                               commtype)
    cdef double calculate(self, Order order):
        return self.commission
