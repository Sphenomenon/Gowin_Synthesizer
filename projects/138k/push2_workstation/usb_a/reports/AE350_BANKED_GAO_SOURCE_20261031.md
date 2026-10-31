# AE350 banked GAO：显式源码候选

日期：2026-10-31。范围：独立 local-memory probe 的源码、Icarus 仿真、固件编译和 prepare；没有综合、P&R、JTAG、SRAM 或 Flash 操作。C11 的 2208-bit full64 物理候选仍独立保留，本报告不将其判为失败，也不提升本候选的硬件状态。

## 目的与选择

为完整 64-word 快照提供可选的较窄 GAO 输入，供后续独立比较资源和布线。`build.py --ae350-local-memory-probe --prepare-only --ae350-probe-gao banked4` 才启用新模式；不传此选项仍为原来的 full64，GAO schema `A1386401`、2208 bits、深度 128。两种模式都不改变 UART、RTC、loader、固件、引脚、电气条件或 PLL/时钟约束。

banked4 使用 `AE350_PROBE_BANKED_GAO` 显式宏，GAO schema 为 `A1386402`、704 bits、深度 128；`workstation_ae350_probe_gao_banks.sv` 只处理已经位于 50 MHz 域的原子 UART 发布快照，不增加 CDC 或 PRESET 握手。最终 `status_50mhz` 仍是保留的实际 50 MHz 寄存器；物理阶段必须使用 `audit_gao_synthesis(..., gao_mode='banked4')` 检查实际综合网表的全部 704 bits，再检查 routed timing、CDC 和 PLL。

## 页契约

每个 32-bit word 的低位在低总线位；各页固定停留 4 个 50 MHz 周期，页号 0→1→2→3→0。顶层再寄存一级，仅增加一周期观察延迟。

| Word | banked4 内容 |
|---|---|
| 0–15 | 当前页的 16 个诊断 word；页 p 对应诊断 word 16p…16p+15 |
| 16 | 原始 UART 发布序列号 |
| 17 | 该候选 UserCode |
| 18 | `0xA1386402` |
| 19 | `{8'd4,8'd64,8'd16,5'd0,published,page[1:0]}` |
| 20 | 与新序列一起冻结的 `{TX边沿计数[29:0],published,TX输出驱动}` |
| 21 | 与新序列一起冻结的平台健康字 |

只有页3→页0边界能替换整个 2080-bit 快照、IO 与健康字，条件为 UART 已发布，且首次有效或序列号改变。重复扫同一序列时，即使 TX、边沿数和平台健康持续变化，所有页的 payload 与冻结元数据也逐位相同。公共 transport reset 清空该 bank；PRESET 不会清空它或伪造 UART ack。实际 TX/health 的冻结值只描述那个序列被 bank 接纳时的数字逻辑状态，不证明 pad 电压或外部 UART 收到了字节。

`tools/decode_ae350_banked_gao.py` 要求精确 704-bit CSV 列、packed/逐位一致、正确 UserCode/schema/页几何、按顺序的完整四页和每页至少两个相同样本。相同序列中任何页内容或冻结元数据改变都会失败；新序列不完整时也失败，不回退宣称旧序列是最新。未知样本打断未完成页组；明确 unpublished 和顶层精确全零 reset 样本分隔 reset context，不能跨 reset 拼页。除全零 reset 外，错误 magic 均失败。已完成同序列扫描后的额外局部扫描不撤销那份已证明快照。它沿用 full64 的诊断评估，诊断 word61 timeout 位继续否决 freshness；GAO 不拥有 UART CRC 证明。

## 离线验证

- `sim/test_ae350_banked_gao.py`：8 项通过。包括全部64字重建、重复页、缺首/中/末页、单样本页、未知间隙、新序列不完整、跨序列回返、复位隔离、timeout、身份/几何/位序错误、legacy544/full2208拒绝、实际704-bit顶层及DAC固定安全驱动。
- 实际 bank RTL 中，UART 序列远慢于页扫描，源字、IO、健康字持续变化；验证同序列不更新、恰好页边界更新和公共 reset。
- 实际异步 UART RTL（pclk周期14、参考周期20）经 banks 和顶层同形寄存器捕获后导出 CSV；normal、PRESET pending、timeout recovery、common reset 四种模式各3个 CRC-valid UART 帧，与 GAO 重建的所有64字及原始序列精确一致。旧的 PRESET-reset ack mutant 在相同刺激下因 forged ack 正确失败。CRC 只证明这些离线 UART 字节，不转移为真实板上 UART 证据。
- 原 `sim/test_ae350_full_gao.py` 5 项、`sim/test_ae350_local_probe.py` 9 项与 `sim/test_current_workstation_sources.py` 17 项通过；默认 full64 GAO XML 与 C11 对同一 UserCode 逐字相同。
- 两种模式使用同一 xPack GCC 15.2.0 编译并 prepare。ELF、BIN、boot.mem 和5份固件源码与 C11 prepare-v11 逐字节相同；UART、RTC、boot-memory 源码也相同。ELF SHA256 `825cf6713e13be6542579d368388642dfe1cc67c111b7b3cdb56d09186a8df64`，BIN `d1bbb2cf9347dadd6c013d1bb77a6603c10ee7847c3e0054354a9dfcbdd92907`，ROM `6afca3a2ceb76d791ab208de8bfd4746ae747674049db82bc5a69b4c9bed8feb`。
- prepare audit 拒绝缺失显式宏、错误页几何、错误 GAO bit 和删去 banks 源码；宏/GAO/TCL 攻击即使刷新直接输入哈希也失败。

外部封存位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-banked-gao-delivery-v1`，含两种 prepare、C11参考副本、实际仿真原始日志/UART/CSV/decoded、测试日志和可重新验证的封存清单。离线 UserCode `00006403`（banked4）与 `00006404`（full64）仅用于源码验证，不是部署身份。

## 后续门禁与回退

该变体是否减少实际 GAO 路由成本仍未知，可能增加页mux、冻结寄存器和控制逻辑；源码通过不能替代 EDA。后续若选择实现，应分配全新部署 UserCode、重新 prepare、锁定所有输入，执行综合网表绑定、资源、PLL、CDC、routed timing 后，再由主任务按既有授权决定 SRAM 与独立读回。Flash 没有变化。回退是保留并选择已封存的 C11/full64 候选；不覆盖、重命名或复用它的身份和输入。
