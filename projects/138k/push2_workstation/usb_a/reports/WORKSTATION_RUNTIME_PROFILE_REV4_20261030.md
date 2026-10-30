# Revision 4：原生双采样率工作站来源与准备闭包

日期：2026-10-30（Asia/Shanghai）。本阶段让既有 `--prepare-custom-board --workstation-profile custom138k-workstation-v1` 显式选择原生 runtime：双时钟与换率服务、单一 session／parameters／最终 PCM、真实 TF 服务、metadata minor 1 显示和 memory guard。配置固定 1080p60、允许 HS、WAV、48 kHz／44.1 kHz、将 epoch 零保留为无效值并从 epoch 一启动，以及原 maintained AE350／scan admission 策略。这里记录源码、prepare 与离线验证；整机综合、P&R 和实板另报。

## 候选身份

最终 prepare 是 `/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2`，候选 `custom138k-workstation-v1-41e653fe462e5ea3`。

- 完整候选输入 SHA256：`41e653fe462e5ea3c5ef09d5a2c161b1444acef61700bd79ccfdd7257935f943`，以附录机器清单为准。
- 配置 SHA256：`cb6a1ed2cf10078afeb08545e329af9b1b772db070382ba5fe7b6ef5db179717`。
- 299 项来源锁、717 项完整源码快照、560 项 staged 文件；256 项启用输入由 253 个 Verilog 编译单元及 GSC／CST／SDC 各一项组成。
- 启用输入来源：124 项版本化维护源、120 项锁定父基线、10 项受检 BLE 适配、2 项受检板级约束组合。253 个编译单元经逐项预处理有 284 个 module、2 个 package，无重复定义或无归属 include。

精确来源、输入哈希与 feature matrix 在 [runtime_profile_rev4.json](workstation_task_20261030/runtime_profile_rev4.json)，逐编译单元／include／端口归属在 [runtime_profile_rev4_source_audit.json](workstation_task_20261030/runtime_profile_rev4_source_audit.json)，测试源码哈希、容量、旧新输入差异和状态在 [runtime_profile_rev4_verification.json](workstation_task_20261030/runtime_profile_rev4_verification.json)。测试脚本作为验证证据绑定哈希，不作为产品输入锁；候选身份仍绑定完整产品来源、准备快照、staged 闭包与固件工具／产物。

## 来源与安装边界

唯一 runtime 编译 provider 是 `workstation_profile_runtime.sv`。它在同一 `WORKSTATION_RUNTIME_NATIVE` 宏作用域包含 top 和 `workstation_profile_hdmi.sv`，随后撤销宏；HDMI wrapper／implementation 不再重复独立编译。新显示、TF、音频与 guard 各自留在所属子系统，没有生成新 RTL 实现或复制完整生产工程。

被替换的父输入保留原字节并禁用编译。维护 TF transport 因路径与父文件相同，明确安装到 `rtl/runtime_replacements/scope_tf_transport.sv`，清单绑定原维护来源与实际目标。controlled services 保留父 prepare 已受检 timing 变换后的字节，另选择维护原生实现；其余 runtime 替换同时检查原父字节。display layout package 与维护 `.svh` 完全同字节，保留父工程首项编译顺序，清单记录版本化等价来源，避免重复 package 或先 import 后定义。

维护 feedback capture／analysis／renderer、minor 1 writer／reader 和分析／调度组合被明确选中，原 output capture／wave align／analysis ROM 等共享支持仍来自锁定父输入。HDMI runtime export-read 输入显式接零，防止旧共享读端成为无 driver 输入。metadata rate／epoch／PCM／effect mask／order 通过完整原子 tuple 传播；上游丢帧另有连续 50 MHz sticky 通知。

BLE 的新 `relative_rom_paths` 只由 runtime profile 显式启用。生成头只引用 `native_bluetooth/rtl8723ds_patch.mem`，配置绑定生成器与原 vendor patch 的哈希；复制后的候选可在自己的 stage 内解析并核对 ROM。默认入口仍使用原绝对候选路径，vendor 字节未修改。runtime metadata 将 capture 来源准确标为最终物理 PCM 的 48 kHz observation。

来源锁还吸收旧 revision 3 清单后已独立提交的三项维护修正：`8296364` 的 scanout underrun pipeline、`89524c8` 的 Push guide snapshot、`8354b66` 的 model-ready 同步级传播约束。A2／D5／C1 历史参考哈希继续保留，当前字节不同的项目在逐文件对照中明确标示；冻结 baseline、vendor、原网表与历史报告未改写。

## 漂移与约束检查

准备和 verify 都重算完整源码快照，拒绝内容变化或新增输入；所有维护拷贝都有唯一安装位置。配置 revision／值、来源锁／glob 库存、编译选择、每个 staged 文件、AE350 证据目录、安装 ROM、USB 固件、BLE 生成头／ROM、feature 或硬件状态被改写均会失败。

旧端口审计曾直接解析含条件宏的 raw top。本阶段改为预处理实际启用的唯一 provider，再严格比较端口与最终 pinout／combined CST。runtime 唯一新增的 `clk_16m9344/J19` 必须同时有受锁定 probe 证据和补充约束；缺失、额外或重复端口／provider 都拒绝。该函数只证明来源和端口，不扩大旧 physical CDC 检查器的覆盖范围。

新 SDC 保留适用约束，并逐行记录替换层级的 54 条省略约束，继续标记 `cdc_constraints_complete=false`。guard 的 registered Gray 首级传播按真实 `ddr_ui100=100 MHz` 限制为 10 ns，仅豁免 hold，不 false-path setup；各 bit 的非负传播上限同时给出 10 ns skew 上界。端点解析和真实 routed bound 仍未证明。省略条目里含有其他仍适用端点的混合命令，也必须在完整端点审计中逐个补回并核对；所有新 runtime CDC／held payload／Gray／reset 路径仍需审查。

## 验证

真实三网表与 xPack RISC-V GCC 15.2.0-1 运行 prepare、profile verify 均成功；USB 与 AE350 从维护源重编译。USB binary 21,380 B，静态 RAM end 27,228 B，剩余栈容量 38,308 B。AE350 binary 10,840 B，RAM end 572／8,192 B，栈容量 7,620 B，保留最少 4 KiB；容量不等于完整调用链或硬件栈水位证明。

| 验证 | 结果 | 范围 |
| --- | --- | --- |
| Profile 与篡改回归 | 17／17，无跳过 | 实际 runtime＋默认 prepare、严格配置、来源／固件／ROM／闭包／状态篡改、复制后 BLE ROM 解析 |
| Runtime 来源与端口 | 7／7，无跳过 | 实际 253 units 的 `SYNTHESIS`＋relative-include 预处理、所有活动 include 来源、module/package 重名、默认／runtime 端口和 J19 |
| 默认准备定向回归 | 5／5 | 完整 prepare、旧 top tokens、CLI 隔离、固件失败不可部署、缺源不物化候选 |
| Current workstation 选源回归 | 10／10 | accepted 输入边界与锁定来源保护 |
| Python 语法／diff 空白检查 | 通过 | 本阶段工具和测试 |

未指定 profile 的真实候选 `native-runtime-profile-legacy-v2` 仍为 a26、230 项启用输入、旧 FPC、父锁定 AE350 ROM、原 BLE 绝对路径策略，没有 runtime／profile scan admission。accepted、pinned 和独立 resource 的入口与锁定输入策略未变。父级另核对旧 top 两个宏关闭分支的 6147／6867 tokens 完全相同，证据位于 cache 的 `runtime-top-default-token-compare.json`。

最初候选 `custom138k-workstation-v1-eeca04948a6f07bb` 保持不可变。v2 与它的启用输入列表完全相同，560 项 staged 中仅 HDMI 实现、对应 provenance 和 BLE path header 三项改变。v1 的绝对 BLE 路径仍依赖原 prepare；v2 已关闭这个缺口。逐项旧新 SHA 留在机器清单中，旧综合不能换名作为新候选结果。

## 仍未完成的整机边界

memory guard 只在首次准备好时授予启动，之后 backend／PLL／heartbeat 失败永久关闭双向事务通道直到 common reset。`started` 身份保留，不能因后端恢复重置 notes、参数或 stream epoch；源级接线及 guard 单元验证不能替代真实 arbiter／DMA 下的全链证明。video reset 仍可重置当前 DDR 客户端，完整视频与 DDR reset 解耦尚未实现。

上游 observation loss 在 50 MHz 撤销新显示发布／raster 资格并保持到 common reset，旧 framebuffer 可继续扫描。PCM 调度不能因此停顿；这不是允许显示回压音频。两个采样率的物理 clock／DCS／mute／prefill、全部 CDC 和 PLL、整机资源／feature preservation／routed timing 仍需单独验收。

BLE format 1 短录音仍是 48 kHz，44.1 kHz observation 被拒绝；真实短录音 busy 到换率服务的互锁、非零乐音、Android 与 AE350 business ownership 仍有整合缺口。TF 继续使用已有 DDR staging，只有匹配当前 rate 的 WAV 可进最终路由，不自动换率或重采样；EOF 没有 ordered drain／播放成功证明，busy 保持到显式取消。长录音、D mode、USB 图像迁移及完整设备验收不能继承本阶段结果。

本阶段没有启动整机综合／P&R、操作 JTAG、下载 SRAM 或写 Flash；实际整机综合由父级在完整逐哈希复制的独立候选执行并另报。`place_route_passed`、`physical_gates_passed`、`hardware_tested`、`sram_programmed`、`flash_programmed`、`deployment_allowed` 均为 false，`bitstream_sha256=null`。脚本继续封闭 P&R／部署入口；用户已授权的后续操作仍须各自完成实际物理门禁和独立证据。

## 复验与回退

输出目录必须新建，命令沿用 [profile 使用说明](../boards/custom_138k/WORKSTATION_PROFILE.md)。对最终现有候选可执行：

```sh
PYTHONPATH=projects/138k/push2_workstation/usb_a python3 -m tools.workstation_profile verify \
  /Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2
GW138K_PROFILE_PREPARED=/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2 \
GW138K_PROFILE_LEGACY_PREPARED=/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-legacy-v2 \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_profile.py
GW138K_PROFILE_PREPARED=/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2 \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_sources.py
```

prepare 原件保持只读，综合应复制全部 560 项 staged 文件并逐哈希复核。源码策略回退可省略显式 profile，恢复未改动的默认 native 准备；硬件回退仍依照架构文档链接的独立已接受部署证据，本阶段不改变板上内容。

父级独立复验：live profile verify 通过；profile 调用 17 项中 16 项通过、仅默认候选 fixture 跳过，随后单独以 legacy-v2 运行该项并通过；源码／端口 7 项全部通过，253 单元／284 module／2 package 的声明与 includes 归属结果与子代理逐项相等。所选顶层端口来源另以最终校验器独立重算并与机器证据相等。已复核最终 top 哈希及 6147／6867 默认分支 tokens；顶层语法检查零诊断，但其 `-i` 忽略子模块，不能当完整 elaboration。父级记录加入 verification JSON。
