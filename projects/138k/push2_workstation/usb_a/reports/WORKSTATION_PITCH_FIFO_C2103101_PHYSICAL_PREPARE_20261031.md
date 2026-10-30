# 18ed C2103101 物理准备父级检查点（2026-10-31）

固定 18ed／源码 `eff1d7d` 的实际 VG `c9f88c71…` 已生成新的 `C2103101` 离线物理实验。父级重新运行适配器 17 组测试、实际 preflight 与 prepare，冻结并逐项重哈 4,278 份复制输入；独立复核另外重建完整清单并重哈两遍，封存 11 项虚拟故障检查。父级重哈该独立交付；其 verify.py 是 hash-only，传入 --replay 也没有行为重放，本报告不把这次调用标为重放负控。原 599 staged／269 enabled、四综合输出／两工具和 VG/process 身份分开绑定。

SDC `06e9739c…`、CST `8c3f8415…` 与 C2103001 逐字相同；Tcl 仅把 UserCode 改为 C2103101，新 SHA `38969dd6…`。place1／route0、replicate=false、timing-driven 与 hold correction 均保持；没有放宽时钟／例外、增加 DDR placement 或额外删功能。包内实际 VG 的 15 时钟声明、六 PLL owner、21 本地面板静态低输出由独立复核重放通过，仍只接受对应静态声明。

适配包用 41 个精确锚点衔接新身份／schema，六个原纯门禁函数保留；helper 固定于 `d606b858…`，编译 RTL 仍为 eff1d7d，未混入后续显示修复。三族 prefix4／native FIFO／TF-counter、全部父级及原综合证据均复制入包。66 个原 live-root 来源先在干净 4308339 捕获，每份与原父 seal 及 Git blob 相同，原路径／hash 和全部捕获 bytes 保留。冻结后继续改 root 不改变本物理输入；后续验物理包内副本，不能声称依赖旧 live-root 路径的原适配器在源码改变后仍应通过。

第一次正式 prepare 使用了 preflight 创建的同名输出目录，被新目录门禁拒绝，尚未写实际工程或启动 EDA。仅含 preflight.json 的目录原样移至单独预检位置，再执行实际 prepare 通过；两次日志与移动前后哈希均保留，未覆盖失败或原 seal。新 prelaunch freeze 时没有 impl／P&R process。完整身份与 SHA 见[机器记录](workstation_task_20261030/pitch_fifo_C2103101_physical_prepare_parent.json)。

本检查点接受输入准备，P&R 及其结果另记。综合计数不作为物理占用，完整 CDC／reset／RAM／PLL／routed STA／功能保全和硬件均未接受，无 SRAM／Flash 或板卡操作；该实验身份不赋予部署接受。回退仍保留 C2103001 及固定 18ed 来源。
