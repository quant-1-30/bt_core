from libc.stdint cimport int32_t
from libcpp.string cimport string as cpp_string

from backtest.execution.core.finance.order cimport Order
from backtest.execution.core.finance.simulate_types cimport ActorId
from backtest.execution.core.finance.cash cimport AsyncCashManager
from backtest.execution.core.finance.cache cimport AssetCache


cdef class ActorMessage:
    cdef ActorId actor_id
    cdef cpp_string experiment_id
    cdef public object payload
    cdef object reply_future  # sync payload


cdef class BatchWriterActor:
    cdef int32_t batch_size
    cdef bint _running
    cdef object _queue
    cdef list _buffer
    cdef object _finished_event 
    
    cdef void push(self, dict snapshot)


cdef class TrackerActor:
    cdef bytes experiment_id
    cdef object _queue        
    cdef BatchWriterActor _writer 
    cdef object _ready_event 
    
    cdef AsyncCashManager cash_manager      
    cdef AssetCache asset_cache       
    cdef dict positions, _fillers
    cdef object _latest_snapshot 
    
    cdef tuple set_cash(self, object event)

    cdef void _sync_event(self, bytes experiment_id, dict pobjs, dict py_adj_table, dict py_rgt_table)

    cdef void _create_and_send_snapshot(self, str reason, ActorMessage msg, bint writer=*)

    cdef object get_snapshot(self)


cdef class Simulator:
    cdef int32_t max_size
    cdef dict _actors 
    cdef BatchWriterActor _writer
    cdef object _loop
    cdef object _asset_cache
    
    cdef void attach(self, loop)
    
    cdef TrackerActor _get_or_create_actor(self, bytes experiment_id)
    