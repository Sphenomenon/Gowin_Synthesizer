# 双 138K v33：M 原生 PCM 入口隔离

M/W 均重新完成完整综合，门禁分别为 **27/27、25/25**。M 新增一级有界原生 PCM 暂存，隔离 A11 已发现的取消／下游背压至原生 RAM CEB 长路径。**本轮未运行 P&R，没有 v33 位流或新物理时序结论，仍不放行 SRAM。** 配置、逐文件输入、网表及验证结果的 SHA-256 见[机器可读记录](DUAL138K_TASK3_PREBOARD_V33_20261108.json)。

| 板 | v33 候选后缀 | 综合耗时 | Register / LUT / ALU | 综合 BSRAM 等效 / SSRAM |
| --- | --- | --- | --- | --- |
| M | `daae0514f9cfd53c` | 216.54 s | 58680 / 70361 / 18345 | 212 / 242 |
| W | `24b07105ddac895e` | 187.74 s | 46724 / 58615 / 15936 | 253 / 779 |

两次综合输入无漂移。综合 BSRAM 等效不当作物理 BSRAM；最近完整布线结果仍是 [v28 A11/B12](DUAL138K_TASK3_PREBOARD_V28_20261108.md)：M 253/340、W 287/340，四项 STA 分别为 M −4.013/−1.957/−1.500/+0.278 ns，W −3.028/+0.042/+1.608/+0.281 ns。那些失败候选的位流哈希和 UserCode 保留，不能归给 v33。

## 已选修复与验证

暂存在 `workstation_tf_direct_runtime_service.sv` 内，容量一帧，只有显式 M preboard 选择启用；默认关闭。原生 RAM 接受只看本地空槽与 PLAY 状态，最大每两拍接受一帧；槽满背压。PCM、尾帧、session 与采样率共同保存，同拍取消仍禁止发布并丢弃暂存，不改变基础音频采样时基。

真实 SPI/FAT/WAV→DSP／router／I2S 的 16 个用例通过，覆盖 44.1/48 kHz 的播放、暂停、取消、STOP、PANIC、非法曲目及在途取消／STOP；冷启动经过实际 memory guard，输入无漂移。远程分析 9 项检查、5 个场景通过。17 项 accepted 来源回归通过，历史路径仍按精确逆变换比较。

新实际网表门禁检查 9 个 RAM、27 个使能引脚，证明 session／receipt／M endpoint 组合依赖已隔离，读 CEB 保留真实 head-valid 支持；检查头寄存器的源时钟、初值、常开 CE 和 source-release 的反相 CLEAR。时钟／复位错误、恢复 session 依赖、读端旁路和缺失 RAM 均被拒绝。首次检查错误地将 Gowin 高有效 CLEAR 当作 release 原值，第二次把 RAM 同名前缀组合单元计入 RAM 清单，均保留失败日志；修正为实际反相方程及原语清单后通过，不修改网表。

M CPU 目的消费者 v7 锁定 8374 个 FF 引脚，逐项核对类型、初值、时钟与 D/CE/CLEAR。只有 `head_valid` 是新增 RTL 状态。其余新增名字是既有状态的映射拆分：`wr[3:4]` 在 v28 共用 `accepted_3/4` 的 Q；有界 timer 的上位现在分别映射。link／analysis-source owner 源字节不变，TF quiet-wait 原有更新方程不变。27 个原生入口 count/read/held/tail 状态和 9 个 RAM CEB 离开此 closure，无新增时钟、RAM 或顶层输出。实际消费者与 MIDI/paired-release 3 项正向及破坏控制通过；head/compute-release 4 项测试通过。

v29 prepare、边运行边改源码的早期 TF 原型、错误的“七个 exact FF 已存在”断言均保留，不引用为有效通过证据。v31/v32 是检查开发期间的准备诊断，没有综合或物理运行。

## W 诊断与剩余门禁

补充 v28 的后续结果：B12 **routed PLL 子门禁通过**；实际 routed 组合检查及缺失 PLL、视频复活、DDR CE/stage 旁路反例拒绝通过。这不消除 B12 −3.028 ns setup，也不等于整板 CDC／时序接受。

W 完成计数发布实验尚未选入生产。它保持本地请求原拍退休，把 ACK 延后一个内存时钟；私有快照准备计数后才发布。CAPTURE_COMMAND=0/1 × 3 种时钟比的 6 组录音协议检查，以及归一化该 ACK 延迟后的 6 组完整参考对比均通过。其余 117 个原有寄存器、189 个公共／内部信号、FIFO、native bridge 和缓存按拍对比；私有完成计数在发布后逐位对比，包含错误计数。独立实际综合中故障至完成计数 D/CE 的组合路径从 7 级变为不存在，Register +34、LUT −129、ALU −1，BSRAM 不变。仍须生产选择、完整 consumer/CDC 证明及整板物理结果，不能当作已修复 W setup。

下一阶段继续处理 M expected-generation→PCM／效果和 oscillator→event 路径、PCM/PANIC hold、DMA 功能 recovery、当前物理 startup/DEMO 证明及真实 PLL 传播预算；W 集成完成发布修复。整合后统一构建／P&R。M 保留本地混响、普通32／矢量8声部和最终输出；W 保留实际 CNN、手机接收解码及唯一录音对象。CAP3 持续手机准入仍关闭。

task2、单板及历史候选未改，回退基点为 `805d8079` 和 v28 封存输入。正确目标、连接、加载、身份独立读回、回退及功能步骤见[SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)。本轮未访问硬件，真实 LCD 吞吐、DAC 延迟和整机演示继续留到上板阶段。
