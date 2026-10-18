# C 版 DDR PHY 复位与停钟窗口审计

此证据只解释 IP 初始化复位为何不能按持续运行的 400 MHz 时钟分析；它不是 DDR 芯片、电气时序或上板校准验证。

复现命令：

```powershell
python scripts/audit_ddr_reset_sequence.py --output docs/evidence/ddr_reset_sequence.json
```

脚本读取硬件资料目录中的原始 `ddr_memory_test_uart/src/ddr3_memory_interface/ddr3_memory_interface.vo`，不复制原厂库。它校验当前工程的加密 `.v` 与该 `.vo` 同目录的 `.v` 字节相同，并限制为已审计的 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| 参考 `.vo` | `0a21efa69eab7d8b9912bb6aaf880ad35de00d562cc451587c11bd3c002ed17b` |
| 当前工程及参考加密 `.v` | `4a6e26d2ccb8d01221103df4cdf71f3517d2700614020e0c414aafec04a495bc` |

两文件来自同一 C 版 IP 生成目录，`.v` 标注 IP 6.0 / Gowin 1.9.12.02_SP1 / 2026-04-03 17:30:28，`.vo` 标注 17:30:29。任何相关文件改变，都应重新审计后才能继续引用此证据。

## 方法与结果

对原始 `ddr_sync` 的全部 LUT/FF，以及 `ddr_rsti_reg[2:0]`、`stop_reg[2:0]` 和必要反相器，共 108 个单元逐周期求值。LUT 使用原始 INIT 真值表；DFFCE 的异步 CLEAR、DFFPE 的异步 PRESET、DFFSE 的同步 SET 按安装目录 `IDE/simlib/gw5a/prim_sim.v` 的公开行为模型实现。所有控制 FF 使用 50 MHz 时钟。

初始化及 `sys_reset` 重校准的有效复位窗口均如下，表中周期零点是 `pll_stop` 变低的边沿：

| 相对周期 | 相对时间 | 行为 |
| --- | --- | --- |
| 0 | 0 ns | `pll_stop=0`，关闭 PLL CLKOUT2 / memory_clk |
| 4 | 80 ns | `ddr_rst=1` |
| 8 | 160 ns | `ddr_rst=0` |
| 12 | 240 ns | `pll_stop=1`，恢复 memory_clk |

因此有效复位释放后到第一个恢复的 memory_clk 边沿之间，有约 80 ns 控制窗口。2026-09-08 第一次优化布局的复位数据布线约 3.3 ns，不能用自由运行 400 MHz 时钟的相邻半周期 1.25 ns 要求替代此实际停钟序列。

此行为与 IPUG281-2.6 §4.4.4 一致：138K 的 `pll_stop` 低有效，直接连接 PLL `enclk2`。工程 `ddr3_platform.v` 保留此连接。只有在该连接、400 MHz 时钟源及复位管线保持不变时，才能引用此窗口。

## 精确约束边界

可据此对 **`ddr_rsti_reg_2_s0/Q` 发往此 DDR IP 内初始化 RESET/CLEAR 端点** 的 recovery/removal 分析应用精确例外。它不授权对 DDR 时钟组整体设置 false path，也不授权豁免 WLOADN、CALIB 后续同步级、DQ/DQS 数据或任何正常命令路径。平台自身和其它模块的复位分发应保留独立分析。

上电及外部 `rst_n` 复位过程中，在 PLL 初始化阶段还会有一次较早的 `ddr_rst` 释放；它随后被上述完整停钟复位覆盖。工程必须等待真正 `init_calib_complete` 后才能使用 DDR 原生命令和返回数据；当前平台已按此门控。

四种审计情形为上电、`sys_reset` 重校准、外部 `rst_n` 复位及短暂 PLL 失锁。**原 IP 的短暂 `pll_lock` 丢失本身不会重新发出上述完整复位序列**，因此失锁后的重新 LOCK 不能视作重新完成 DDR 校准。工程已增加 `ddr_recovery_guard`，在校准后的失锁事件触发完整初始化，见 [平台恢复行为](../ddr_platform_notes.md#工作中失锁的恢复)。这与正常初始化路径的时序例外是两个独立问题；本脚本仍保持只审计原厂 IP 控制逻辑。

脚本验证的是理想离散逻辑控制序列；停钟硬块的最大传播时间、异常电源情况及真实 DDR 读写仍需官方硬块时序和板上测试确认。
