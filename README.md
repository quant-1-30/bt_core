## 1. 项目概述

`bt_core` 是一个量化回测与仿真交易框架，当前版本 `0.4.1`。

- **定位**：基于 [backtrader](https://www.backtrader.com/) 的 Lines/元类架构进行重构，剥离 broker、feed、store、trade 等核心模块，并将回测逻辑针对 A 股 T+1 交易规则重新实现。
- **运行模式**：统一支持**历史回测**与**在线仿真交易**。通过 `Cerebro` 编排数据流、策略、指标、观察器与分析器；通过 `Store` 单例封装行情（`MdApi`）与交易（`TdApi`）接口。
- **协议依赖**：交易协议层复用 `bt_sdk` / `bt_protocol`，网络层使用 gRPC / Protobuf。
- **性能优化**：关键路径（仓位/现金控制器 `Pnc`、行情 Sink、共享内存缓冲区、日期转换等）使用 **Cython** 编写并编译为 C++ 扩展。

---

## 2. 技术栈

| 类别 | 主要技术 |
|------|----------|
| 语言 | Python 3.11+（`pyproject.toml` 声明 `>=3.11,<3.15`） |
| 包管理 | Poetry 1.8+（`pyproject.toml` + `poetry.lock`） |
| 包源 | 主源 Tsinghua PyPI（`tuna`），补充源 `devpi`（`http://localhost:3141/bt_sdk/dev/+simple/`） |
| 编译构建 | Cython 3.0+、setuptools、numpy、pybind11、CMake、wheel |
| 数值/科学计算 | numpy、scipy、numba、pandas、polars、pyarrow、patsy、ta-lib |
| 数据存储/IO | Parquet、PyArrow、SQLAlchemy、asyncpg、joblib、cloudpickle |
| 可视化 | matplotlib、bokeh |
| 协议/网络 | grpcio、protobuf、httpx、reactivex |
| 日志/性能 | memray、py-spy、snakeviz、line-profiler |
| 外部量化 SDK | `bt-sdk==0.14.3`、`bt-protocol>=0.2.0` |

---

## 3. 目录与模块组织

```
bt_core/
├── __init__.py              # 公共 API 统一导出
├── _version.py              # 版本信息
├── cerebro.py               # 回测引擎主控（Cerebro）
├── strategy.py              # 策略基类（Strategy / SignalStrategy）
├── signal.py                # 信号类型定义
├── feed.py                  # 数据馈送抽象基类（AbstractDataBase）
├── dataseries.py            # DataSeries / OHLC / TimeFrame / _Bar
├── resamplerfilter.py       # 数据重采样/回放（Resampler）
├── linebuffer.py            # LineBuffer 核心数值缓冲区
├── lineroot.py              # LineRoot / LineSingle / LineMultiple
├── lineseries.py            # LineSeries / Lines / LineAlias
├── lineiterator.py          # LineIterator / IndicatorBase / ObserverBase / StrategyBase
├── indicator.py             # Indicator 元类与基类
├── observer.py              # Observer 元类与基类
├── analyzer.py              # Analyzer 元类与基类
├── broker.py                # BrokerBase 抽象基类
├── store.py                 # Store 元类与基类（Singleton）
├── sizer.py                 # Sizer 基类
├── pnc.pyx / pnc.pxd        # Cython 仓位/现金/风控控制器
├── timer.pyx / timer.pxd    # Cython 定时器
├── tradingcal.py            # 交易日历
├── writer.py                # 结果输出（WriterFile）
├── optimizer.py             # 参数优化器
├── log.py                   # 日志
├── errors.py                # 异常定义
├── metabase.py              # 元类基础设施
├── flt.py / logic.py        # 过滤器辅助 / Lines 运算逻辑
│
├── analyzers/               # 内置分析器（Sharpe、DrawDown、TradeAnalyzer、SQN ...）
├── brokers/                 # 经纪商实现（BTBroker、IBBroker、OandaBroker ...）
├── feeds/                   # 具体数据源（ParquetData、RPCFeed、PandasFeed、CSV ...）
├── filters/                 # 数据过滤器（Session、CalendarDays ...）
├── indicators/              # 技术指标库（SMA、EMA、MACD、ATR、RSI、Bollinger ...）
├── observers/               # 观察器库（Broker、BuySell、Trades、DrawDown ...）
├── sizers/                  # Sizer 实现（FixedSize、WeightedSizer、TurtleSizer、KellySizer）
├── stores/                  # Store 实现（LocalStore / IBStore / OandaStore）
├── control/                 # Cython 风控/仓位模块
├── execution/               # 执行层（与 bt_sdk 交互）
│   ├── actor/               # Actor 模型（BatchWriterActor）
│   ├── gateway/             # 网关抽象
│   ├── core/                # 核心金融/引擎抽象
│   └── trade_api.pyx        # 交易 API（TdApi）
├── shm/                     # 共享内存环形缓冲区（Cython）
├── sink/                    # 日志/数据消费线程与 Cython Sink
└── utils/                   # 通用工具（日期转换、AutoDict、编码器、装饰器）
```

---

## 4. 架构要点

### 4.1 元类驱动参数系统

- 所有可配置类通过 `params = (('name', default), ...)` 声明参数。
- `metabase.py` 中的 `MetaParams` 元类在实例化时将 kwargs 绑定到 `self.p`。
- 类创建时自动注册子类（`MetaStrategy`、`MetaIndicator`、`MetaObserver` 等）。

### 4.2 Lines 时间序列抽象

- `LineBuffer` 是核心数值缓冲区，索引语义：
  - `line[0]` = 当前 bar 值
  - `line[-1]` = 上一 bar 值
  - `line[1]` = 未来值（若已 extend）
- 支持 `forward()`、`advance()`、`qbuffer()` 控制内存与指针移动。

### 4.3 运行时调用链路（简化）

```
Cerebro.run()
  ├── 数据准备：data._start() → feed._prepare()
  ├── 策略实例化：runstrategies()
  │     ├── 注册默认 Observers（Broker、Trades、BuySell、DrawDown ...）
  │     ├── strat._start() → 设置资金、计算 minperiod
  │     └── writer.start()
  └── 主循环 _runnext()
        ├── 对每个 data 调用 next() 加载新 bar
        ├── _check_timers() → notify_timer() → store.on_dt_over() 日终结算
        └── 对每个 strategy 调用 _next()
              ├── 级联调用 indicator._next()
              ├── 调用 observer / analyzer
              └── 调用用户 next() / nextstart() / prenext()
```

### 4.4 Store-Broker 解耦

- `LocalStore`（单例）统一封装行情 `MdApi` 与交易 `TdApi`，并启动异步事件循环。
- `BTBroker` 只做协议转换，调用 `tdapi.submit()` / `tdapi.on_dt_over()` 等。
- 订单流：`Strategy.buy/sell()` → `OrderBody` → `Store.submit()` → `Broker.submit()` → `TdApi.submit()` → 返回 `SnapshotBody`。

### 4.5 风控与仓位（Pnc）

- `control/pnc.pyx` 是 Cython 实现的高频仓位/现金控制器。
- 职责：硬止损（`p_tolerance` / `act_tolerance`）、止盈止损、锁仓（`lock_days`）、先卖后买、调用 Sizer 计算目标权重。

---

## 5. 构建与安装命令

### 5.1 环境准备

项目使用 Poetry 管理虚拟环境。推荐 Python 版本 3.11.x。

```bash
# 安装依赖并创建虚拟环境（如不存在）
poetry install --no-root

# 或安装本项目自身作为包
poetry install
```

> 注意：`bt-sdk`、`bt-protocol` 等包可能只存在于项目配置的 `devpi` 私有源（默认 `localhost:3141`），本地开发前请确保该源可访问或已配置替代源。

### 5.2 编译 Cython 扩展

Cython 扩展通过 `build_ext.py` / `setup.py` 定义，`pyproject.toml` 中指定 `build = "build_ext.py"`。

```bash
# 方式 1：使用 Poetry 构建 wheel（会触发 build_ext.py）
poetry build

# 方式 2：本地原地编译扩展（开发调试常用）
python setup.py build_ext --inplace

# 方式 3：直接生成扩展模块信息
python build_ext.py
```

构建产物：

- `.cpp` 中间文件（`build/` 及源码目录，已被 `.gitignore` 忽略）
- `.so` / `.pyd` 动态链接库（已被 `.gitignore` 忽略）
- `dist/` 目录下的 wheel / sdist

### 5.3 Docker 构建

```bash
docker build -t bt_core .
```

`Dockerfile` 基于 `python:3.11.5-slim`，安装 `build-essential`、Poetry，并设置 `virtualenvs.create false`。

---

## 6. 测试策略与运行方式

### 6.1 测试组织

- 项目位于 `tests/` 目录。
- 当前没有 `pytest.ini`、`tox.ini` 或 `conftest.py`。
- 测试文件本质上是**可执行脚本**，入口在 `if __name__ == '__main__':` 中。

### 6.2 主要测试文件

| 文件 | 说明 |
|------|------|
| `tests/test_strategy.py` | 基础策略运行示例，展示 Cerebro、Store、PNC、Timer、Resample 用法 |
| `tests/test_signal.py` | 多信号策略示例（WeekPriceSignal、MACDSignal、VolSignal、DrawDownSignal 等） |
| `tests/test_resample.py` | 日/周/月/年级别重采样测试 |
| `tests/test_plot.py` | 基于 Bokeh 的结果可视化 |
| `tests/experiment/run_simulation.py` | FSM 策略实验脚本，使用 polars 读取 parquet 面板数据 |

### 6.3 运行测试

```bash
# 进入项目虚拟环境
poetry shell

# 运行单个脚本
python tests/test_strategy.py
python tests/test_signal.py
python tests/test_resample.py
```

> 运行测试前通常需要 `load_dotenv()` 读取 `.env` 文件，并确保本地 devpi 源及行情/交易服务可用。多数测试脚本会连接 `LocalStore` → `bt_sdk` 的 `MdApi` / `TdApi`，在缺少服务时会报错。

---

## 7. 代码风格与开发约定

### 7.1 文件头

几乎每个 `.py` 文件顶部都包含统一的 backtrader GPL v3 版权头：

```python
#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# ...
#
###############################################################################
```

新增模块时建议保持相同风格。

### 7.2 命名与格式

- 缩进：4 个空格。
- 类名：`CamelCase`（`Cerebro`、`LocalStore`、`FixedSize`）。
- 函数/变量：`snake_case`。
- 私有成员：以 `_` 开头。
- 类参数：通过 `params = (("name", default), ...)` 声明；实例化后通过 `self.p.name` 访问。

### 7.3 注释与文档

- 代码注释混合中文与英文，核心算法注释多为中文。
- 公共类/方法使用 Google / backtrader 风格的文档字符串。
- Cython 文件（`.pyx`）中常见编译优化相关中文注释，例如 `language_level`、`boundscheck`、`wraparound`。

### 7.4 Cython 扩展约定

- `.pyx` 源码与 `.pxd` 声明文件成对出现。
- 编译选项统一使用 `-O3 -std=c++11`，`language="c++"`。
- `compiler_directives` 关闭边界检查以提升性能（生产环境需谨慎）：
  - `boundscheck=False`
  - `wraparound=False`
  - `initializedcheck=False`
  - `cdivision=True`

---

## 8. 部署说明

- `deploy.sh`：Poetry 环境检查/安装脚本，同时创建日志文件 `/var/log/bt_core.*.log`。
- `Dockerfile`：容器化部署入口，构建后通过 `poetry install` 安装。
- 发布包：当前 `dist/` 下已有 `bt_core-0.4.1-cp311-cp311-macosx_26_0_arm64.whl` 与源码包。

---

## 9. 安全与注意事项

1. **私有 PyPI 源**：`pyproject.toml` 配置了 `devpi` 源（默认指向 `localhost:3141`），在 CI/其他机器上需要替换为可用的内网地址。
2. **`.env` 文件**：项目使用 `python-dotenv` 读取环境变量；`.env` 文件包含敏感配置，已加入 `.gitignore`，请勿提交。
3. **Cython 编译安全**：`boundscheck=False` / `wraparound=False` / `cdivision=True` 会跳过运行期检查，修改 Cython 代码时务必保证索引与除法安全。
4. ** grpc / 网络**：`bt_protocol` 与 `bt_sdk` 依赖 gRPC 通信，本地测试需启动对应服务。
5. **资金管理**：`Pnc` 与 `Sizer` 直接控制真实/仿真账户的资金与仓位，修改相关逻辑前务必充分回测。

---

## 10. 常用扩展点

| 扩展目标 | 继承/实现 |
|----------|-----------|
| 自定义策略 | `class MyStrategy(bt.Strategy)`，重写 `next()` |
| 自定义指标 | `class MyInd(bt.Indicator)`，重写 `next()` |
| 自定义 Observer | `class MyObs(bt.Observer)`，重写 `next()` |
| 自定义 Analyzer | `class MyAna(bt.Analyzer)`，重写 `next()` / `get_analysis()` |
| 自定义 Sizer | `class MySizer(bt.Sizer)`，重写 `_getsizing()` |
| 自定义数据源 | `class MyFeed(bt.feed.DataBase)`，重写 `_load()` |
| 自定义 Broker | 继承 `bt.BrokerBase` |
| 自定义 Store | 继承 `bt.Store`，重写数据与交易连接 |

---

## 11. 关键配置文件速查

| 文件 | 作用 |
|------|------|
| `pyproject.toml` | Poetry 项目元数据、依赖、包源、构建后端配置 |
| `poetry.lock` | 依赖锁定文件 |
| `setup.py` | Cython 扩展模块定义，也支持独立 `python setup.py build_ext --inplace` |
| `build_ext.py` | Poetry 构建钩子，调用 `setup.get_ext_modules()` |
| `MANIFEST.in` | 指定发布包包含的额外文件（README、LICENSE、CHANGELOG） |
| `Dockerfile` | 容器构建 |
| `deploy.sh` | 部署/环境初始化脚本 |
| `.gitignore` | 忽略编译产物、虚拟环境、日志、Parquet、.env 等 |
| `ARCHITECTURE.md` | 详细架构文档（中文） |
| `README.md` | 核心架构设计说明（中文） |
| `CHANGELOG.md` | 版本变更记录 |
