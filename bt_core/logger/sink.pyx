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

import os
import json
import pyarrow.parquet as pq
import pyarrow.csv as pacsv

from libc.stdint cimport int32_t

from bt_core.utils.encoder import CustomJSONEncoder


cdef class FileSink:
    def __init__(self, str cerebro_id, str output_dir, object schema, str backend):
        self.cerebro_id = cerebro_id
        self.backend = backend
        self.output_dir = output_dir
        self.schema = schema

        self.writer = None
        self.file_index = 0
        self.current_path = ""

    cdef void _generate_path(self):
        path = os.path.join(self.output_dir, f"log_{self.cerebro_id}_{self.file_index}.{self.backend}")
        self.current_path = path
        self.file_index += 1 # only consumer so safety

    cpdef void check_rotation(self, int32_t max_size_bytes):
        if self.writer and os.path.exists(self.current_path):
            if os.path.getsize(self.current_path) >= max_size_bytes:
                self.close()

    cpdef void write(self, object table): # pa.Table
        raise NotImplementedError

    cpdef void close(self):
        if self.writer:
            self._close()
            self.writer = None

    cdef void _close(self):
        self.writer.close()


cdef class ParquetSink(FileSink):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, backend="parquet", **kwargs)

    cpdef void write(self, object table): # pa.Table
        if not self.writer:
            self._generate_path()
            self.writer = pq.ParquetWriter(self.current_path, self.schema, compression='snappy')
        self.writer.write_table(table)


cdef class CSVSink(FileSink):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, backend="csv", **kwargs)

    cpdef void write(self, object table): # pa.Table
        if self.writer is None:
            self._generate_path()
            write_options = pacsv.WriteOptions(include_header=True)
            self.writer = pacsv.CSVWriter(self.current_path, self.schema, write_options=write_options)
        
        self.writer.write_table(table)


cdef class JSONSink(FileSink):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, backend="jsonl", **kwargs)

    cpdef void write(self, object table): # pa.Table
        cdef object rows

        if not self.writer:
            self._generate_path()
            self.writer = open(self.current_path, 'ab')

        rows = table.to_pylist()
        for row in rows:
            line = json.dumps(row,  cls=CustomJSONEncoder).encode('utf-8') + b'\n' # jsonlines
            self.writer.write(line)


sinks = {
    "parquet": ParquetSink,
    "csv": CSVSink,
    "json": JSONSink 
}
