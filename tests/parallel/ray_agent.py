import ray
import os
import reactivex.operators as ops
import ray.util.scheduling_strategies

from dotenv import load_dotenv
from bt_sdk.core.protocol import *
from bt_sdk.core.client import MdApi, TdApi, SubTopic, OrderType, ExecType


@ray.remote
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
        self._benchmark_cache = {} 

    def get_calendar(self):

        def process_batch(table):
            datas.append(table.to_numpy()) 

        datas = []
        obs = mdapi.get_calendar()
        obs.subscribe( 
            on_next=process_batch,
            on_completed=lambda: print("Calendar Loaded")
        )
        obs.run() 
        calendar = np.concatenate(datas)
        return calendar
    
    def get_instrument(self):
        
        def process_batch(table):
            datas.extend(table)

        datas = []
        obs = mdapi.get_instrument().pipe( # ops.buffer_with_count(self.batch_size) # ops.to_list()
            ops.buffer_with_time_or_count(
                timespan=0.5,            
                count=self.batch_size    
                )
            )
        obs.subscribe(
            on_next=process_batch
        )
        obs.run() 
        
        table = pa.concat_tables(datas)
        assets = table.to_pylist() 
        return assets

    def get_stream(self, body: QueryBody):
        """
        Queue as bridge between rx callback and Generator
        """
        q = queue.Queue(maxsize=5) 
            
        def on_batch_ready(batch_table):
            ref = ray.put(batch_table)
            q.put(ref) # ref via plasma zero_copy

        # body = QueryBody(sid=[sid], start_date=start_date, end_date=end_date) # 
            
        observable = self.mdapi.subscribe(body)
        observable.subscribe( # nonblocking and let rx run in daemon thread
            on_next=on_batch_ready, # buffer_with_count
            on_error=lambda e: q.put(e),
            on_completed=lambda: q.put(StopIteration) 
        )
        try:
            while True:
                ref = q.get()
                if ref == StopIteration:
                    break
                yield ref 
        finally:
            if hasattr(subscription, 'dispose'):
                subscription.dispose()

    def get_adjfactor(self, body: QueryBody):
        adj = self.mdapi.get_factor(body) 

        factors = adj.raw_factors if adj else {} 
        if factors:
            factors = dict(sorted(factors.items())) 
        return factors

    def get_benchmark(self, body: QueryBody):

        def process_batch(batch_list):
            data_chunks.extend(batch_list)

        cache_key = (tuple(body.sid), body.start_date, body.end_date)
        if cache_key in self._benchmark_cache:
            return self._benchmark_cache[cache_key]

        data_chunks = []
        obs = self.mdapi.get_benchmark(body).pipe( 
            ops.buffer_with_time_or_count( # ops.do_action(on_next=process_batch)
                timespan=0.5,            
                count=self.batch_size    
                ),
            )
        obs.subscribe(
            on_next=process_batch
        )
        obs.run() 

        if not data_chunks:
            return None 

        bench_table = pa.concat_tables(data_chunks)
        self._benchmark_cache[cache_key] = bench_table
        return bench_table 

    def register(self, body: RegisterBody) -> List[Resp]:
        fut = self.tdapi.register(body)
        data = fut.result()
        body = self.get_body(data) 
        print("register body ", body)
        return body[0].experiment_id
    
    def set_cash(self, body: CashBody, experiment_id: bytes) -> List[Resp]:
        fut = self.tdapi.set_cash(experiment_id, body)
        data = fut.result()
        return data

    def getvalue(self, topic: int, experiment_id='') -> List[Resp]:
        fut = self.tdapi.getvalue.remote(experiment_id, topic) 
        data = fut.result()
        return data
    
    def subscribe(self, topic:int, body: QueryBody, experiment_id:str) -> List[Resp]: 
        fut = self.tdapi.subscribe.remote(experiment_id, topic, body)
        data = fut.result()
        return data

    def submit(self, body: OrderBody, experiment_id:str) -> List[Resp]:
        fut = self.tdapi.submit.remote(experiment_id, body) 
        data = fut.result()
        return data

    def on_dt_over(self, body: QueryBody, experiment_id:str) -> List[Resp]:
        fut = self.tdapi.on_dt_over.remote(experiment_id, body)
        data = fut.result()
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