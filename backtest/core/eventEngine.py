# !/usr/bin/env python3
# -*- coding: utf-8 -*-
from threading import Thread
from queue import Queue
from collections import defaultdict


class EventEngine(object):
    """
        定义策略引擎将不同的算法按照顺序放到一个队列里面依次进行执行，算法对应事件，可以注册、剔除事件
    """
    def __init__(self):

        self._queue = Queue()
        self._thread = Thread(target=self._run)
        # 以计时模块为例，换成其他的需求添加都队列里面
        self._timer = Thread(target=self._run_timer)
        self._handlers = defaultdict(list)
        self._general = []

    def _run(self):
        while self._active:
            try:
                algo = self._queue.get(block=True, timeout=1)
                self._process(algo)
            except Empty:
                pass

    def _process(self, algo):
        if algo._type in self._handlers:
            [handler(algo) for handler in self._handlers[algo._type]]

        if self._general:
            [handler(algo) for handler in self._general]

    def _run_timer(self):

        while self._active:
            # sleep(self._interval)
            event = Event('timer')
            self.put(event)

    def start(self):

        self._active = True
        self._thread.start()
        self._timer.start()

    def stop(self):
        self._active = False
        self._timer.join()
        self._thread.join()

    def put(self, event):
        self._queue.put(event)


class Dispatcher(object):
    def __init__(self):
        self.__subjects = []
        self.__stop = False
        self.__startEvent = observer.Event()
        self.__idleEvent = observer.Event()
        self.__currDateTime = None

    # Returns the current event datetime. It may be None for events from realtime subjects.
    def getCurrentDateTime(self):
        return self.__currDateTime

    def getStartEvent(self):
        return self.__startEvent

    def getIdleEvent(self):
        return self.__idleEvent

    def stop(self):
        self.__stop = True

    def getSubjects(self):
        return self.__subjects

    def addSubject(self, subject):
        # Skip the subject if it was already added.
        if subject in self.__subjects:
            return

        # If the subject has no specific dispatch priority put it right at the end.
        if subject.getDispatchPriority() is dispatchprio.LAST:
            self.__subjects.append(subject)
        else:
            # Find the position according to the subject's priority.
            pos = 0
            for s in self.__subjects:
                if s.getDispatchPriority() is dispatchprio.LAST or subject.getDispatchPriority() < s.getDispatchPriority():
                    break
                pos += 1
            self.__subjects.insert(pos, subject)

        subject.onDispatcherRegistered(self)

    # Return True if events were dispatched.
    def __dispatchSubject(self, subject, currEventDateTime):
        ret = False
        # Dispatch if the datetime is currEventDateTime of if its a realtime subject.
        if not subject.eof() and subject.peekDateTime() in (None, currEventDateTime):
            ret = subject.dispatch() is True
        return ret

    # Returns a tuple with booleans
    # 1: True if all subjects hit eof
    # 2: True if at least one subject dispatched events.
    def __dispatch(self):
        smallestDateTime = None
        eof = True
        eventsDispatched = False

        # Scan for the lowest datetime.
        for subject in self.__subjects:
            if not subject.eof():
                eof = False
                smallestDateTime = util.safe_min(smallestDateTime, subject.peekDateTime())

        # Dispatch realtime subjects and those subjects with the lowest datetime.
        if not eof:
            self.__currDateTime = smallestDateTime

            for subject in self.__subjects:
                if self.__dispatchSubject(subject, smallestDateTime):
                    eventsDispatched = True
        return eof, eventsDispatched

    def run(self):
        try:
            for subject in self.__subjects:
                subject.start()

            self.__startEvent.emit()

            while not self.__stop:
                eof, eventsDispatched = self.__dispatch()
                if eof:
                    self.__stop = True
                elif not eventsDispatched:
                    self.__idleEvent.emit()
        finally:
            # There are no more events.
            self.__currDateTime = None

            for subject in self.__subjects:
                subject.stop()
            for subject in self.__subjects:
                subject.join()
