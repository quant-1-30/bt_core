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

__all__ = ['Fixed', 'Pyramid']


class Fixed(Sizer):
    '''This is the default sizer used by ``backtrader`` if no other sizer is
    set

    It will simply return a size of ``1`` for each operation
    '''
    params = (
      ("perc", (90, 100)),
    )
    
    def _getsizing(self, datas, isbuy):
        if isbuy:
          return self.p.perc[0]
        return self.p.perc[1]


class Pyramid(Sizer):
    """
      Pyramid holding policy
    """
    params = (
      ("perc", (90, 100),)
    )   # reserve a fraction of cash
    
    def __init__(self):
        self.pyramid = {0: 0.4, 1: 0.4, 2: 0.2}
        self.step = 0

    def _getsizing(self, datas, isbuy):
        if isbuy:
            self.restore()
            return self.pyramid[self.step]
        return 100

    def restore(self, reset=False):
        if reset:
            self.step = 0
            return
        step = self.step + 1
        self.step = step % len(self.pyramid) 
