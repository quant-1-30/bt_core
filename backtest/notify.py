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

        _obj._data_notification = collections.deque()
        _obj._indicator_notification = collections.deque()
        _obj._observer_notification = collections.defaultdict() 
        _obj._timer_notification = collections.defaultdict() 

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
    
    def _start(self):
        """ """

    def notify_data(self, data):
        '''Notify daily data delivered'''

    def notify_indicator(self, inds):
        '''Notify indicator updated'''

    def notify_observer(self, obs):
        '''Notify observer --- order / trade / account '''

    def notify_timer(self, msg):
        '''Receives a timer notification where ``timer`` is the timer which was
        returned by ``add_timer``, and ``when`` is the calling time. 

        The actual ``when`` time can be later, but the system may have not be
        able to call the timer before. This value is the timer value and no the
        system time.
        '''

    def stop(self):
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._stop()
            '''Notify analyzer data updated'''
            self._analyer_notify[analyzer] = analyzer.get_analysis()

    # def put_notification(self, msg):
    #     self.notifs.append(msg)

    # def get_notification(self):
    #     return self._notifs.pop()
    # 
     