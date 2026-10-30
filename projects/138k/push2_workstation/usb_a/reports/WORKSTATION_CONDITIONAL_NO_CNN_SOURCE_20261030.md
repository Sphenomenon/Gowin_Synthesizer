# 显式 no-CNN 候选：源码与离线准备（2026-10-30）

[F8/F9](WORKSTATION_RUNTIME_F09_RESOURCE_FAILURE_20261030.md) 两次同输入实际资源 P&R 分别留下 8,083／32,709 条未布通网络，已满足用户的条件裁剪前提。本阶段在 `b59a4a5` 的 PCM 约束和跨域控制输出注册修复上，增加独立 `custom138k-workstation-no-cnn-v1` revision1；旧 `custom138k-workstation-v1` revision5、accepted、pinned、resource-only 和无 profile 默认仍保留识别。两次失败的物理结果不转移给新输入。

registry 是配置／编译入口／能力元数据的统一权威。新入口只以局部宏包含原 runtime provider，随后撤回宏，不复制整机。源组合不实例化完整 `u_music`、CNN score FIFO 或 song-command CDC，USB owner 不实例化 guide/menu consumer；model_status=0、result/score/done=0，DDR 请求为零且 mask 全屏蔽，五个共享 Flash pad 经原 guard 释放为 Z。没有伪造模型 ready，也没有回收 NN 地址池、recording granule305 或声称释放共享 PLL。

关闭配置的 PC UART 无需模型加载即可进入原演奏路径；TF restart／track 保留原始控制，cancel、stop、拔卡、采样率拒绝及已受理读事务 drain 仍归原 owner。Push 分析曲目菜单／跟奏不可用；85 回到本地 cue，44／45／48 走既有 CC108／CC90。generic CC110／111／112 继续本地消费，25K 隔离保留。CPU 手工 LED cue、本地 256-cue score、REC、service CDC、MMIO0x60 非 CNN 字段及0x64服务 mask 保留。公共参数、实时音频、效果、FFT／XY／meter、USB／BLE／AE350未由本开关改写。实现与退出策略见 [RECOGNITION_POLICY.md](../rtl/workstation/RECOGNITION_POLICY.md)。

两份实际 prepare 使用同一显式 xPack 编译器和三个锁定 netlist，均成功并经来源复核：

| 项目 | 默认 enabled | 显式 disabled |
|---|---|---|
| profile | `custom138k-workstation-v1` revision5 | `custom138k-workstation-no-cnn-v1` revision1 |
| integration identity | `custom138k-native-dual-rate-runtime-revision5` | `custom138k-native-dual-rate-no-cnn-revision1` |
| candidate | `e75f17baaa084543` | `7c57812471a5e336` |
| config SHA256 | `8ef954a5a5db16eca7b54eddfc800be0a269f16b8bbcb2d83a270294b7328e72` | `8907b17a341351e5284f067e728c6eafa0c00ebe0f604a5b21f0fb93bce0dad4` |
| source lock／snapshot／staged | 317／742／570 | 325／742／571 |
| enabled entries／source compilation units | 259／256 | 259／256 |
| 完整 SDC 行数 | 320 | 301 |

表内 candidate 后缀分别以前述 profile 名为完整前缀；完整输入摘要、配置、stage/source hashes 和验证范围见[机器证据](workstation_task_20261030/conditional_no_cnn_source_checkpoint.json)。两个 prepare 的共同 staged 文件只在 GPRJ 和 SDC 有字节差异；disabled 额外暂存极小入口，原入口保留为依赖。识别模块定义继续保留于来源闭包，不能把定义数量当成实际综合层级或资源节约。

enabled SDC 与父级 `1aea3c01fa6c1b14` prepare 逐字节相同。disabled 只退役十九条完整的 CNN 专用既有行，集合 SHA256 为 `d1eb3a7588f267fdf32dc7e032bf0b5bda6891f7eaab29a1df5e76ef90e93689`；逐行唯一锚点、原始行号、输入／输出 hash 可重建并复验。未知、漂移、重复或混合 live endpoint 查询均拒绝。其余约束逐字保留，包括本地服务 CDC 和新增 PCM 五十行；未新增宽 false path 或改变时钟。

验证已完成：

- enabled 通用 profile **20/20**，含显式无 profile prepare 对照；enabled／disabled 来源审计各 **12/12**，accepted 来源 **10/10**。
- 新识别 profile **7/7**；覆盖默认／历史入口 token 保留、完整 producer／专用 CDC 移除、宏不泄漏、exact SDC 及 drift／mixed query 负例。实际 prepare 的身份、混合 provider、能力、runtime provider、artifact alias 与 CLI 错误 profile 七种篡改均拒绝。
- 八项行为检查通过：默认播放策略与旧提交 cycle miter 8,247 检查、226 enabled cycles，关闭分支 487 raw restart；真实 USB owner 的 13 音频事件、4 attach／3 detach／5 barrier／8 cancel；原 enabled guide 的85事件；Flash 五 pad Z；三种播放 mutant 和错误吞掉本地 cue 的 USB mutant 均拒绝。
- 最终真实 controlled 组合通过：1,078 physical／observed frames（48 kHz 361、44.1 kHz 717，977 nonzero），1,077 display frames、384 FFT bins、1,077 APB、33 USB、28 CPU 事件；含实际115200 PC UART、两次换速、REC／本地 cue 和失败边界。该 fixture 验证原 managed 路径，未代替整机顶层硬件验收。
- 最终 media policy 的自然 score 完成及三种 epoch 政策通过，每种11检查／5 core请求／10 TF stop／8 done／2 fail／11 seal。TF stop／clear 的原真实 transport 回归和1106事务／256 cue／16384 score-frame服务回归，其全部登记输入已重新核对当前字节一致。注册控制输出长期回归两测试／四仿真通过，包括两速旧组合实现负控。

prepare 原件在 `/Users/sphenicidition/.cache/gw138k-task-20261030/conditional-no-cnn-{enabled,off}-prepare-final`，完整仿真日志及输入 hash 见机器证据内的 cache 清单。初次草稿曾因默认 `riscv64-elf` 缺少 `string.h` 而准备失败，原失败目录保留；最终显式使用 `/Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf`。可用原 `build.py --prepare-custom-board --workstation-profile <名称> --netlist-dir <三个锁定netlist目录> --riscv-prefix <上述前缀> --custom-board-output <新目录>` 重建；已存在目录拒绝覆盖。

本阶段仅源码、prepare 与离线行为验证；未综合、P&R、JTAG、SRAM 或 Flash，bitstream identity 为 null，deployment_allowed=false。新网表的 CDC／reset／PLL、物理 auditor 的配置专用保留清单、双模式 routed setup／hold、净资源／时钟／拥塞比较及整机实板仍待完成。现有 physical auditor 的 runtime 缺口继续阻断；端口／来源检查没有升级为全量物理通过。未选入的 recording DDR backend／owner8、D mode 和138K BLE业务整合仍是原独立缺口。

回退时重新 prepare enabled 名称并使用相应新身份，不复用 disabled 身份或失败位流；若撤回代码，须一起撤回入口／registry／RTL能力分支／配置锁／测试及本阶段证据。冻结 baseline、原始 manifest、历史失败证据和当前板卡均未改变。

## 父级主线复验与明确选入

父级在主工作区按二十文件白名单导入隔离提交 `5d5a10ef434edde205ba4e24dfee826a31b17b1e`，重新执行两份完整 prepare。父级 enabled 身份为 `custom138k-workstation-v1-03b7a208e6bb6f2d`，disabled 身份为 `custom138k-workstation-no-cnn-v1-525ffff10d622031`；各自与上表隔离 prepare 的742项完整来源快照、259项启用输入完全一致，staged 仅 `native_usb_firmware/build.log` 因工作目录记录不同而改变。因此记录新身份，不把两个 prepare 当成同一候选。

父级独立运行并通过识别 profile 7项、disabled 来源12项、enabled通用 profile20项及来源12项、accepted来源10项，全部无跳过；另重跑八项真实行为检查，其中四个故意破坏版本均被拒绝。关闭配置301行 SDC 的 SHA256 为 `ead347d58729b7ac917ca6b27a0c0d65c598ac4cd8f8dcd7fa1cd127c19c4036`；保留所有现有时钟和非CNN约束。完整日志与 prepare 比较见[父级机器证据](workstation_task_20261030/conditional_no_cnn_parent_integration.json)。

依据已满足的条件授权，明确选择父级 disabled 候选进入下一轮资源／时序实验；从已复验 prepare 独立复制到 `no-cnn-synthesis-525ffff1` 并启动整机综合。这里只记录启动，综合与实际新网表、P&R结果另立检查点；没有资源节省、完整CDC、位流或板级接受。默认／accepted配置继续保留识别，当前板卡未由本阶段修改。
