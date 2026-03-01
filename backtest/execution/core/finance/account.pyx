#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True

"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import uuid
from backtest.execution.core.gateway.operator.schema import vtAccount
from bt_sdk.core.protocol import AccountBody, Resp

from backtest.execution.core.finance.position cimport Position


cdef class Account:
    '''
    Keeps and updates the size and price of a position. The object has no
    relationship to any asset. It only keeps size and price.

    Member Attributes:
      - size (int): current size of the position
      - price (float): current price of the position

    The Position instances can be tested using len(position) to see if size
    is not null
    '''

    def __init__(self, 
                bytes experiment_id, 
                int64_t datetime=0, 
                double portfolio_value=0.0, 
                double cash=0.0, 
                double pnl=0.0, 
                double leverage=1.0, 
                double margin=0.0
                ):

        self.core.experiment_id = experiment_id
        self.core.datetime = <int64_t>datetime
        self.core.portfolio_value = portfolio_value
        self.core.cash = cash
        self.core.pnl = pnl 
        self.core.leverage = leverage
        self.core.margin = margin
 
    cdef void set_cash(self, CashData body, bint reset=True):
        # print("set_cash body", body)
        if reset:
            self.restore()
        self.core.cash = body.cash
        self.core.datetime = body.session

    cdef void restore(self):
        """set to zero"""
        self.core.datetime=0
        self.core.portfolio_value=0.0
        self.core.cash=0.0
        self.core.pnl=0.0
        self.core.leverage=1.0
        self.core.margin=0.0

    cdef void add_cash(self, double cash):
        cdef double _cash
        _cash = self.core.cash + cash
        self.core.cash = _cash

    cdef void update(self, dict pobjs):
        '''
        Updates the current position on Account
        '''
        cdef double _v = 0.0
        cdef double _cash = 0.0
        cdef double _pnl = 0.0
        cdef int64_t max_dt = self.core.datetime
        
        # cdef pair[int, Position] item # pair ---> C++ for(auto& item : pobjs)
        cdef Position p

        for p in pobjs.values():
            _v += p.core.pval
            _cash += p.core.cash
            _pnl += p.core.pnl
            max_dt = max(p.core.datetime, max_dt)

        self.core.portfolio_value = _v
        self.core.pnl = _pnl
        self.core.datetime = max_dt
        self.core.cash += _cash

    cdef sync_dt(self, int64_t tick):
        self.core.datetime = tick

    cdef Account clone(self):
        cdef Account obj = Account.__new__(Account) # only allocate memory
        cdef AccountCoreData core

        core.experiment_id = self.core.experiment_id
        core.portfolio_value=self.core.portfolio_value 
        core.cash=self.core.cash
        core.pnl=self.core.pnl
        core.leverage=self.core.leverage 
        core.margin=self.core.margin
        core.datetime = self.core.datetime
        obj.core = core
        return obj

    cdef object serialize(self):
        cdef object body, resp

        body = AccountBody(experiment_id=self.core.experiment_id, datetime=self.core.datetime, portfolio_value=self.core.portfolio_value, 
                            cash=self.core.cash, pnl=self.core.pnl, leverage=self.core.leverage, margin=self.core.margin)
        resp = Resp(body=body)
        return resp

    cdef object to_schema(self):
        cdef object experiment_id = uuid.UUID(bytes=self.core.experiment_id)

        return vtAccount(experiment_id=experiment_id, 
                         datetime=self.core.datetime, 
                         portfolio_value=self.core.portfolio_value, 
                         cash=self.core.cash,
                         pnl=self.core.pnl, 
                         leverage=self.core.leverage, 
                         margin=self.core.margin)

    def __reduce__(self):#  class / args
        return (Account, (self.core.experiment_id, 
                          self.core.datetime, 
                          self.core.portfolio_value, 
                          self.core.cash, 
                          self.core.pnl, 
                          self.core.leverage, 
                          self.coremargin))
    
    def __repr__(self):
        template = "Account(experiment_id={experiment_id} ," \
                   "datetime={datetime} ," \
                   "portfolio_value={portfolio_value} ," \
                   "cash={cash} ," \
                   "pnl={pnl} ," \
                   "leverage={leverage} ," \
                   "margin={margin})"
        return template.format(
            experiment_id=self.core.experiment_id,
            datetime=self.core.datetime,
            portfolio_value=self.core.portfolio_value,
            cash=self.core.cash,
            pnl=self.core.pnl,
            leverage=self.core.leverage,
            margin=self.core.margin,
        )

