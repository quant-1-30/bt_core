# 核心架构设计
    项目基于backtrader重构， 核心从两个维度 a. broker feed store trade 核心模块剥离 ; b. 回测逻辑由 T+1 基于A股市场交易策略rewrite。主体backtest 负责 indicator 与 strategy 构建，
    构建方式基于type元类 构建框架类，抽象具体实现细节，具体可以深入backtrader metabase 源码了解细节。关于 feed 与 broker 集成方式， 借鉴xtp系统 mdapi / tdapi 构建sdk 集成到backtest。 


## 元类与类构造机制

Backtrader 使用元类系统实现类的自动注册和属性管理：

```
class MetaParams(type):
    """参数元类，用于自动处理类参数"""
    def __new__(cls, name, bases, dct):
        # __new__ 处理类属性：property、method等
        # dct 包含所有类级别的属性定义
        return super().__new__(cls, name, bases, dct)
    
    def __call__(cls, *args, **kwargs):
        # __call__ 处理实例化参数：**kwargs 对应实例属性
        return super().__call__(*args, **kwargs)

class Strategy(metaclass=MetaParams):
    """策略基类使用元类"""
    pass
```

### 关键点：
    __new__ 操作类属性字典（dct）
    __call__ 处理实例化参数（**kwargs）
    类的 __class__ 始终指向元类，与继承层次无关


## 数据流引擎

### 核心数据流动

    Cerebro.runnext() → data[0] 数据点变化 → Strategy.next() 触发 → Indicator 重新计算 → addbindings 同步所有数据的 minperiod

### 组件层级关系
    DataFeed (Lineseries) → Indicator (Lines) → Strategy → Cerebro (执行引擎)


## 线条(Line)系统

### Line 架构设计

```
class LineIterator:
    """线条迭代器基类"""
    def _next(self): pass  # 单步执行
    def _once(self): pass  # 批量执行

class LineOperation(LineIterator):
    """线条操作，支持表达式树"""
    def __init__(self, *args):
        self.args = args  # 构建二元/多元表达式树
        
class LineCoupler(LineIterator):
    """线条耦合器，对齐不同长度线条"""
    def __init__(self, *lines):
        self.lines = lines
```

### 线条派生系统

```
class MyIndicator(Indicator):
    lines = ('myline',)  # 自动派生线条
    params = (('period', 20),)  # AutoInfoParam 自动更新
```

## 执行模式详解

| 模式 | 执行方法 | 适用场景 | 内存使用 | 
|:---------:|:---------:|:---------:|
| 传统模式   | _runnext_old → _next while   | 实时数据   | 较高 
| 优化模式   | _runnext → _next_open/_next   | 批量处理   | 中等
| Once模式   | runonce_old → _once   | 历史回测   | 较低
| 优化Once   | _runonce → _once/reset   | 高效回测   |  最低
| 优化模式   | 内容5   | 内容6   |

### 内存管理策略

```
cerebro = Cerebro()
cerebro.run(exactbars=1)  # 只保存当前值
cerebro.run(exactbars=0)  # 保存完整历史
cerebro.run(exactbars=-1) # 低内存模式
```

数据处理流水线

数据加载流程

    添加数据源 → 预加载 → while循环加载 → _load方法 → 数据过滤

数据重采样
    compress ---> onendge ---> checkbarover

    bar2edge  adjbartime  rightedge boundoff

    resample  masterdata last 由于forward存在nan 导致indicator为nan ; 而resample 存在last函数 _fromstack fill forward导致的nan
    replay 含义举例 重建4小时数据(next 推进，数据是更新的, 需要将数据保存在stash中)

    2>/dev/null --- 0 1 2  |  find . -name / -type / -size / -perm / -group / -mtime

定时模块
    lastcall --- month --- weekday --- when --- repeat  when reach not on day or not repeat or execeed nexteos to update _lastcall
    daycarry ---> 3, 5 target is 4 , when acceed 3 but bisect.bisect_right == bisect.bisect_left and carry is True (1 + False = 1)

    optimize to implement 9:30 timer_event and monitor data with timer


# 涉及 linebuffer __init__ /  具体值计算比较 next  __getitem__
# basciops to implement next method and use linebuffer instead of __getitem__
# self define need to addminpeeriod and define dmaster
# PeriodN __init__ already addimperiod self.p.period
# signal scale to 0 - 1 / bool(self.delta[0] > 0) # np.False_ ---> bool 

find . -name "test_ind_*.py" -type f -exec mv {} test_bt_ind/ \;

# Profile

## memory
python -m memray run --aggregate -o output.bin my_script.py
python -m memray flamegraph output.bin
python -m memray summary output.bin
python -m memray table output.bin
python -m memray tree output.bin
python -m memray stats output.bin

## memory html
python3 -m http.server 8000 | ***.html
open ***.html 

## performance
py-spy record -o profile.svg --pid 12345
# OR
py-spy record -o profile.svg -- python myprogram.py


# Homebrew

# 禁用自动更新
export HOMEBREW_NO_AUTO_UPDATE=1

# 禁用 JSON API 安装（强制使用本地 Git taps）
export HOMEBREW_NO_INSTALL_FROM_API=1

# 使用国内 Bottle 镜像（加速下载预编译包）
export HOMEBREW_BOTTLE_DOMAIN=https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles

git -C "$(brew --repo homebrew/core)" remote -v
https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-core.git


set dmaster which means target data


# risk_system/
# ├── position_risk.py      # 头寸风险
# ├── portfolio_risk.py     # 组合风险  
# ├── market_risk.py        # 市场风险
# ├── liquidity_risk.py     # 流动性风险
# └── risk_orchestrator.py  # 风险协调器

# git commit failure and git reset --soft HEAD~1

# cython 优化 util 模块主要涉及时间处理 / data对象
# 指标核心计算公式通过cython改写 / 复用 numpy / dataclone memoryveiw
# 保留metabase 核心架构

# tls context = threading.local()

# class PricingDataAssociable(ABC) / PricingDataAssociable.register(Asset) 
# 虚拟子类不需要直接继承自抽象基类, 注册虚拟子类不论是否实现抽象基类中的抽象,Python都认为它是抽象基类的子类
# from toolz import curry / np.vectorize

sync: threading.Event() set and wait

if ext.endswith('.py'): # execute external code
    with open(ext) as f:
        ns = {}
        exec(compile(f.read(), ext, 'exec'), ns, ns)

def is_sorted_ascending(a):
    """Check if a numpy array is sorted."""
    return (np.fmax.accumulate(a) <= a).all()


# ta-lib
tar -xzf ta-lib-0.6.4-src.tar.gz
cd ta-lib-0.6.4

chmod +x autogen.sh  # ensure the permissions are set to generate the configure file
./autogen.sh         # generate the configure file
./configure
make
sudo make install

# line_profiler

@profile
kernprof -l -v my_script.py
python -m line_profiler my_script.py.lprof # metrics on line 


python -m cProfile -o output.prof myscript.py # locate function
python -m snakeviz output.prof

# Ray Scale
RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER=1 ray start --address='172.20.10.3:6379' / --head --object-store-memory=****

ray stop 

ray status

127.0.0.1:8265 # dashboard


Ray can't initialize sys standard streams due to fd restricted

Mac ulimit -n 256 default to adapt old select program 

select / epoll / kqueue , select traverse / epoll notify (epoll_create / epoll_ctl / epoll_wait) / kqueue (kevent register / wait)

epoll (red-black tree) io callback linux / kqueue macos trigger by lt and et

Ray:
** StoreAgent **基础设施服务（Infrastructure Service）** Detached 模式 (`lifetime="detached"`) **机制**：**全局注册（Pinned by GCS） 引用数 = 0 (来自脚本) + 1 (来自 GCS) = 1 **

1.  **持久化连接**：它持有的 TCP/ZMQ 连接非常昂贵，不能因为你跑了一次 `backtest.py` 脚本结束了，连接就断开。下次跑还得重新连。
2.  **共享复用**：你可能同时起 5 个不同的回测脚本（Driver），它们都要连接同一个 `StoreAgent`。如果是默认模式，谁创建谁负责销毁，很难共享。
3.  **服务发现**：因为它是 Detached 且有名字（Name），任何后来的脚本只要知道名字 `StoreAgent_NodeID`，就能通过 `ray.get_actor()` 连上它，而不需要重新创建

1.  `self.chan.put`  Actor 无法访问你本地进程的 Queue

*   **原则** **Rx 流操作 (pipe/subscribe)**、**复杂中间态处理** 的逻辑，都应该 **留在 Actor 内部**
*   **接口** Actor 对外只暴露 **“请求 -> 响应”** 的粗粒度接口

# .  **内存极度受限**：你设置了 `object_store_memory=2GB`。
# 2.  **并发压力**：4 个 Agent 同时在跑，每个都在疯狂往里 `ray.put` 数据（PyArrow Tables）。
# 3.  **驱逐机制 (Eviction)**：当 Object Store 满了（2GB 很容易满），Ray 会触发 **LRU 驱逐策略**。它会尝试把“引用计数看似较少”或者“旧的”对象清理掉，或者 Spill（溢出）到磁盘

ValueError: The configured object store size (25.0GiB) exceeds the optimal size on Mac (2.0GiB). This will harm performance! There is a known issue where Ray's performance degrades with object store size greater than 2.0GB on a Mac.To reduce the object store capacity, specify`object_store_memory` when calling ray.init() or ray start.To ignore this warning, set RAY_ENABLE_MAC_LARGE_OBJECT_STORE=1.


# Parallel(n_jobs=pool_size)(delayed(rpc)(meta) for meta in batches) # Parallel(n_jobs=2, return_as="generator")
# export RAY_record_ref_creation_sites=1

ray start --head --object-store-memory 21474836480 # 20G 

ray service struck reason:
1\  allocate memory and cpus
2\ ray start memory = ray actor + 
3\ Ray 的 CPU 资源是「并发上限约束」，而非「任务总数约束」

export RAY_OBJECT_STORE_ALLOW_SLOW_STORAGE=0 # avoid swap to ssd


ray start --head --num-cpus 8 --memory 34359738368 

✅ ray.put + yield ObjectRef:  The object has already been deleted by the reference counting protocol. This should not happen.


CPU 使用率从 20% 提升到 30% 说明之前的优化（如 Async StoreAgent）生效了，消除了死锁和部分阻塞，但**系统的并发度（Concurrency）依然不足以填满 CPU**。

这通常是因为：**Ray 的 Worker 申请了 CPU 资源（比如 `num_cpus=1`），但大部分时间在等待数据（IO Wait）或等待 Actor 响应，导致物理 CPU 并没有真正在计算。**

要将 CPU 压榨到 80%-90% 以上，你需要实施 **“超额订阅（Oversubscription）”** 和 **“去中心化（Sharding）”**

StoreAgent 占用的 CPU 100% 计入 ray start / ray.init() 启动的 Ray 节点资源池里，它不会是“额外”的系统进程资源

# pytest 

| scope    | 作用范围             |
| -------- | ---------------- |
| function | 每个 test 一次（默认）   |
| class    | 每个类一次            |
| module   | 每个文件一次           |
| session  | 整个 pytest 进程一次 ⭐ |


asyncio.get_running_loop()` 的行为**：
    *   这个函数只有在 **协程内部** 或者已经通过 `asyncio.run()` 启动的上下文中才能调用 

grpc-aio 与 uvloop 冲突
import asyncio
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


## 1. 为什么不能直接用 `get_running_loop`？（死锁陷阱）

Ray 的 Async Actor 或某些 Worker 环境确实自带一个 Event Loop（运行在主线程）。但是，如果你尝试在这个 Loop 上玩“同步桥接”，会引发死锁。

#### 死锁场景复现：
1.  **Ray 主线程**：正在运行 Event Loop。
2.  **你的代码**：调用 `td_api.submit()`（同步接口）。
3.  **你的操作**：
    *   获取主线程 Loop：`loop = asyncio.get_running_loop()`。
    *   提交任务：`fut = asyncio.run_coroutine_threadsafe(coro, loop)`。
    *   **死锁点**：`result = fut.result()`（阻塞主线程，等待结果）。
4.  **后果**：
    *   主线程被 `fut.result()` 卡住了（Block）。
    *   Event Loop 也就被卡住了（因为它跑在主线程）。
    *   提交的 `coro` 永远得不到执行机会（因为 Loop 被卡住了）。
    *   **结果：程序永久挂起（Deadlock）。**

# 性能分析 recursive 是 killer

loop.create_task() 返回的 asyncio.Task 需用 await 等待，而 run_coroutine_threadsafe 返回的 Future 需用 result() 等待（不能 await，需用 asyncio.wrap_future() 转换后才能 await）。

读写架构分离 （ 分布式读取 / 去中心写入）
   **MdApi** -> **Worker 进程级单例**（Factory Pattern）。因为它是读操作，且连接开销相对较小，分散在 Worker 中可以利用多网卡带宽。
   ***Writer** -> **Cluster 级单例**（Ray Actor）。因为它是写操作，数据库连接是瓶颈，必须中心化管理以利用 Batch Insert 的优势。
