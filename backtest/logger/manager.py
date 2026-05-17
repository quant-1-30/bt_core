#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import pyarrow as pa

from .sink import sinks


class LogConsumerThread(threading.Thread):
    def __init__(self, log_shm, cerebro_id, output_dir,
                 fmt="parquet", 
                 max_file_size_mb=512, 
                 flush_threshold=500000):
        super().__init__(daemon=True)

        self.log_shm = log_shm
        self.flush_threshold = flush_threshold
        self.max_size_bytes = max_file_size_mb * 1024 * 1024
        
        self._buffer = []

        # align to Cython struct
        self.schema = pa.schema([
            ('datetime', pa.int64()),
            ('value', pa.float64()),
            ('metrics', pa.binary()),
            # ('_pad', pa.int32())
        ])
        
        self.sink = sinks.get(fmt.lower())(cerebro_id, output_dir, self.schema)
        
        self._stop_event = threading.Event()

    def run(self):
        try:
            while not self._stop_event.is_set() or self.log_shm.has_data():
                arr = self.log_shm.drain_metrics(min_batch=5000, max_batch=100000)

                if arr is not None and len(arr) > 0:
                    print("LogConumserThread run arr: ", len(arr), arr)
                    table = self._process_and_buffer(arr)
                else:
                    time.sleep(0.001)
        except Exception as e:
            import traceback
            print(f"!!! FATAL ERROR IN LOG THREAD !!!: {e}")
            traceback.print_exc()
        finally:
            print("LogConsumerThread fully exited.")

        # drain
        while True:
            arr = self.log_shm.drain_metrics(min_batch=1, max_batch=50000)
            if arr is None:
                break
            self._process_and_buffer(arr)

        self.sink.close()

    # @staticmethod
    def _process_and_buffer(self, arr):
            """
            Structured Array to Pyarrow Table
            """
            # 1D Structured Array to List of 1D Arrays / numpy_arr['column_name'] zero_copy view
            arrays = [
                pa.array(arr['datetime']),
                pa.array(arr['value']),
                pa.array(arr['metrics']),
                # pa.array(arr['_pad'])
            ]
            table = pa.Table.from_arrays(arrays, schema=self.schema)
            self._buffer.append(table)
        
            if len(self._buffer) >= self.flush_threshold:
                self._flush()

    def _flush(self):
        if not self._buffer: return
        
        big_table = pa.concat_tables(self._buffer)
        
        self.sink.check_rotation(self.max_size_bytes)
        
        self.sink.write(big_table)
        
        self._buffer = []

    def stop(self):
        self._stop_event.is_set()
