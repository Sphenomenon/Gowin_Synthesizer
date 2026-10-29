# 自制 138K：已跑通模块，待整机装配

根目录入口：[`example/CUSTOM_138K/`](../../../example/CUSTOM_138K/)。这是同一个目录，不是另一份工程。

| 分类 | 已验证程序／候选 | 源码入口 | 下一步 |
|---|---|---|---|
| [USB_HS](USB_HS/README.md) | `C11030A2`：原生 Host，Push HS 枚举、热插拔及 MIDI 恢复 | `rtl/`、`firmware/`、`top.sv` | 将同一 Host／业务固件接入整机输入链 |
| [HDMI](HDMI/README.md) | `C11028D5`：用户接受的 1080p 显示、DDR 数据路径 | `rtl/`、`prepare.py`、`baseline.json` | FPGA 实时绘图写 DDR，保留扫描路径；AE350 负责交互和辅助 UI |
| [BLUETOOTH](BLUETOOTH/README.md) | `C11027C1`：业务 GATT、重连、短录音、下载校验 | `driver.sv`、`protocol/`、`transport/` | 复用业务协议与最终音频取样接口 |
| [AK4493_AMP](AK4493_AMP/README.md) | `13802302`：修焊后 CN 扬声器出声；另保留后续声道诊断 | `bringup/`、`driver.sv` | 使用工作站 FPC/I2S 接口接入最终 PCM |

本次只整理和提交原有源码、来源清单与验证记录，不新增独立顶层、构建器或位流发布。

## 一条清晰链路

```text
example/CUSTOM_138K/<分类>/
  ├── README.md       接线、怎么检查／准备、如何装配
  ├── module.json     参考候选身份、位流哈希、来源文件哈希
  ├── 源码相对链接     直接进入唯一实现，不复制第二套
  └── 证据相对链接     直接进入原始报告，不改历史记录
           ↓
现有 prepare/build 入口 → 新输出目录与输入清单 → 综合／P&R
           ↓
新候选 SRAM 身份读回 → 用户逐模块实物验收 → 完整工作站
```

例程分类不改变现有工程的 source policy、引脚、协议或构建输入。`module.json` 中的 `source_sha256` 锁定本次整理的入口源码，**不是完整构建输入清单**；完整输入仍由对应 prepare 工具的 manifest 校验。参考候选的硬件结果只属于其原有身份，整机装配状态统一为 `pending`。

## 克隆后的第一条命令

从仓库根目录执行，仅检查分类、相对链接、源码哈希和证据路径，不综合、不访问板卡：

```sh
python3 example/CUSTOM_138K/check.py
python3 example/CUSTOM_138K/check.py --module USB_HS
python3 example/CUSTOM_138K/test_examples.py
```

每类 README 给出对应的离线回归与现有准备入口。新构建使用新 UserCode 和新输出目录，不覆盖参考候选。

## 构建产物与多机交接

- Git 保存源码、相对链接、候选身份和验证摘要；不保存 `.fs`、`.vg`、`.p/.pr`、实现数据库或原始捕获。
- 各模块 README 给出已知本机产物位置；不存在时明确按准备入口重建，不自动寻找“最新目录”。
- 跨机复用已验证镜像或增量检查点，需要单独传递对应工程／产物及其哈希；只拉取 Git 不等于获得这些产物。
- USB／HDMI 的新板准备仍显式需要仓库外的三份锁定网表，通过 `--netlist-dir` 提供；本次没有搬迁或修改它们。
- `example/` 里的 LCD、Wi-Fi、晶振测量等原始例程仍保留。晶振测量是音频依赖证据；未完成的 LCD 或 Wi-Fi 业务不冒充本表的已完成模块。

后续只更新对应分类的来源和候选，不再新增一套散落的“最新版驱动”。
