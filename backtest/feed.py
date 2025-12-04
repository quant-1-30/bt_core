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
        _obj._name = _obj.plotinfo.plotname or _obj.__class__.__name__
        _obj.extra_info = ""

        _obj._compression = _obj.p.compression
        _obj._timeframe = _obj.p.timeframe
        _obj._calendar = _obj.p.calendar

        if _obj.p.sessionstart is None:
            _obj.p.sessionstart = datetime.timedelta()

        if _obj.p.sessionend is None:
            # remove 9 to avoid precision rounding errors
            _obj.p.sessionend = datetime.timedelta()

        _obj._barstack = collections.deque()  # for filter operations
        _obj._barstash = collections.deque()  # for filter operations
        _obj._filters = list()
 
        return _obj, args, kwargs


class AbstractDataBase(with_metaclass(MetaAbstractDataBase, OHLCDateTime)):

    params = (
        ('dataname', ""),
        ('timeframe', TimeFrame.Minutes),
        ('compression', 1),
        ('tz', 'Asia/Shanghai'),
        ('tzinput', None),
        ('sessionstart', datetime.timedelta(hours=9, minutes=30)),
        ('sessionend', datetime.timedelta(hours=15, minutes=0)),
        ('calendar', None),
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

    def updateminperiod(self, minperiod):
        self._minperiod = minperiod

        for dline in self.lines:
            dline.updateminperiod(minperiod)
            print("feed updateminperiod line ", dline, dline._minperiod)

    def _start(self, *args, **kwargs):
        self.start(*args, **kwargs)
        if not self._started:
            self._start_finish() # dynamic update and add attributes _tzinput, _tz, _calendar, _started

    def start(self, *args, **kwargs):
        self._barstack = collections.deque()
        self._barstash = collections.deque()
        # self._laststatus = self.CONNECTED
        
        fromdate = datetime.datetime.strptime(str(kwargs["fromdate"]), "%Y%m%d") 
        self.fromdate = fromdate + self.p.sessionstart
        todate = datetime.datetime.strptime(str(kwargs["todate"]), "%Y%m%d")
        self.todate = todate + self.p.sessionend
        self.sid = kwargs["sid"]
    
    def _start_finish(self):
        self._tz = self._gettz()
        self.lines.datetime._settz(self._tz)
        self._tzinput = Localizer(self._gettzinput())
        self._started = True
        self._calendar = cal = self.p.calendar

        self.extra_info = f"FeedInfo: {self.fromdate}:{self.todate}@{','.join(self.sid)}" # any extra info to relate with feed

    def _gettzinput(self):
        '''Can be overriden by classes to return a timezone for input'''
        return tzparse(self.p.tzinput)

    def _gettz(self):
        '''To be overriden by subclasses which may auto-calculate the
        timezone'''
        # tz = pytz.timezone(self.p.tz)
        # return Localizer(tz)
        return tzparse(self.p.tz)

    def _dt_over(self, last=False): # to adapt A stock T + 1 policy
        dt = num2date(self.lines.datetime[0])
        pre_dt = num2date(self.lines.datetime[-1]) # nan to zero if nan

        if self._timeframe >= TimeFrame.Days or last:
            isover = True
        else:
            isover = (dt - pre_dt).days > 0 if isinstance(pre_dt, datetime.datetime) else False

        return isover, (pre_dt, dt)

    def date2num(self, dt):
        if self._tz is not None:
            return date2num(self._tz.localize(dt))
        return date2num(dt)

    def num2date(self, dt, tz=None):
        return num2date(dt, tz or self._tz) # default is Asia/Shanghai
    
    def _getnexteos(self): 
        '''Returns the next eos using a trading calendar if available'''
        if self._clone:
            return self.data._getnexteos()

        if not len(self):
            return datetime.datetime.min, 0.0

        dt = self.lines.datetime[0]
        dtime = num2date(dt)
        
        total_seconds = int(self.p.sessionend.total_seconds())
        nexteos = dtime.replace(
            hour= total_seconds // 3600,
            minute=(total_seconds % 3600) // 60,
            second=total_seconds % 60
        )
        nextdteos = date2num(nexteos) # localize
        return nexteos, nextdteos 

    def _load(self):
        return False

    def load(self):
        while True:
            self.forward()

            if self._fromstack():  # resample bar is available
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
            # import pdb; pdb.set_trace()
            for ff, fargs, fkwargs in self._filters:
                if self._barstack: # previous filter may have put things onto the stack 
                    for i in range(len(self._barstack)):
                        self._fromstack(forward=True)
                        retff = ff(self, *fargs, **fkwargs) # check
                else:
                    retff = ff(self, *fargs, **fkwargs)

            #     if retff:  # bar removed from systemn
            #         break  # out of the inner loop

            # if retff:  # bar removed from system - loop to get new bar
            #     continue  # in the greater loop

            return True

    def _tick_nullify(self):
        # These are the updating prices in case the new bar is "updated"
        # and the length doesn't change like if a replay is happening or
        # a real-time data feed is in use and 1 minutes bars are being
        # constructed with 5 seconds updates
        for lalias in self.getlinealiases():
            if lalias != 'datetime':
                setattr(self, 'tick_' + lalias, None)

        self.tick_last = None

    def _tick_fill(self, force=False):
        # If nothing filled the tick_xxx attributes, the bar is the tick
        alias0 = self._getlinealias(0)
        if force or getattr(self, 'tick_' + alias0, None) is None:
            for lalias in self.getlinealiases():
                if lalias != 'datetime':
                    setattr(self, 'tick_' + lalias,
                            getattr(self.lines, lalias)[0])

            self.tick_last = getattr(self.lines, alias0)[0]

    # def next(self, datamaster=None, ticks=True):

    #     if len(self) >= self.buflen():
    #         if ticks:
    #             self._tick_nullify()

    #         # not preloaded - request next bar
    #         ret = self.load()
    #         if not ret:
    #             # if load cannot produce bars - forward the result
    #             return ret

    #         if datamaster is None:
    #             # bar is there and no master ... return load's result
    #             if ticks:
    #                 self._tick_fill()
    #             return ret
    #     else:
    #         self.advance(ticks=ticks)

    #     # a bar is "loaded" or was preloaded - index has been moved to it
    #     if datamaster is not None:
    #         # there is a time reference to check against
    #         if self.lines.datetime[0] > datamaster.lines.datetime[0]:
    #             # can't deliver new bar, too early, go back
    #             self.rewind()
    #             return False
    #         else:
    #             if ticks:
    #                 self._tick_fill()

    #     else:
    #         if ticks:
    #             self._tick_fill()

    #     # tell the world there is a bar (either the new or the previous
    #     return True

    def next(self, datamaster=None):

        ret = self.load()
        if not ret:
            return ret
 
        # if len(self) >= self.buflen(): # consume > buffer size
        #     self.apply_factor()

        return True
    
    def advance(self, size=1, datamaster=None):

        self.lines.advance(size)
        if datamaster is not None:
            if self.lines.datetime[0] > datamaster.lines.datetime[0]:
                self.lines.rewind()

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
        # import pdb; pdb.set_trace()
        print("_add2stack ", self, bar)
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

# --------------------------------------------------------------------- resample ---------------------------------------------------------------

    def resample(self, **kwargs):
        self.addfilter(Resampler, **kwargs)
        self.resampling = 1

    def addfilter(self, p, *args, **kwargs):
        if inspect.isclass(p):
            pobj = p(self, *args, **kwargs)
            self.extra_info += f"  ResampleInfo: {str(pobj.p)}"
            self._filters.append((pobj, [], {}))
        else:
            raise TypeError(f'{p} is not class')

    def _last(self, datamaster=None):
        ret = 0
        for ff, fargs, fkwargs in self._filters:
            if hasattr(ff, 'last'):
                ret += ff.last(self, *fargs, **fkwargs) # _add2stack

        while self._fromstack(forward=True):
            # consume bar(s) produced by "last"s - adding room
            pass

        return bool(ret)

# --------------------------------------------------------------------- clone------------------------------------------------------------------------

    def clone(self, **kwargs):
        return DataClone(dataname=self, **kwargs)

    def copyas(self, _dataname, **kwargs):
        d = self.clone(**kwargs)
        # d._dataname = _dataname
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
            # print("apply_factor ", self, self.lines.datetime.array)
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

    # def preload(self):
    #     while self.load():
    #         pass

    #     self._last()
    #     self.home()

    #     # preloaded - no need to keep the object around - breaks multip in 3.x
    #     self.f.close()
    #     self.f = None

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
        # self._dataname = self.data._dataname

        # Copy date/session parameters
        self.p.sessionstart = self.data.p.sessionstart
        self.p.sessionend = self.data.p.sessionend

        self.p.timeframe = self.data.p.timeframe
        self.p.compression = self.data.p.compression
    

    def _start(self, *args, **kwargs):
        # redefine to copy data bits from guest data
        self.start(*args, **kwargs)

        # Copy tz infos
        self._tz = self.data._tz
        self.lines.datetime._settz(self._tz)

        # self._calendar = self.data._calendar

        # input has already been converted by guest data
        self._tzinput = self.data._tzinput  # no need to further converr

        self.adj_factors = self.data.adj_factors
        
        self._name = "DataClone"

    def start(self, *args, **kwargs):
        super(DataClone, self).start(*args, **kwargs)
        # self._dlen = 0

    def _load(self):
        # assumption: the data is in the system
        # simply copy the lines
        for line, dline in zip(self.lines, self.data.lines.itersize()):
            line[0] = dline[0]
        return True

    # def advance(self, size=1, datamaster=None):
    #     self._dlen += size
    #     super(DataClone, self).advance(size, datamaster)
