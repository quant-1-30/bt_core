#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import traceback
import pyarrow as pa

from .sink import sinks


class LogConsumerThread(threading.Thread):
    def __init__(self, 
                 log_shm: object, 
                 log_id: str, 
                 fmt: str,
                 output_dir: str,
                 batch=10000, 
                 max_file_size_mb: int =512, 
                 flush_threshold: int =10000):
        super().__init__(daemon=False)

        self.log_shm = log_shm
        self.flush_threshold = flush_threshold
        self.max_size_bytes = max_file_size_mb * 1024 * 1024
        self.batch = batch
        
        self._buffer = []
        self._current_rows = 0 

        # align to Cython struct
        self.schema = pa.schema([
            ('datetime', pa.int64()),
            ('value', pa.float64()),
            ('metrics', pa.binary()), # pa.binary(length=64)导致填充 \x0
            # ('_pad', pa.int32())
        ])
        
        self.sink = sinks.get(fmt.lower())(log_id, output_dir, self.schema)
        
        # self._stop_event = threading.Event()
        self._running = True

    def run(self):
        try:
            # while not self._stop_event.is_set():
            while self._running:
                arr = self.log_shm.drain_metrics(batch=self.batch)
                if len(arr) > 0:
                    print("LogConumserThread run arr: ", len(arr))
                    table = self._process_and_buffer(arr)
                else:
                    time.sleep(0.001)

            # drain
            while True:
                arr = self.log_shm.drain_metrics(batch=self.batch)
                if not len(arr):
                    break
                self._process_and_buffer(arr)
            self._flush() 

            self.sink.close()
            print("sink close")
        except Exception as e:
            with open("FATAL_THREAD_CRASH.txt", "w") as f:
                f.write(traceback.format_exc())
            print(f"!!! LOG THREAD CRASHED: {e}")
        finally:
            print("LogConsumerThread fully exited.")

    # @staticmethod
    def _process_and_buffer(self, arr):
        """
        Structured Array to Pyarrow Table
        """
        # 1D Structured Array to List of 1D Arrays / numpy_arr['column_name'] zero_copy view
        decode_metrics = [m.decode('utf-8').rstrip('\x00') for m in arr['metrics']]

        arrays = [
            pa.array(arr['datetime']),
            pa.array(arr['value']),
            pa.array(decode_metrics),
            # pa.array(arr['_pad'])
        ]
        table = pa.Table.from_arrays(arrays, schema=self.schema)
        self._buffer.append(table)

        self._current_rows += table.num_rows
        if self._current_rows >= self.flush_threshold:
            self._flush()

    def _flush(self):
        if not self._buffer: return
        
        big_table = pa.concat_tables(self._buffer)
        
        self.sink.check_rotation(self.max_size_bytes)
        
        self.sink.write(big_table)
        
        self._buffer = []
        self._current_rows = 0

    def stop(self):
        # self._stop_event.is_set()
        self._running = False
        print("thread stop")
