# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++

import asyncio
import numpy as np
cimport numpy as cnp
import polars as pl

from libc.stdint cimport int32_t

from bt_core.execution.core.finance.asset cimport Asset
from bt_core.execution.gateway.interface cimport AsyncGateway # cdef class info 
from bt_core.execution.gateway.interface import async_gt  # load.so used for cast cdef type     
from bt_sdk.core.protocol import QueryBody
from bt_sdk.core.client import RpcTopic


cdef class AssetCache:
    def __cinit__(self): # initialize memory allocate
        pass

    def __init__(self):
        self._sharded_lock = asyncio.Lock()
    
    async def _fetch_from_rpc(self):
        cdef object table
        cdef int32_t rpc_type = RpcTopic.Instrument

        df = await async_gt.rpc({}, rpc_type) # complete
        return df

    cdef void _add_to_cache(self, object df):
        cdef:
            int32_t i, df_len
            const cnp.int32_t[:] v_int_sids 
            const cnp.int32_t[:] v_firsts
            const cnp.int32_t[:] v_delists
            Asset asset 
            bytes sid_bytes
            list v_names, v_sids
    
        df_len = df.height
        if df_len == 0:
            return
     
        v_int_sids = df.get_column("sid").cast(pl.Int32).to_numpy() 
        v_firsts = df.get_column("first_trading").cast(pl.Int32).to_numpy()
        v_delists = df.get_column("delist").cast(pl.Int32).to_numpy()
        
        v_names = df.get_column("name").to_list() 
        v_sids = df.get_column("sid").to_list()
    
        for i in range(df_len):
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
