from libc.stdint cimport int64_t, int32_t


cdef class FileSink:
    cdef str cerebro_id
    cdef str output_dir
    cdef str backend
    cdef str current_path
    cdef object schema
    cdef object writer

    cdef int32_t file_index
    
    cdef void _generate_path(self)

    cpdef void check_rotation(self, int32_t max_size_bytes)

    cpdef void write(self, object table)

    cpdef void close(self)

    cdef void _close(self)


cdef class ParquetSink(FileSink):
    
    cpdef void write(self, object table)# pa.Table


cdef class CSVSink(FileSink):
    
    cpdef void write(self, object table) # pa.Table


cdef class JSONSink(FileSink):

    cpdef void write(self, object table)# pa.Table
