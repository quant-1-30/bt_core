# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++

import asyncio
import numpy as np
cimport numpy as cnp
import polars as pl

from libc.stdint cimport int32_t

from bt_core.execution.gateway.interface cimport AsyncGateway # cdef class info 
from bt_core.execution.gateway.interface import async_gt  # load.so used for cast cdef type    

from bt_protocol._protocol import QueryBody
from bt_protocol.constant import RpcTopic


cdef class AssetCache:

    def __cinit__(self): 
        self._c_cache = {} # initialize memory allocate
        
    def __init__(self):
        self._sharded_lock = asyncio.Lock()
    
    async def _fetch_from_rpc(self):
        cdef object df
        cdef int32_t rpc_type = RpcTopic.Instrument

        df = await async_gt.rpc({}, rpc_type) # complete
        # merger: null -> "0" int
        # ratio: NaN -> 0.0
        df = df.with_columns([
            pl.col("merger").fill_null(b"0").alias("merger_fill"),
            # pl.col("merger").fill_null(pl.lit(b"0")).alias("merger_fill"),
            pl.col("ratio").fill_nan(0.0).fill_null(0.0).cast(pl.Float64).alias("ratio_float")
        ])
        return df

    cdef void _add_to_cache(self, object df):
        cdef:
            int32_t i, df_len
            const cnp.int32_t[:] v_firsts
            const cnp.int32_t[:] v_delists
            
            const cnp.float64_t[:] v_ratios
        
            Asset asset 
            bytes sid_bytes
            list v_names, v_sids

        df_len = df.height
        if df_len == 0:
            return
     
        v_firsts = df.get_column("first_trading").cast(pl.Int32).to_numpy()
        v_delists = df.get_column("delist").cast(pl.Int32).to_numpy()
        
        v_ratios = df.get_column("ratio_float").to_numpy()

        v_names = df.get_column("name").to_list() 
        v_sids = df.get_column("sid").to_list()
        v_mergers = df.get_column("merger_fill").to_list()
    
        for i in range(df_len):
            sid_bytes = v_sids[i].encode("utf-8")
            name_bytes = v_names[i].encode("utf-8")
            asset = Asset(sid_bytes, name_bytes, v_firsts[i], v_delists[i], v_mergers[i], v_ratios[i])
            self._c_cache[sid_bytes] = asset

    async def _async_fetch(self, bytes sid):
        async with self._sharded_lock:
            if sid in self._c_cache:
                return
            data = await self._fetch_from_rpc()
            self._add_to_cache(data)

    cdef Asset get_cache_info(self, bytes sid, object loop):
        """
            wrap async api
        """
        if sid not in self._c_cache:
            if loop is None:
                raise RuntimeError("AssetCache initialization requires an active event loop.")
            asyncio.run_coroutine_threadsafe(self._async_fetch(sid), loop).result()

        return self._c_cache.get(sid, None)
