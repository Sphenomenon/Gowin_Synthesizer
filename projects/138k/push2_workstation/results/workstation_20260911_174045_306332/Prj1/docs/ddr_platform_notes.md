# Tang Mega 138K DDR3 平台适配

核对日期：2026-09-08。平台为 GW5AST-138C / PG484A，工程目标器件为 `GW5AST-LV138PG484AC2/I1`。本文记录设计依据与接口契约；是否已完成板测以 [verification.md](verification.md) 中的实测记录为准。

## 硬件和资料来源

优先核对本地 [UG986-1.2.7 PG484A Pinout](../../../Doc/GW官方/UG986-1.2.7_GW5AST-138器件Pinout手册.pdf) 的 PG484A Bank 6/7 表、[UG984-1.2.2 原理图指导](../../../Doc/GW官方/UG984-1.2.2_GW5AT_&_GW5AST系列FPGA产品原理图指导手册.pdf) 的 VCCIO/VREF 说明。DDR 颗粒位于核心板，不在 Dock 上；[30354 SOM 原理图](../../../Doc/Mega_138K_60K/02_Schematic/SOM/tang_mega_138k_30354_Schematics..pdf) 第 3 页渲染后可确认两颗 **H5TQ4G63EFR-RDC**，共享地址/命令、各提供 16 DQ，合计 **32-bit、1 GiB**。实物可能装兼容料，以丝印和板测为准。

本地 `Doc/GW官方` 未包含 DDR IP 手册，因此补查高云官网 [IPUG281-2.6，2026-01-16](https://cdn.gowinsemi.com.cn/IPUG281.pdf)。重点为第 4.4.2-4.4.7 节时钟、复位、地址、握手，以及第 6 章端口定义。该手册规定 GW5AST-138 使用 1:4 控制器比例、支持至 800 Mbit/s。来源 PDF、文本和关键页渲染缓存在被忽略的 `build/hardware_audit/`，不修改原始资料。

生成 IP 取自 [ddr_memory C 版示例](../../../Doc/tangMega-138K-example/ddr_memory/README.md)，该示例于 2026-04-03 用 Gowin V1.9.12.02_SP1 生成，目标 `gw5ast138c-007` / C1/I0。Prj1 使用同一 C 版和 PG484A 封装，最终工程按 C2/I1 综合、布局布线与时序检查；这不替代当前板卡校准和数据一致性测试。`cam_dvi` 中的 IP 仍为 B 版，不用于当前 PHY。

## 固定配置

| 项目 | 配置 |
|---|---|
| 物理组织 | 一 rank、8 bank、32768 row、1024 column、32-bit DQ |
| 总容量 | `2^3 × 2^15 × 2^10 × 4 = 1,073,741,824` 字节 |
| 电气 | Bank 6/7，1.5 V SSTL15；CK/DQS 为 SSTL15D |
| DDR 时钟 | 400 MHz，双沿数据率 800 Mbit/s/DQ |
| 控制器时钟 | `clk_out = 100 MHz`，1:4 |
| 理论总带宽 | 3.2 GB/s，实际需扣除刷新、激活、读写切换等开销 |
| 用户数据和 mask | 256-bit / 32-bit；mask bit=1 屏蔽对应字节 |
| burst | 固定 BL8、顺序 burst；一个用户数据拍传输 32 字节 |
| 原生地址 | 29-bit：rank[28]、bank[27:25]、row[24:10]、column[9:0] |
| 时序 | CL=6，CWL=5，AL=0，tRCD/tRP=15 ns，tRFC=260 ns |
| 刷新 | IP 自动刷新，tREFI=7.8 µs；用户 sr_req/ref_req 固定 0 |
| 终端 | 保留 C 版示例的 RTT_NOM=40 Ω、RTT_WR=OFF、OUTPUT_DRV=HIGH |

`app_addr` 按物理 DQ 字计数，**不是字节地址，也不是 256-bit beat 编号**。单次 BL8 占 8 个原生地址，因此连续传输地址为 `0,8,16,...`；字节地址除以 4 后才是原生地址。所有请求保持 `app_addr[2:0]=0`，唯一物理 rank 对应 `app_addr[28]=0`。一个 1920×1080 RGB565 帧占 4,147,200 字节、129,600 个 BL8；双缓冲按每帧 4 MiB 划分，预留范围为前 8 MiB。1080p60 读出有效像素带宽为 248.832 MB/s；全速重绘加读出约 497.664 MB/s，仍须以实际仲裁/缓存和板测结果验收。

## 平台接口与启动

[ddr3_platform.v](../src/memory/ddr3_platform.v) 封装 PLL、IP、复位和管脚，不承担仲裁。

1. 50 MHz 连续晶振送 IP `clk` 和 DDR PLL。[ddr_recovery_guard.v](../src/memory/ddr_recovery_guard.v) 异步接受外部低有效复位，将控制器及 PLL 复位保持 256 个 50 MHz 周期（5.12 µs），然后在该时钟边沿释放。
2. 保留 C 版 `PLL_INIT` 的模拟参数搜索过程；`pll_lock` 接此 PLL 的有效 LOCK，不能绑 1。400 MHz 必须从 PLL `CLKOUT2` 输出。
3. IP 的 `pll_stop` 直接连接 PLL `ENCLK2`，这是官方 138K 专用初始化路径，不能省略或替换为普通逻辑门控。
4. `ddr_rst` 为 IP 输出的高有效全局复位。只有控制器复位及 `ddr_rst` 均解除、原始 PLL LOCK 有效、LOCK 已通过两个 50 MHz 周期观察且 `init_calib_complete=1` 后，`ui_rst_n` 才在 100 MHz 下三级同步释放。
5. 请求/响应均以 `ui_clk` 为时钟。命令 `000=write`、`001=read`；命令仅在 `app_en && app_rdy` 时接受；写数据仅在 `app_wren && app_wrdy` 时接受。单拍 BL8 的 `app_wend` 与 `app_wren` 同时有效。上层必须正确处理两个独立握手，不能用“已提交命令”代替“写数据也已接受”。
6. 读数据无 ready 反压，所有 `app_rvalid` 都必须接收。平台在 `ui_rst_n=0` 时禁止用户请求并屏蔽 ready/valid。固定 BL8 时 `burst` 端口无效，按原示例固定 0。

### 工作中失锁的恢复

原厂 C 版 IP 的校准状态机不会因每次短暂 PLL 失锁而自动重启，重新 LOCK 后不能继续信任此前的校准。恢复保护在首次校准成功后监测失锁；校准前的 PLL 模拟参数搜索允许 LOCK 多次升降，不会反复复位导致初始化无法完成。

LOCK 下降会异步清零观察链，因而两个 50 MHz 边沿之间的短脉冲也能触发恢复。平台立即关闭 UI 释放条件；最迟下一个 50 MHz 边沿将控制器及 PLL 重新复位 5.12 µs。即使原 IP 的旧 `init_calib_complete` 尚未清零，LOCK 的两周期恢复观察和控制器复位仍会保持 UI 关闭。另一路健康观察直接覆盖 `init_calib_complete` 刚上升、尚未经过状态同步器时发生失锁的边界。

复位后重新执行完整 PLL 搜索、PHY 初始化及校准。视频模块的 UI、音频采样快照及像素侧握手一起复位，重新运行前 8 MiB 自检并生成新帧；在此期间保留黑色 1080p 光栅。音频合成与串口控制不依赖 DDR 恢复流程。

`sim/tb_ddr_recovery_guard.sv` 覆盖首次 PLL 搜索、亚周期失锁、持续失锁、复位宽度、再次校准后重新监测、外部复位，以及校准刚上升时失锁。正常初始化中原 IP 的停钟复位窗口另见 [DDR 复位序列审计](evidence/ddr_reset_sequence.md)；数字仿真不代表已经实测 PLL 最小可捕获失锁脉宽。

## 引脚和物理资源

完整参考约束保存于 `vendor/gowin_ddr3/reference_demo.cst`，仅供核查。工程实际约束必须使用当前 top 的层级和端口。

| 总线/信号 | 球位，按 bit 0 起排列 |
|---|---|
| ADDR[14:0] | M1,K2,G2,J4,J2,H2,G3,J1,J5,H5,L1,H3,K4,K1,D1 |
| BANK[2:0] | P5,P2,M6 |
| CS/RAS/CAS/WE | P4,L5,L4,M5 |
| CKE/ODT/RESET_N | K6,M2,L6 |
| CK P/N | L3/K3 |
| DQ[7:0] | Y4,AB3,AA5,V4,AA1,AB2,AB5,AB1 |
| DQ[15:8] | AA8,Y8,AB7,Y7,AB8,W9,AB6,Y9 |
| DQ[23:16] | U5,R6,U6,R4,Y6,T4,V5,T5 |
| DQ[31:24] | W2,Y1,T1,U3,U2,V2,U1,Y2 |
| DM[3:0] | AA4,V7,T6,W1 |
| DQS0/1/2/3 P/N | Y3/AA3，V9/V8，W6/W5，R3/R2 |

C 版 `ddr_memory` 示例漏列 DM 引脚，Prj1 集成时需补齐上表四个 DM（SOM 和 `cam_dvi` 一致）。DDR DQ 顺序必须保持示例映射，不能按原理图颗粒数据编号重新排序而忽略 FPGA DQS lane 组合。

平台实例名若为 `u_memory`，对应资源约束为：

```text
u_memory/u_pll/u_pll_0/PLL_inst                       PLL_L[0]
u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_dll             DDRDLLM_BL
u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv           LEFTSIDE[4]
```

参考 demo SDC 把 50 MHz `clk` 写成 10 ns，不能原样采用。工程应约束 50 MHz 为 20 ns、memory_clk 为 2.5 ns、用户 clk_out 为 10 ns，并对真正的跨域握手/多位稳定数据路径做针对性约束。不能用全局忽略时序替代 CDC 设计。IPUG281 第 5 章另说明 FPGA 侧 ODT 可按板测需要配置；默认不应擅自更改已采用的电气参数。

初始化 RESET 的停钟窗口与 DLLSTEP/HOLD 配置路径分别由 [复位序列审计](evidence/ddr_reset_sequence.md) 和 [配置路径审计](evidence/ddr_configuration_paths.md) 给出原始网表、官方原语模型和可复现脚本依据。WLOADN 继续保留实际 setup/hold 检查。最终是否满足时序，以同一构建生成的完整报告和检查结果为准。

当前 SDC 只豁免已审计的 101 个 DDR IO 原语 RESET 和 8 个 `rburst_neg` / `rburst_neg_r` CLEAR。这八个寄存器的时钟由受门控的 UI 时钟反相得到，复位直接来自同一官方停钟状态机；构建检查逐一验证实际接线和 40 ns SDF 传播预算。`u_dll/RESET` 不在此例外内。DLL 的八位 STEP 快照使用端点最大延迟 40 ns，路由网表校验每位 D 的唯一 STEP 来源、采样使能和历史流水，避免 Gowin 的源引脚选择器显示激活却没有实际约束路径。

WLOADN 的 UI→50 MHz 保持时间通过物理位置修复：`ddr_init_internal_r_s0` 固定到已验证的 CLB FF 位置 `R52C59[0][B]`，`wloadn_3_s0` 固定到 `R17C2[0][A]`，增加实际数据布线延迟。该路径以及目标寄存器至四个 DQS.WLOADN 的 setup/hold 均继续检查；没有为其增加假路径或放宽保持时间要求。2026-09-08 13:45:44 的正式集成报告中 setup/hold 违例均为零。

## 自检范围与验证边界

[ddr3_bist.v](../src/memory/ddr3_bist.v) 在校准之后、帧缓存开始运行之前，对前 **8 MiB** 进行两轮完整写/读，第二轮为第一轮的逐位反码；每个地址和 burst 内 8 个 32-bit 位置具有不同数据，覆盖两颗 16-bit 芯片的数据线。读最多一笔在途。默认连续 10,000,000 个 100 MHz 周期没有请求/响应进展即失败并停止；数据错误累计到 `error_count`，`first_error_addr` 记录首错原生地址。

`done=1` 只表示自检结束，必须同时 `failed=0` 才能启用显示。BIST 会覆写测试区，不保存原内容；启动时该区域还没有有效帧。它不检查后续约 1016 MiB，不等价于全容量 March 测试或长期信号完整性验收。

`sim/tb_ddr3_bist.sv` 已通过：随机请求反压、随机响应延迟、完整两轮次序、反码关系、两颗 DRAM 的 bit 错误、读超时和命令超时。此仿真检查用户逻辑协议，不模拟加密 DDR PHY 的模拟校准或 PCB。

### 1080p60 吞吐预算回归

`sim/tb_ddr_bandwidth.sv` 使用实际 `ddr_frame_writer`、`video_ddr_scanout` 和 `video_timing_1080p`，100 MHz 用户时钟、148.5 MHz 像素时钟、2200×1125 总时序。轻量渲染器在 ready 时每周期提供两个 RGB888 像素；每个新帧采用不同颜色，逐一检查所有有效像素，确保没有旧帧、黑线或半帧混用。

DDR 原生端口是**确定性的行为压力模型**：读请求优先；命令通道每四周期阻塞一次，写数据通道额外每八周期阻塞一次；每 780 个用户周期暂停命令及返回 26 周期，用作 260 ns / 7.8 µs 刷新预算；读请求在 12-15 周期后具备返回条件，按请求顺序最多每周期返回一拍，刷新和排队会延长实际延迟，最多允许 64 笔在途。这些设定不是当前板卡实测效率，不包含模拟校准、走线质量或真实控制器 bank/row 调度。

2026-09-08 回归结果：

| 观测项目 | 结果 |
|---|---|
| 连续稳态输出 | 3 个完整 1920×1080 帧，6,220,800 个有效像素全部正确 |
| 换帧间隔检查 | 每帧 16.666667 ms，检查容差 ±20 ns |
| 欠载/取数错误 | 0 / 0 |
| 启动第一帧写完 | 12.796000 ms |
| 并行读屏时后续帧写完 | 14.274120、14.274300、14.274020 ms |
| 最慢渲染及写入时间 | 14.274300 ms，低于 60 FPS 周期 2.392367 ms |
| 最大读请求在途 | 12 笔 |
| 接受/返回读拍 | 388,800 / 388,800 |
| 完整接受写拍 | 518,400，四个完整 back frame |

这确认当前两像素渲染接口、打包器、读优先仲裁和两行预取在上述模型下能够保持每帧刷新。真实 DDR 校准、自检、长期欠载计数和显示器 1080p60 锁定仍需独立板测。

## 第三方文件记录

`vendor/gowin_ddr3/provenance.json` 记录每个导入文件的本地来源与 SHA-256。加密控制器 `.v` 原样保存；三个 PLL 文件仅重命名模块以避免与视频 PLL 冲突，逻辑/参数未改。`.ipc` 保留来源目标型号而不伪装成重新生成的文件。来源文件中的 Gowin 版权声明保留，不将其声称为项目原创或另行授予开源许可证。
