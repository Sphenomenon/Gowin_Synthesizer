# C11027C1 蓝牙实板检查（2026-10-27）

用户要求“你自己先测试蓝牙”后，直接测试当前 SRAM 中的 C1 工作站。**业务广播、GATT、会话、重连、短录音和下载校验通过；非静音音频内容尚未验证。** 没有重新综合、布局布线或烧录，没有操作 Flash、断电或更换位流。

## 身份与方法

- 日期／时区：2026-10-27，Asia/Shanghai。协议与短录音检查为 12:56:46～12:57:22，扩展下载检查为 13:00:50～13:01:00。
- 测前／测后独立 JTAG 均读到 ID `0x0001081B`、UserCode `0xC11027C1`；读身份时使用既有排他锁。
- 位流 SHA256：`91101332be8d8d5ac3511cc36227d77ab0fe2511f5869efb90c657b55ee1386a`。配置、源码与物理证据沿用 [C1 交付报告](WORKSTATION_RESOURCE_A26_PHYSICAL_20261027.md)，没有改变候选输入。
- 主机实际扫描到 `GW138K-MAIN`，地址 `D8:30:6D:A1:41:9E`，广播含业务 service `9b6d0000-4c2a-4f87-9a31-138000000001`。
- 使用已有主机环境 `bleak 3.0.2`，复用独立协议工程的 `protocol_check.connection_test`、`recording_check.Session`、`protocol_v1` 和 `pcm_lossless`，仅适配目标名称与原生实时 PCM 来源；未另写线协议。
- Capability 为协议 1、逻辑消息上限 512、能力 `0x68`、默认块 256、窗口 1、录音槽 1。跨普通重连的 boot_id 均为 `0x1B6858306DA160C0`。

## 实际通过项目

| 检查 | 实际结果 |
|---|---|
| 业务 GATT | Capability、Command、Response、Status、Transfer 均发现，属性正确；不是仅发现 FFF0 诊断服务 |
| HELLO／GET_STATUS | 两次独立连接通过；GET_STATUS 逻辑响应恰为 **84 字节**，payload 64 字节，CRC 正确 |
| 去重／错误处理 | HELLO 与状态重放逐字节一致；重复首片可恢复；同 ID 不同命令返回 `0x86`，未知命令返回 `0x80`，坏 CRC 无业务响应，乱序分片被 ATT 拒绝，随后正常命令仍成功 |
| 原生短录音 | 初始 EMPTY，创建 recording_id 1；48 kHz、双声道 PCM16，**4,800 帧／19,200 字节／0.1 秒**，按指定帧数自动封存为 READY |
| 录音完整性 | 容量 16,384 帧；stop_reason 2，fault_detail 0，incomplete 未置位，crc_valid 置位 |
| 完整下载 | 每块 CRC 与对象 CRC 均通过；对象 CRC32 **`f2b78ffb`**，写出标准 WAV |
| 断线续传 | 下载至 1,024 字节后主动断连，新 nonce 重连；boot／对象／CRC 不变，从已 ACK 偏移继续，最终对象一致 |
| 下载保护 | 错 boot 被拒绝；引用中 CLEAR 被拒绝；过早 CLOSE、错误 ACK CRC、末尾越界 READ 被拒绝；READ 重放数据一致 |

完整基础检查含 179 次命令交换；扩展检查另有 48 次。基础下载耗时约 22.68 秒，包含重连和负例，**不是纯链路吞吐测量**。

## 下载扩展保留检查

不清除或重录对象，以 Write Command 发送命令，对同一不可变对象读取不同的四字节对齐偏移，并与第一次完整下载逐字节比较。下表 notification 数不含额外的重放检查。

| OPEN opcode | 分片 | 单块 PCM 字节 | DATA notification 数 | 结果 |
|---|---|---:|---:|---|
| `0x30` | B1 | 256 | 22 | 通过 |
| `0x36` | B1 | 460 | 37 | 通过 |
| `0x37` | B2 | 460 | 32 | 通过 |
| `0x38` | B3 | 460 | 3 | 通过 |
| `0x39` | B3、direct | 460 | 3 | 通过 |
| `0x3b` | B3、long | 972 | 5 | 通过 |
| `0x3c` | B3、extended | 8,112 | 34 | 通过 |
| `0x3d` | B3、lossless | 8,112 | 22 | 通过 |
| `0x40` | B3、second lossless | 8,112 | 13 | 通过 |

另验证 `0x37/0x39/0x3c/0x3d/0x40` READ 重放，包含压缩 wire payload 一致；最后切回 `0x30` 成功。结束时 transfer 已关闭，recording_id 1 保持 READY，未清除，用户可继续下载。

## 验证边界与证据

**本次 PCM 全为零：9,600 个样本均为零，peak／RMS 均为零。** 没有播放内置测试 WAV，也没有把独立 25K 音频冒充 138K 输出。原生录音调度和传输校验已验证，但不能据此声称真实乐音、声道顺序、主音量或效果取样正确。尝试只读现有 FTDI UART，115200 8N1、DTR／RTS 关闭，4 秒未收到数据；没有盲发 MIDI、修改公共参数或引入新诊断位流。

本候选 GAO 不含 BLE 内部探针，默认 UART 也不是 BLE1。因此未声称读取到 H5 内部计数；真实业务 GATT 往返已证明此次链路可用。早期版本的 H5 失败仍是历史证据，不再代表 C1 本轮结果。GET_STATUS 的 valid_mask 仅为录音组 `0x04`，本次不验收公共参数控制、Android 真机、DDR 长录音、并发压力、物理 DAC／HDMI、冷启动或整机发布。

首次发现探针已收到正确的 20 字节 HELLO payload，但宿主误用只接受 16 字节的 `struct.unpack` 而结束；随后使用原有正式检查器的 `unpack_from` 完成上述测试。该宿主错误不归为板级故障，原记录仍保留。

机器摘要与原始文件哈希见 [ble_c11027c1.json](ae350_resources_20261027/ble_c11027c1.json)。本机完整命令／notification／脚本／WAV 位于忽略目录 `out/workstation_resource_a26_20261027_c1_physical/ble_test_20261027_125349/`；WAV 文件为 `workstation_live_pcm.wav`，SHA256 `3ac1bdf363578593c029ce12bf607ba277901c9c959ad7fed11b05d0edaadb06`。原始现场数据不进入源码提交。
