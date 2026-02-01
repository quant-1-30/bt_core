import ray
import os
import asyncio
import reactivex.operators as ops
import ray.util.scheduling_strategies

from dotenv import load_dotenv
from bt_sdk.core.protocol import *
from bt_sdk.core.client import MdApi, TdApi, SubTopic, OrderType, ExecType


@ray.remote(max_concurrency=100, num_cpus=1)  # signal thread max_concurrency ---> asyncio concurrent 
class StoreAgent:
    def __init__(self, config={}):
        print(f"StoreAgent initialized on Node: {ray.get_runtime_context().get_node_id()}")
        # md_addr = os.getenv("MD_ADDR").split(":")
        self.mdapi = None
        self.tdapi = None

        self.batch_size = 2 
        self._calendar = {} 
        self._instrument = {} 
        self._benchmark_cache = {}

    def _ensure_initialized(self): # loop 
        """Lazy initialize to ensure get_running_loop not new_loop"""
        if self.mdapi is None or self.tdapi is None:
            print(f"[Agent] Initializing APIs on Node {ray.get_runtime_context().get_node_id()}...")

            md_host = os.getenv("md_host", "127.0.0.1") # "172.20.10.3" 
            md_port = os.getenv("md_port", 9000)
            self.mdapi = MdApi(addr=(md_host, int(md_port)))

            td_host = os.getenv("td_host", "127.0.0.1") 
            td_port = os.getenv("td_port", 8888)
            client_id = b"e9f8cd38-e73c-453f-8a47-55beda640ae6"
            self.tdapi = TdApi(client_id=client_id, addr=(td_host, int(td_port)))
            print("self.tdapi :", self.tdapi) 
    
    async def get_calendar(self):
        self._ensure_initialized()
        if self._calendar:
            return self._calendar
        calendar = await self.mdapi.get_calendar_async()
        if calendar:
            self._calendar = calendar
        return 

    async def get_instrument(self):
        self._ensure_initialized()
        if self._instrument:
            return self._instrument
        assets = await self.mdapi.get_instrument_async()
        if assets:
            self._instrument = assets
        return assets

    async def get_benchmark(self, body: QueryBody):
        cache_key = (tuple(body.sid), body.start_date, body.end_date)
        if cache_key in self._benchmark_cache:
            return self._benchmark_cache[cache_key]
        
        self._ensure_initialized()
        bench_table = await self.mdapi.get_benchmark_async(body)
        self._benchmark_cache[cache_key] = bench_table
        return bench_table 

    async def get_adjfactor(self, body: QueryBody):
        self._ensure_initialized()
        adj = await self.mdapi.get_factor_async(body)
        factors = adj.raw_factors if adj else {} # adj_factors
        return factors

    async def get_stream(self, body: QueryBody):
        q = asyncio.Queue(maxsize=self.batch_size)
        self._ensure_initialized()
        loop = asyncio.get_running_loop()

        def on_next(table):
            print("on_next :", table)
            try:
                ref = ray.put(table) # zero_copy
                fut = asyncio.run_coroutine_threadsafe(q.put(ref), loop) # call_soon_threadsafe sync method
            except Exception as e:
                print(f"Error in on_next: {e}")

        def on_complete():
            asyncio.run_coroutine_threadsafe(q.put(StopIteration), loop)

        obs = self.mdapi.subscribe(body)
        obs.subscribe(on_next=on_next, on_completed=on_complete)
        try:
            while True:
                ref = await q.get()
                print("ref ", ref)
                if ref == StopIteration:
                    break
                yield ref # Ray Generator ---> ObjectRef 
        finally:
            if hasattr(obs, 'dispose'):
                obs.dispose()

    async def register(self, body: RegisterBody) -> List[Resp]:
        self._ensure_initialized()
        data = await self.tdapi.register_async(body) # asyncio.wrap_future(fut)
        return data

    async def set_cash(self, experiment_id:bytes, body: CashBody) -> List[Resp]:
        self._ensure_initialized()
        data = await self.tdapi.set_cash_async(experiment_id, body)
        return data

    async def getvalue(self, topic:int, experiment_id:bytes) -> List[Resp]:
        self._ensure_initialized()
        data = await self.tdapi.getvalue_async(topic, experiment_id) 
        return data
    
    async def subscribe(self, topic:int, experiment_id:bytes, body: QueryBody, ) -> List[Resp]: 
        self._ensure_initialized()
        data = await self.tdapi.subscribe_async(topic, experiment_id, body)
        return data

    async def submit(self, experiment_id:bytes, body: OrderBody, ) -> List[Resp]:
        self._ensure_initialized()
        data = await self.tdapi.submit_async(experiment_id, body) 
        return data

    async def on_dt_over(self, experiment_id:bytes, body: QueryBody) -> List[Resp]:
        self._ensure_initialized()
        data = await self.tdapi.on_dt_over_async(experiment_id, body)
        return data
    
    def stop(self):
        self.mdapi.disconnect()
        self.tdapi.disconnect()


def start_agents(store_config={}):
    ray.init(
        address="auto", 
        namespace="backtest")
        # object_store_memory=20 * 1024 * 1024 * 1024) # ray init overwrite ray start --object_store_memory

    nodes = [n for n in ray.nodes() if n["Alive"]]
    for node in nodes:
        node_id = node["NodeID"]
        actor_name = f"StoreAgent_{node_id}"
        try:
            ray.get_actor(actor_name)
            print(f"Agent {actor_name} already exists.")
        except ValueError:
            strategy = ray.util.scheduling_strategies.NodeAffinitySchedulingStrategy( # force deploy node 
                node_id=node_id, soft=True
            )
            StoreAgent.options(
                name=actor_name, 
                lifetime="detached", # gcs regiter despite script exit
                scheduling_strategy=strategy,
                num_cpus=0.1 
            ).remote(store_config)
            print(f"Started {actor_name}")


if __name__ == "__main__":

    load_dotenv()
    start_agents()
    # agent = ray.get_actor("StoreAgent_xxxxx")
    # ray.kill(agent) # ray stop 