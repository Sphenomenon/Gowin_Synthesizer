# task3 双 138K 上板前收尾（2026-11-08）

本轮止于离线候选和 SRAM 验证步骤，不识别、连接或加载板卡，不写 Flash。M 保留交互、唯一参数应用点、普通 32／矢量 8 声部、基础音频、本地混响和最终输出；W 保留实际 CNN、手机接收／解码及唯一录音对象。task2、单板及所有冻结失败候选继续保留。

## 当前状态

收尾进行中。v21 完整综合审计已通过 M 26/26、W 25/25；M A8 因时钟网络资源分配失败结束，W B7 已完成但 STA 未通过。正在准备有诊断依据的 A9／B8 物理修正，尚不能加载本轮中间位流。两板本轮编译字节与各自已完成的有效综合完全一致，复用综合后对新身份重新执行了完整审计。候选目录及证据位于 `/Users/sphenicidition/.cache/gw138k-task3-20261108/`，后续以本报告最终表格和完整哈希清单为准。

| v21 综合审计输入 | 候选身份后缀 | 配置 SHA-256 | 完整审计 |
| --- | --- | --- | --- |
| `m-preboard-prepare-v21` | `efb3c440adaf9cf6` | `94e15ebce001b27b9e27865f9953d4742c9c5edd9561b99dfb218d97ca968c5c` | 26/26 |
| `w-preboard-prepare-v21` | `6de492194395db37` | `5212dca8a3383a051cb901653ab01ef654a968b80bbdd7db3651bf1272c91ab1` | 25/25 |

v22 已封存当前布局修订及检查器，M 身份后缀为 `eb5787e6837a0a43`，配置 SHA-256 为 `ecf3e2fe7f381bd03acfc1d3bb6cdba28c5a9b4696b3452d04e3935555884909`；W 为 `96d052186a73ae48`，配置 SHA-256 为 `b1b644a7ab17aa78acf6b18c35bda318c94a412ea23a53bf5ac54438ec9c957f`。两板全部暂存字节、启用顺序与已做双目录复现的 v20 相同，严格综合复用记录各绑定 7 个产物；只更新来源锁及外部物理检查，不替换旧候选身份。v22 的 17 项 accepted-source 检查通过，完整综合审计 M **26/26**、W **25/25**；阶段身份及证据哈希见[源码与综合清单](DUAL138K_TASK3_PREBOARD_SOURCE_20261108.json)。

## 本次修复及验证范围

- M 的 CC5 滑音系数在同一次参数提交中应用，保留真实采样捕获边沿；效果 slew 保持原更新边沿，配置／history 事务先保留，再交付 held 配置。普通 32／矢量 8 声部和本地混响保留。
- M 的 PCM bitmap 权限、TF 错误存在判定和品牌字形取址按实际长路径拆解。TF 功能 compute FF 使用已有本域 release；root 仍异步断言，不把会话取消当 mailbox reset。
- W 的完整 128 位会话比较分成 16 个精确字节比较，早级 release 消费者完整核对。raw DDR 命令先在 DDR 域锁存 89 位 tuple，下一拍才开始业务；旧默认参数保持。
- 新物理结果又暴露两个同域故障：M TF BPB geometry → read-sector CE 为 −4.569 ns，W HCI active → phone ARM boot CE 为 −1.548 ns。前者改为真实扇区完成后八拍计算，计算完成前保留 inflight，后者先捕获 ARM tuple／资格，下一拍检查当前身份和原始撤销条件后应用。SPI、取消、超时和 generation 退役语义保留。
- 源码来源仍由原始 CRC/FAT-cache 锁及严格逆变换校验。新 geometry adaptation 独立记录，未修改原始 manifest、vendor 字节或历史描述符。
- M CPU release 的新网表有 8371 个 FF 消费引脚，仍在既有已审查状态族内；新标签比较综合造成的 29 加／29 减打包变化独立记录为 inventory v5，保留全部旧清单。时钟、RAM 和外部输出清单保持逐项检查，不按前缀放行；v5 定向测试和 v21 完整 held 证明均通过。
- M 回执的 epoch 比较实际映射为 31 位 carry 链加最高位 LUT；正式证明包含全部 32 位，最高位未作任意控制切点。37 个既有破坏反例及 4 个新增漏位／错位／LUT／carry 反例均被拒绝。W ARM 捕获后重新核对完整 key equality、load 和 flight 的实际逻辑；新综合网表按实际 INIT 选择两种已逐项审查的逻辑因式分解形式，69 个来源／网表破坏反例全部被拒绝。保留局部证明与完整状态机证明的区别。
- F808、M PANIC、M HCI session 和 W raw-command 的 held 数据有实际源／接收及完整消费者证明，使用有限 max 10 ns／min 1.8 ns，保留 hold。B6 的 F808 数据短线仅 0.36 ns，源／捕获共 164 个数据 FF 现按精确清单分置两区；保留原 min/max 和时钟。同步器例外只到已证明隔离的采样级／release CLEAR；不切功能 CLEAR。
- B6 音频 held 标签到串行器序号 CE 为 −5.483 ns；现将 64 位标签比较拆成八个保持同拍语义的字节谓词，无新状态或等待周期。真实双时钟／双采样率 I2S、背压、超时、旧流回复和源错误回归通过；实际新 W 网表的八个谓词全部核对，八个破坏比较均拒绝。
- B6 还暴露 CNN staging FIFO Gray 最高位别名未命中旧 `*gray*` 选择器。现证明三位 binary、两位独立 Gray 的 next-Q、最高位别名及首级完整消费者，再为该位保留 10 ns flight 上限、首级 hold 例外及后级 2 ns 上限。broker fault、memory-failed 和 transport-fault 的实际两级同步链只对隔离首级 D 给异步例外；六条链和七个破坏反例检查通过。transport fault 包含加密 DDR 状态，不声称证明所有来源 FF。
- DDR 初始化继续用相同加密输入和实际旧 VO 核对结构及相对角区域，功能 reset max 7.5 ns 保留。Gowin 的 `set_min_delay` 替换 hold 边沿关系，不能当作插线延迟命令；3.5→4 ns 的试验使要求增加 0.5 ns，但实际数据延迟仍约 4.65 ns。现恢复原始 min 0.8 ns 有限要求，保留修复短线的远距布局、实际时钟偏斜及全部原生 hold 检查。4 ns 失败证据不改写；新物理结果通过前不宣称修复完成。

真实 SPI/FAT 回归通过 56 场景及 8 个破坏反例；ARM 捕获通过 23 项定向检查；PCM 分块、typed bus、真实异步 APB/PCM1 owner 与音频端点回归通过。17 项 accepted-source 检查通过。滑音提交、效果增益、TF 错误、消费者和 CDC 的定向破坏反例分别保留原日志。

真实 C 固件＋理想 LCD／PCM1 模型完成 20 ms 窗口回归：两个 W 时钟下，生产配置均拒绝未获持续吞吐准入的手机启动；显式注入能力的有限手机／三路并发模型每组完成 8 次 COMMIT、无 owner failure。它不证明实板吞吐、RF/SBC、持续音频、LCD、DAC 或端到端延迟。CAP3 生产准入保持关闭，待上板实测后按原合同验收。

## 保留的失败证据

| 冻结物理候选 | BSRAM | setup / hold / recovery / removal（ns） | 状态 |
| --- | --- | --- | --- |
| M `D21108A4`，`m-preboard-tight-p2r0-v4` | 253/340 | −7.100 / −1.059 / −5.630 / +0.265 | 失败，保留位流及原始报告，未部署 |
| W `D21108B3`，`w-preboard-tight-p2r0-v3` | 287/340 | −3.121 / −1.055 / +1.370 / +0.281 | 失败，保留位流及原始报告，未部署 |
| W `D21108B6`，`w-preboard-physical-v6` | 287/340 | −5.483 / −2.855 / +0.865 / +0.134 | v16 综合审计全通过后的完整 P&R，仍失败，未部署 |

B6 的额外剩余 setup 族包括 recording tag→raw-store／delay-DMA（约 −0.617 ns）、CNN descriptor→endpoint（−0.616 ns）、CQT sample→signal RAM（−0.613 ns）等。DDR 在 4 ns 试验要求下为 −0.782 ns。新结果必须重新检查全部 setup、hold、recovery、removal，不能只复查最差音频路径。M `D21108A7` 仅准备了物理输入，尚无 P&R 或位流，不列为可加载候选。

新候选不能继承这些候选的通过项或部署身份。中间 prepare、审计调试失败和拒绝加载门禁均保留；检查器变化与 RTL 变化分别绑定。仅在全部编译输入、顺序、工程、脚本、ROM 和 IP 字节一致时复用综合；显式允许的非编译变化限于未被工程或 HDL 引用的 W 来源检查和 M 回执证明 Python 工具，旧／新哈希单列，仍需新候选完整审计。严格默认模式已实际拒绝变化的 M 工具，只有显式非编译审查模式才复用网表。

## A8／B7 后续诊断

- M A8 的 `run pnr` 返回失败，保留全部原输入及失败日志；报告的 8 条 PRIMARY、8 条 LW 已满，三路外部实际时钟没有专用网络。相同器件的最小网表实测 `BUFG[8]` 使用 LW，`BUFS` 不支持。A9 为 ULPI、12.288 MHz、16.9344 MHz 明确预留 LW8–10，将三条实际复位发布网指定为普通布线；不改变频率、SDC 或功能。实际网表输入、唯一发布者及时钟域均核对，重复约束及三项断开输入反例被拒绝。
- W B7 为 287/340 BSRAM，setup/hold/recovery/removal 为 **−7.666/−0.919/+0.185/−0.011 ns**；位流 `26592c4511abb2cd6f7d08e13bef9ce92ce5c857d8f0b2d69e167d4bbeaa452e` 保留为失败证据。最差 setup 为 DDR 返回标签至 delay DMA，17.478 ns 数据路径主要来自跨区域布线。B8 对 9147 个实际 native DDR／raw-store／delay-DMA 原语施加局部区域，另按完整清单分离 280 个 command/completion held FF；保留 payload min/max、同拍 fault 和原生 STA。raw-store 的两级 release CLEAR 及隔离的 memory-up 首级 D 经实际逻辑与完整首级消费者证明后加入例外，功能消费者不切。
- W 无视频组合的 PLL／启动／保留邮箱检查已覆盖实际四 PLL 及真实 W 网表；定向检查拒绝缺失 PLL、视频逻辑复活、DDR CE 损坏和 startup 级绕过。完整审计及新物理结果仍须单独通过，不能把检查器修订记作时序改善。
- B8 的约束解析发现 5 个综合 INV 名称已被 P&R 吸收到原语极性，报 CT1135；该调用已停止，未形成物理候选。局部布局修订为约束 9130 个可放置寄存器／LUT／ALU／MUX，不为 INV 指定位置，280 个 held FF 原清单保留。定向实际网表和破坏反例通过；v22 对两板重新 prepare，全部编译输入逐字节相同后复用综合，完整审计分别重跑。

- M A9 已完成 P&R，物理 BSRAM **253/340**、CLS **61129/69120**，setup/hold/recovery/removal 为 **−3.909/−2.867/−7.854/+0.284 ns**。位流 SHA-256 为 `a0da9fea692a8c865ac0249c55059dd88b2b6df97227fa951338d393d5698dda`，未放行、未部署。三路实际时钟的普通布线警告消失；50 MHz 输入仍有一条警告。首级 owner-live 同步器的 D、PCM session release/live 的 CLEAR 需要按完整隔离与释放证明补齐约束；PANIC held 数据短线仍须修复且保留 hold。实际同域长路径包括 command-ID 至 PCM bitmap（18 级逻辑，16.472 ns）、PANIC 至 cue/player、TF session 至 source/record、矢量包络，不能用同步器例外遮盖这些路径。W B9 使用 v22 与修正后的局部布局运行，尚待结果。

## 可复现输入

v20 在两个独立输出目录重复 prepare：M 707 个、W 697 个暂存输入及启用顺序完全相同，固件内存镜像也相同，见缓存 `diagnosis/prepare-reproducibility-v20.json`。M 两次编号均为 `4d9acb481b632c8b`；W 正式审计输入为 `c9c83f8917ae8f90`，重复目录为 `79e0f5d1bbfd3e23`。W 编号还封存带输出目录路径的 stack/callgraph 诊断及其元数据，故编号不同；不把两个运行身份混用，也不把诊断路径变化说成硬件输入变化。此检查证明 prepare/编译输入复现，不声称第二次 P&R 位流逐字节复现。

重建继续使用现有入口 `build.py --prepare-custom-board --workstation-profile custom138k-workstation-task3-{m,w}-preboard-v1`，明确 `--custom-board-output`、已锁定的 `--netlist-dir` 和 xPack `riscv-none-elf` GCC 15.2.0-1 前缀。随后在各自 `workstation/Prj1` 执行 Gowin 的 `scripts/custom_board_synthesis.tcl`，使用 `python3 -m tools.workstation_custom_board_audit <prepare目录>` 做完整审计。物理准备使用现有 `tools.workstation_custom_board_implementation` 的 reference 模式、`--preboard-releases --primary-clk50 --preboard-ddr-reference`，M 另选 `--task3-pin-collections`。参考 CST、相同加密输入的旧 DDR VO/元数据和全部哈希必须与候选包一起保留，不能只留一个本地 latest 指针。缓存脚本不是生产来源或必需构建入口。

## SRAM 清单及回退

操作步骤见 [SRAM 验证清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)。本轮不执行该清单。正确目标板、线缆和链位置须独立识别；当前电脑连接的其他分支板卡不是默认目标。保留 task2、单板、M v21／W banked96 及本轮各中间候选；回退只使用各自冻结文件及原哈希，不把失败位流列为可加载版本。

后续仍须独立验收真实 LCD 有效吞吐／RTT／拥塞、TF→W CNN→Push、手机 D 按放效果、M 最终输出→W 唯一录音／封口／下载、DAC 延迟、连续性与整机演示。离线模型、综合、布局布线和 SRAM 身份读回分别记录，不互相代替。
