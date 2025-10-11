# /usr/bin/env python3
# -*- coding: utf-8 -*-

import itertools
import collections

import backtest as bt
from .metabase import findowner, ItemCollection, with_metaclass
from .lineiterator import NotifyBase

__all__ = ['Notify']


class MetaNotify(NotifyBase.__class__):

    def donew(cls, *args, **kwargs):
        # # Hack to support original method name for notify_order
        # if 'notify' in dct:
        #     # rename 'notify' to 'notify_order'
        #     dct['notify_order'] = dct.pop('notify')
        # if 'notify_operation' in dct:
        #     # rename 'notify' to 'notify_order'
        #     dct['notify_trade'] = dct.pop('notify_operation')
        _obj, args, kwargs = super(MetaNotify, cls).donew(*args, **kwargs)
        _obj.store = store = findowner(_obj, bt.stores)
        _obj.datas = store.datas
        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs)

        _obj.analyzers = ItemCollection()
        _obj._slave_analyzers = list()
        _obj._alnames = collections.defaultdict(itertools.count)
        _obj.stats = _obj.observers = ItemCollection()
        # self._notifs = collections.deque()
        return _obj, args, kwargs


class Notify(with_metaclass(MetaNotify, NotifyBase)):

    # keep the latest delivered data date in the ldine
    """
      - ``stdstats`` (default: ``True``)

        If True default Observers will be added: Broker (Cash and Value),
        Trades and BuySell
    """
    params = (
        ('stdstats', True),  # add standard observers if True
    )
    
    def _addanalyzer_slave(self, ancls, *anargs, **ankwargs):
        '''Like _addanalyzer but meant for observers (or other entities) which
        rely on the output of an analyzer for the data. These analyzers have
        not been added by the user and are kept separate from the main
        analyzers

        Returns the created analyzer
        '''
        analyzer = ancls(*anargs, **ankwargs)
        self._slave_analyzers.append(analyzer)
        return analyzer

    def _addanalyzer(self, ancls, *anargs, **ankwargs):
        anname = ankwargs.pop('_name', '') or ancls.__name__.lower()
        nsuffix = next(self._alnames[anname])
        anname += str(nsuffix or '')  # 0 (first instance) gets no suffix
        analyzer = ancls(*anargs, **ankwargs)
        self.analyzers.append(analyzer, anname)

    def _addobserver(self, multi, obscls, *obsargs, **obskwargs):
        obsname = obskwargs.pop('obsname', '')
        if not obsname:
            obsname = obscls.__name__.lower()

        if not multi:
            newargs = list(itertools.chain(self.datas, obsargs))
            obs = obscls(*newargs, **obskwargs)
            self.stats.append(obs, obsname)
            return

        setattr(self.stats, obsname, list())
        l = getattr(self.stats, obsname)

        for data in self.datas:
            obs = obscls(data, *obsargs, **obskwargs)
            l.append(obs)            

    def _start(self):
        """
            alanyzers and obs
        """
        # if self.p.stdstats:
        #     self.quicknotify._addobserver(False, observers.Broker)
            
        #     self.quicknotify._addobserver(True, observers.BuySell,
        #                         barplot=True)

        #     self.quicknotify._addobserver(False, observers.DrawDown)
        
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._start()

        for obs in self.observers:
            obs._start()

    def _next(self, minperstatus):
        self._next_observers(minperstatus)
        self._next_analyzers(minperstatus)

    def _next_observers(self, minperstatus):
        for observer in self.observers:
            for analyzer in observer._analyzers:
                if minperstatus < 0:
                    analyzer._next()
                elif minperstatus == 0:
                    analyzer._nextstart()  # only called for the 1st value
                else:
                    analyzer._prenext()
            observer._next()

    def _next_analyzers(self, minperstatus):
        for analyzer in self.analyzers:
            if minperstatus < 0:
                analyzer._next()
            elif minperstatus == 0:
                analyzer._nextstart()  # only called for the 1st value
            else:
                analyzer._prenext()

    def notify_data(self, data):
        '''Notify daily data delivered'''
        # for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        #     if hasattr(analyzer, 'notify_data'):
        #         analyzer.notify_data(data)

    def notify_order(self, order):
        '''Notify order status changed'''
        # for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        #     if hasattr(analyzer, 'notify_order'):
        #         analyzer.notify_order(order)

    def notify_account(self, data):
        '''Notify account and position updated'''
        # for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        #     if hasattr(analyzer, 'notify_account'):
        #         analyzer.notify_account(data)

    # def notify_timer(self, msg):
    #     '''Receives a timer notification where ``timer`` is the timer which was
    #     returned by ``add_timer``, and ``when`` is the calling time. 

    #     The actual ``when`` time can be later, but the system may have not be
    #     able to call the timer before. This value is the timer value and no the
    #     system time.
    #     '''
    #     for observer in self.observers:
    #         if hasattr(observer, 'notify_timer'):
    #             observer.notify_timer(msg)

    def stop(self):
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._stop()

    # def put_notification(self, msg):
    #     self.notifs.append(msg)

    # def get_notification(self):
    #     return self._notifs.pop()
    # 
     