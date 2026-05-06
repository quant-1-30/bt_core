import os
import time
import json
import asyncio
import logging
from libc.stdint cimport int32_t

from backtest.execution.core.finance.position cimport Position 
from backtest.execution.core.finance.order cimport Order
from backtest.execution.core.finance.account cimport Account
from backtest.execution.core.finance.simulate_types cimport MsgType
from backtest.execution.gateway.interface import async_gt

logger = logging.getLogger(__name__)


cdef class IBatchWriter:

    cpdef void push(self, list data):
        raise NotImplementedError


cdef class BatchWriterActor(IBatchWriter): # CPU Intensive

    def __init__(self, int32_t q_size, int32_t batch_size, int32_t retries=3):
        self._buffer = []
        self._running = True
        self.retries = retries
        self.batch_size = batch_size
        self._queue = asyncio.Queue(maxsize=q_size)
        self._finished_event = asyncio.Event()

    cpdef void push(self, list snapshots):
        self._queue.put_nowait(snapshots) # may cause oom

    async def run(self):
        logger.info("BatchWriterActor started.")
        cdef object data

        while self._running:
            try:
                data = await self._queue.get()
                if [MsgType.Sentinel] == data: 
                    await self._flush()
                    self._running = False
                    break

                self._buffer.extend(data)
                if len(self._buffer) >= self.batch_size:
                    await self._flush()

            except Exception as e:
                logger.error(f"BatchWriterActor running error: {e}")
        
        self._finished_event.set()
        logger.info("BatchWriterActor stopped.")

    async def _flush(self):
        cdef list account_data = []
        cdef list order_data = []
        cdef list orderbit_data = []
        cdef list position_data = []
        
        cdef dict dedup_positions = {}  
        cdef dict dedup_accounts = {}   
        
        if not self._buffer:
            return
        
        try:
            for item in self._buffer:
                if "order" in item:
                    schema_obj = item["order"] 
                    order_dict = schema_obj.to_dict()
                    order_data.append(order_dict)
                    
                    if hasattr(schema_obj, 'order_bits'):
                        for bit in schema_obj.order_bits:
                            orderbit_data.append(bit.to_dict())

                if "positions" in item:
                    for sid, p_schema in item["positions"].items():
                        p_dict = p_schema.to_dict()

                        # raw_sid = p_dict['sid']
                        # if isinstance(raw_sid, bytes):
                        #     safe_sid = raw_sid
                        # elif isinstance(raw_sid, str):
                        #     safe_sid = raw_sid.encode('utf-8') 
                        # elif isinstance(raw_sid, memoryview):
                        #     safe_sid = raw_sid.tobytes() # memoryview != bytes
                        # elif isinstance(raw_sid, bytearray):
                        #     safe_sid = bytes(raw_sid) # bytearray 
                        # else:
                        #     safe_sid = str(raw_sid).encode('utf-8') 

                        key = (int(p_dict['datetime']), sid, str(p_dict['experiment_id']))
                        dedup_positions[key] = p_dict
                
                if "account" in item:
                    a_schema = item["account"]
                    a_dict = a_schema.to_dict()
                    key = (int(a_dict['datetime']), str(a_dict['experiment_id']))
                    dedup_accounts[key] = a_dict
            
            if order_data:
                await self._retry_write("vtorder", order_data)
            if orderbit_data:
                await self._retry_write("order_bit", orderbit_data)
            
            if dedup_positions:
                await self._retry_write("vtposition", list(dedup_positions.values()))
            if dedup_accounts:
                await self._retry_write("account", list(dedup_accounts.values()))

        except Exception as e:
            logger.error(f"Critical error during flush: {e}", exc_info=True)
            print("crush error: ", e)
            import sys
            sys.exit()
            await self._dump_fallback("flush_crash", self._buffer)
        
        finally:
            self._buffer.clear()

    async def _retry_write(self, str table, list data):
        cdef int i = 0
        
        while i < self.retries:
            try:
                await async_gt.bulk_insert(table, data) 
                return 
            except Exception as e:
                i += 1
                if i < self.retries:
                    logger.warning(f"Write {table} failed (attempt {i}), retrying... Error: {e}")
                    await asyncio.sleep(0.1 * i)
                else:
                    logger.error(f"Write {table} failed permanently. Dumping to disk. Error: {e}")
                    await self._dump_fallback(table, data)

    async def _dump_fallback(self, str prefix, object data):
        try:
            dump_dir = "./dump_fallback"
            if not os.path.exists(dump_dir):
                os.makedirs(dump_dir, exist_ok=True)
            
            timestamp = int(time.time() * 1000)
            filepath = f"{dump_dir}/{prefix}_{timestamp}.json"
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._sync_write_file, filepath, data)
            logger.info(f"Data saved to {filepath}")
        except Exception as e:
            logger.critical(f"FATAL: Could not dump data! Data lost. {e}")

    cdef _sync_write_file(self, str path, list data):
        try:
            with open(path, 'w') as f:
                json.dump(data, f, default=str, indent=4)
        except TypeError:
             with open(path, 'w') as f:
                f.write(str(data))

    async def wait_until_finished(self):
        await self._finished_event.wait()

