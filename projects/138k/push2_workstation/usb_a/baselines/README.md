# 可版本化的生产输入闭包

这里锁定的是**源码基线**，不是新位流或新的实体验收。当前完整工作站的三条准备路径不再读取本机忽略的 full83、full85 或资源优化历史暂存目录。

## 组成

| 文件／目录 | 用途 |
|---|---|
| `index.json` | 基线名称与描述清单 SHA256；构建必须显式选择，不寻找“最新目录” |
| `accepted_full83.json` | accepted full83 的必要输入与来源映射 |
| `timing85.json` | full85 锁定输入；整机路径仍只从中选择原有六个 CNN 时序文件 |
| `resource_rework_route0.json` | 资源时序路径原有参考树的必要输入和三份来源元数据 |
| `origins/` | 原始输入清单与必要元数据，原始字节和哈希不改；历史路径只是来源说明 |
| `objects/` | 现有不可变源码中缺少的内容，按 SHA256 去重保存；不是另一套活动 RTL |

优先复用 Git 已跟踪的 2026-09-11 `Prj1` 冻结树和 USB-A vendor 输入，其余内容才进入 `objects/`。三个基线共复用 266 份新增冻结内容，约 3.3 MB；没有复制三套完整工程，也没有导入网表、位流或实现数据库。旧的 Git 跟踪冻结树目录名仍含 `results/`，本次没有移动它；消除的是对 **Git 忽略的私有历史暂存** 的依赖。

这些内容继承原文件的来源和许可，不是新编写的 DSP 实现。活动开发继续在现有 `rtl/`、固件和工具目录进行；不要直接编辑哈希命名对象来修功能。

## 输入锁定与字节保持

解析器是 [`../tools/workstation_baselines.py`](../tools/workstation_baselines.py)。每个目标文件记录暂存路径、仓库内来源和最终 SHA256；先校验描述清单、原始输入清单、文件来源以及 `.gprj` 引用，再生成新工程。缺失、篡改、路径逃逸或非法排除均失败，不回退到本机历史目录。

默认按原始字节复制。四份无文件末尾换行的历史输入以 `.b64` 保存，另校验存储哈希，解码后再次校验原始 SHA256。已有冻结树另有 27 个文件的 Git 存储是 LF，但历史验收绑定的是 CRLF 或混合换行，其中 16 个需要逐行换行位置表；清单显式绑定 LF 存储哈希和还原规则，再验证最终原始字节哈希。不会改写原文件或放宽最终输入哈希检查，未声明这种还原的文件也不会自动归一化换行。`.gitattributes` 保持新冻结内容的原始字节。

| 基线 | 原始清单项 | 保留源码／必要输入 | 明确排除 | `.gprj` 引用 |
|---|---:|---:|---:|---:|
| accepted full83 | 594 | 414 | 180 | 181 |
| timing85 | 597 | 417 | 180 | 184 |
| resource rework route0 | 617 | 437 | 180 | 200 |

各基线排除的 180 项仅为 `docs/` 历史说明／捕获，以及 `firmware/boot.elf`、`firmware/boot.bin` 两个中间产物。它们仍记录在原始清单及 `excluded` 中，未改旧证据；编译所需的 RTL、约束、ROM／模型数据、脚本、仿真和许可文件保留。当前 `.gprj` 无引用被排除的文件。

USB ROM 与 AE350 `boot.mem` 是已有构建真正使用的文本输入，不能因为“由程序生成”就删除。accepted 整机路径仍用原有工具重新构建活动 USB 固件；资源时序路径保留其锁定参考 ROM，不因此宣称采用了所有活动固件改动。

## 使用与验证

从仓库根目录执行：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_baselines.py
python3 projects/138k/push2_workstation/usb_a/build.py --current-workstation --prepare-only
python3 projects/138k/push2_workstation/usb_a/build.py --current-workstation --cnn-timing85 --prepare-only
python3 projects/138k/push2_workstation/usb_a/build.py --resource-rework --resource-timing --prepare-only
```

需要 Python 3.9+；重新编译 USB 固件的路径还需要 GNU bare-metal RISC-V `gcc/objcopy/size/nm`，可用 `GW138K_RISCV_PREFIX` 指定前缀。准备阶段不需要 Gowin 综合／布局布线，也不操作板卡。完整实现仍需合法安装的 Gowin 工具和独立门禁；本次没有重新执行完整实现。

快速回归：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
python3 projects/138k/push2_workstation/usb_a/sim/test_stage_usb_firmware.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_baselines.py
```

无私有历史输入的集成验证会建立临时本地克隆，覆盖本轮工作区源码改动，在原工作区和临时克隆分别执行三种 prepare，逐文件比较，再运行诊断 CDC 和接入生命周期仿真，并验证篡改输入被拒绝：

```sh
GW138K_VERIFY_CLEAN_PREPARE=1 python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_baselines.py
```

该验证另外需要 Git 和 Icarus Verilog；临时克隆结束后清理。可选 `GW138K_CLOSURE_REPORT` 指定 JSON 报告路径。最新实施范围及迁移前后的输入比较见 [闭包验证记录](../reports/SOURCE_CLOSURE_20261021.md)。

## 后续修改规则

- 基线是不可变历史输入；活动源码变化不应隐式改写 accepted 输入。
- 新的来源策略使用新的基线身份，保留原始清单、排除原因、来源哈希及针对性测试，不直接替换旧来源来“修复哈希失败”。
- `build_metadata.json` 的 `source_baselines` 记录实际采用的锁定描述清单；活动 overlay 和生成后的总清单继续分别记录。
- 不把当前构建中的字符串变换称为已经消除。本次仅先切断私有暂存依赖；配置收敛、稳定第一方逻辑归位和发布门禁统一仍是下一阶段。
- 旧编号实验构建器与早期默认构建路径仍按其原有输入策略工作，不在本次迁移中全部改写或删除。
