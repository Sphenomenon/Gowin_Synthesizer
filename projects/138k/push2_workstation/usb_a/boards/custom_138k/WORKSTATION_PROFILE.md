# 新板完整工作站来源 profile

`custom138k-workstation-v1` 当前为 revision 3：保留 F02 可重编译 AE350 固件，并迁入版本化 HDMI 组合及扫描窗口写入 admission。它继续复用现有 `--prepare-custom-board` 装配，不复制工程，不选择 accepted full83、pinned timing85 或独立 resource 配置，也不改变未指定 profile 的原生默认来源。revision 1／2 的来源与验收范围保留在此前提交和阶段报告中。

配置是 [workstation_profile_v1.json](workstation_profile_v1.json)，校验器是 [workstation_profile.py](../../tools/workstation_profile.py)。当前固定 1080p60、允许 HS 协商、WAV、已实现的 48 kHz 音频路径、`ae350_firmware_policy=maintained_ae350_v1` 和 `scan_window_policy=native_admission_v1`。目标仍含 48 kHz／44.1 kHz 切换；独立时钟／串行器尚未接入此 profile，统一最终 PCM、DDR USB 图像和 AE350 业务迁移等缺口在 feature matrix 中逐项列出。不能把 prepare 成功作为实现、时序或实板验收。

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
- D5：复用 `video_ddr_scanout.v`、DDR 地址图及资源基线 UI／DDR 依赖；revision 3 以版本化 admission 模块实现扫描窗口内暂停新 CPU／raster／snapshot 后台写，已接受尾部、CPU 读及 TF／delay／CNN 请求保留。没有调用独立 D5 的文本 overlay；实际并发期限和 D01／D04 仍未完成。逐文件对照继续保留与历史参考的字节关系。
- C1：BLE transport、business adaptation、FPC PCM 短录音来源逐项绑定到历史源码提交及当前字节。C1 的历史录音 PCM 全零；本 profile 不继承真实乐音、Android 真机或长录音验收。

profile 配置摘要表示来源策略；`candidate_identity` 另外绑定实际 staged 闭包、USB 与 AE350 固件工具／生成产物，换编译器或 ROM 不会复用候选身份。旧 `identity` 字段继续表示共享 a26 装配策略；不能用它替代新候选身份。后续综合和 P&R 仍使用独立新 UserCode，位流 SHA256、硬件验收、SRAM 和 Flash 状态分别追加证据。本文件和工具均不操作板卡。

## AE350 固件来源

只有显式 profile 会调用 `stage_ae350_firmware()`，将 [firmware/ae350](../../firmware/ae350/README.md) 的版本化 C／头文件／启动汇编／链接脚本编译到候选自己的 `ae350_firmware/`，随后安装其中的 `boot.mem` 到 `workstation/Prj1/firmware/boot.mem`。安装前核对父基线 ROM，安装后核对新 ROM；缺源、编译或容量失败直接停止，不能回退旧 ROM。未指定 profile 的 a26 以及 accepted／pinned／resource 仍保留锁定 ROM。

`integration_inputs.json.ae350_firmware` 保存实际工具、ELF／binary／ROM 哈希、16 KiB ROM／8 KiB RAM 的容量与至少 4 KiB 栈保留检查、历史 ROM 对比，以及独立固件证据目录的完整文件身份。`workstation_profile.json.generated_data_inputs` 将最终 `firmware/boot.mem` 明确标为该维护源码的生成输入。校验器同时核对固件证据和工程中安装的字节，不能只改 ROM 或元数据冒充一次重编译。编译器逐函数栈值仍不能证明完整调用链上界、运行时栈水位、CPU 服务时限或新 ROM 的硬件验收。

## 后续维护

revision 3 只禁用父 `src/video/hdmi_display.v` 的编译，保留其原始字节。单一 [profile wrapper](../../rtl/workstation/workstation_profile_hdmi.sv) 包含 [版本化 HDMI 组合](../../rtl/workstation/workstation_hdmi_display.sv) 并显式启用 [扫描 admission](../../rtl/display_data/workstation_ddr_scan_window.sv)；实现、wrapper、gate 和迁移 provenance 均纳入 lock 与 staged 闭包。新实现默认关闭时保留原通路；不根据历史模块名字隐式选源。该迁移不改物理时钟、DDR 地址、owner 或服务保证。

先修改所属版本化源码及其针对性验证，再审查来源差异、更新 feature matrix 和逐文件 lock，并增加配置 revision。不可只改哈希使失败消失，不可修改冻结基线或历史参考身份。父基线的清单、编码还原和漂移失败继续由既有 baseline 工具负责；profile 额外拒绝新增 glob 输入、来源快照漂移、编译清单变更、未登记 staged 文件、依赖内容及 feature／硬件状态被改写。

本阶段没有新增 RTL overlay。既有资源／板级适配保留原哈希和锚点，生成报告列出实际变换；F05 继续负责将稳定适配归回原生源。后续 AE350 业务修改直接维护活动源码，并随新的 profile revision 重新编译和校验；不修改冻结输入或复用旧候选身份。
