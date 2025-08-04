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
from backtest.sizer import Sizer

__all__ = ['FixedSize']


class FixedSize(Sizer):
    '''
    This sizer simply returns a fixed size for any operation.
    Size can be controlled by number of tranches that a system
    wishes to use to scale into trades by specifying the ``tranches``
    parameter.
    '''
    params = (('reserve', 0.1),)

    def _call_sizing(self, strat_metrics):
        sizer = (1 - self.p.reserve) / len(strat_metrics)
        return {strat: sizer for strat in strat_metrics}
    
    def _put_sizing(self, strat_metrics):
        return {strat: -1  for strat in strat_metrics}


SizerFix = FixedSize


class NoSizer(Sizer):

    def _getsizing(self, meta, sids, isbuy):
        return {}