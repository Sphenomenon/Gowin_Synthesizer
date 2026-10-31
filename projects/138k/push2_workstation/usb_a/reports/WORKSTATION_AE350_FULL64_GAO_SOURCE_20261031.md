# AE350 完整 64-word GAO 观测来源阶段

2026-10-31，独立基线 `75e9233`，保留已修正的 RTC 和 `PLL_R[0]` 约束。
本阶段只读旧证据、修改独立源码、prepare、编译固件和运行仿真；没有运行 Gowin EDA、操作板卡或 push。
机器记录见 `workstation_task_20261030/ae350_full64_gao_source.json`。

## 旧观测的实际范围

核对的是 C10 `C21031CC` 的实际综合网表 SHA256
`293ed42abaddafcdb15ca00b7b2d7530b928a5a1de8812347d391d0ca3a9da55`。
它有 544 个顶层 `status_50mhz` 寄存器；原 GAO 定义只采这些位，
其中 512 位是 16 个软件摘要。不能用它补全 cache CSR、计数器 delta 和内存 pattern 检查计数。

实际网表中的 `u_uart/tx_s1` 是 50 MHz DFFPE，其 Q 通过 `debug_uart_tx_d`
接 `debug_uart_tx_obuf`，最终驱动顶层 `debug_uart_tx`；CST 的 U15 来自
`unchanged_locked_core`。这条链是维护的 PL 串行器。
官方 MUG1031 v1.3.1 PDF 第 27 页列出的是硬核外设 UART1/2_TXD；
锁定 wrapper 也把它们置于各自条件端口中，C10 config 未定义相应 UART enable。
这些资料没有把 U15 映射到 Mac 的 `/dev/cu.usbserial-21201`。
旧采集 0 bytes 可以确认该次主机读取没有数据，不能推出 CPU 未运行或 PL TX 未翻转。

## 新观测结构

沿用现有 APB→50 MHz request/ack、保持数据总线和 settle 窗口，
在与 UART 帧相同的 publish 点同时锁存 64 字 bank 和序号。
顶层仍用真实、保留的 50 MHz 寄存器供 GAO 采集，宽度改为 2,208 位，深度仍为 128：

| 32-bit 字索引 | 内容 |
|---|---|
| 0–63 | 完整已发布 transport bank；与同序号 UART 帧一致 |
| 64 | bank/frame sequence |
| 65 | 声明的设计 UserCode；不能替代独立 JTAG 身份读回 |
| 66 | 格式标志 `0xa1386401` |
| 67 | bit0 UART 输出驱动电平，bit1 已发布，bits31:2 为 30-bit 翻转计数 |
| 68 | 原 32-bit 平台 live health |

bank 的 0–57 字是固件写入的报告，58/59 字是 PL 同步的 ROM/外部访问标志，
61 字是 transport flags/timeout，60/62/63 保留。
IO 字是片内数字输出驱动观测，随当前 50 MHz 采样更新；它没有 pad 回读或外接串口接收证据。
live IO/health 与固件 bank 的采样时刻不同，在输出 JSON 中明确分开。

局部 APB reset 原先会把 ack 清零。当 request=0 尚待确认而 ack=1 时，
这会产生伪确认，并改变正在跨域保持的 bank。现在源、目标握手状态只随共同 transport reset 复位；
局部 `preset_n` 只暂停新捕获，保留 ack 和 held bank。超时继续保留旧 bank，
word61 bit4 明确置位；不会把重传旧数据当作新鲜本地存储或计数器通过。
新增信号全部在 50 MHz 域内，不新增逐位跨域拼接，也未放宽 SDC。

`tools/decode_ae350_probe_gao.py` 严格检查完整列名/位序、packed 与逐位值、格式标志，
并拒绝同序号 bank 内容变化。它保留全部 64 字，重用现有诊断判断，
对 timeout、未发布或身份不符的 bank 撤销当前计数器通过资格；没有构造或声称捕获 UART CRC。

```sh
python3 tools/decode_ae350_probe_gao.py --input capture.csv --manifest inputs.json --output observation.json
```

`audit_prepare` 独立核对生成 GAO 的完整 schema，即使输入清单里的 hash 被刷新也拒绝位列漂移。
新增 `audit_gao_synthesis(vg_text)` 供主代理对新实际综合网表检查 2,208 位均由 50 MHz 寄存器驱动。
旧 C10 实际网表已被此门禁拒绝；新实际网表尚未生成，不能宣称已经通过。

## 实际校验和后续边界

27 项针对性检查通过：完整 GAO 新测试 5、原 probe 所属边界测试 5、accepted 来源 17。
异步 RTL 用每个 pclk 都变化的 64 字数据，核对正常、局部 reset pending、timeout→恢复场景，
逐字比对三个实际 CRC-valid UART 帧与各自的完整发布 bank。
恢复旧 reset 行为的实际 RTL mutant 在伪 ack 断言处失败。
生成固件的严格指令模型完成真实 CRC/pattern/counter 测试，其全部诊断字可通过新解码器判断。
负例覆盖旧 544 位、缺列/错序、packed 不符、错误 magic、同序号修改第 55 字、
timeout 保留旧有效 delta、未发布、改定义并刷新 hash，以及旧 C10 网表冒充完整 bank。

离线 prepare 测试夹具身份为 `00006402`，不是物理候选；只用于验证 8 个编译源、38 项固定输入。
五份固件源码与 C10 的 hash 相同，但本机默认 GCC16.2 产生 36,352 B BIN，
C10 的 BIN 为 36,368 B，所以没有继承旧 ELF/BIN/FS 身份。
RTC/PLL 维护文件和约束未修改；原 UART 280-byte wire 格式不变。

完整 GAO 的原始存储位数从 69,632 增至 282,624；实际 BSRAM 映射、寄存器保留、
CDC 端点、时序和芯片内观测必须由主代理生成新身份后实际综合/P&R/上板核对。
不得复用 C10 身份或以源码测试代替 SRAM Verify、独立身份读回或硬件验收。
封存包预定位置 `~/.cache/gw138k-task-20261030/ae350-full64-gao-parent-v1`。
