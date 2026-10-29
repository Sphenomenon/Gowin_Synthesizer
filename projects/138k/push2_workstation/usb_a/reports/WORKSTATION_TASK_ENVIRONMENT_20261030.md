# 完整工作站任务：构建环境与基线保全

日期：2026-10-30（Asia/Shanghai）。起点 `632888a`，开发分支 `codex/138k-workstation-task-20261030`。本阶段为 M0 的环境准备和来源回归，不勾选尚未完整验收的 F01—F03。机器可读结果见 [environment_verification.json](workstation_task_20261030/environment_verification.json)。

## 实施与验证

- GNU RISC-V 自动发现增加 Homebrew 的 `riscv64-elf` 前缀，仍要求 gcc／objcopy／size／nm 齐全；显式前缀优先级和原 Linux 默认不变。
- 干净克隆测试先规范化临时目录路径，修复 macOS `/var` 与 `/private/var` 别名导致的输出路径识别失败；没有修改生产来源或放宽哈希校验。
- 来源边界 10 项、USB 固件 staging 7 项通过。`GW138K_VERIFY_CLEAN_PREPARE=1` 的 23 项通过：accepted full83、pinned timing85、resource-timing 在本地与无私有暂存克隆中分别 prepare，逐文件一致；CNN trace CDC 和接入生命周期仿真通过，篡改来源仍拒绝。

最初 Homebrew GCC 16.2 缺少 newlib 头文件，USB 真实编译因 `string.h` 缺失失败；没有改 vendor 或补假头文件。随后安装官方 xPack GNU RISC-V 15.2.0-1 darwin-arm64 完整工具链，核对发布 SHA256 `6588e8351455fad8aca37551f0e5a5543f3346bfa9a837cf03cbd3bdd4989f8f` 后重跑通过。仿真工具为 Icarus 13.0、Verilator 5.052。工具和生成目录未入库。

复现环境：将 `/opt/homebrew/bin` 加入 PATH，设置 `GW138K_RISCV_PREFIX` 为完整工具链的 `bin/riscv-none-elf`，再执行基线 README 的 clean-prepare 命令。Homebrew compiler-only 包可编译当前不依赖 libc 头的 AE350 固件，但不能单独满足 USB 固件编译要求。

用户提供的 `Downloads/138k_locked_netlists_20261030_034210.zip` 包含三份原始网表；解压后逐一通过 `pinout.json` 已锁定的 SHA256 检查。它们保存在本机任务缓存，未更改来源哈希或冻结基线。

## 板卡边界

本轮用户已授权综合、SRAM 和探针迭代。只读检查确认 Mac 的 FT2CH channel 0 可访问 138K：ID `0x0001081B`、UserCode `0xC11028E5`、Status `0x00022020`。该结果来自实际读回，没有用历史 Flash 记录推断。当前阶段未综合、未下载 SRAM、未写 Flash，也未声称 USB／音频／HDMI 实体验收。

后续先固定新板整机 profile 和 A2／D5／C1 的逐文件复用矩阵，再接入可维护 AE350 固件、双音频时钟及 DDR／最终 PCM 契约。已确认 D5 取行窗口适配尚未进入完整新板装配，不能从独立 D5 继承整机显示验收。
