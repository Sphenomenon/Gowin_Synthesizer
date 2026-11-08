# 双 138K v37：完整综合与消费者证明收尾

M/W 完整综合审计分别 **29/29、26/26** 通过。W 原消费者证明失败、M 新网表消费者清单及 TF receipt 的分组比较证明已闭合。本阶段仍是源码／综合检查点，**没有 v37 P&R、位流或时序闭合结论，不放行上板**。全部配置、输入、网表、复用收据和验证哈希见[机器记录](DUAL138K_TASK3_PREBOARD_V37_20261108.json)。

| 板 | v37 候选后缀 | Register / LUT / ALU | 综合 BSRAM 等效 / SSRAM |
| --- | --- | --- | --- |
| M | `33632cd650f42875` | 58680 / 70629 / 18339 | 212 / 242 |
| W | `f4d596b8e1744006` | 46758 / 58601 / 15934 | 253 / 779 |

两板复用 v35 的完整实际综合，原综合耗时 M 224.285 s、W 197.305 s。逐字节检查全部 RTL、固件、ROM、IP、工程和选项不变；只允许收据中列出的非编译证明工具变化，核验它们未被工程、HDL、include 或脚本引用。v35/v36 的失败审计原样保留，未改旧输入、网表或历史锁。综合 BSRAM 等效不能替代物理块数。

## 修复与真实故障验证

W 显式选择一内存拍的完成发布：本地完成仍在原边沿退休，私有完成计数快照冻结后再发布 ACK/计数。默认路径和其他配置不变。12 个协议与完整参考用例比较原有 117 个寄存器、189 个信号、24 个输出，以及 FIFO/native bridge/cache；包含同拍取消／故障和错误计数。该 twin 先于映射检查器新增代码，当前映射证明由 v37 完整审计另外提供，不能将两个证据范围混合。

M 的 TF 32 位 generation guard 分成四个保留的 8 位比较，不加状态或等待拍。真实 SPI/FAT/WAV→DSP/router/I2S 的 16 用例和远程分析 9 检查／5 场景通过；映射检查证明全部 32 个操作数和真实 active 消费者。busy/pause 被综合分配到更大的消费者方程，保留源逆变换及功能证据，未声称独立输出映射证明。

M 的声部分配可用信号采用 8 组四声部 OR，不改变候选位、索引或时序语义。四项原声部引擎回归及精确等价通过，来源／dispatch 链路 7 正向和 18 拒绝用例通过。TF16 结果早于此 availability 编辑；其覆盖与独立声部回归分别记录。局部综合级数改善不当作 routed slack。既有同拍 CC5 滑音、同边沿效果 slew 继续选入，混响保留 M。

M 目的消费者 v8 精确枚举 8370 个 FF 引脚，旧 v7 保持不变。14 个发生 D/CE／后缀打包变化的状态位，五个源 owner 字节一致，INIT、时钟及包含复位优先级的有效下一拍函数全部相同；无新逻辑状态、时钟、RAM 或顶层输出。精确 Boolean miter 均为 UNSAT，PRESET／CE／D 三个错误变异均被拒绝。这是基于同名状态对应关系的条件单步证明，不是整机归纳或异步事件等价。

完整 held 审计原先固定四条 abort/status NE 链，而新字节结构实际为七条。检查器现在先证明四字节的全部 32 位等式，再保留三个 abort 比较、源接受、34 个 queue、66 个 history 和 76 个 receipt 状态的完整方程。3 项实际网表测试拒绝 38 个错误变异；旧 v33 四链路径的正向兼容性也通过。17 项 accepted 输入边界回归通过，历史 baseline 未改。

## 物理阶段与复现

物理准备选用 M A12/W B13：M PANIC/PCM 精确源／接收区域、memory_release[2] 的 BUFG11，以及十五个真实注册 PLL 控制的更严格 5ns Q→PLL max；保留原 10ns 全传播审计、全部时钟和有限 min/max。M A12 首次调用在 CST 解析阶段被 CT1014 拒绝：功能 memory release 被错误标为 CLK，未进入布局、无 STA／位流；保留该失败，按厂商网络类型规则修复后另建身份。W B13 的 P&R 尚在运行，不在本源码检查点宣称结果。旧 A11 startup/mailbox 诊断及反例只证明其明确子集，完整 peripheral/FIFO/tail routed CDC 仍须检查。指定 DDR 初始化 hold 的 +2.429ns 是旧 A11 结果，不能归给 v37。

实际重建继续使用维护入口，在 usb_a 根目录执行：

```sh
python3 build.py --prepare-custom-board --workstation-profile custom138k-workstation-task3-m-preboard-v1 --custom-board-output <新M目录> --netlist-dir /Users/sphenicidition/.cache/gw138k-cnn-demo-20261102/netlists --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf
# W 将 profile 中 m 替换为 w，并使用独立输出目录。
# 在每个 workstation/Prj1 中以 Gowin gw_sh 执行 scripts/custom_board_synthesis.tcl。
python3 -m tools.workstation_custom_board_audit <候选目录>
```

Gowin 使用已记录的 IDE 安装及其 lib 环境；完整命令、cwd 和输入哈希见原综合 invocation。物理 reference 模式、约束参考及保留要求沿用[收尾报告](DUAL138K_TASK3_PREBOARD_20261108.md)的复现说明。缓存监督脚本不是唯一生产输入。

最近完整物理结果仍是 [v28 A11/B12](DUAL138K_TASK3_PREBOARD_V28_20261108.md)：M 253/340、W 287/340 BSRAM，setup 分别 −4.013/−3.028ns，其余失败和位流原样保留。下一阶段统一 P&R、资源、STA、PLL/startup 和必要 routed CDC；任何未通过项继续阻止加载。

M 保留普通32／矢量8声部、本地效果和最终输出；W 保留真实 CNN、手机接收解码及唯一录音对象。CAP3 持续手机准入仍关闭。回退为 `bff8dd10`、v33 源码／综合检查点与 v28 冻结物理包，task2、单板及其他历史输入未改。

本轮未连接、识别或操作板卡；[SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)继续准备正确目标、接线、加载、独立读回、回退及功能验证。真实 LCD 吞吐、DAC 延迟和整机演示留到上板阶段。
