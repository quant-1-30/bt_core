import ray
import os
import asyncio
import reactivex.operators as ops
import ray.util.scheduling_strategies

from dotenv import load_dotenv
from bt_sdk.core.protocol import *
from bt_sdk.core.client import MdApi, TdApi, SubTopic, OrderType, ExecType


@ray.remote(max_concurrency=1000) 
class StoreAgent:
    def __init__(self, config={}):

        print(f"StoreAgent initialized on Node: {ray.get_runtime_context().get_node_id()}")
        # md_addr = os.getenv("MD_ADDR").split(":")
        self.batch_size = 1000
        md_addr = "127.0.0.1:9000"
        self.mdapi = MdApi(addr=(md_addr[0], int(md_addr[1])))

        # td_addr = os.getenv("TD_ADDR").split(":")
        td_addr = "127.0.0.1:8888"
        client_id = b"e9f8cd38-e73c-453f-8a47-55beda640ae6"
        self.tdapi = TdApi(client_id=client_id, addr=(td_addr[0], int(td_addr[1])))

        self._calendar = {} 
        self._instrument = {} 
        self._benchmark_cache = {} 
    
    async def get_calendar(self):
        if self._calendar:
            return self._calendar
        print(f"Agent: Fetching Calendar")

        calendar = await self.mdapi.async_get_calendar(body)
        # calendar = np.concatenate(data_chunks)
        if calendar:
            self._instrument = assets
        return 

    async def get_instrument(self):
        if self._instrument:
            return self._instrument
        print(f"Agent: Fetching Instrument")

        assets = await self.mdapi.async_get_instrument(body)
        if assets:
            self._instrument = assets
        return assets

    async def get_benchmark(self, body: QueryBody):
        cache_key = (tuple(body.sid), body.start_date, body.end_date)
        if cache_key in self._benchmark_cache:
            return self._benchmark_cache[cache_key]

        print(f"Agent: Fetching benchmark for {body.sid}...")

        bench_table = await self.mdapi.async_get_benchmark(body)
        # bench_table = pa.concat_tables(data_chunks, promote_options="permissive")
        
        self._benchmark_cache[cache_key] = bench_table
        return bench_table 

    async def get_adjfactor(self, body: QueryBody):
         
        factors = await self.mdapi.async_get_factor(body)
        return factors

    async def get_stream(self, body: QueryBody):
        print(f"Agent: Start streaming {body}")
        
        q = asyncio.Queue(maxsize=5)

        def on_next(table):
            print("on_next :", table)
            loop = asyncio.get_running_loop()
            # ray.put 是耗时操作，尽量放在回调里做，但要注意线程安全
            # 如果 ray.put 非线程安全，需要用 loop.call_soon_threadsafe 包装
            try:
                ref = ray.put(table)
                asyncio.run_coroutine_threadsafe(q.put(ref), loop)
            except Exception as e:
                print(f"Error in on_next: {e}")

        def on_complete():
            asyncio.run_coroutine_threadsafe(q.put(None), loop)

        self.sdk.mdapi.subscribe(body, on_next=on_next, on_completed=on_complete)
        try:
            while True:
                ref = q.get()
                if ref == StopIteration:
                    break
                yield ref 
        finally:
            if hasattr(subscription, 'dispose'):
                subscription.dispose()

    async def register(self, body: RegisterBody) -> List[Resp]:
        fut = self.tdapi.register(body)
        data = await asyncio.wrap_future(fut) # await asyncio.to_thread(submit)
        return data

    async def set_cash(self, body: CashBody, experiment_id: bytes) -> List[Resp]:
        fut = self.tdapi.set_cash(experiment_id, body)
        data = await asyncio.wrap_future(fut)
        return data

    async def getvalue(self, topic: int, experiment_id='') -> List[Resp]:
        fut = self.tdapi.getvalue.remote(experiment_id, topic) 
        data = await asyncio.wrap_future(fut)
        return data
    
    async def subscribe(self, topic:int, body: QueryBody, experiment_id:str) -> List[Resp]: 
        fut = self.tdapi.subscribe.remote(experiment_id, topic, body)
        data = await asyncio.wrap_future(fut)
        return data

    async def submit(self, body: OrderBody, experiment_id:str) -> List[Resp]:
        fut = self.tdapi.submit.remote(experiment_id, body) 
        data = await asyncio.wrap_future(fut)
        return data

    async def on_dt_over(self, body: QueryBody, experiment_id:str) -> List[Resp]:
        fut = self.tdapi.on_dt_over.remote(experiment_id, body)
        data = await asyncio.wrap_future(fut)
        return data
    
    def stop(self):
        self.mdapi.disconnect()
        self.tdapi.disconnect.remote()


def start_agents(store_config={}):
    ray.init(address="auto", namespace="backtest")
    
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


    # *方法一：脚本显式销毁**
    # agent = ray.get_actor("StoreAgent_xxxxx")
    # ray.kill(agent)

    # **方法二：重启整个 Ray 集群**
    # `ray stop` 会关闭 GCS 和所有 Raylet 所有的 Actor 进程都会被操作系统回收

if __name__ == "__main__":

    load_dotenv()
    start_agents()