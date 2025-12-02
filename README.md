# 核心架构设计
    项目基于backtrader重构， 核心从两个维度 a. broker feed store trade 核心模块剥离 ; b. 回测逻辑由 T+1 基于A股市场交易策略rewrite。主体backtest 负责 indicator 与 strategy 构建，
    构建方式基于type元类 构建框架类，抽象具体实现细节，具体可以深入backtrader metabase 源码了解细节。关于 feed 与 broker 集成方式， 借鉴xtp系统 mdapi / tdapi 构建sdk 集成到backtest。 

```mermaid

graph Backtest
    rpc_feed

```

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

    bar2edge  adjbartime  rightedge boundoff

    resample 
    replay 含义举例 重建4小时数据(next 推进，数据是更新的, 需要将数据保存在stash中)

    2>/dev/null --- 0 1 2
