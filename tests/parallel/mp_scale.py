# -*- coding : utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Pool
from toolz import compose, identity
import multiprocessing, os, math, sys, time


p = multiprocessing.Process(target=clock, args=(15,))
# process.daemon = True
p.start()
p.join()


class ClockProcess(multiprocessing.Process):
    def __init__(self, interval):
        multiprocessing.Process.__init__(self)
        self.interval = interval

    def run(self): # default api
        while True:
            print('the time is %s' % time.ctime())
            time.sleep(self.interval)

ClockProcess(5).start()


def f(x):
    return x*x


with Pool(processes=4) as pool:
    # map ---> sequence / imap_unordered stream in time
    
    print(pool.map(f, range(10)))

    for i in pool.imap_unordered(f, range(10)):
        print(i)

    # launching multiple evaluations asynchronously *may* use more processes # similar to future / set_result
    multiple_results = [pool.apply_async(os.getpid, ()) for i in range(4)]
    print([res.get(timeout=1) for res in multiple_results])

# exiting the 'with'-block has stopped the pool
print("Now the pool is closed and no longer available")


class Parallel(object):
    """
    from joblib import Memory,Parallel,delayed
    from math import sqrt

    cachedir = 'your_cache_dir_goes_here'
    mem = Memory(cachedir)
    a = np.vander(np.arange(3)).astype(np.float)
    square = mem.cache(np.square)
    b = square(a)
    Parallel(n_jobs=1)(delayed(sqrt)(i**2) for i in range(10))
    """

    def __init__(self, n_jobs=2):
        self.n_jobs = n_jobs

    def __call__(self, iterable):
        result = []

        def when_done(r):
            result.append(r.result())

        if self.n_jobs <= 0:
            self.n_jobs = multiprocessing.cpu_count()

        if self.n_jobs == 1:
            for jb in iterable:
                result.append(jb[0](*jb[1], **jb[2]))
        else:
            with ProcessPoolExecutor(max_worker=self.n_jobs) as pool:
                for jb in iterable:
                    future_result = pool.submit(jb[0], *jb[1], **jb[2])
                    future_result.add_done_callback(when_done)
        return result

    def run_in_thread(func, *args, **kwargs):
        from threading import Thread
        thread = Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread

# mp4ipy

# ray
