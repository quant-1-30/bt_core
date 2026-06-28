from libc.stdint cimport int32_t
from libcpp.string cimport string as cpp_string

cdef enum MsgType:
    Account = 1
    Order = 2      
    Tplus1 = 3     
    Snapshot = 4  
    Sentinel = 99    


ctypedef struct ActorId:
    int32_t MsgType
    cpp_string experiment_id
