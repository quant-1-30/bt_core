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

import io
import os
import collections
import datetime
import inspect
import numpy as np

from .dataseries import OHLCDateTime, TimeFrame
from .metabase import with_metaclass
from .resamplerfilter import Resampler 
from backtest.utils.dateintern import *


class MetaAbstractDataBase(OHLCDateTime.__class__):
    _indcol = dict()

    def __init__(cls, name, bases, dct):
        '''
        Class has already been created ... register subclasses
        '''
        # Initialize the class
        super(MetaAbstractDataBase, cls).__init__(name, bases, dct)

        if not cls.aliased and \
           name != 'DataBase' and not name.startswith('_'):
            cls._indcol[name] = cls
        
    def dopreinit(cls, _obj, *args, **kwargs):
        print("MetaAbstractDataBase dopreinit", kwargs)
        _obj, args, kwargs = \
            super(MetaAbstractDataBase, cls).dopreinit(_obj, *args, **kwargs)

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        print("MetaAbstractDataBase dopostinit", kwargs)
        _obj, args, kwargs = \
            super(MetaAbstractDataBase, cls).dopostinit(_obj, *args, **kwargs)

        # Either set by subclass or the parameter or use the dataname (ticker)
        _obj._name = _obj.p.dataname or cls.__class__.__name__

        _obj._compression = _obj.p.compression
        _obj._timeframe = _obj.p.timeframe

        if _obj.p.sessionstart is None:
            _obj.p.sessionstart = datetime.timedelta()

        if _obj.p.sessionend is None:
            # remove 9 to avoid precision rounding errors
            _obj.p.sessionend = datetime.timedelta()

        if not isinstance(_obj.p.fromdate, datetime.date):
            # push it to the end of the day, or else intraday
            # values before the end of the day would be gone
            _obj.p.fromdate = datetime.datetime.strptime(str(_obj.p.fromdate), "%Y%m%d")

        _obj.fromdate = _obj.p.fromdate + _obj.p.sessionstart

        if not isinstance(_obj.p.todate, datetime.date):
            # push it to the end of the day, or else intraday
            # values before the end of the day would be gone
            _obj.p.todate = datetime.datetime.strptime(str(_obj.p.todate), "%Y%m%d")

        _obj.todate = _obj.p.todate + _obj.p.sessionend

        _obj._barstack = collections.deque()  # for filter operations
        _obj._barstash = collections.deque()  # for filter operations

        _obj._filters = list()
        _obj._ffilters = list()
        for fp in _obj.p.filters:
            if inspect.isclass(fp):
                fp = fp(_obj)
                if hasattr(fp, 'last'):
                    _obj._ffilters.append((fp, [], {}))

            _obj._filters.append((fp, [], {}))
        
        return _obj, args, kwargs


class AbstractDataBase(with_metaclass(MetaAbstractDataBase, OHLCDateTime)):

    params = (
        ('dataname', ""),
        ('timeframe', TimeFrame.Minutes),
        ('compression', 1),
        ('filters', []),
        ('tz', 'Asia/Shanghai'),
        ('tzinput', None),
        ('sessionstart', datetime.timedelta(hours=9, minutes=30)),
        ('sessionend', datetime.timedelta(hours=15, minutes=0)),
        ('fromdate', None),
        ('todate', None),
        ("sid", []),
        ("benchmark", ''),
    )

    (CONNECTED, DISCONNECTED, CONNBROKEN, DELAYED,
     LIVE, NOTSUBSCRIBED, NOTSUPPORTED_TF, UNKNOWN) = range(8)

    _NOTIFNAMES = [
        'CONNECTED', 'DISCONNECTED', 'CONNBROKEN', 'DELAYED',
        'LIVE', 'NOTSUBSCRIBED', 'NOTSUPPORTED_TIMEFRAME', 'UNKNOWN']

    @classmethod
    def _getstatusname(cls, status):
        return cls._NOTIFNAMES[status]

    _clone = False

    # Set to non 0 if resampling/replaying
    resampling = 0
    # replaying = 0

    _started = False
    
    _tmoffset = datetime.timedelta()

    def _start(self, **kwargs):
        self.start()
        if not self._started:
            self._start_finish() # dynamic update and add attributes _tzinput, _tz, _calendar, _started

    def start(self):
        self._barstack = collections.deque()
        self._barstash = collections.deque()
        # self._laststatus = self.CONNECTED
    
    def _start_finish(self):
        self._tz = self._gettz()
        self.lines.datetime._settz(self._tz)

        self._tzinput = Localizer(self._gettzinput())
        self._started = True

    def updateminperiod(self, minperiod):
        self._minperiod = minperiod
        for line in self.lines:
            line.updateminperiod(minperiod)
            print("feed updateminperiod line ", line, line._minperiod)

    def _gettzinput(self):
        '''Can be overriden by classes to return a timezone for input'''
        return tzparse(self.p.tzinput)

    def _gettz(self):
        '''To be overriden by subclasses which may auto-calculate the
        timezone'''
        # tz = pytz.timezone(self.p.tz)
        # return Localizer(tz)
        return tzparse(self.p.tz)

    def date2num(self, dt):
        if self._tz is not None:
            return date2num(self._tz.localize(dt))
        return date2num(dt)

    def num2date(self, dt, tz=None):
        return num2date(dt, tz or self._tz) # default is Asia/Shanghai
    
    def _getnexteos(self): 
        '''Returns the next eos using a trading calendar if available'''
        if self._clone:
            return self.data._geteos()

        if not len(self):
            return datetime.datetime.min, 0.0

        dt = self.lines.datetime[0]
        dtime = num2date(dt)
        nexteos = dtime.replace(
            hour=self.p.sessionend.hour,
            minute=self.p.sessionend.minute,
            second=self.p.sessionend.second,
            microsecond=self.p.sessionend.microsecond
        )
        nextdteos = date2num(nexteos) # localize
        return nexteos, nextdteos
    
    def _dt_over(self, last=False): # to adapt A stock T + 1 policy
        dt = num2date(self.lines.datetime[0])
        pre_dt = num2date(self.lines.datetime[-1]) # nan to zero if nan
        if self._timeframe >= TimeFrame.Days or last:
            isover = True
        elif pre_dt:
            isover = (dt - pre_dt).days > 0
        else:
            isover = False

        return isover, (pre_dt, dt)
    
    def advance(self, size=1, datamaster=None):

        self.lines.advance(size)
        if datamaster is not None:
            if self.lines.datetime[0] > datamaster.lines.datetime[0]:
                self.lines.rewind()
    
    def next(self, datamaster=None):
        ret = self.load()
        if not ret:
            return ret
        
        if len(self) >= self.buflen(): # consume > buffer size
            self.apply_factor() 
        return True

    def _load(self):
        return False

    def load(self):
        while True:
            self.forward()

            if self._fromstack():  # bar is available
                return True

            if not self._fromstack(stash=True):
                _loadret = self._load()
                # print("load _loadret", _loadret)
                if not _loadret:  # no bar use force to make sure in exactbars
                    self.backwards()  # undo data pointer
                    return _loadret

            dt = self.lines.datetime[0]
            if self._tzinput:
                dtime = num2date(dt)  # get it in a naive datetime
                dtime = self._tzinput.localize(dtime)  # pytz compatible-ized
                self.lines.datetime[0] = dt = date2num(dtime) 

           # Pass through filters
            retff = False
            for ff, fargs, fkwargs in self._filters:
                if self._barstack: # previous filter may have put things onto the stack 
                    for i in range(len(self._barstack)):
                        self._fromstack(forward=True)
                        retff = ff(self, *fargs, **fkwargs) # check
                else:
                    retff = ff(self, *fargs, **fkwargs)

                if retff:  # bar removed from systemn
                    break  # out of the inner loop

            if retff:  # bar removed from system - loop to get new bar
                continue  # in the greater loop
            return True
    
    def _fromstack(self, forward=False, stash=False):
        '''Load a value from the stack onto the lines to form the new bar

        Returns True if values are present, False otherwise
        '''
        coll = self._barstack if not stash else self._barstash

        if coll:
            if forward:
                self.forward()
            for line, val in zip(self.itersize(), coll.popleft()):
                line[0] = val
            return True
        return False
    
    def _add2stack(self, bar, stash=False):
        '''Saves given bar (list of values) to the stack for later retrieval'''
        if not stash:
            self._barstack.append(bar)
        else:
            self._barstash.append(bar)

    def _save2stack(self, erase=False, force=False, stash=False):
        '''Saves current bar to the bar stack for later retrieval

        Parameter ``erase`` determines removal from the data stream
        '''
        bar = [line[0] for line in self.itersize()]
        if not stash:
            self._barstack.append(bar)
        else:
            self._barstash.append(bar)

        if erase:  # remove bar if requested
            self.backwards(force=force)

    def _updatebar(self, bar, forward=False, ago=0):
        '''Load a value from the stack onto the lines to form the new bar

        Returns True if values are present, False otherwise
        '''
        if forward:
            self.forward()

        for line, val in zip(self.itersize(), bar):
            line[0 + ago] = val

    def _last(self, datamaster=None):
        ret = 0
        for ff, fargs, fkwargs in self._ffilters:
            ret += ff.last(self, *fargs, **fkwargs)

        while self._fromstack(forward=True):
            # consume bar(s) produced by "last"s - adding room
            pass

        return bool(ret)
    
# --------------------------------------------------------------------- resample ---------------------------------------------------------------

    def resample(self, **kwargs):
        self.addfilter(Resampler, **kwargs)

    def addfilter(self, p, *args, **kwargs):
            if inspect.isclass(p):
                pobj = p(self, *args, **kwargs)
                self._filters.append((pobj, [], {}))

                if hasattr(pobj, 'last'):
                    self._ffilters.append((pobj, [], {}))
            else:
                self._filters.append((p, args, kwargs))

# --------------------------------------------------------------------- clone------------------------------------------------------------------------

    def clone(self, **kwargs):
        return DataClone(dataname=self, **kwargs)

    def copyas(self, _dataname, **kwargs):
        d = self.clone(**kwargs)
        d._dataname = _dataname
        d._name = _dataname
        return d
    
 # --------------------------------------------------------------------- adjust api -----------------------------------------------------------------   
    def calc_adjfactor(self, reqmeta):
        raise NotImplementedError()

    def apply_factor(self):
        """
            ohlc factors
        """
        if self.adj_factors:
            line_dt = [int(num2date(ts).strftime("%Y%m%d")) for ts in self.lines.datetime.array]

            # 预处理复权因子数据
            adj_dates = np.array(sorted(self.adj_factors.keys()))
            adj_factors = np.array([self.adj_factors[dt] for dt in adj_dates])

            indices = np.searchsorted(adj_dates, line_dt, side='right') - 1
            indices = np.clip(indices, 0, len(adj_dates) - 1)

            # 批量应用复权因子
            align_factors = adj_factors[indices]

            # datetime
            adj_lines = {name: getattr(self, name) for name in ["open", "high", "close", "low"]}
        
            for line in adj_lines.values():
                line.apply_factor(align_factors) 

    def notify_data(self):
        for line in self.itersize():
            line.notify_data()

    def plot(self, linealias):
        pass

    def plotrange(self, linealias, start, end):
        pass
    
    def stop(self):
        pass


class DataBase(AbstractDataBase):
    pass


class MetaCSVDataBase(DataBase.__class__):
    def dopostinit(cls, _obj, *args, **kwargs):
        # Before going to the base class to make sure it overrides the default
        if not _obj.p.name and not _obj._name:
            _obj._name, _ = os.path.splitext(os.path.basename(_obj.p.dataname))

        _obj, args, kwargs = \
            super(MetaCSVDataBase, cls).dopostinit(_obj, *args, **kwargs)

        return _obj, args, kwargs


class CSVDataBase(with_metaclass(MetaCSVDataBase, DataBase)):
    '''
    Base class for classes implementing CSV DataFeeds

    The class takes care of opening the file, reading the lines and
    tokenizing them.

    Subclasses do only need to override:

      - _loadline(tokens)

    The return value of ``_loadline`` (True/False) will be the return value
    of ``_load`` which has been overriden by this base class
    '''

    f = None
    params = (('headers', True), ('separator', ','),)

    def start(self):
        super(CSVDataBase, self).start()

        if self.f is None:
            if hasattr(self.p.dataname, 'readline'):
                self.f = self.p.dataname
            else:
                # Let an exception propagate to let the caller know
                self.f = io.open(self.p.dataname, 'r')

        if self.p.headers:
            self.f.readline()  # skip the headers

        self.separator = self.p.separator

    def stop(self):
        super(CSVDataBase, self).stop()
        if self.f is not None:
            self.f.close()
            self.f = None

    def preload(self):
        while self.load():
            pass

        self._last()
        self.home()

        # preloaded - no need to keep the object around - breaks multip in 3.x
        self.f.close()
        self.f = None

    def _load(self):
        if self.f is None:
            return False

        # Let an exception propagate to let the caller know
        line = self.f.readline()

        if not line:
            return False

        line = line.rstrip('\n')
        linetokens = line.split(self.separator)
        return self._loadline(linetokens)

    def _getnextline(self):
        if self.f is None:
            return None

        # Let an exception propagate to let the caller know
        line = self.f.readline()

        if not line:
            return None

        line = line.rstrip('\n')
        linetokens = line.split(self.separator)
        return linetokens


class DataClone(AbstractDataBase):
    _clone = True

    def __init__(self):
        self.data = self.p.dataname
        self._dataname = self.data._dataname

        # Copy date/session parameters
        self.p.sessionstart = self.data.p.sessionstart
        self.p.sessionend = self.data.p.sessionend

        self.p.timeframe = self.data.p.timeframe
        self.p.compression = self.data.p.compression

    def _start(self):
        # redefine to copy data bits from guest data
        self.start()

        # Copy tz infos
        self._tz = self.data._tz
        self.lines.datetime._settz(self._tz)

        self._calendar = self.data._calendar

        # input has already been converted by guest data
        self._tzinput = None  # no need to further converr

        # FIXME: if removed from guest, remove here too
        self.sessionstart = self.data.sessionstart
        self.sessionend = self.data.sessionend

    def start(self):
        super(DataClone, self).start()
        self._dlen = 0
        self._preloading = False

    def preload(self):
        self._preloading = True
        super(DataClone, self).preload()
        self.data.home()  # preloading data was pushed forward
        self._preloading = False

    def _load(self):
        # assumption: the data is in the system
        # simply copy the lines
        if self._preloading:
            # data is preloaded, we are preloading too, can move
            # forward until have full bar or data source is exhausted
            self.data.advance()
            if len(self.data) > self.data.buflen():
                return False

            for line, dline in zip(self.lines, self.data.lines):
                line[0] = dline[0]

            return True

        # Not preloading
        if not (len(self.data) > self._dlen):
            # Data not beyond last seen bar
            return False

        self._dlen += 1

        for line, dline in zip(self.lines, self.data.lines):
            line[0] = dline[0]

        return True

    def advance(self, size=1, datamaster=None):
        self._dlen += size
        super(DataClone, self).advance(size, datamaster)
