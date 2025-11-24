#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import numpy as np
from backtest.risk import Risk

__all__ = ['Fixed', 'Pyramid']


class CashRisk(Risk):
    '''This is the default Risk used by ``backtrader`` if no other risk is
    set
    '''
    params = (
      ("safety", 0.1),
    )

    def is_restricted(self, strat):
      acct, _ = strat.getval()
      ratio = acct.cash / (acct.portfolio_value + acct.cash)
      is_r = False if ratio >= self.p.safety else True
      return is_r


class LossRisk(Risk):
    """
        DrawDown exceed threshold 
    """
    params = (
      ("ratio", 30.0),
    )

    def is_restricted(self, strat):
      dd = strat.stats.getattr("DrawDown")
      loss_ratio = dd.lines.drawdown[0] 
      is_r = True if loss_ratio >= self.p.ratio else False
      return is_r
