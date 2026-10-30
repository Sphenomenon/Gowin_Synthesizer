# 显式 CNN／跟奏能力选择

`custom138k-workstation-no-cnn-v1` 是独立的离线资源候选。它使用自己的配置、revision、源闭包、编译 provider 和候选身份；不替换 `custom138k-workstation-v1` revision5，不改变 accepted/pinned、resource-only 或无 profile 的默认入口。是否把条件裁剪合入/选入主任务，由两次同源实际 P&R 的资源失败证据另行决定。prepare 本身不证明该前提，也不授权综合、部署或硬件验收。

唯一权威选择是 profile registry 的 `recognition_policy`。新配置同时关闭 music analysis 和 CNN score follow，不允许不存在识别 producer 却声称可跟奏的组合。极小 `workstation_profile_no_cnn_runtime.sv` 在包含既有 runtime provider 的范围内定义/撤回宏；不复制整机 RTL、不生成文本实现。旧 runtime provider 原字节保留。

组合根不实例化 `u_music`、CNN score FIFO 或分析曲目命令 CDC。music DDR 请求/写/地址/数据为零，mask 全屏蔽；无 result/score/done，model_status=0，不伪造14/ready。PCM ready=1，report UART idle；已有 Flash guard 保留，内部 CS=1/SCK=0/MOSI=0，五个共享 Flash pad 均释放为Z。NN DDR 池和 recording granule305均保留，不能据此重新分配存储。

`workstation_playback_service.RECOGNITION_ENABLE` 默认true。关闭时 analysis enable/restart/hold和score_accept均为0，reader restart/track直接取原始TF控制，不因模型ready、分析song请求或恢复计时制造重启。TF reader自身的取消、run、匹配采样率、拔卡及媒体停止规则继续归原owner；普通PC UART在关闭识别时直接开放，无需模型加载或TF模式。

`CNN_FOLLOW_ENABLE` 从组合根经 `workstation_usb2_input` 传至原USB owner，默认true。关闭分支不实例化CNN guide/menu队列及analysis_done同步、score-flush状态，score输入被接受并丢弃，guide目标/计数/游标/错误计数为零。Push的分析曲目菜单和跟奏不可用，屏幕保持原普通页面；按钮85恢复已有本地cue命令，44/45/48走原CC108/CC90，generic MIDI CC110/111/112仍本地消费，25K隔离不变。

CPU手工LED cue、256-cue本地score、REC、media-stop及它们的CDC保持，不能按“score”文本删除。MMIO0x5c/0x68/0x6c的CNN字段为零；0x60保留track_count和service_state等非CNN字段，0x64保留原本地score mask。公共参数、18-bit事件、PANIC/lifecycle、TF、FFT/XY/meter、USB/BLE/AE350及合成/效果路径均不由本开关重新定义。

约束适配只针对已删除端点的19条完整既有行。固定行集合及SHA、每行一次的锚点、原始行号、输入/输出SDC哈希均入证据；其余行逐字保留。未知CNN引用、混合新旧端点查询、重复或漂移均失败关闭。默认enabled不改SDC字节。退役缺失实例的约束不等于新增CDC或物理时序已闭合；旧native整机物理auditor的runtime缺口继续阻断，不能把部分source/port审计提升为全量通过。

撤销此候选时重新prepare原enabled配置并使用其新身份，不复用off身份。识别源文件和历史证据继续保留；测量关闭后的净资源/CLK/拥塞以及两速功能，必须用同工具、同其余输入的独立综合/P&R和硬件证据。
