import asyncio
import numpy as np
import pyarrow as pa

from backtest.execution.core.finance.asset cimport Asset
from backtest.execution.gateway.interface cimport AsyncGateway, RpcTopic  # cdef class info 
from backtest.execution.gateway.interface import async_gt  # load.so used for cast cdef type     
from bt_sdk.core.protocol import QueryBody

from libc.stdint cimport int32_t

cimport numpy as cnp


cdef class AssetCache:
    def __cinit__(self): # initialize memory allocate
        pass

    def __init__(self):
        self._sharded_lock = asyncio.Lock()
    
    async def _fetch_from_rpc(self):
        cdef object table
        cdef int32_t rpc_type = RpcTopic.Instrument

        table = await async_gt.remote(rpc_type, None) # complete
        return table

    cdef void _add_to_cache(self, object table):
        cdef:
            object batch
            int i, batch_len
            # MemoryView is mutable but pyarrow is immuatable
            const cnp.int32_t[:] v_int_sids 
            const cnp.int32_t[:] v_firsts
            const cnp.int32_t[:] v_delists
            Asset asset 
            bytes sid_bytes
            list v_names, v_sids

        for batch in table.to_batches(): # table cpu seek + caluate / batch seek avoid combine_chunk
            batch_len = batch.num_rows
            
            v_int_sids = batch.column("sid").cast(pa.int32()).to_numpy(zero_copy_only=True) # sid column is string
            # v_firsts = batch.column("first_trading").to_numpy().astype(np.int32, copy=False)
            v_firsts = batch.column("first_trading").cast(pa.int32()).to_numpy(zero_copy_only=True) 
            v_delists = batch.column("delist").cast(pa.int32()).to_numpy(zero_copy_only=True) 
            
            v_names = batch.column("name").to_pylist() # better than as_py()
            v_sids = batch.column("sid").to_pylist() # better than as_py()

            for i in range(batch_len): # C++ struct / std::string 或 char*
                sid_bytes = v_sids[i].encode("utf-8")
                asset = Asset(sid_bytes, v_names[i], v_firsts[i], v_delists[i])
                self._c_cache[v_int_sids[i]] = asset.core

    async def addinfo(self, bytes sid):
        cdef int32_t c_sid = int(sid.decode("utf-8"))

        if self._c_cache.count(c_sid):
            return self._c_cache[c_sid]

        async with self._sharded_lock:
            data = await self._fetch_from_rpc()
            self._add_to_cache(data)
        return self._c_cache[c_sid]
