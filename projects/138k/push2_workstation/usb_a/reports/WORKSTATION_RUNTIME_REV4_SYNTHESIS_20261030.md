# Revision 4 原生整机综合

日期：2026-10-30（Asia/Shanghai）。[revision4 来源闭包](WORKSTATION_RUNTIME_PROFILE_REV4_20261030.md)已进入真实 Gowin 整机综合；本阶段只记录综合及父级输入／产物复核。两次运行均使用现有 `scripts/custom_board_synthesis.tcl`，没有新增生产 builder，未运行 P&R 或操作板卡。

## 来源与执行

prepare 原件保持不变，全部 560 项 staged 文件逐项复制到独立综合目录，调用前、调用后及父级复核时均重新计算 SHA256。启用输入仍为 256 项，编译单元为 253 项。执行持有 `/private/tmp/gw138k-build.lock`，避免 EDA 并行修改产物。配置和所有输入／工具／输出哈希、完整警告清单、进程记录与父级校验脚本身份见 [runtime_rev4_synthesis.json](workstation_task_20261030/runtime_rev4_synthesis.json)。

| 项目 | 首次 v1 | 修正后 v2 |
| --- | --- | --- |
| 候选 | `custom138k-workstation-v1-eeca04948a6f07bb` | `custom138k-workstation-v1-41e653fe462e5ea3` |
| 综合目录（cache 根下） | `runtime-rev4-synthesis-eeca0494` | `runtime-rev4-synthesis-41e653fe` |
| 退出码／输入保持 | 0／全部保持 | 0／全部保持 |
| 耗时 | 457.271 s | 460.401 s |
| VG SHA256 | `79edb30a67bebaf9b61f320588d4e96780799ebcf176410d9b0bff5798779287` | `2319746ad8eabba1e19721908402dd0c25bd91aba52b896650d82153e6c4e3da` |
| 综合警告 | 334 | 331 |

cache 根为 `/Users/sphenicidition/.cache/gw138k-task-20261030`。工具报告为 GowinSynthesis V1.9.12，器件 `GW5AST-LV138PG484AC2/I1`、GW5AST-138 version C，顶层 `workstation_custom_138k_top`。`gw_sh` 与 `GowinSynthesis` 可执行文件也已按实际字节绑定。

v1 到 v2 的编译输入路径集合完全相同，560 项 staged 文件中只有三项改变：HDMI 实现、其 provenance 和 BLE `patch_path.vh`。HDMI 旧共享读输入显式接零后，`shared_read_enable/kind/addr` 三条 EX1998 消失。比较警告时只归一化候选根路径和源码行号，没有新增警告；原始逐条内容仍保留。BLE v1 头引用原 immutable prepare 的绝对 ROM，父级核对该 ROM 与复制输入字节相同；v2 改为 stage-relative 引用，关闭外部路径依赖。旧候选和旧综合结果保留原身份。

## 综合资源

两次资源报告相同：

| 指标 | 综合结果 |
| --- | --- |
| Logic | 119,348／138,240（工具显示 87%） |
| Logic 组成 | 91,728 LUT、18,344 ALU、1,546 RAM16 |
| Register | 60,853／139,095，无 latch |
| 综合 BSRAM | 259／340（工具显示 77%） |

这里的 BSRAM 是综合统计；实际物理分块、复制与占用尚未测量，不能据此宣称还有 81 块物理余量。网表 DFF 解析器的层级统计也不替代工具资源数。综合时序估计不作为 routed timing 证据。

## 尚未关闭的诊断和门禁

v2 仍有九条 EX1998：vendor VexRiscv 的 `IBusSimplePlugin_rspJoin_fetchRsp_isRvc`，以及 CNN 分支的八条 `nn_*`。另有宽度截断、未连接端口、隐式声明、优化移除及三条时钟关系警告；完整计数在 JSON，不能写成零警告。`u_scan_window`、未消费的 fanout／FFT／UART 等移除项需要按实际功能路径解释；综合成功本身不证明 feature preservation。

综合 HTML 将 ULPI、12.288 MHz／16.9344 MHz 音频参考和 DCS 输出列为默认 100 MHz base clock。后续必须加载并独立核对真实 SDC 与实际实现端点；不能使用这份综合 clock summary 证明双时钟或 USB 时序通过，也不能放宽时钟来消除警告。

新 runtime 的完整 CDC／held payload／Gray／reset 协议、仍适用但被混合旧层次命令省略的约束、PLL、电气、DDR 初始化与资源／功能门禁仍未闭合。源码审查还发现 TF `memory_quiet` 组合聚合跨域，以及计算停钟期间完整 USB 拔插的旧 FIFO 重放，正分别修复。改变这些来源后必须形成新的 prepare 与综合身份，不能沿用本阶段 v2 结果。

本阶段 `synthesis_passed=true`；`place_route_run`、`physical_resources_verified`、`routed_timing_verified`、`cdc_verified`、`pll_verified`、`feature_preservation_verified`、`hardware_tested`、`sram_programmed`、`flash_programmed`、`deployment_allowed` 和 `release_ready` 均为 false，位流 SHA256 为 null。没有新位流，也没有改变板上内容或推断当前 SRAM 身份。

## 复核与回退

父级重新计算两份 profile 的所有 560 项输入、所有输出、工具二进制、完整日志及 v1 外部 ROM 哈希，并与原 prepare 和进程记录逐项相等；两次 enabled 路径集合相等，三项变更和警告差集符合预期。JSON 保留该次复核的脚本哈希及完整输入清单，生成数据库／VG／日志仍只放 cache。

源码策略回退沿用 profile 文档：省略显式 runtime profile 可恢复原默认 native prepare，accepted／pinned／resource 路径的来源不因本次综合改变。硬件无需回退操作；后续实际部署与回退仍按架构文档链接的独立部署证据执行。
