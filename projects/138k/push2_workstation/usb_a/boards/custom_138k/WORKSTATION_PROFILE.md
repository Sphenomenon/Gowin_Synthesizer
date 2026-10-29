# 新板完整工作站来源 profile

`custom138k-workstation-v1` revision 1 是 F01 的显式源码检查点，继续复用现有 `--prepare-custom-board` 装配，不复制工程。它不选择 accepted full83、pinned timing85 或独立 resource 配置，也不改变这些入口及原生默认装配的来源策略。

配置是 [workstation_profile_v1.json](workstation_profile_v1.json)，校验器是 [workstation_profile.py](../../tools/workstation_profile.py)。当前固定 1080p60、允许 HS 协商、WAV 和已实现的 48 kHz 音频路径。目标仍含 48 kHz／44.1 kHz 切换；44.1 kHz、统一最终 PCM、DDR USB 图像和 AE350 业务迁移等缺口在 feature matrix 中逐项列出。不能把本 profile 的名字或 prepare 成功作为这些能力的实现、时序或实板验收。

## 使用

从仓库根目录执行，输出目录必须不存在：

```sh
PYTHONPATH=projects/138k/push2_workstation/usb_a \
  python3 -m tools.workstation_profile check
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-custom-board --workstation-profile custom138k-workstation-v1 \
  --netlist-dir /path/to/locked-netlists --custom-board-output /tmp/workstation-profile-new
PYTHONPATH=projects/138k/push2_workstation/usb_a \
  python3 -m tools.workstation_profile verify /tmp/workstation-profile-new
GW138K_PROFILE_PREPARED=/tmp/workstation-profile-new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_profile.py
```

prepare 使用现有 USB 固件交叉编译入口，需要完整 GNU RISC-V bare-metal 工具链及 C 头文件；可用 `GW138K_RISCV_PREFIX` 指定。三份外部网表仍按 `pinout.json` 校验原始字节，不从测试 fixture 替代生产输入。省略 `--workstation-profile` 时保持原有 prepare 行为；新 profile 不能与旧整机入口、FS-only 或 720p 配置混用。

## 身份和来源

`integration_inputs.json.workstation_profile` 指向新生成的 `workstation_profile.json` 及其哈希。后者记录每个实际启用编译输入的哈希、版本化来源或锁定父基线来源、受检变换、USB 固件编译器／ELF／ROM 身份、完整 staged 文件闭包，以及 A2／D5／C1 的逐文件对照和 feature matrix。没有启用的独立诊断顶层明确列为参考或准备输入；共同名字不等于共同实现。

- A2：当前 USB Host RTL、生产固件和原生 owner 使用共享版本化源码；A2 的 headless 顶层和探针入口仍只作为来源参考。完整工作站的枚举、会话恢复和发声需要 I01 的新证据。
- D5：复用活动 `video_ddr_scanout.v`、DDR 地址图及资源基线的 UI／DDR 依赖；独立 `scanout_write_window()` 适配没有进入此完整装配，D04 仍未完成。逐文件对照同时保留当前字节是否与 D5 参考相同。
- C1：BLE transport、business adaptation、FPC PCM 短录音来源逐项绑定到历史源码提交及当前字节。C1 的历史录音 PCM 全零；本 profile 不继承真实乐音、Android 真机或长录音验收。

profile 配置摘要表示来源策略；`candidate_identity` 另外绑定实际 staged 闭包和固件工具／生成产物，换编译器或 ROM 不会复用候选身份。旧 `identity` 字段继续表示共享 a26 装配策略；不能用它替代新候选身份。后续综合和 P&R 仍使用独立新 UserCode，位流 SHA256、硬件验收、SRAM 和 Flash 状态分别追加证据。本文件和工具均不操作板卡。

## 后续维护

先修改所属版本化源码及其针对性验证，再审查来源差异、更新 feature matrix 和逐文件 lock，并增加配置 revision。不可只改哈希使失败消失，不可修改冻结基线或历史参考身份。父基线的清单、编码还原和漂移失败继续由既有 baseline 工具负责；profile 额外拒绝新增 glob 输入、来源快照漂移、编译清单变更、未登记 staged 文件、依赖内容及 feature／硬件状态被改写。

本阶段没有新增 overlay。既有资源／板级适配保留原哈希和锚点，生成报告列出实际变换；F05 继续负责将稳定适配归回原生源。F02 的 AE350 可重编译输入应在后续显式 revision 接入，不能悄悄替换本检查点仍由父基线提供的 boot.mem。
