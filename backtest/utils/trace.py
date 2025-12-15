#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    trace memory usage
"""
import time
import tracemalloc
import matplotlib.pyplot as plt


def memory_monitor(duration_sec=60, interval=1):
    tracemalloc.start()
    snapshots = []
    timestamps = []
    start_time = time.time()

    while time.time() - start_time < duration_sec:
        time.sleep(interval)
        snapshot = tracemalloc.take_snapshot()
        total = sum([stat.size for stat in snapshot.statistics('filename')])
        snapshots.append(total / 1024 / 1024)  # MB
        timestamps.append(time.time() - start_time)

    plt.plot(timestamps, snapshots)
    plt.xlabel("Time (s)")
    plt.ylabel("Memory Usage (MB)")
    plt.title("Memory Trend")
    plt.show()
