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
from backtest.risk import RiskBase

__all__ = ['PortfolioRisk']


class PortfolioRisk(RiskBase):
    """
      Portfolio Risk Management 
    """
    params = (
      ("thres", 0.7),
    )

    def _check_risk(self, strat):
        initial_cash = self._owner.cash
        acct = [strat.getvalue()[0] for strat in self._owner.runningstrats] 
        v = np.sum([a.portfolio_value + a.cash for a in acct])
        
        signal = v / initial_cash < self.p.thres
        return signal
