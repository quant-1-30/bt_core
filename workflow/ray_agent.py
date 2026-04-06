import ray
import os
import asyncio
import reactivex.operators as ops
import ray.util.scheduling_strategies

from dotenv import load_dotenv
from bt_sdk.core.protocol import *
from workflow.preprocess import _initialize_mdapi


@ray.remote(num_cpus=0.1, max_concurrency=1000) # default 0.1 used for socket light service
class MdapiAgent:
    def __init__(self, config={}):
        load_dotenv()
        print(f"MdapiAgent initialized on Node: {ray.get_runtime_context().get_node_id()}")
        self.mdapi = None

    def _ensure_initialized(self): # loop 
        """Lazy initialize to ensure get_running_loop not new_loop"""
        if self.mdapi is None:
            print(f"[Agent] Initializing APIs on Node {ray.get_runtime_context().get_node_id()}...")
            self.mdapi = _initialize_mdapi()

    async def get_tick(start_date: int, end_date: int, sid: bytes):
        self._ensure_initialized()
        body = QueryBody(start_date=start_date, end_date=end_date, sid=[sid])
        tick_data = await self.mdapi.get_subscribe_async(bdoy, adj=FactorTopic.Hfq)
        return tick_data

    async def submit(sid:bytes, rq_config: ray.ObjectRef, bench_ref):
        tick_data = await get_tick(rq_config["start_date"], rq_config["end_date"], sid)
        return run_backtest.remote(
                sid, 
                tick_data,
                rq_config,
                bench_ref=bench_ref
            )

    def stop(self):
        self.mdapi.disconnect()


def start_agents(pool_size=10, cluster=False):
    """
        local and cluster
    """
    if not ray.is_initialized():
        ray.init(address="auto", namespace="backtest") # object_store_memory= **B # ray.init overwrite ray start command

    if cluster:
        print("Starting agents in Node Binding mode...")

        active_nodes = [
            n for n in ray.nodes() 
            if n["Alive"] and "node:127.0.0.1" not in n["Resources"] 
            if n["Alive"] 
        ]

        for node in active_nodes:
            node_id = node["NodeID"]
            actor_name = f"MdapiAgent{node_id}"
            try:
                ray.get_actor(actor_name)
            except ValueError:
                strategy = ray.util.scheduling_strategies.NodeAffinitySchedulingStrategy( # force binding
                    node_id=node_id, soft=True # wait util node is avaiable 
                )
                MdapiAgent.options(
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
            actor_name = f"MdapiAgent_Local_{i}" 
            try:
                ray.get_actor(actor_name)
                print(f"Agent {actor_name} exists.")
            except ValueError:
                MdapiAgent.options(
                    name=actor_name,
                    lifetime="detached"
                ).remote()
                print(f"Started {actor_name}")


if __name__ == "__main__":

    agent_num = 10
    start_agents(pool_size=agent_num)
