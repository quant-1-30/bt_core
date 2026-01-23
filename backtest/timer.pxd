from libc.stdint cimport int64_t

cpdef enum Session:
    SESSION_START = 0
    SESSION_END = 1


cdef class Timer:
    cdef object when
    cdef int offset
    cdef int repeat
    cdef list weekdays
    cdef list monthdays
    cdef bint weekcarry
    cdef bint monthcarry
    cdef object allow
    cdef object _tzdata
    
    cdef bint _isdata
    cdef double _dtwhen
    cdef object _dwhen
    cdef object _lastcall
    cdef object _rstwhen
    
    cdef int _curmonth
    cdef int _curweek
    cdef int _curmonth_idx
    cdef int _curweek_idx

    cdef object _curdate
    cdef double _nextdteos

    cpdef void start(self, object data)

    cdef void _reset_when(self, object ddate=?)

    cdef bint _check_month(self, int dday, int dmonth)

    cdef bint _check_week(self, int dwkday, int dweek)

    cpdef bint check(self, double dt)
    