# /usr/bin/env python3
# -*- coding: utf-8 -*-

import itertools
import collections
from .metabase import ItemCollection
from utils.wrapper import singleton


@singleton
class NotifyCenter:

    def __init__(self):
        self.analyzers = ItemCollection()
        self._slave_analyzers = list()
        self._alnames = collections.defaultdict(itertools.count)
        self.stats = self.observers = ItemCollection()

    def _start(self):
        """
            alanyzers and obs
        """
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._start()

        for obs in self.observers:
            obs._start()

    def notify_order(self, order):
        for observer in self.observers:
            if hasattr(observer, 'notify_order'):
                observer.notify_order(order)
                
        for analyzer in self.analyzers:
            if hasattr(analyzer, 'notify_order'):
                analyzer.notify_order(order)
                
    def notify_trade(self, trade):
        for observer in self.observers:
            if hasattr(observer, 'notify_trade'):
                observer.notify_trade(trade)
                
        for analyzer in self.analyzers:
            if hasattr(analyzer, 'notify_trade'):
                analyzer.notify_trade(trade)

    def notify_account(self, acct):
        for observer in self.observers:
            if hasattr(observer, 'notify_account'):
                observer.notify_trade(acct)
                
        for analyzer in self.analyzers.values():
            if hasattr(analyzer, 'notify_account'):
                analyzer.notify_trade(acct)
                
    def notify_data(self, data, status, *args, **kwargs):
        # stats for feeds
        for observer in self.observers:
            if hasattr(observer, 'notify_data'):
                observer.notify_data(data, status, *args, **kwargs)
                
    # def notify_store(self, msg, *args, **kwargs):
    #     for observer in self.observers:
    #         if hasattr(observer, 'notify_store'):
    #             observer.notify_store(msg, *args, **kwargs)

    def notify_timer(self, msg, *args, **kwargs):
        '''Receives a timer notification where ``timer`` is the timer which was
        returned by ``add_timer``, and ``when`` is the calling time. ``args``
        and ``kwargs`` are any additional arguments passed to ``add_timer``

        The actual ``when`` time can be later, but the system may have not be
        able to call the timer before. This value is the timer value and no the
        system time.
        '''
        for observer in self.observers:
            if hasattr(observer, 'notify_timer'):
                observer.notify_store(msg, *args, **kwargs)
    
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

    def _addobserver(self, multi, obscls, datas, *obsargs, **obskwargs):
        obsname = obskwargs.pop('obsname', '')
        if not obsname:
            obsname = obscls.__name__.lower()

        if not multi:
            newargs = list(itertools.chain(datas, obsargs))
            # automatically observer to _ltype
            obs = obscls(*newargs, **obskwargs)
            # self.stats.append(obs, obsname)
            return

        setattr(self.stats, obsname, list())
        l = getattr(self.stats, obsname)

        for data in datas:
            obs = obscls(data, *obsargs, **obskwargs)
            l.append(obs)

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

    # def register_plugin(self):
    #     """
    #         stmp / sms / webrtc / ws / 
    #     """

    def stop(self):
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._stop()

    