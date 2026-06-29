# bt_core 性能卡点梳理与优化方案

> 范围：除 `bt_core/execution/core/finance/filler.pyx` 之外的核心模块
> 目标：识别严重性能卡点并给出优化方案，**不修改代码**

---

## 1. 关键性能卡点总览

| 优先级 | 卡点 | 主要文件 |
|--------|------|----------|
| **严重** | Indicator 每次 `next()` 全量重算 → O(N²) | `bt_core/indicators/*.py` |
| **严重** | `LineBuffer` 每次读写都重新取模 + binding 级联 | `bt_core/linebuffer.py`, `bt_core/lineseries.py` |
| **严重** | Feed / Resample 频繁构造 `datetime` 对象 | `bt_core/feed.py`, `bt_core/resamplerfilter.py` |
| **高** | Execution `Lines` 属性每次访问都分配新 NumPy 数组 | `bt_core/execution/core/finance/line.pyx` |
| **高** | Analyzer 重复拉取 snapshot / SHM events | `bt_core/strategy.py`, `bt_core/analyzers/*.py` |
| **高** | `PeriodStats` 每次都对全量收益做 mean/std → O(N²) | `bt_core/analyzers/periodstats.py` |
| **中** | Strategy 每 bar  housekeeping 存在不必要分配 | `bt_core/strategy.py` |
| **中** | `dateintern` 在热路径创建 Python datetime / timezone | `bt_core/utils/dateintern.pyx` |
| **中** | CSV / Pandas feed 逐行处理 + 重复 `getattr` | `bt_core/feeds/csvgeneric.py`, `bt_core/feeds/pandafeed.py` |
| **中** | SHM metric 逐个发布、字符串解码 | `bt_core/shm/shm_buffer.pyx`, `bt_core/sink/manager.py` |

---

## 2. 严重卡点详细说明与优化方案

### 2.1 Indicator 全量重算（O(N²)）

**代码位置**

- `bt_core/indicators/basicops.py:98-103` (`Highest`)
- `bt_core/indicators/basicops.py:123-128` (`Lowest`)
- `bt_core/indicators/basicops.py:150-155` (`FindIndexHighest`)
- `bt_core/indicators/basicops.py:177-182` (`FindIndexLowest`)
- `bt_core/indicators/sma.py:46-51`
- `bt_core/indicators/ema.py:51-57`
- `bt_core/indicators/rsi.py:69-74`

**问题描述**

每个 `next()` 都执行类似：

```python
def next(self):
    _arr = np.asarray(self.data.array, dtype=np.float64)
    sma = talib.SMA(_arr, self.p.period)
    self.line[0] = sma[-1]
```

每一步都：
1. 把不断增长的数据数组 copy/convert 成 numpy；
2. 调用 TA-Lib 跑完整段历史；
3. 分配一个完整输出数组；
4. 只取最后一个值，其余全部丢弃。

单 indicator 每 bar 复杂度为 O(N)，整体 O(N²)。多个 indicator 叠加时，这是 CPU 大头。

**优化方案**

1. **增量/递推公式**：
   - SMA：维护滚动窗口和 `window_sum`，每 bar 加新值、减旧值；
   - EMA：`ema[t] = alpha * price[t] + (1-alpha) * ema[t-1]`；
   - RSI：使用 Wilder 平滑，维护上升/下降移动平均；
   - Highest/Lowest：使用单调队列（deque）维护滑动窗口最值。
2. **如必须用向量化，改为一次性预计算**：在 `_start` / `nextstart` 阶段对输入调用一次 TA-Lib，缓存完整结果，后续 `next()` 只按索引取当前值。
3. 仅当 indicator 需要滚动窗口时，传递 `self.data.get(size=self.p.period)` 而不是整个 `self.data.array`。

---

### 2.2 `LineBuffer` 每次读写取模 + binding 级联

**代码位置**

- `bt_core/linebuffer.py:122-126` (`__getitem__`)
- `bt_core/linebuffer.py:128-139` (`__setitem__`)
- `bt_core/linebuffer.py:208-238` (`forward` / `backwards`)
- `bt_core/lineseries.py:239-295` (`Lines.forward/backwards/rewind`)

**问题描述**

```python
def __getitem__(self, ago):
    idx = self.idx % self.maxlen
    return self.array[idx + ago]

def __setitem__(self, ago, value):
    idx = self.idx % self.maxlen
    self.array[idx + ago] = value
    for binding in self.bindings:
        binding[ago] = value
```

- 每次读写都要重新算 `idx % maxlen`；
- `__setitem__` 遍历 `self.bindings`，对每个 binding 再走一次递归设置 + 取模；
- `forward` / `backwards` 在 `UnBounded` 模式下用 Python 循环逐个 `append` / `pop`；
- `Lines.forward` 对每条 line 单独循环推进。

这些操作每 bar 被 indicator、feed、strategy 调用数百万次。

**优化方案**

1. 在热循环内把 `idx = self.idx % self.maxlen` 缓存到局部变量，避免每次属性访问重复取模。
2. 减少不必要的 line binding；如必须保留，维护一个扁平的 C 级 binding 列表，或在 Cython 中统一广播写入。
3. `UnBounded` 模式下用 `array.extend([value] * size)` 或预分配 `numpy` 数组批量推进，替代 Python 循环 `append`。
4. 考虑用单一二维 `numpy` buffer  backing `Lines`，通过一次 slice/index 偏移推进所有 line。

---

### 2.3 Feed / Resample 频繁构造 `datetime` 对象

**代码位置**

- `bt_core/feed.py:226-230`
- `bt_core/resamplerfilter.py:195-200` (`_barover_days`)
- `bt_core/resamplerfilter.py:251-283` (`_barover_subdays`)
- `bt_core/resamplerfilter.py:285-324` (`_dataonedge`)
- `bt_core/resamplerfilter.py:327-382` (`_calcadjtime`)

**问题描述**

```python
# feed.py
dt = self.lines.datetime[0]
if self._tzinput:
    dtime = num2date(dt, localize=True)
    self.lines.datetime[0] = dt = date2num(dtime)

# resamplerfilter.py
_, _, day = data.num2date(self.bar.datetime).date().isocalendar()
_, _, barday = data.datetime.datetime().isocalendar()
```

- `num2date` 每调用一次都构造 Python `datetime`；
- `_barover_days`、`_barover_weeks`、`_barover_months`、`_barover_subdays`、`_calcadjtime` 反复做 `num2date`、`.date()`、`.time()`、`isocalendar()`、`replace()`、`combine()`。

Python datetime / timezone 转换本身很重，resample 每 bar 又调用多次。

**优化方案**

1. 所有边界判断都基于**数值时间戳**或整数日期部分（如 `int(datefloat)`）完成，避免先转 `datetime`。
2. 预先计算每个 session 的开始/结束为数值 timestamp，直接比较 `datetime[0]`。
3. 用整数运算替换 `isocalendar()`、`replace()`、`combine()` 链条：
   - 日/周/月/年边界可通过 `ts2intdt` 或 `get_dt_cmpkey` 风格实现。
4. 时区转换只在最终输出/展示阶段做，回测主循环保持 UTC 或内部数值。

---

## 3. 高优先级卡点详细说明与优化方案

### 3.1 Execution `Lines` 属性每次访问分配新数组

**代码位置**

- `bt_core/execution/core/finance/line.pyx:82-110`

**问题描述**

```cython
property high:
    def __get__(self):
        cdef double[:] arr = <double[:self._size]>self.high.data()
        return np.asarray(arr)
```

调用方（如 filler）每次 `lines.high[exec_loc]` 都会：创建 memoryview → `np.asarray` → 再索引。每次访问都是一次分配。

**优化方案**

1. 在 `Lines` 对象中缓存 `numpy` 数组，仅当 `_size` 变化时重新创建。
2. 暴露 C 级 `__getitem__` / `get_price(idx)`，直接索引底层 C++ `std::vector<double>`，不经过 Python 数组。
3. filler 中一次性取出所需列数组，避免循环内反复访问 property。

---

### 3.2 Analyzer 重复拉取 snapshot / SHM events

**代码位置**

- `bt_core/strategy.py:237-249` (`on_dt_over`)
- `bt_core/analyzers/periodstats.py:77-79`
- `bt_core/analyzers/drawdown.py:88`
- `bt_core/analyzers/sharpe.py:139`
- `bt_core/analyzers/timereturn.py:106`
- 其他 analyzers 的 `on_dt_over` / `notify_timer`

**问题描述**

```python
# strategy.py
def on_dt_over(self, last_dts: int, dts: int):
    snapshot = self.store.on_dt_over(...)
    ...
    for analyzer in self.analyzers:
        if hasattr(analyzer, 'on_dt_over'):
            analyzer.on_dt_over(dts)
```

每个 analyzer 的 `on_dt_over` 又独立调用 `self._owner.get_snapshot()`、独立 `get_shm_events()`。`Cerebro` 默认开启 10+ 个 analyzer（`stdstats=True`），同一条 bar 的 snapshot 被重复拉取、SHM 事件被重复遍历。

**优化方案**

1. 在 `Strategy.on_dt_over()` 中**每 bar 只拉取一次 snapshot 和一次 events batch**，作为参数传给各个 analyzer。
2. analyzer 接口新增 `on_dt_over(dt0, snapshot, events)`，旧签名保留兼容但内部复用传入数据。
3. 允许用户通过 `stdstats=False` 关闭不需要的默认 analyzers，减少注册数量。

---

### 3.3 `PeriodStats` 全量收益统计 → O(N²)

**代码位置**

- `bt_core/analyzers/periodstats.py:77-94`

**问题描述**

```python
def on_dt_over(self, dt0: int):
    ...
    self.period_returns.append(ret)
    avg_ret = np.mean(self.period_returns)
    std_ret = np.std(self.period_returns)
    pos_cnt = sum(1 for r in self.period_returns if r > 0.0)
    neg_cnt = sum(1 for r in self.period_returns if r > 0.0)
```

`period_returns` 每 period 增长一个元素，每次都要扫全量计算 mean/std/counts，总复杂度 O(N²)。

**优化方案**

1. 使用 Welford 在线算法维护 mean / variance，每 period 只更新一次。
2. 维护 `pos_cnt`、`neg_cnt`、`zero_cnt` 三个计数器，新收益到来时只比较一次并增量更新。
3. 仅在有分析输出需求时计算完整统计量，或按用户配置降低 publish 频率。

---

## 4. 中优先级卡点与优化方案

### 4.1 Strategy 每 bar housekeeping

**代码位置**

- `bt_core/strategy.py:228-235` (`clk_update`)

**问题描述**

```python
def clk_update(self):
    newdlens = np.array([len(d) for d in self.datas])
    if any(nl > l for l, nl in zip(self._dlens, newdlens)):
        self.forward()
    self.lines.datetime[0] = np.max([d.datetime[0] for d in self.datas if len(d)])
    self._dlens = newdlens
```

- 对通常只有 1~3 个 data 的系统使用 `np.array` + `np.max`，比纯 Python `max` 开销大；
- `any(...)` 配合 zip 生成器尚可，但 `_dlens` 作为状态可进一步优化。

**优化方案**

1. data 数量少时直接用 Python `max()` / 列表推导；
2. 维护一个全局最大长度变量，只有某个 data 长度变化时才更新，避免每 bar 全量计算。

---

### 4.2 `dateintern` 热路径创建 Python datetime

**代码位置**

- `bt_core/utils/dateintern.pyx:32-53` (`num2date`)

**问题描述**

```cython
cpdef object num2date(double ts, bint localize=True):
    ...
    dt_aware = py_datetime.datetime.fromtimestamp(ts, tz=UTC_TZ)
    if localize:
        return dt_aware.astimezone(SHANGHAI_TZ)
```

每次 `num2date` 都构造 `datetime` 对象并做时区转换。在 feed / resample / linebuffer 中被频繁调用。

**优化方案**

1. 时区对象 `UTC_TZ`、`SHANGHAI_TZ` 已缓存，保持现状；
2. 在热路径（resample 边界判断、feed 过滤）避免调用 `num2date`，全部使用数值 timestamp；
3. 如必须返回 datetime，考虑增加 `num2date_parts` 直接返回 `(year, month, day, hour, minute, second)` 元组，避免完整对象构造。

---

### 4.3 CSV / Pandas feed 逐行加载

**代码位置**

- `bt_core/feeds/csvgeneric.py:139-156`
- `bt_core/feeds/pandafeed.py:245-277`

**问题描述**

```python
for datafield in (x for x in self.getlinealiases() if x != 'datetime'):
    csvidx = getattr(self.params, datafield)
    line = getattr(self.lines, datafield)
    line[0] = float(float(csvfield))
```

每行都通过 `getattr` 查找 `params` / `lines`，并做字符串→浮点转换。

**优化方案**

1. 在 `start()` 中预计算 `(line_ref, column_index)` 元组列表，避免每行反射查找。
2. Pandas feed 将所需列一次性转为 numpy 数组，批量写入 `LineBuffer`，而非 `iloc` 逐行访问。
3. 数值解析使用 `np.fromiter` 或 pandas 原生类型转换，减少 Python float 构造函数调用。

---

### 4.4 SHM metric 逐个发布与字符串解码

**代码位置**

- `bt_core/shm/shm_buffer.pyx:333-354` (`publish_metric`)
- `bt_core/sink/manager.py:73-87`
- `bt_core/feed.py:375-392`
- `bt_core/strategy.py:255-266` (`notify_timer`)

**问题描述**

```python
# sink/manager.py
decode_metrics = [m.decode('utf-8').rstrip('\x00') for m in arr['metrics']]
```

每个 metric 都经过 GIL、`strncpy`、UTF-8 decode。每 bar 可能有 5+ feed metrics、indicator metrics、10+ analyzer metrics。

**优化方案**

1. 减少 metric 数量：默认只开启必要 analyzers；`notify_timer` 中 `ind_log` 按需注册。
2. 提供批量接口 `publish_metrics(metric_array, value_array, dt_array)`，一次写入共享内存。
3. metric name 使用固定长度二进制 ID 或短字节串，sink 端按 ID 查表，避免每 bar 解码大量字符串。

---

## 5. 推荐优化顺序

1. **Indicator 全量重算**：收益最大，通常占 CPU 40% 以上；
2. **`LineBuffer` 热路径**：影响所有模块，但修改面广，需充分测试；
3. **Feed / Resample datetime 对象**：减少对象分配，立竿见影；
4. **Analyzer snapshot / SHM 复用** + **PeriodStats 在线算法**：降低跨线程和重复计算开销；
5. **Execution `Lines` 数组缓存**：减少 filler 周边分配；
6. 中优先级项作为后续打磨。

---

## 6. 备注

- 以上分析仅基于静态代码阅读，未运行 profiler；实际优化前建议用 `py-spy` / `cProfile` / `line_profiler` 在真实回测上验证热点。
- 修改 `linebuffer.py` / `lineseries.py` 属于基础结构改动，需同步跑完整测试套件，防止破坏 line binding、resample、replay 等逻辑。
