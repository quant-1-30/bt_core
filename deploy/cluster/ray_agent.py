import ray
import os
import asyncio
import reactivex.operators as ops
import ray.util.scheduling_strategies

from dotenv import load_dotenv
from bt_sdk.core.protocol import *
from bt_sdk.core.client import GetMdApi


@ray.remote(num_cpus=0.1, max_concurrency=10000) # default 0.1 used for socket light service
class StoreAgent:
    def __init__(self, config={}):
        load_dotenv()
        print(f"StoreAgent initialized on Node: {ray.get_runtime_context().get_node_id()}")
        self.mdapi = None

        self.batch_size = 10000 
        self._calendar = {} 
        self._instrument = {} 
        self._benchmark_cache = {}

    def _ensure_initialized(self): # loop 
        """Lazy initialize to ensure get_running_loop not new_loop"""
        if self.mdapi is None:
            print(f"[Agent] Initializing APIs on Node {ray.get_runtime_context().get_node_id()}...")

            md_host = os.getenv("md_host", "127.0.0.1") # "172.20.10.3" 
            md_port = os.getenv("md_port", 50051)
            self.mdapi = GetMdApi(addr=(md_host, int(md_port)))

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

    def stop(self):
        self.mdapi.disconnect()


def start_agents(store_config={}, iscluster=False, pool_size=1):
    """
        local and cluster
    """
    if not ray.is_initialized():
        ray.init(address="auto", namespace="backtest") # object_store_memory= **B # ray.init overwrite ray start command

    if iscluster:
        print("Starting agents in Node Binding mode...")

        active_nodes = [
            n for n in ray.nodes() 
            if n["Alive"] and "node:127.0.0.1" not in n["Resources"] 
            if n["Alive"] 
        ]

        for node in active_nodes:
            node_id = node["NodeID"]
            actor_name = f"StoreAgent_{node_id}"
            try:
                ray.get_actor(actor_name)
            except ValueError:
                strategy = ray.util.scheduling_strategies.NodeAffinitySchedulingStrategy( # force binding
                    node_id=node_id, soft=True # wait util node is avaiable 
                )
                StoreAgent.options(
                    name=actor_name,
                    lifetime="detached",
                    scheduling_strategy=strategy,
                    # num_cpus=0.2,
                    # max_concurrency=1000
                ).remote()
                print(f"Started {actor_name} on node {node_id}")
    else:
        print(f"Starting {pool_size} agents in Local mode...")
        for i in range(pool_size):
            actor_name = f"StoreAgent_Local_{i}" 
            try:
                ray.get_actor(actor_name)
                print(f"Agent {actor_name} exists.")
            except ValueError:
                StoreAgent.options(
                    name=actor_name,
                    lifetime="detached",
                    # num_cpus=0.2, 
                    # max_concurrency=1000
                ).remote()
                print(f"Started {actor_name}")


if __name__ == "__main__":

    start_agents()