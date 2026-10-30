# HDMI owner8 显式来源适配父级复验（2026-10-30）

完整显示 runner 新增显式 `--hdmi-adaptation recording_owner8_v1`，父级已独立执行并通过。该入口锁定当前 native HDMI `724f23fd…`，精确逆转 `524f533` 引入的两个 owner8 条件接口／仲裁装配变更，再执行原 provenance 的十九项逆向链及 3,210 个默认预处理 token 对照。原 RTL、原 manifest、历史期望及默认入口保持；默认不加选项仍正确报 `Native HDMI provenance checksum changed`，父级保留该负例记录。

父级实际复验 default、runtime、runtime_owner8 三种完整官方 GW5A elaboration；owner8 使用实际 prepared 且启用、与当前 SHA 匹配的 queue／core，核对 RECORDING_ENABLE=1 和九请求槽。完整显示流水线通过六 publications、九 commits、128,702 原子 tuple、1,024 waveform samples、131,072 XY pixels、1,024 FFT columns 与 60 CDC drops；本次拥有范围 warning 为零。八项单测包含三十个来源／manifest／anchor／选择负例，17 项 accepted 来源回归也通过。

所有交付 source／cache seal 逐项复核；用作支持的 `c7d66b419868f7f4` 593 项 staged 输入保持，未修改其编译字节或复用身份。此变化只提供独立验证入口，不改变生产来源选择；未来 prepare 将生成自身的新来源快照身份。原失败证据保留。详细路径和 SHA 见[机器记录](workstation_task_20261030/hdmi_recording_owner8_provenance_parent.json)。

本阶段是来源链／elaboration／数字显示功能接受。真实 owner8 elaboration不等于录音端到端行为或物理验收；完整 DDR 截止期限、CDC／reset／PLL、routed STA 与实板仍未接受。没有新增时序例外、EDA、SRAM 或 Flash 操作，整机任务方框保持未完成。适配退出计划见独立 manifest：待维护 canonical 来源链正式拥有该变更后另行审查退休，原 manifest 与历史证据继续保留。
