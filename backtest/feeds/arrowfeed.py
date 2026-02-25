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
import datetime
from backtest.utils.dateintern import date2num
from backtest.feed import DataBase


class ArrowData(DataBase):
    '''
    Uses a Pyarrow Table as the feed source, iterating directly over the
    tuples returned by "itertuples".

    This means that all parameters related to lines must have numeric
    values as indices into the tuples

    Note:

      - The ``dataname`` parameter is a Pyarrow Table

      - A negative value in any of the parameters for the Data lines
        indicates it's not present in the DataFrame
        it is
    '''

    params = (
        ('datetime', 0),
        ('sid', 1),
        ('open', 2),
        ('high', 3),
        ('low', 4),
        ('close', 5),
        ('volume', 6),
        ('amount', 7),
    )

    datafields = [
        'datetime', 'sid', 'open', 'high', 'low', 'close', 'volume', 'amount'
    ]

    def start(self):
        super(ArrowData, self).start()

        # reset the iterator on each start
        self._rows = self.p.dataname.itertuples()

    def _load(self):
        try:
            row = next(self._rows)
        except StopIteration:
            return False

        # Set the standard datafields - except for datetime
        for datafield in self.getlinealiases():
            if datafield == 'datetime':
                continue

            # get the column index
            colidx = getattr(self.params, datafield)

            if colidx < 0:
                # column not present -- skip
                continue

            # get the line to be set
            line = getattr(self.lines, datafield)

            # indexing for pandas: 1st is colum, then row
            line[0] = row[colidx]

        # datetime
        colidx = getattr(self.params, 'datetime')
        tstamp = row[colidx]

        # convert to float via datetime and store it
        dt = tstamp.to_pydatetime()
        dtnum = date2num(dt)

        # get the line to be set
        line = getattr(self.lines, 'datetime')
        line[0] = dtnum

        # Done ... return
        return True

    def _load(self):
        while True:
            if self._row_iter is not None:
                try:
                    row = next(self._row_iter)
                    # print("_load row ", row)
                    if self.p.rtbar:
                        self._load_rtbar(row)
                    else:
                        self._load_bar(row)
                    return True
                except StopIteration:
                    self._row_iter = None

            msg = self.chan.get() # next pa.Table
            if msg is StopIteration:
                return False
            if isinstance(msg, Exception):
                raise msg

            self._row_iter = self._make_iter(msg)

    def _make_iter(self, table):
        cols = [table[name].to_numpy() for name in ['tick', 'open', 'high', 'low', 'close', 'volume', 'amount']] # iter(msg.to_pylist()) 
        return zip(*cols)

    def _load_bar(self, row):
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= row[0]:
            return False 
        
        self.lines.datetime[0] = row[0]
        self.lines.open[0] = row[1]
        self.lines.high[0] = row[2]
        self.lines.low[0] = row[3]
        self.lines.close[0] = row[4]
        self.lines.volume[0] = row[5]
        self.lines.amount[0] = row[6]
        return True

    def _load_rtbar(self, row): # tick 3s
        dt = self.lines.datetime[0]
        if not np.isnan(dt) and dt >= row[0]:
            return False  
        
        self.lines.datetime[0] = row[0]
        self.lines.open[0] = row[1]
        self.lines.high[0] = row[1]
        self.lines.low[0] = row[1]
        self.lines.close[0] = row[1]
        self.lines.volume[0] = row[2]
        self.lines.amount[0] = row[3]
        return True

    def calc_adjfactor(self, body: QueryBody):
        adj = self.mdapi.get_factor(body)
        factors = adj.raw_factors if adj else {} # adj_factors
        if factors:
            factors = dict(sorted(factors.items())) # sort by key
            self.adj_factors = factors

    def calc_benchmark(self, body: QueryBody):
        self.bench = self.mdapi.get_benchmark(body)


