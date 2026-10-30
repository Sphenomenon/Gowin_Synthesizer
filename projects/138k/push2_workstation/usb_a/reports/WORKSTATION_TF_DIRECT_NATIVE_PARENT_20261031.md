# 真实 TF 文件至直接 PCM 组合父级复验（2026-10-31）

主线导入 `232a3eb` 的五个新增文件，把已封存的唯一 SPI／sector／FAT 文件 owner 与严格 WAV／PCM ingress 组合起来。已有两份 owner、vendor／baseline、四 profile 与构建入口逐字保持。新组合仍未由整机选择，只有同一 50 MHz 域的请求、文件、解码和有界 PCM 交接，不另建采样率、源选择或串行时钟 owner。

请求在接受时保留曲号、命令 generation 和采样率，等真实 `track_applied` 才开始新 ingress；接受下一首不会提前撤销旧数据。停止立即撤销本地队列，再等文件 owner 的实际 payload／CRC 排空。独立真实 SPI 审查复现了旧 wrapper 的两个死锁：失败排空后再次停止，以及停止与排空 ACK 同沿。修复后 `stop_completed_o`／`stop_failed_o` 各自报告本次停止的互斥终态，`cancelled_o` 保持原始 reader 的实际排空诊断。重复停止可以复用仍被保持的同一排空证明；新请求清掉旧证明，传输错误要求明确失败／reset。

作者完成 24 个真实 SPI/FAT16/FAT32、MBR／superfloppy、双率、暂停、换曲、停止、坏文件／拔卡／失败恢复案例，以及 11 个行为负控和一个实际 elaboration DDR requester 注入负控。父级在主线完整重跑相同矩阵，全部通过：47,697 帧 PCM、17,120 项检查、526 个数据 sector、1,133 个 CMD17、76,255 个本地消费 deadline。暂停期间 PCM 峰值 4,096 帧、byte 峰值 4,002；七个实际 RTL 实例的组件闭包没有 DDR 请求端口或请求源。17 项 accepted 来源回归另行通过。

默认 `SPI_CLK_DIV_FAST=12`、每 cluster 一个 sector 的真实 FAT 读取，在 7,790 帧后出现持续供给欠载 code 6，随后实际停止／排空，并显式重启另一曲，97 帧 PCM oracle 通过。默认参数保持；正常矩阵的 FAST2 是明确的数字 fixture 配置，不是卡片实测吞吐。未证明实卡 50 ms 最坏停顿预算，SPI CRC 只排空未校验，快速换卡仍须 reset；不据此声称播放满足硬件期限。

独立审查另完成 12 个边界正向与一个实际 wrapper 负控，保留两份旧死锁失败；父级完整重放其只读 verifier 通过。额外验证重复三次 cached stop 各仅返回一次完成、raw ACK 不增加，以及 pending stop 后迟到的真实 R1 错误只返回失败，reset 后恢复。完整 24+11+1 的语义 JSON、全部日志及每份卡镜像／PCM oracle 已与作者对照；路径前缀明确归一，VVP 的进程／路径相关摘要分别逐份校验，不声称它们跨进程相同。

作者 seal `fa6d0f5d…` 绑定 302 个本地文件、43 外部依赖和五份新源码；独立 seal `83364c61…` 绑定 365 文件／15 外部依赖。父级额外绑定 runner 只读作 DDR 对照而未列入作者 input map 的原 legacy runtime 源，并核对作者／主线／原 Git blob；已封存源码未改。父 seal `9a4f0ce2…`，43 文件／1,057 输入，冻结 31 份 root 来源，最终 hash-only 校验通过。完整身份、测试和限制见[机器记录](workstation_task_20261030/tf_direct_native_parent.json)。

该组件没有 CDC 或物理完成帧协议。`decoded_eos` 与 `local_tail_drained` 仍是本地事实，不能当作 DAC 尾帧已完成；文件率必须匹配固定 session，无 SRC。整机 owner4 请求记录、正式播放／媒体停止组合、资源净变化、完整 CDC／reset／PLL、P&R、实卡及硬件验收仍待完成，M03 不勾选。本阶段没有 EDA、位流、板卡操作、SRAM 或 Flash 部署；下一阶段通过浅 FIFO、末帧 token 与真实 I2S 完成帧确认连接唯一 runtime 音频 owner。
