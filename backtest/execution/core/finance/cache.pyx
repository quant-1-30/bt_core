import asyncio

from backtest.execution.core.finance.asset cimport Asset
from backtest.execution.core.gateway.interface cimport AsyncGateway  # cdef class info 
from backtest.execution.core.gateway.interface import async_gt  # load.so used for cast cdef type     
from backtest.execution.core.gateway.rpc.client cimport RpcTopic


cdef class AssetCache:
    def __cinit__(self): # initialize memory allocate
        pass

    def __init__(self):
        self._sharded_lock = asyncio.Lock()
    
    async def _fetch_from_rpc(self, bytes sid):
        cdef dict req = {"start_date": 0, "end_date": 0, "sid": [sid]}
        cdef int rpc_type = RpcTopic.Instrument

        iterator = await async_gt.rpc(rpc_type, req)
        async for row in iterator:
            return row

    cdef void _add_to_cache(self, bytes sid, object data):
        cdef Asset asset 
        cdef int c_sid = int(sid)
        cdef str name = data.column("name")[0].as_py() # Scalar to py
        cdef int first_trading = data.column("first_trading")[0].as_py() 
        cdef int delist = data.column("delist")[0].as_py()

        asset = Asset(sid, name, first_trading, delist)
        self._c_cache[c_sid] = asset.core

    async def addinfo(self, bytes sid):
        cdef int c_sid = int(sid)

        if self._c_cache.count(c_sid):
            return self._c_cache[c_sid]

        async with self._sharded_lock:
            data = await self._fetch_from_rpc(sid)
            self._add_to_cache(sid, data)
        return self._c_cache[c_sid]
