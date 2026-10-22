# 行为测试（A 股撮合/账务/指标/缓存回归安全网）

锁住全库核心不变量与生产加固契约（见 `agents.md` §4~§7）。
**改动 `bt_core/execution/`、`bt_core/indicators/`、`pnc.pyx`、`shm/`、`timer.pyx`、`feed.py`、`linebuffer.py` 后必须运行本目录。**

## 运行

```bash
$PY -m pytest tests/behavior -q
```

首次运行或 `.pxd`/`.pyx`/`.so` 更新后，`_extbuild.py` 会自动重编 `_finance_behavior.pyx`。

## 覆盖矩阵

| 文件 | 锁定的核心行为 |
|---|---|
| `_finance_behavior.pyx` + `test_finance.py` | T+1 锁定/解锁/超卖 raise、日内 unix ts 与日终 ymd 归一、分红送转/配股/滚动现金判定/零股 `floor`、退市全损与重启分桶持久化、吸并换股+零股现金补偿+幂等守卫、**停牌日 `Account.sync` 保市值**、订单累计成交量状态机与 pickle 往返、`Asset.restricted`（科创/创业/北交 30%/全面注册制主板新股/核准制首日 44%/主板及旧制创业板 ST 5%/跨周末豁免）、Filler 显式卖出 clamp、std 封板拒单、**单边急拉流动性折减 $\gamma_{\text{liq}}$**、**限价单未穿透排队折减 $\gamma_{\text{queue}}$（含 IEEE-754 1-tick 容差）**、**`AssetCache` 负缓存与未知 `sid` 优雅拒单**、Timer `tzdata` 契约 |
| `test_comminfo.py` | 费率四分界恒等式（佣金 3‰→0.5‰@2015-06-09、印花 1‰→0.5‰@2023-08-28、过户费三分界、2015-08-01 前沪市面值 0.06‰×size 与深市免收）、5 元最低仅适用佣金 |
| `test_timer.py` | `repeat<=0` 每日一次、负 offset、allow 过滤器、日内 repeat |
| `test_feed_factor.py` | 交付式无状态后复权 `prod(1/r, ex_date <= D)`、停牌窗口复合、**`DataClone` 短路且自算 `adj_scale` / `to_raw_price()`**、**`ParquetPatch`/`SignalPatch` 别名 + 三维特征字典下发 + `lag=1` 防前视与防空信号日陈旧复用** |
| `test_linebuffer.py` | `UnBounded` 与 `QBuffer` 环形 `get(ago, size)` 窗口公式、`reset` 索引复位 |
| `test_indicators_pnc_shm.py` | **27 个增量指标在 `UnBounded` 与 `QBuffer` 环形回绕双模式下与 TA-Lib 逐位对齐**、`Strategy._getminperstatus` 被动 feed 排除、`PeriodStats` Welford 在线统计、`Pnc` 部分卖出意图跟踪与 0 股截断死循环守卫、`SharedRingBuffer.unregister_consumer` 与 `LogRingBuffer.release_consumer` 解除自旋死锁、`BatchWriterActor.reset` 多轮执行、`Cerebro(watchdog=...)` 参数化 |
