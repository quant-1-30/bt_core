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
import asyncio
from collections import deque


cdef class AsyncSemaphoreWrapper:

    def __init__(self, semaphore):
        self._sem = semaphore

    async def __aenter__(self):
        await self._sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._sem.release()


cdef class Distributor:

    def __init__(self, int maxsize):
        self.queue = deque(maxlen=maxsize)
        self.event = asyncio.Event()
    
    cpdef void put(self, object resp):
        if isinstance(resp, list):
            for item in resp:
                self.queue.append(item)
        else:
            self.queue.append(resp)
        self.event.set()

    async def drain(self):
        if not self.queue:
            await self.event.wait()
        cdef list items = []
        while self.queue:
            items.append(self.queue.popleft())
        self.event.clear() # awake by event
        return items
