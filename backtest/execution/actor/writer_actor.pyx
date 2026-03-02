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


cdef class BatchWriterActor: # CPU Intensive

    def __init__(self, int32_t max_size, int32_t batch_size):
        self._buffer = []
        self._running = True
        self.batch_size = batch_size
        self._queue = asyncio.Queue(maxsize=max_size)
        self._finished_event = asyncio.Event()

    cdef void push(self, dict snapshot):
        self._queue.put_nowait(snapshot) # may cause oom

    async def run(self):
        logger.info("BatchWriterActor started.")
        cdef dict data

        while self._running:
            try:
                data = await self._queue.get()
                if MsgType.Sentinel in data: 
                    await self._flush()
                    self._running = False
                    break

                self._buffer.append(data)
                if len(self._buffer) >= self.batch_size:
                    await self._flush()

            except Exception as e:
                logger.error(f"BatchWriterActor running error: {e}")
        
        self._finished_event.set()
        logger.info("BatchWriterActor stopped.")

    async def _flush(self):
        cdef Account acct_obj
        cdef Order order_obj
        cdef Position pos_obj
        
        cdef tuple key
        cdef dict item
        cdef dict dedup_positions = {}  # used to filter duplicated
        cdef dict dedup_accounts = {}   
        cdef list account_data = []
        cdef list order_data = []
        cdef list orderbit_data = []
        cdef list position_data = []
        
        if not self._buffer:
            return

        try:
            for item in self._buffer:
                if "order" in item and item["order"] is not None:
                    order_obj = <Order>item["order"]
                    schema_obj = order_obj.to_schema()
                    schema_bit = [d.to_dict() for d in schema_obj.order_bits]

                    order_data.append(schema_obj.to_dict())
                    # orderbit_data = [d.to_dict() for d in schema_obj.order_bits]
                    orderbit_data.extend(schema_bit)

                if "positions" in item and item["positions"] is not None:
                    positions_map = item["positions"]
                    for p in positions_map.values():
                        pos_obj = <Position>p
                        data = pos_obj.to_schema().to_dict()
                        # key = f"{data['datetime']}_{data['sid']}_{data['experiment_id']}" # repr not reliable when bytea and uuid
                        # key = (data['datetime'], data['sid'], data['experiment_id'])
                        # Normalization
                        raw_sid = data['sid']
                        if isinstance(data, bytes):
                            safe_sid = raw_sid
                        elif isinstance(raw_sid, str):
                            safe_sid = raw_sid.encode('utf-8') 
                        elif isinstance(raw_sid, memoryview):
                            safe_sid = raw_sid.tobytes() # memoryview != bytes
                        elif isinstance(raw_sid, bytearray):
                            safe_sid = bytes(raw_sid) # bytearray 
                        else:
                            safe_sid = str(raw_sid).encode('utf-8') 

                        safe_dt = int(data['datetime'])
                        raw_exp = data['experiment_id']
                        safe_exp_id = str(raw_exp) 
                        key = (safe_dt, safe_sid, safe_exp_id)
                        dedup_positions[key] = data
                
                if "account" in item and item["account"] is not None:
                    acct_obj = <Account>item["account"]  # cast
                    data = acct_obj.to_schema().to_dict()
                    # key = (data['datetime'], data['experiment_id'])
                    safe_dt = int(data['datetime'])
                    raw_exp = data['experiment_id']
                    safe_exp_id = str(raw_exp) 
                    key = (safe_dt, safe_exp_id)
                    dedup_accounts[key] = data
            
            if order_data:
                await self._retry_write("vtorder", order_data)
                await self._retry_write("order_bit", orderbit_data)
            
            position_data = list(dedup_positions.values())
            account_data = list(dedup_accounts.values())

            if position_data:
                await self._retry_write("vtposition", position_data)
            
            if account_data:
                await self._retry_write("account", account_data)

        except Exception as e:
            logger.error(f"Critical error during flush preparation: {e}", exc_info=True)
            await self._dump_fallback("flush_crash", self._buffer) # retry + degrade
        
        finally:
            self._buffer.clear() 

    async def _retry_write(self, str table, list data):
        """
            retry ---> failure ---> disk
        """
        cdef int retries = 3
        cdef int i = 0
        
        while i < retries:
            try:
                await async_gt.bulk_insert(table, data) 
                return 
            except Exception as e:
                i += 1
                if i < retries:
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
                json.dump(data, f, default=str)
        except TypeError:
             with open(path, 'w') as f:
                f.write(str(data))

    async def wait_until_finished(self):
        await self._finished_event.wait()
