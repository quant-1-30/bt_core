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
                 flush_threshold=50000):
        super().__init__(daemon=True)
        self.log_shm = log_shm
        self.flush_threshold = flush_threshold
        self.max_size_bytes = max_file_size_mb * 1024 * 1024
        
        self._buffer = []
        self._pending_count = 0
        
        # align to Cython struct
        self.schema = pa.schema([
            ('datetime', pa.int64()),
            ('value', pa.float64()),
            ('metrics', pa.int32()),
            # ('_pad', pa.int32())
        ])
        
        self.sink = sinks.get(fmt.lower(), ParquetSink)(cerebro_id, output_dir, self.schema)
        
        self._running = True

    def run(self):
        while self._running or self.log_shm.has_data():
            arr = self.log_shm.drain_metrics_ndarray(max_batch=10000)
            
            if arr is not None and len(arr) > 0:
                table = pa.Table.from_array(arr, schema=self.schema) # zero_copy
                self._buffer.append(table)
                self._pending_count += len(arr)
                
                if self._pending_count >= self.flush_threshold:
                    self._flush()
            else:
                time.sleep(0.001)
                if not self._running and self._buffer: self._flush()

        self.sink.close()

    def _flush(self):
        if not self._buffer: return
        
        big_table = pa.concat_tables(self._buffer)
        
        self.sink.check_rotation(self.max_size_bytes)
        
        self.sink.write(big_table)
        
        self._buffer = []
        self._pending_count = 0

    def stop(self):
        self._running = False