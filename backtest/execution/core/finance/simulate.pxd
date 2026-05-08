from libc.stdint cimport int32_t
from libcpp.string cimport string as cpp_string

from backtest.execution.core.finance.order cimport Order
from backtest.execution.core.finance.simulate_types cimport ActorId
from backtest.execution.core.finance.cash cimport AsyncCashManager
from backtest.execution.core.finance.cache cimport AssetCache
from backtest.execution.actor.writer_actor cimport BatchWriterActor


cdef class ActorMessage:
    cdef ActorId actor_id
    cdef cpp_string experiment_id
    cdef public object payload
    cdef object reply_future  # sync payload


cdef class TrackerActor:
    cdef bytes experiment_id
    cdef int32_t buffer_size
    cdef AsyncCashManager cash_manager      
    cdef AssetCache asset_cache  

    cdef object _queue        
    cdef object _ready_event
    cdef object _put_buffer 
    cdef object _writer 
    cdef object _latest_snapshot
    cdef object cached_uuid

    cdef dict positions, _fillers
    
    cdef tuple set_cash(self, object event)

    cdef void _sync_event(self, bytes experiment_id, dict pobjs, dict py_adj_table, dict py_rgt_table)

    cdef void _create_and_send_snapshot(self, str reason, ActorMessage msg, bint writer=*, list ord_body=*)

    cdef object get_snapshot(self)
    
    cdef _flush(self)
    
    cdef void _collect(self)


cdef class Simulator:
    cdef int32_t q_size
    cdef int32_t buffer_size
    cdef AssetCache _asset_cache
    cdef object _writer
    cdef object _loop
    cdef dict _actors 
    
    cdef void attach(self, loop)
    
    cdef TrackerActor _get_or_create_actor(self, bytes experiment_id)
    
    