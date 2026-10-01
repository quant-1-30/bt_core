# agents.md — bt_core 工程 Agent 工作指南

面向在本仓库工作的 AI/自动化 agent。架构总览见 `README.md` 与 `docs/architecture/ARCHITECTURE.md`，本文只讲**怎么安全地改这个仓库**：构建命令、关键不变量、历史踩坑、验证方法。

---

## 1. 项目一句话

A 股量化回测/仿真框架：backtrader 的 Lines/元类体系（纯 Python） + Cython 撮合账务核心（`bt_core/execution/core/finance/`） + Actor 异步执行层 + 共享内存零拷贝 IO（`bt_core/shm/`）。

## 2. 环境与构建（改任何 .pyx 后必读）

- Python venv（poetry）：`/Users/hengxinliu/Library/Caches/pypoetry/virtualenvs/bt-core-GmpHtvLH-py3.11`（下称 `$PY`）
- Cython 扩展清单由 `setup.py:get_ext_modules()` 提供（finance 全部 + timer/pnc/shm_buffer/writer_actor/interface/engine/trade_api/sizer/sink）。
- **改 .pyx/.pxd 后必须重编**，否则运行的还是旧 .so：

```bash
cd /Users/hengxinliu/startup/bt_core
$PY setup.py build_ext --inplace
```

- Cython 语法坑（都在本仓库踩过）：
  1. `cdef` 声明必须**文本位置在使用之前**（如 `cdef int32_t avail` 放到使用它的 clamp 之前），否则 C 编译错。
  2. `.pxd` 中的方法签名必须与 `.pyx` 一致，改签名两边同步改（报 `Signature not compatible`）。
  3. **cdef 方法对未类型的 Python 变量不可见**（`AttributeError`）。要测试 cdef 方法，写一个 Cython 测试模块，在函数体内 `cdef Position p` 等类型声明后调用；基类的 `def __call__`（如 `CommInfoBase.__call__`）可从 Python 直接调。
  4. 编译生成的 `.cpp` 与 `.so` 均在源码目录 in-place，不要手工编辑。

## 3. 时间表示约定（全仓库最大的坑）

两种表示混用，必须分清：

| 表示 | 含义 | 出现位置 |
|---|---|---|
| unix 秒（int64/double） | 真实时间戳（日内工作表示，保序） | Order.core.created_dt、OrderExecutionBit、Asset 上市日、EventItem、Position/Account.core.datetime（日内） |
| ymd int（如 20240105） | 交易日（结算/持久化表示） | on_dt_over 参数、Position.core.datetime（`_dt_over` 后）、Account.core.datetime（`sync` 后）、benchmark 日收益表 |

- unix → ymd（北京时间）用 `bt_core.utils.dateintern.ts2intdt`（内部 +28800 后 gmtime）。
- **ts 是日内工作表示，ymd 只在结算边界归一化一次**：`Position._dt_over` 写入 ymd（持久化前）；`Account.sync` 是唯一转换点——tick 从 simulate 传来是 ts、positions 已被 on_dt_over 归一为 ymd，ts 数值（~1.7e9）恒大于 ymd（~2e7）故 max 后单次 ts2intdt 即正确；并用 `>= 1e8` 量级守卫防止对已是 ymd 的值二次转换（ts2intdt(20240105) → 19700823）。
- **禁止**在日内路径（update/_execute）预先 ts2intdt——同日多次成交需保持严格时序。
- 跨日回调 `on_dt_over(prev_dts, cur_dts)` 两个参数都是 unix ts（cerebro 在推进 `last_dts` 前捕获 prev）；simulate 内部再 ts2intdt。`strategy.on_dt_over` 中 publish_dts 为 0 时回退 last_dts（stop() 结算最后一次）。

## 4. A 股规则实现位置（改动手册）

| 规则 | 位置 | 要点 |
|---|---|---|
| T+1 | `position.pyx`（available vs size）、`filler.pyx` 卖出 clamp | 买入当天 available=0；`on_dt_over` 解锁 |
| 手数 | `filler.pyx _round_to_lot` | 买入按 100 股整手；**零股只能在卖出最后一笔一次性卖出**（`last_fill` 参数控制） |
| 印花税/过户费/佣金 | `comminfo.pyx` | 费率带时间分界点（常量 `*_CKPT`）；5 元最低**仅佣金**；过户费 2015-08-01 前沪市按面值 0.06‰、深市免收。分项费率唯一来源是 `CommInfo_Stocks._fee_rates`（calculate/getcommission 共用，勿再复制） |
| 涨跌停硬约束 | `filler.pyx`（`_limit_fillable` bar 内在封板判定：价差 ≤1.5 tick 且 close 贴边；无昨收锚点/无板价 clamp，`limit_ratio=inf` 哨兵=不设防）+ `simulate.pyx`（`_fetch_from_rpc` 唯一 RPC 入口 + `_prev_closes[(sid,day)]` 写穿；停牌日无行 → closes_map 0.0，position.on_dt_over 走 suspend 分支保 pnl）| process_order 零 RPC（昨收不随订单传输）；封板仅 bar 内在证据，ST/北交所未建模 |
| 已实现盈亏持久化 | `position.pyx serialize`（realized_pnl 独立带出）+ `simulate._create_snapshot`（不再 pop）+ `simulate._start`（分桶恢复） | `vtposition.realized_pnl` 列（迁移 `a7b8c9d0e1f2`）；DB 语义：**pnl 列=浮动桶，realized_pnl 列=已实现桶**，而引擎快照 `PositionBody.pnl` 仍是 total（客户端契约）。修复前重启恢复 realized 归零，退市/并构会把历史已实现利润误清零 |
| 分红送转/配股 | `position.pyx _process_event` | 送转/配股按 `floor` 截断（零头不足 1 股直接舍去，"不足就是不足"）；配股现金 = -rights_size*price；成本加权；**配股缴款超过现金则整体放弃配股（`process_events(events, cash)` 滚动现金判定，同批分红先到账可认购），`Account.add_cash` 禁止 cash<0（raise）** |
| 新股涨跌幅豁免 | `asset.pyx restricted()` → `tradingcal.trading_days_between` | 按**交易日**序号（上市日=1，含第 5 日）；交易日历 = `tradingcal.DataTradingCalendar`（基准指数 Close 的 day 列驱动，`rpcfeed.get_dret` 拉到基准后 `set_calendar` 升级单例——真实节假日天然内含），无数据/窗口外自动退化到周末近似（`_weekdays_between`，与旧 asset 内联口径逐位一致）。不能用 ymd 直接相减（跨月/跨年会错），也不能用日历日差（周五上市第 5 个交易日会落在下周四） |
| 除权除息因子 | `feed.py apply_factor`（**交付式后复权，无状态**） | 历史永不回写：当根交付 bar 的累计因子 = `prod(1/r, ex_date ≤ 当根日)` **逐 bar 现算**（价格 ×scale、量 ÷scale，amount 不动自洽）——序列单一固定基准（上市日口径），**指标 `[-n]` 与 `[0]` 恒同基**，无前视（字典中的未来 ex_date 被日期过滤排除）、无需 fwd_scale/record_dt 等存储态。停牌洞天然兼容（复牌首根日期晚于洞内全部 ex_date，一次性乘洞内累计，300308 2016 停牌、20160801 十派0.1 同源）；warmup 逐 bar 同路径天然 point-in-time；**DataClone（resample）短路**——主 feed 交付 bar 已带因子，clone 复制聚合即继承，自行再乘即双重缩放。执行/账务层（filler/ref_close/涨跌停/费率）全部走 RPC **原始价**，与 feed 复权口径隔离。注意：feed 价格 = 后复权尺度，绝对价位类策略逻辑需自行换算 |

## 5. 关键不变量（违反即引入回归）

1. **`dataseries._Bar` 字段插入顺序必须与 lines 定义顺序一致**（open,high,low,close,volume,amount,datetime）——resample 通过 `lvalues()/_fromstack` zip 装配，错位会导致开收/高低互换。
2. **Timer 语义**：`repeat<=0` 的定时器每天只触发一次（`_lastcall` 守卫）；负 offset 有效（如 -10 表示收盘前 10 分钟）；`allow` 过滤器从 kwargs 透传。
3. **Cerebro 事件顺序**：日内新 bar 先判日切换（Day Rollover → `strat.on_dt_over(prev, cur)`）再跑 Scheduled Timers——保证 T+1 解锁先于当日 RISK/开仓定时器，且 `on_dt_over` 拿到的是**上一交易日**的 ymd。
4. **shm 消费者注册**：`analyzer.py dopostinit` 只给 `consumes_shm = True` 的对象注册共享内存消费者，其余 `shm_id = -1`——否则不排水消费者冻结 min_tail，卡死生产者。新增需要读 shm 的 analyzer 必须声明该类属性。
5. **analyzers 不得重名/不得 raise**：多个 analyzer 发布同名 metric 会互相覆盖（calmar/drawdown 事件已改名 `CalmarMaxDrawdown`）；order_id 未命中应 warning 跳过（历史被 merge/prune 过）而非抛异常终止整个回测。
6. **`Order.execute` 的完成判定**：按 `_exbits` 累计成交量判断 Completed/Partial，不看单笔。
7. **`Order.__reduce__` 参数顺序必须与 `__init__` 一致**（9 个参数），writer/sink 依赖 pickle。
8. **writer_actor.stop()** 先入队 sentinel 再置 `_running=False`（先置标志会与排水循环竞态丢尾数据）。
9. `linebuffer.get(idx, ago, size)` 两条分支统一窗口公式 `[idx+ago-size+1, idx+ago]`。
10. Python 3.11 兼容：`collections.abc.Iterable`（非 `collections.Iterable`）；无 `__div__`；functools.wraps。
11. **事件时序模型（经 DB 反向验证，易误读）**：主时钟是 store 的分钟 feed（`Cerebro Prepare Feed and Set Dmaster`），resample 出的日/周线是其 clone。Day Rollover 在 **D+1 首个 bar**（≥12h 间隔）触发、结算 D（prev_dts=D 最后一根 bar）→ D 的买入在 D+1 开盘解锁，T+1 恰好成立。`order_bit.executed_dt` 是**成交 bar 的戳**而非提交时刻：次晨提交的市价卖单对齐上一根已完成日 bar（戳 15:00 D、价=D 收盘）——"次开≈前收"近似。account/vtposition 的 D 行在 D+1 开盘 rollover 时写入，**不含 D+1 晨提交（戳 D 15:00）的卖单**：该行权益与真实值仅差未扣的卖佣（次行自愈），非记账错误。**T+1 解锁边界不变量**：`on_dt_over` 无条件 `available = size` 之所以精确，是因为成交与 bar 同步、end_dt=rollover 前最后一根 bar 的日子 ≥ 一切已成交买入日（勿引入按买入日记账的锁字段——曾实现过并回退，属不可达防御且维护成本高）。若未来引入异步成交/事件驱动时钟，此不变量失效，解锁逻辑必须改为按买入日判定。
12. **多标的常态化次晨盖章（2026-08 多标的闭环发现）**：`strategy.lines.datetime` 在 timer 派发时（`_check_timers` 先于 `strat._next()`）**停在前一根 bar**——隔夜即停在昨夜末根 bar。故 D+1 09:30 的 `on_risk` 卖单 created_dt 盖 D 末根 bar 的戳，filler 按戳回填到 D 的 bar 上成交。单标的低频下是罕见边角（12/2590 行次日自愈）；**多标的每日轮动下成为常态**（3 标的 14.5 年：2509 单/3483 笔全部正确，但 1061/1338 行的"盖章日视角"与真实时序错位）。DB 反向验证的重放规则：卖单 size 超过盖章日当时可卖量（T+1 使其当日不可能成交）⇒ 必为次晨卖单，推迟到 D+1 开盘前应用（见 tests/verify_event_cash.py）。重放后现金守恒 0.0000、轨迹 1334/1338 精确 + 4 行次日自愈。**回测口径注意**：这些次晨卖单的成交价取的是 D 末根 bar 价（"次开≈前收"），对高换手策略是系统性近似。

## 6. 验证方法

- 端到端冒烟：`tests/run_simulation.py`（需要 `~/startup/bt_studio/result/fsm/scores` 下含 `day/sid/fsm_score` 列的 parquet；缺文件时静默空信号、无成交）。
- **多标的端到端**（2026-08 起入库）：`tests/test_multi_instrument.py`（3 标的 300308/600000/000001、日/周/月 resample、MultiSignalPatch 按 ymd 轮动信号；FROMDATE/TODATE/RUNTAG 环境变量控制窗口与唯一性）→ `tests/verify_event_cash.py` 反向验证（默认取 client `5a1f0c9e-...` 最新实验）。前置：md-server（`cd ~/startup/rpc_feed && PYTHONPATH=. poetry venv 的 python rpc_feed/run_server.py`，端口 50051）、PG bt_trade 库、client 已注册 user_info。同配置重跑需换 RUNTAG（`uq_client_strategy_extra_info` 唯一约束，引擎不 upsert）。
- **DB 反向验证**（跑完 tests/test_strategy.py 后，`PGPASSWORD=... psql -U postgres -h localhost -d bt_trade`）：
  1. `account` 全部 datetime ∈ [19900101,21001231] 且每日唯一（`uq_acct_datetime_experiment_id` 不炸）；
  2. 逐 bit 费率恒等式（**分片线性口径**，5 元下限不作用于分片）：`comm == amt*(3e-3|5e-4 @2015-06-09) + 卖出印花(1e-3|5e-4 @2023-08-28) + 过户费(1e-5|2e-5 @分界 2022-04-29/2015-08-01；2015-08-01 前沪市按**面值** 6e-5×size、深市免收)`，容差 0.005；
  3. 现金守恒：`100000 + Σ(±px*sz) - Σcomm == account 末日 cash`，残差 = 持仓期现金分红总和 + 换股零股补偿（>0）。分红可**逐笔闭环**：用 `account` 日现金跳变（非交易日流日）独立提取每笔实付分红，应逐一等于除权日持仓 `size × bonus/10`（bonus 来自 mdapi `RpcTopic.Adjustment`，与 simulate 同源）；送转后 size = `floor(size × fl(sizer_ratio))`（浮点下 5700×fl(1.4)=7979 而非 7980，DB 实测吻合）。
  4. 买入 size % 100 == 0；`vtposition` 无 available > size。
  5. 长期停牌场景（已修复，勿回退成精确匹配）：300308 在 20160311–20160929 重组停牌，**停牌不是数据缺失**——Adjustment 表明确记录洞内 `ex_date=20160801`（十派0.1、`register_date=20160729` 停牌中名册冻结）。引擎曾按"ex_date == 下一根 bar 日"精确拉事件/匹配因子，窗口内事件被静默丢弃：现金分红不入账、若为送转/配股则仓位轨迹永久错误。现为区间语义：`simulate._fetch_from_rpc` 按 `(prev, curr]` 拉事件（复牌 rollover 补派，`_sync_event` 按 ex_date 排序）、`feed.apply_factor` 按 `(record_dt, current_dt]` 到期区间补乘因子（复牌首根 bar）。验证：结算日行 20160310 现金跳 +72.15，残差与逐笔重放完全一致。停牌期无 rollover/account/vtposition 行属正常（时钟随 bar 走）；换标的后遇长期无 bar 先对照 Adjustment 表区分"停牌"（有洞内 ex_date 行）与"真数据缺失"（什么表都没有）。
- finance/timer 行为测试：Cython 测试模块方案（见 §2.3），历史上放在 `/tmp/bt_test/_financetest.pyx`，覆盖 T+1、分红/配股账务、多笔成交状态机、pickle 往返、费率分界点、新股跨月豁免。
- 改 .py 后：`$PY -m py_compile <files>`；再逐模块 import 一遍（很多 bug 只有 import 时暴露，如缺失导入名）。
- 提交前 `git diff` 通读一遍；生成物（.cpp/.so/build/）不要提交。

## 7. 已知未修复项（改动相关模块时优先评估）

- ~~涨跌停**撮合侧**无硬约束：`asset.restricted()` 只给费率/幅度参考，filler 只用振幅启发（`_execute_factor`），一字板无法成交的场景未完全建模~~ **已修复（2026-09，按 `docs/price_limit_plan.md` 落地）**：`Asset.restricted()` 经 `process_order` 激活注入订单，撮合层对封死板拒单、板价 clamp 成交价；无价位信息时退回振幅启发式。残留：ST 5% 差异化、北交所 30%、主板新股首日 44% 未建模。
- ~~交易日历无真实节假日表~~ **部分修复（2026-09）**：`tradingcal.DataTradingCalendar` 由基准指数历史驱动（`rpcfeed.get_dret` 自动升级单例，`asset.restricted` 新股豁免已接入真实交易日计数）；`tradingcal.TradingCalendar` 本体仍是周末近似，timer/session 排程未接入数据日历——如需覆盖，用 `get_calendar()` 替换 `_nextday` 周末判定即可。
- 分红持有期个税（差别化征税）未实现。
- ~~日内 VWAP filler 用全天量归一（未来函数）~~ **已修复**：`AlgoFiller` 是完全因果无前视的逐 bar 执行调度器——TWAP 按窗口 bar 时间均分；VWAP 以**窗口内已实现量为量钟**（跟量、缺口自动追赶），唯一事前标量 Ŝ=trailing 历史交易日同时段真实量均值（`_ensure_window_volume` RPC 拉取，数据驱动，**无硬编码 U 型先验曲线**；`seed_window_volume` 钩子供测试/确定性重放；无历史时降级 TWAP）。逐 bar 施加真实成交量与 impact 参与率硬约束、自动滚入追赶补齐（catch-up），严格遵循 A 股整手买入与卖出零股规则。sizing 契约：`sizer_ratio` 恒为 **<1.0 的比例**——买入=现金比例（预算=ratio×cash 按每手成本折手数，floor，绝不透支），卖出=可卖比例（1.0=全部可卖）；`calculate` 为唯一换算点，sizer.getsizing 返回的就是该比例。
- 科创板最小价差 200 股/ tick 近似。
- `publish_metric` 多生产者递增非原子（当前单生产者架构下无害）。
- merger（吸收合并）在 positions 侧换股保留仓位（`size×ratio` 截断）；**换股零股现金补偿**：不足 1 股部分折现金（补偿价取旧收盘、停牌按成本；`cost_basis=cost/ratio` 成本守恒），comp 经 `on_dt_over` 返回值上抛、simulate 注入 account cash（勿回退成"只清仓不记账"或"全损失"）；**幂等**：simulate 换 key 时刷新为新 sid 的 asset + `_dt_over` 的 `sid==merger` 守卫双保险（否则旧 asset 滞留导致每日重复换股+重复补偿）；换股当日 closes_map 以旧收盘/换股比平移到新 sid（市值守恒近似，次日自愈）；零仓壳标记 dirty 次日 `_clean` 回收；sqn analyzer 仍按全部损失处理。
- 多 data feed 的 bar 对齐（cerebro）未严格按时间戳归并。

## 8. 提交约定

- 分支：日常开发 `dev`，PR 目标 `main`。
- Bug 修复附简短说明；系统性修复写 `docs/bugfixes/<topic>.md`（已有先例：consecutive_run_deadlock、fix_analyzers 等）。
- 不要在代码里留调试 print（历史清理过一轮：cerebro/_dispatch、strategy.stop、btbroker 等）。
