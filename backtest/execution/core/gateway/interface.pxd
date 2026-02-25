
from backtest.execution.core.gateway.rpc.client cimport RpcClient

cdef enum SubTopic:
    Order = 0
    Position = 1
    Account = 2


cdef class AsyncGateway:
    cdef RpcClient rpc_gt
