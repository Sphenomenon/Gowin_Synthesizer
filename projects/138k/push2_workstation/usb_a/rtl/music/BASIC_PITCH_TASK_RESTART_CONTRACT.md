# Basic Pitch 任务取消与重启契约

适用源码是 `basic_pitch_workstation_link.sv` 中显式启用的
`DRAIN_RESTART_ENABLE=1`。它实例化维护中的真实 PCM → CQT → 六层 CNN →
Viterbi 流水线，使用原权重、DDR16 适配器和请求/响应 CDC FIFO；不是识别结果桩。
2026-11-01 源码与验证身份见
[`DUAL138K_TASK3_CNN_RESTART_20261101.json`](../../reports/DUAL138K_TASK3_CNN_RESTART_20261101.json)。

## 默认行为与集成状态

默认 `DRAIN_RESTART_ENABLE=0` 保留旧契约：`analysis_restart` 直接复位分析运行态，
PCM、结果和内存请求采用旧直通路径；新增状态输出为 ready=1、busy=0、fault=0、
done=`analysis_restart`、failure_code=0。这个模式不提供排空保证。
默认模式与启用模式的取消后新分析已用真实模型、相同 PCM、原生 DDR 通路比较，
六层哈希、各层写入次数与 Viterbi 输出相同。它不是对全部旧配置的形式等价证明。

目前没有 task3 W 整机 profile 选择并启用此边界。已有 W21 无 CNN 的候选不会因本文件
自动恢复 CNN。本工作提供实际 link 内的可选实现与离线验证，不构成 W 整机接回 CNN、
跨 LCD 传输或 Push 指导的集成完成证据。W 集成必须显式选择维护源码、启用参数、
连接状态端口、保存新输入与位流身份，并完成对应的资源、时序和硬件门禁。

## 请求、状态和 PCM

`analysis_restart` 不是标准 valid-ready 请求。当前实现的实际受理条件是
`state==RUN && armed && analysis_restart && !fault`，没有以 `restart_ready_o`
作为受理条件。调用者应在 ready 高时发请求，但不能据此假定 ready 低时请求一定被忽略。

| 信号或状态 | 启用后的实际语义 |
| --- | --- |
| `armed` | 全局复位后为 1；RUN 受理请求时清 0；任意状态采样到 `analysis_restart=0` 后置 1。 |
| `restart_ready_o` | RUN、已重装、无故障且同步内存 ready 时为 1；不包含模型上传/CRC 完成条件，也不是 PCM ready。 |
| RUN 收到已重装的高电平 | 当拍组合阻止 PCM、结果、score、analysis_done 和新 DDR 请求；下一拍进入 DRAIN。 |
| DRAIN | 旧请求和响应继续走原真实通路；拒绝新请求，等实际读写 ledger 相等。 |
| RESET_PIPELINE | 排空后对分析运行态和 44.1→48 kHz 转换器复位一拍；模型 loader 保持原全局复位域。 |
| RELEASE_PIPELINE | 再保持一拍隔离，然后回 RUN 并产生一拍 `restart_done_o`。 |
| `restart_busy_o` | 非 RUN 且无故障；故障后 busy 为 0，因此 busy 下降不代表完成，必须检查 done/fault。 |
| `restart_done_o` | 成功重启完成脉冲；无故障且同步内存 ready 才能输出。它不表示模型 ready、歌曲分析完成或新任务已开始。 |

一次受理后始终维持请求高电平不会重复受理；完成回到 RUN 后 PCM 可恢复，而
`restart_ready_o` 仍会因为未重装而为 0。请求在 busy 期间拉低会重新置 armed；若又拉高并
保持到 RUN，可能在返回 RUN 后受理下一次请求。busy 中没有请求 FIFO：不保持到 RUN 的
短脉冲可能丢失。推荐调用顺序为 ready → 请求高 → 观察 done/fault → 请求低至少一个
`clk_50m` 周期 → 再开始下一任务，避免把 busy 中的脉冲当成排队命令。

同步内存 ready 是 `memory_reset_n && memory_calibrated` 经两级源域采样的结果，
与模型 loader 的 done/CRC 状态不同。初次内存尚未 ready 时，任务 PCM ready、结果和新
内存请求被阻止；若此时在 RUN 发出已重装请求，仍会进入 DRAIN。只有内存 ready 且
ledger 相等才会复位并完成；否则到 `RESTART_TIMEOUT_CYCLES` 后故障。默认超时
50,000,000 个 `clk_50m` 周期，50 MHz 下为约 1 秒；应由实际 W 时钟与服务预算确认。

内存 ready 但模型尚未完成时，本边界不会以模型状态进一步阻止 PCM 或请求；
`pcm_ready` 仍取决于原流水线/转换器。原流水线在窗口完整且外部模型 done 后才开始 CQT，
不能把 `restart_ready_o` 或 `restart_done_o` 当作模型验证完成信号。调用者必须依据原模型
状态安排分析及上传，不得用本取消脉冲替代模型加载/校验协议。

取消隔离期间，44.1 kHz 转换器的输入 valid 和输出 ready 都被阻止；已有采样保持到
实际延迟复位才清除。结果的 valid、score 的 valid/ready 与 analysis_done 被隔离，
数值总线不另行清零。诊断 UART 可保留历史诊断，它不是新增的任务结果通道。
跨板 session/generation、输入 PCM 队列、识别结果接收及 PANIC 仍须由 W/M 任务所有者
按现有分层契约处理；该 link 不自行添加另一份共同参数权威。

## 真实事务 ledger

| 计数 | 增加条件 | 不能替代它的事件 |
| --- | --- | --- |
| `reads_accepted` | `bp_mem_req && bp_mem_ready && !bp_mem_write`，请求真实进入源域请求 FIFO | 流水线产生请求但 FIFO 不接收 |
| `reads_consumed` | 响应 FIFO 的源域 valid；原 read_ready 恒为 1，同拍真实弹出 | DDR 发起读或内存域刚生成响应 |
| `writes_accepted` | `bp_mem_req && bp_mem_ready && bp_mem_write`，请求真实进入请求 FIFO | 上游宣称写完 |
| `writes_committed` | 内存复位已释放、校准有效且 `ddr_cmd_valid && ddr_cmd_ready && write`；DDR16 ready 包含原生 DDR 实际接收 | 请求 FIFO 已弹出、命令 buffer 已装入 |

取消同拍的请求 valid 和返回 pipeline 的 ready 使用同一个 admission gate；被隔离的请求
既不进入 FIFO，也不收到假 ready。ledger 记录每一次真实接受，不靠取消时猜测 FIFO 为空。
写完成计数与其 Gray 值在同一个内存时钟沿从同一笔原生写接受事件注册；每个内存周期
最多加一，Gray 源最多改变一位，再经源域两级同步解码。排空要求源域累计读接受数等于
实际弹出响应数，累计写接受数等于同步回来的实际写完成数。

计数器为 16 位并按模 65,536 累加，任务重启和局部 `memory_reset_n` 不将其清零。
这里使用相等比较，成立条件是未完成差值严格小于一次完整回绕，不能允许两条 ledger
相差 65,536 笔仍被判空。当前 pipeline 只有一个读 outstanding，因此读债务最多 1；
写债务受请求 FIFO 的 16 项与命令 buffer 的 1 项约束，实际未提交写最多 17 项。
源域比较另外包含有限的 Gray 同步可见延迟；当前每源周期最多接受一笔、两级同步及
本次 20 ns/14 ns 仿真时钟配置下，可保守控制在 32 项以内，远小于 65,536。
修改 outstanding、FIFO 深度、提交率、时钟或同步级数后必须重新证明这个界限。
测试的真实推理有超过 120 万笔原生读，读计数发生多次回绕；测试未专门驱动写计数回绕。

## 故障与恢复

failure code 1 为 DRAIN 超时；2 为曾经 ready 后内存复位或校准丢失。后续观察到内存丢失
会把先前 code 1 更新为 code 2，并非保留首个原因。内存域有粘性故障记录，源域也独立
检查曾经 ready 后的同步 readiness 丢失，因此内存时钟停止时仍能隔离。

fault 为粘性状态；即使旧响应后来到达、ready 恢复或请求拉低，也不能输出成功 done，
不能重新接受 PCM、新请求或结果。超时不会伪造空队列，也不强行清除 outstanding。
恢复要求系统所有者协调 `reset_n`、`memory_reset_n`、两个 FIFO 域及原生 DDR/仲裁器的
旧事务，完成共同复位和重新校准/模型验证后再开启任务。只切换 `memory_reset_n`、
重新连接或再发 `analysis_restart` 都不是故障恢复。不能让复位前的 DDR 响应在新任务
请求后重新出现；这个系统级保证不由局部 link 单独提供。

## 验证边界与物理门禁

`run_bp_link_restart.py` 使用真实维护源、原生 256-bit DDR 行为模型、两个实际 CDC FIFO、
真实 DDR16 port、真实 CQT/六层 CNN/Viterbi。严格单 anchor 的仿真副本把 WIN_LEN 从
43844 改为 2048、FRAME_LIMIT 从 172 改为 2，生产 literal 与 builder anchors 保持不变。
v4 比较取消后的启用实例和新启动的默认实例；七个场景覆盖排队写、延迟读、响应 CDC、
44.1 kHz pending、超时、内存复位、校准丢失及内存时钟停止。负向副本绕过 drained
判断，被 `pipeline reset before actual DDR drain` 断言拦住。

这份重启回归预置真实 DDR 模型并强制 UART loader 状态为 DONE；它没有测试模型上传、
loader CRC、取消期间的串行上传流控、完整歌曲质量、独立训练/浮点 oracle 或板上延迟。
真实模型未被改写的检查也不能替代 CRC loader 测试。另行实跑的
`test_cnn_flash_boot.py` 覆盖真实 52,239-word 模型、写/读回、CRC `AF01A61B` 和
SPI/UART fallback 故障情形；这是单独组件仿真，不是本 link 中并发取消 loader 的验收，
没有对硬件 Flash 执行读写。

离线异步时钟仿真和 `ASYNC_REG` 属性不能替代实际 W 的 CDC/复位与物理门禁。新 W profile
需要检查两个 FIFO 的 Gray 指针、写完成 Gray 总线、ready/failure 同步链及复位释放；
应按实际时钟与 Gowin 约束语义限制 Gray 源至首级同步器的总线 skew/max delay，确保
多位先后到达不会跨越一次源更新间隔。异步 false path 不能代替这些证明，也不能放宽
真实音频/PLL 时序来隐藏问题。必须保留完整 routed STA、时钟/PLL、CDC、BSRAM 物理
统计与功能门禁，再记录独立的整机集成和板上验证证据。当前没有 W 综合、P&R、位流、
LCD 吞吐/时延、SRAM 或 Flash 部署证据。
