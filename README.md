# 核心架构设计
    项目基于backtrader重构， 核心从两个维度 a. broker feed store trade 核心模块剥离 ; b. 回测逻辑由 T+1 基于A股市场交易策略rewrite。主体bt_core 负责 indicator 与 strategy 构建，
    构建方式基于type元类 构建框架类，抽象具体实现细节，具体可以深入backtrader metabase 源码了解细节。关于 feed 与 broker 集成方式， 借鉴xtp系统 mdapi / tdapi 构建sdk 集成到bt_core。 


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


恭喜你找到了引发这个诡异 Bug 的罪魁祸首！`pdb.set_trace()` 在异步（Asyncio）和 Actor 模型的架构中确实是一个非常危险的调试工具，因为它会挂起当前协程，但底层的事件循环、系统时钟或者队列重试机制可能会继续运行，从而导致同一笔消息被重复推入 `_queue`。这个排查非常精彩！

既然根本原因是由于 Debug 造成的重复发单，你的系统在正常运行时的逻辑确实是清晰的
放弃纠缠那个“幽灵逻辑”是明智的，在复杂的异步重构中，有些 side-effects（副作用）来自于事件循环的触发时机或缓存残留，强行定位可能事倍功半。

如果 `BatchSize` 大，且你在 `run` 循环中频繁调用这个过程，可能会出现：
1.  **对象的延迟属性加载问题**：如果模型对象在 `_flush` 时试图去访问已经改变的 `Position` 对象（由于浅拷贝或引用），数据可能会错乱。
2.  **内存对象的不一致**：SQLAlchemy 对象带有 `_sa_instance_state`，在多线程/协程的高并发 Buffer 中，这些状态可能会产生冲突。


### 真相一：为什么 BatchSize 变大会导致 `vtposition` 彻底归零？

这绝对不是你的去重逻辑写错了，而是你触碰到了 **PostgreSQL 数据库的“参数数量硬上限” (Parameter Limit)**！

**深度原理解析：**
1. **参数爆炸**：`asyncpg`（PG 数据库驱动）在执行 `bulk_insert` 时，底层使用的是扩展查询协议。PostgreSQL 对单个查询语句的参数占位符（如 `$1, $2...`）有一个严格的硬性上限：**老版本是 32,767 个，新版本 (PG 14+) 是 65,535 个**。


python -m build --wheel --no-isolation
poetry build --format wheel # pure python

# 当你把指针转换成 <EventMsg*> 时，C 语言允许你使用下标语法 [i]。编译器魔法：当你访问 self.buffer[i] 时，编译器会自动计算地址：$$\text#   {Target Address} = \text{Base Address} + (i \times \text{sizeof(EventMsg)})$$这种“基地址 + 偏移”的模式，让这个指针在行为上表现得完全像一个数组

bint 的大小：通常是 4 字节（随 C int），但不绝对保证

结论：必须替代。在 SHM 结构体定义中，永远不要使用 int, long, short, bint 等模糊类型，必须全部使用 int8_t, int32_t, int64_t 等来自 libc.stdint 的类型，以确保内存布局在不同进程、不同编译器下严格对齐

volatile 是一个非常关键的限定符。它的核心作用是：告诉编译器不要对该变量进行任何“优化”，每次读写都必须直接操作内存地址，而不是使用寄存器中的缓存
在共享内存（SHM）或多线程编程中，volatile 是一个非常关键的限定符。它的核心作用是：告诉编译器不要对该变量进行任何“优化”，每次读写都必须直接操作内存地址，而不是使用寄存器中的缓存。

1. 为什么需要 volatile？（场景还原）
假设有两个进程：进程 A（生产者）负责更新 head 指针，进程 B（消费者）在一个循环里不断检查 head 的值。

如果没有 volatile：
编译器在编译进程 B 的代码时，可能会认为：“这个 head 变量在循环内部没有被修改过啊！”为了提高效率，编译器会把 head 的值一次性读入 CPU 的寄存器中，之后每次循环都直接从寄存器读。

结果：即使进程 A 在共享内存里修改了 head，进程 B 也看不到，因为它还在读旧的寄存器副本。这会导致死循环或数据积压。

有了 volatile：
编译器被强制生成 LDR（加载）指令，每次判断 while(head == ...) 时，CPU 必须重新去内存条（或 Cache）里取最新的值。

2. volatile 的三大职能
A. 禁止寄存器缓存（内存可见性）
确保变量的修改对其他“观察者”是可见的。对于 Ring Buffer 的 head 和 tail，这是它们能在多进程间同步的基础。

B. 防止指令重排（有限）
编译器有时会为了效率调整指令顺序。volatile 告诉编译器，不要把我对这个变量的操作和周围的代码顺序调换。

注意：volatile 只能防止编译器重排，不能防止 CPU 硬件层面的指令重排（乱序执行）。在极高性能场景下，通常还需要搭配 Memory Barrier（内存屏障）。

C. 确保操作不被“优化掉”
如果你写了 head = 1; head = 2;，编译器可能会觉得第一句没用，直接删掉。但在硬件编程或 SHM 中，这两次写入可能都有意义（比如触发某种硬件信号），volatile 能保证每一行代码都转化为实际的机器指令。

3. 在 Ring Buffer 中的具体表现
在你的 RingHeader 中：

head：写端（写入数据后）更新它，读端（检查是否有新数据）读取它。

tail：读端（处理完数据后）更新它，写端（检查是否有剩余空间）读取它。

如果这两个字段不加 volatile，在高并发下，读端可能认为 Buffer 一直是空的（读不到最新的 head），或者写端认为 Buffer 一直是满的（读不到最新的 tail）。

4. 避坑指南：它不是原子操作！
这是最常见的误区。volatile 不能保证原子性：

volatile int64_t head 保证你读到的是内存里的值。

但如果你执行 head += 1，这依然包含“读取-修改-写回”三个步骤。如果两个进程同时执行加法，依然会产生冲突。

结论：在 Cython 的 Ring Buffer 实现中，head 和 tail 通常由单边操作（写端改 head，读端改 tail），所以只需 volatile 保证可见性即可。如果两边都要改同一个变量，则必须使用 Atomic（原子操作）

#### 2. 如何保持关联？
*   **Python 端持久化**：当 Observer 实例化并调用 `register_consumer` 得到 `i=2` 后，它必须在自己的 Python 对象属性里记录下这个 `self._consumer_id = 2`。
*   **后续调用**：此后该 Observer 调用 `get_events(self._consumer_id)`。底层 Cython 代码直接访问 `self.header.tails[2]`。

#### 3. 如果消费者崩溃了，槽位怎么回收？
这是共享内存最头疼的问题。如果消费者 `i=2` 异常退出了，`active_consumers[2]` 依然是 `True`，会导致槽位浪费，甚至导致主进程因为等待这个永远不会移动的 `tail[2]` 而永久阻塞。


# **`shared_memory.SharedMemory`**：在底层，它在 Linux / macOS 下调用的是 `shm_open()` + `ftruncate()` + `mmap(..., MAP_SHARED, ...)`。这就保证了这块内存在 OS 层面是唯一的，并且所有进程映射后的修改都能互现。
# bytearray is allocate on heaq
# 此处省略：通过 mmap 或 sysv ipc 分配 SHM，并将指针绑定到 header 和 buffer
# 此处省略 OS 级别的 mmap/shmget 内存分配

pl.read_ndjson(...)
jsonl

# macos
~/Library/Caches/pypoetry/virtualenvs

find bt_core -type f \( -name "*.so" -o -name "*.cpp" \)  -print0 | xargs -0 rm -f #  -0 --> or /  print\0 sep and xargs -0 

xargs 默认按 空格 ｜ tab ｜ 换行 分割
