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
from backtest.restricted import MetaRestricted

__all__ = ['DD']


class DD(MetaRestricted):
    """
        DrawDown Restricted 
    """
    params = (
      ("thres", 30.0),
    )

    def is_restricted(self, strat):
      dd = strat.stats.getbyname("drawdown") # lowercase
      _ratio = dd.lines.drawdown[0] 
      is_r = True if _ratio >= self.p.thres else False
      return is_r
