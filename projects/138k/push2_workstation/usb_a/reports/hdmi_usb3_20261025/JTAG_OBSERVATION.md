# HDMI 内部状态观测（2026-10-25）

## 已得到的实板信息

用户在 D3 SRAM 下载后反馈“依旧没有图片”。接受其硬件和线路正常的前提，继续从程序运行状态收敛，不反复改线、调整同一延时或重复下载 D3。

本轮从 `/dev/serial/by-id/usb-FTDI_Dual_RS232-HS-if01-port0` 按 115200 8N1 独占接收 12 秒，发送零字节，没有收到任何字节或 `H3D1` 报告。随后只执行 Read Device Codes（操作 0），读到 UserCode `0xC11025D3`、ID `0x0001081B`、Status `0x00022230`。没有重新下载 SRAM、写 Flash 或发出 FPGA 复位命令。

原始记录位于 `out/hdmi_usb3_diagnostic_20261025_c11025d3/uart_observation_20261025_01/` 的 `result.json`、`uart.bin`、`identity_read.json` 及日志。串口名称只证明电脑看到 FTDI 的 UART B，不证明 U15 的实际信号已进入该接口；零字节不能区分 UART 接收路径和逻辑运行状态。JTAG 身份正确也不证明 PLL 已锁或像素时钟存在。

## 新观测版 D5：不改变视频 RTL

为直接观察内部状态，新增临时 `prepare_jtag.py`，从锁定 D3 的 `.vg` 插入 post-synthesis GAO。使用现有显式 netlist 入口的方式：`set_device`、`add_file -type netlist`、`add_file -type gao`、`run pnr`；不打开包含 RTL 的工程，不改变生产 profile，不改冻结输入。

- D3 `inputs.json` SHA256：`4f90d273063b032dd2c4b5dd65131cac643bd1583ed1835b45dd969865ba40b2`。
- 复用 `.vg` SHA256：`012f162c0c92f8ac0467740a452c1fa3a4d908d16bde1addb4770df27d4f7284`；构建后逐字节不变。
- D5 的 CST、SDC、视频 RTL 与 D3 一致。日志明确记录 `Skip synthesis, because there is only one netlist file in this project`。只对 GAO 观察核生成实现，再对带探针设计 P&R；没有重综合视频 RTL 或整机。
- 采样时钟是直接 50MHz 域的 `clk_50m_d`，不是可能停掉的像素时钟。捕获 27 个信号、1024 个样本：上电／下游复位、重启完成、同步后的时钟就绪／串行器复位／像素复位／HPD／像素心跳、报告状态／计数器及两级资格化 PLL ready。
- 观察核只读取信号，不提供任何控制输出；不改变 TMDS 极性、位序、光栅、PLL 参数、CEC 或 Flash 管脚行为。不直接用 50MHz 采样 742.5MHz 波形，也不把心跳当精确频率测量。
- 主诊断仍为 614 个逻辑单元、386 个寄存器；GAO 单独新增 423 个逻辑单元、343 个寄存器及 2 块物理 BSRAM。这不是整机资源统计。

## 候选身份与检查

所有输出路径以 `projects/138k/push2_workstation/usb_a/` 为根。

| 项目 | 身份 |
|---|---|
| 候选目录 | `out/hdmi_usb3_diagnostic_20261025_c11025d5/` |
| UserCode | `C11025D5` |
| GAO ID | `0010010111010101` |
| 工具实际输出位流 | `impl/pnr/ao_0.fs`，不是普通诊断文件名 |
| 位流 SHA256 | `27748b893afb980e22cecd05b1b5e2d183fd3cbe05a0dadb9a5fb5c1d15a2c8b` |
| 输入清单 SHA256 | `c3e7bc33b46bb83981fbc5e11a3e25efcddb12933a9639d6238b8ba97dbb84c3` |
| 汇总清单 | `observation_candidate.json`，SHA256 `0e95ce2bd7873e45eff2c0496628daa04e059c397e0f27757b68b51c3e3ec086` |

新增 prepare 回归 2 项、既有诊断 5 项、accepted 输入边界 10 项、官方原语／反接线缆 TMDS 回归 1 项，共 18 项通过。路由后的原视频 PLL、四个串行器及分频启动检查通过，保留原有负向对照；新增检查核验工具跳过视频综合、复用网表哈希、GAO 配置到生成 wrapper 的全部采样信号和时钟映射，以及真实 `ao_0.fs` 头部 UserCode。`verification.json`、`regressions.json` 和汇总清单绑定原始输出、检查器、命令及日志；GAO 生成代码与其原始 vendor 输入单独记录哈希。

原始视频 STA 仍保留 setup +2.721ns、hold +0.247ns、recovery −6.394ns、removal +0.040ns，`timing_closed=false`。Vendor 路由仿真网表不包含 GAO 核，现有路由检查不能冒充完整 GAO CDC／时序检查。没有放宽约束或隐藏负值；没有围绕负余量反复优化。

### 未采用的 D4 尝试

首次尝试仅复制 D3 工程、把 `run all` 改为 `run pnr`，工具仍因新工程上下文自动重综合了小型视频工程。输入哈希校验发现 `.vg` 与声明的复用输入不一致，拒绝验证。D4 从未下载，其原始目录、清单及日志保留，另有 `rejected.json`。没有修改旧清单把失败改写为通过，也没有用 D4 身份包装 D5 的新输入。

## 下一步和退出条件

D5 初次离线构建时未下载，构建清单中的未板测／未下载字段保留为当时快照。用户随后以“下载吧”回应 D5 SRAM 下载及 JTAG 捕获请求，2026-10-25 18:24:55（UTC+08:00）完成 SRAM Program（操作 2）和独立身份读回：下载前为 `C11025D3`，下载后为 `C11025D5`，ID `0x0001081B`、Status `0x00022230`，配置错误位 0–3 为零。本次未重建、未写 Flash；授权、位流哈希及原始命令／日志见 D5 输出目录的 `sram_deployment_20261025_01/result.json`。原 D3 构建、下载与观察记录保持不变。

### 18:26–18:32 的初次 JTAG 捕获结果

- 第一次通过 `gao_sh`／FT2CH 后端启动捕获，日志仅到 `Start running GAO analyzer.`；30 秒未获得样本，主动终止本次进程组。记录在 `jtag_capture_20261025_01/`，不将超时解释为 PLL 未锁。
- 第二次仅对运行时捕获配置将 M0 的 Basic 比较值改为 `X`，尝试无条件触发，保留相同 GAO ID 和信号拓扑，不修改位流或 canonical `.gao`。工具在约 2 秒后返回 `Error: Can not connect to JTAG server.`，退出码 2；记录在 `jtag_capture_20261025_02/`。这次尚未连上服务器，不能据此声称已经排除了触发条件问题。
- 两次均没有 CSV／VCD／GWD 或有效样本，未得到实际 PLL ready、复位、HPD、像素心跳或 GAO ID 读数。工具链捕获尚未验通，不能把其失败当成视频逻辑故障。
- 结束捕获后没有残留本次 `gao_sh`／`jtagserver` 进程。18:32:35 再次只读确认 UserCode 仍为 `C11025D5`、Status 仍为 `0x00022230`。附加日志在部署目录的 `after_capture_codes.*`，本轮汇总为 D5 的 `capture_summary_20261025.json`。

这两次失败当时要求先处理捕获服务器／FTDI 后端，再判断时钟和复位；下面的继续排查已经取得样本。原 `capture_summary_20261025.json` 保留为初次失败快照，不覆盖为成功。

## 19:04 实际捕获：时钟／复位链已经运行

用户要求继续后，仅操作现有 D5 的观测链路。未重新综合、P&R、下载 SRAM、写 Flash、冷启动或恢复工作站。

### 主机侧问题及临时绕过

1. 真正残留的本次 socket 在 `$TMPDIR/gao1`，即 `/home/sphenicidition/.cache/fpga-validation/20261025/gao1`，不是此前检查的 `/tmp/gao1`。其修改时间为 18:26:33。确认该路径是当前用户拥有的 socket，且 `ss -xlpn` 没有活动监听后才移除。清理后服务器能连接，但捕获仍不完成，故残留 socket 不是全部原因。
2. 对主机 `gao_sh` 的发送／返回包作调试观察：默认路径只发送 `CHAIN` 的 `OPEN`，随后寄存器访问返回 `RES=-1`，没有有效采样数据。该状态不能被解释为 FPGA 等待触发或没有采样时钟。
3. 本版本解析的是单横线 `-location`、`-device`；双横线尝试没有达到预期选择效果。`-device` 也没有把实际 `OPEN` 的 cable index 改为 WINUSB。显式 location 后观察到 FT2CH 的 `cable_index=0`、`cable_location=54`，`OPEN RES=1`，工具打印 `Unknown device error`，但进程仍退出 0。不能仅据退出码判定成功。第 04／05 次尝试清单中的 `reason` 是当时的试验假设，不是最终参数解析结论。
4. 临时由 GDB 在主机 `initDeviceChainandLocation` 的 QString 参数中选用安装版本已有的 `Gowin USB Cable(WINUSB)` 名称，此后实际发送 `cable_index=2`、`cable_location=54`，`OPEN RES=0`，八段 `READ_RAM` 均返回 `RES=0` 和数据，并成功导出 CSV。这里的 GAO index 2 与 Programmer CLI 的 index 5 属于不同枚举，不能混用。

该绕过只改变主机的线缆选择参数，不修改 vendor 文件、FPGA RTL、GAO 拓扑或板上位流，也不调用 Programmer 下载。调试位置绑定 `gao_sh` SHA256 `4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b`；不是跨版本可用的正式工具接口。进程和子进程均已清理，未留下后台采样程序。后续应优先用正式支持 WINUSB 的捕获入口替代临时调试绕过，不把它升级为生产构建依赖。

### 两次有效捕获

| 记录 | 配置／结果 |
|---|---|
| `jtag_trace_20261025_06/` | 运行时 M0 比较值为 X；1024 点、27 信号；八段 RAM 读回成功 |
| `jtag_capture_20261025_07/` | 原始 canonical `diagnostic.gao`，`power_reset_n == 1`；1024 点、27 信号；八段 RAM 读回成功 |
| 第二次 CSV SHA256 | `54f73b6e8be2e105e3196c1b4dbff85297ebb06f188747d6cb649b5b2e5c8c72` |
| 新观测汇总 | `capture_observation_20261025_02.json`，SHA256 `d573bf9bfec1915dff12785a1e75dd8982944037acb377a7c09ae5abc6115e2b` |

第二次捕获保留原触发配置，其 `.gao` 哈希为 `fb02513570ef9572074d5401d8c6b3e866eb7ee944edf0280ab30ae25bc523d0`。生成 CSV 的列顺序与 canonical 27 信号逐项一致，逐行核验 1024 个连续样本索引及二进制值；状态汇总在各目录的 `status_summary.json`。原始包、CSV、工具日志、独立身份读回及各次失败尝试均保留在 ignored 输出目录，不加入源码。

两次观测一致：

| 信号／状态 | 实际读数 | 能说明什么 |
|---|---|---|
| `power_reset_n`、`reset_n_Z`、`restart_done_Z` | 全部 1024 点为 1 | 上电／下游复位已释放，一次性重启已完成 |
| `reference_ready`、`tmds_ready`、`status_sync_q[0]` | 全部为 1 | 两级资格化 PLL 就绪及综合时钟就绪标志均有效 |
| `status_sync_q[1]`、`status_sync_q[2]` | 全部为 1 | 像素域、串行器复位释放标志均有效 |
| `status_sync_q[4]` | 每次捕获均有 24 次跳变 | 像素计数器在运行，不是一直停钟或保持复位 |
| 相邻心跳跳变间隔 | 21 次为 43 点、2 次为 44 点 | 与名义 50MHz 采样、148.5MHz 像素计数器的比值一致；不是精密频率／抖动测量 |
| `status_sync_q[3]`，即同步 HPD | 两次全部为 0 | 当前程序读到 HPD 低；尚未定位低值的原因 |
| `report_flags[5:0]` | 两次全部为 `0x37` | 已重启、已见像素活动、HPD 低、其余三个就绪位高；不是之前假设的 `0x3F` |

CSV 虽标 `time unit: us`，数值列实际为 0–1023 的连续索引；不把该标签直接当作测得的微秒时间。采样周期仅依据已实现的名义 50MHz 配置解释。GAO ID 仍只有配置值 `0010010111010101`，未单独执行实际 GAO ID 读回，不将成功捕获冒充该项检查完成。

19:04:28（UTC+08:00）随后独立执行 Read Device Codes（操作 0），再次读到 ID `0x0001081B`、UserCode `0xC11025D5`、Status `0x00022230`。原 D5 位流哈希和输入清单逐项仍匹配。现有离线清单不改写，新观测汇总另行绑定真实证据。

### 定位收敛与剩余工作

现在有实板依据排除“当前像素链一直没有启动／一直保持复位”的假设，不再反复增加上电延时或重新下载相同程序。HPD 未门控该诊断的像素时钟、光栅或 TMDS 输出；接受用户硬件与线路已正常的前提，不把 HPD 低直接当作 PCB 故障或无图根因，也不通过强拉 HPD 来伪造修复。

D5 的固定探针不包含 HS／VS／DE、光栅计数和 OSER10 并行输入，因此就绪与心跳有效仍不能证明正确光栅、TMDS 内容、引脚高速波形或显示器成功锁定。下一步先确认显示器当前是“无信号”还是“识别信号但黑屏”；若仍有问题，扩展光栅和编码观测点，继续复用锁定视频网表，仅生成新的观察核与 P&R。新位流须独立身份、离线检查，并在用户明确授权后才下载 SRAM，不自动写 Flash。

用户授权后可 SRAM 恢复原 D3 或 `C1102515`，不做 Flash 回退或冷启动。定位失败环节后退役该观察核；只有经实板确认必要的修改才能进入版本化原生装配及新的整机候选。该临时辅助工具不是长期生产构建入口。

## 用户确认出图，结束诊断并恢复工作站

用户随后明确确认：“正常出图，是硬件问题我现在搞定了，现在把之前那个完整工作站烧进去”。这确认 D5 在用户修复硬件后已正常显示；未提供具体故障器件或机制，不再臆测硬件细节，也不把之前 HPD 低的样本直接解释为已证实的故障原因。先前计划的光栅／编码扩展探针不再继续，未生成或下载 D6。

用户反馈单独记录在 D5 输出目录的 `user_display_acceptance_20261025.json`，SHA256 `3b6cefe5123ae857b3d0f7bc339413185bba4aee4c6f6be82685a1690c2c8826`；来源是用户显示验收，不是仪器测得的 TMDS 波形或新增 GAO ID 读回。原始失败尝试、有效捕获及离线构建清单均保持不变。

2026-10-25 19:55:05（UTC+08:00）按该请求和此前 SRAM-only 范围，将原完整工作站 `C1102515` 下载至 SRAM，独立身份读回通过；没有重建、写 Flash、冷启动或恢复 Flash 备份。详细身份与证据见 [工作站恢复记录](../WORKSTATION_DEPLOYMENT_20261025.md)。当前板上不再是 D5；完整工作站的功能验收另行进行，不由 D5 出图结论代替。
