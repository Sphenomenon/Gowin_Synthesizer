# 原生工作站 AE350 独立 RTC 接入与来源闭包（2026-10-31）

本批在父提交 `3cce72e3004812a0e981be535a28418bd0a76a28` 上，把已有的 `workstation_ae350_rtc.sv` 接入原生工作站 AE350。分支为 `codex/native-ae350-rtc`。本批只执行源码、仿真、真实 prepare 和固定既有网表的只读验证，没有运行综合、P&R、烧录、探针或板上操作。

## 运行边界与约束

- 仅 `WORKSTATION_CUSTOM_138K` 分支实例化 `u_rtc`，输入是板级 50 MHz，复位是 common `system_reset_n=reset_n`；AE350 `RTC_CLK` 直接取 `rtc_clk`。它不依赖 CPU/APB、PLL 资格或内存就绪，不改变音频采样安排。
- 复用的维护 RTL 字节未变，SHA256 为 `59fbe21b3a6627245c9edb38484e9ae9955f615e9dba445a21e22ff66a22f536`。累加器平均输出 32,768 Hz，半周期为 762/763 个参考周期。STA 使用两个最短半周期组成的保守完整周期 1524（30.480 µs），不能以平均周期替代该下界。
- `clocks.json` 升到 v5，三个主时钟和十个原有 PLL/CLKDIV 频率条目不变；新增独立的 `fabric_generated` RTC 条目，分别记录平均频率、半周期范围和 STA 下界。保留寄存器目标沿用实际 C10 探针确认的 `u_rtc/rtc_tick_s1/Q`。带 LCD 的基础声明共 14 条，无 LCD 为 13 条；运行时另加三条声明。
- 新 `workstation_ae350_rtc.py` 重新核对维护源、native-only 装配、common reset、暂存源和唯一精确 RTC SDC，并在网表要求 `DFFCE`、INIT=0、50 MHz 来源、toggle CE 恒 1、唯一 AE350 宏及 Q→RTC_CLK 直连。该 Q 只允许自身输出、唯一硬宏输入和 `u_rtc/` 内 LUT 输入反馈，额外驱动、缓冲、外部端口或消费者均失败。
- 实际物理候选 RTC 子门禁重新验证 prepared 元数据、实际 SDC 和实际 VO；其失败计入总 PLL 门禁。元数据不声称 STA、抖动或硬件验收。旧无 RTC 的历史物理输入显式标记为未应用该新子门禁，不向新候选转移接受结论。

非原生分支保留原 RTC 接法。默认预处理 token SHA256 仍为 `ec71aeb68d53a11eb7975b4e643be673f30301565f10f671f8b822e6d2674f69`。accepted/pinned、frozen baselines、供应商源、既有原始 manifests 与历史证据没有修改。

## 来源与解析修复

六个新原生配置都锁定 RTC 源、helper 和相关回归，并准确刷新受影响的现有工具来源。业务 profile 升为 revision 4，增加 `ae350_rtc_policy=reference50_fractional32768_bound1524_v1`，整合身份为 `custom138k-native-ae350-business-revision4`；其余五个 revision、功能配置及所有 source_sets 保持不变。

真实 prepare 首次因 `workstation_delay_storage_provenance.py` 的维护顶层全文件引用哈希变化而正确停止。随后只把该维护引用更新到新顶层 SHA256 `f5f94091d268ec81df803b3036baebe3ffe494e79f51ae8daf4b7f52867d4476`。原 effects provenance、adaptation、原 prepared slice、FIFO 字节及两个 block_ram selector 均保留，四项原有来源链回归通过。失败日志保留在外部 checks-v1。

对现有整机真实 VG 的只读检查还发现两种合法语法：模块头可写成跨行 `) ;`，转义 formal 后必须有终止空白。严格 checker 与层次读取器现一致支持这些空白形式，完整命名绑定和语句 residue 检查仍保留。新增跨层转义 formal 正例、额外驱动与嵌套/重复绑定负例；实际旧 VG 的 156,652 个 cell、264 个 frame 完整解析成功，但因没有新 RTC 被新门禁正确拒绝。这只是解析兼容证据。

独立只读 review 找到过 SDC 行前缀检查可漏过分号、conditional 或 remove_clock 覆盖。本批已改为 RTC token 只能出现在唯一精确声明，禁止时钟移除/reset，并加入这些反例。review 对修复、实际 C10 和 VG 兼容再次复核，无剩余 blocker；这不构成任意 Tcl 解释或工具 object resolution 证明。

## 最终真实 prepare 与校验

最终产物均位于外部 `~/.cache/gw138k-task-20261030/native-ae350-rtc-checks-v3/`，使用显式 xPack `riscv-none-elf-gcc-15.2.0-1` prefix 和固定网表缓存。

| 配置 | 新候选身份 | staged / enabled | 实际编译单位 / module / package |
| --- | --- | --- | --- |
| AE350 business revision 4 | `custom138k-workstation-ae350-business-v1-901ed4db39f2e36c` | 614 / 272 | 269 / 301 / 2 |
| 默认 runtime revision 5 | `custom138k-workstation-v1-398f3be95d03c424` | 581 / 261 | 258 / 290 / 2 |

两份产物都明确选择 `rtl/clock/workstation_ae350_rtc.sv` 为 RTC 唯一编译 owner，保持 prepare_only 和未部署状态。此前 v2 产物属于解析兼容修复之前的输入，保留追溯，不作为本批最终身份。

| 最终校验范围 | 结果 |
| --- | --- |
| 源码、RTC/C10/VG 解析、profile、时钟、延迟 provenance、物理与 implementation 单元 | 75 通过；5 个未选择的 opt-in 测试跳过 |
| accepted/current 输入边界 | 17 通过 |
| 通用原生 prepare、默认 token、CLI 与失败隔离 | 5 通过 |
| 真实 business 的 RTC/PLL 篡改、编译闭包及业务来源回归 | 11 通过 |
| 真实默认产物的 RTC/PLL 篡改及完整准备闭包 | 17 通过 |
| 一秒 / 50,000,000 参考周期 RTC 仿真 | 1 通过；65,536 边沿、32,768 上升沿、762/763 脉宽、复位与重启 |

共 126 个成功测试方法，5 个 opt-in 跳过。固定 C10 的四个原始输入前后哈希相同，RTC 直接端点为保持 Q、内部反馈 LUT2/I0 和唯一硬宏 RTC_CLK；4235 条该探针 CPU PLL 实际位置行仍为 R0。既有 C10 的 STA/物理/硬件状态以其原记录为准，不向本批完整工作站继承。

## 后续、证据与回退

机器索引为 [ae350_native_rtc_source_20261031.json](workstation_task_20261030/ae350_native_rtc_source_20261031.json)，包括六个 profile 的逐项配置/来源对照、真实准备身份、完整闭包和全部检查日志哈希。源码补丁、变更源码归档、固定输入清单及校验器封存到外部 `native-ae350-rtc-delivery-v1`。

主线集成同期修改后需重新锁定来源并真实 prepare，保留新合并候选身份，再做实际整机综合，确认 RTC 保留 FF 及硬宏连接，随后补齐 P&R、STA/CDC/PLL、实际频率/抖动和硬件验收。现有 generic synthesis 回归中的历史精确资源数字需以新完整综合结果另行审查；本批没有伪造新的资源 oracle。C06/C07、完整业务负载、长录音、D 模式和整机硬件接受仍未由本批关闭。

回退使用本批父提交及其固定来源/候选；不得移除新约束后复用新候选身份。本批不生成 bitstream，也不改变 SRAM/Flash。
