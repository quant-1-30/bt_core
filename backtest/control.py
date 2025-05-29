# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""

import warnings
import logging
import operator
from functools import reduce


class TradingControlViolation(Exception):
    """
    Raised if an order would violate a constraint set by a TradingControl.
    """
    msg = """
            {asset} at {datetime} violates trading constraint
            {constraint}.
        """.strip()


class TradingControl(object):
    """
    Abstract base class representing a fail-safe control on the behavior of any
    algorithm.
    """
    def __init__(self,
                 on_error='log',
                 _fail_args='violate_trading_controls'):
        self.on_error = on_error
        self._fail_args = _fail_args

    def validate(self,
                 asset,
                 algo_datetime):
        """
        Before any order is executed by TradingAlgorithm, this method should be
        called *exactly once* on each registered TradingControl object.

        If the specified asset and amount do not violate this TradingControl's
        restraint given the information in `portfolio`, this method should
        return None and have no externally-visible side-effects.

        If the desired order violates this TradingControl's contraint, this
        method should call self.fail(asset, amount).
        """
        raise NotImplementedError("")

    def handle_violation(self,
                         asset,
                         date_time):
        """
        Handle a TradingControlViolation, either by raising or logging and
        error with information about the failure.

        If dynamic information should be displayed as well, pass it in via
        `metadata`.
        """
        constraint = repr(self)

        if self.on_error == 'fail':
            raise TradingControlViolation(
                asset=asset,
                datetime=date_time,
                constraint=constraint)
        elif self.on_error == 'log':
            logging.info("{asset} at {dt} "
                         "violates trading constraint {constraint}",
                         asset=asset, dt=date_time,
                         constraint=constraint)
        elif self.on_error == 'warn':
            warnings.warn("{asset} at {dt} violates trading constraint {constraint}",
                          asset=asset, dt=date_time,
                          constraint=constraint)
        else:
            raise TradingControlViolation(
                asset=asset,
                datetime=date_time,
                constraint=constraint)

    def __repr__(self):
        return "{name}({attrs})".format(name=self.__class__.__name__,
                                        attrs=self._fail_args)

    def __or__(self, asset, algo_datetime):
        """
            Base implementation for combining two restrictions.
        """
        return reduce(
            operator.and_,
            (r.validate(asset, algo_datetime) for r in self.controls)
        )
