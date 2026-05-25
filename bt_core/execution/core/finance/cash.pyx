# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import asyncio
import warnings
from bt_sdk.core.protocol import Event

from libc.stdint cimport int64_t

from bt_core.execution.core.finance.common cimport CashData
from bt_core.execution.gateway.interface import async_gt
from bt_core.execution.gateway.interface cimport AsyncGateway


cdef class AsyncCashManager:
    
    def __init__(self):
        self.acct = {}

    async def _start(self):
        cdef object row, body # resp
        cdef bytes experiment_id
        cdef list cash_data
        
        cash_data = await async_gt.get_account()
        for row in cash_data: # row
            body = row.body
            experiment_id = body.experiment_id

            self.acct[experiment_id] = Account(experiment_id=experiment_id,
                                                datetime=body.datetime,
                                                portfolio_value=body.portfolio_value,
                                                cash=body.cash,
                                                pnl=body.pnl,
                                                leverage=body.leverage,
                                                margin=body.margin)

    cdef Account get_account(self, bytes experiment_id):
        acct = self.acct.setdefault(experiment_id, Account(experiment_id=experiment_id))
        return acct

    cdef void set_cash(self, object event):  
        """set cash from start"""
        cdef CashData meta
        cdef Account acct 
        cdef bytes experiment_id = event.experiment_id
        cdef object body = event.body

        meta.cash = body.cash
        meta.session = body.session
        acct = self.get_account(experiment_id)
        acct.set_cash(meta)

    cdef void add_cash(self, bytes experiment_id, double cash):
        cdef Account acct

        acct = self.get_account(experiment_id)
        acct.add_cash(cash)

    cdef void update(self, bytes experiment_id, list trades, double pnl):
        """update account with position"""
        cdef Account acct

        acct = self.get_account(experiment_id)
        acct.update(trades, pnl)

    cdef void sync(self, bytes experiment_id, int64_t sync_tick, dict pobjs):
        """sync account on_dt_over"""
        cdef Account acct

        acct = self.get_account(experiment_id)
        acct.sync(sync_tick, pobjs)

    cdef remove_client(self, bytes experiment_id):
        self.acct.pop(experiment_id, None)
