# B04 HCI／CPU classic 基础源码父级复验

日期：2026-10-31。两个未选择的源码阶段已精确导入主线，并由父级在新的外部输出目录实际运行验证。它们尚未进入整机 profile；本报告不代表 B04 整项、A2DP1.4 合规、手机互通、完整固件容量／时限或硬件接受。

## 来源与封存

| 阶段 | 作者提交 | 主线导入 | 新增文件 |
|---|---|---|---|
| 共享 HCI accounting／原始事件校验 | `cd34562c31f71a8579a868d6d56844f9eee4a2d7` | `1be86627cd3d945788ae4a772ad1775252f41e0c` | 7 |
| 有界 CPU classic 实验组件 | `beae08d7dd7ddb70a12b217a2b7afd3cea27e039` | `5eed03e25aef3df4525e6857606f94533f1b7122` | 9 |

两项提交均只增加文件。父级逐文件对比主线工作区、导入提交 blob 和固定作者树，16 项导入字节全部相同；两个父级测试报告的 `inputs` 与各自作者最终报告完全一致，全部对应当前源码。组件设计、接口及原阶段限制分别见 [HCI 源阶段](WORKSTATION_HCI_OWNER_SOURCE_20261031.md)和 [CPU 源阶段](WORKSTATION_B04_CPU_STANDARD_SOURCE_20261030.md)。本次没有改变生产 profile、builder、冻结输入或历史证据。

固定作者包分别位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/b04-hci-owner-v1` 和 `b04-cpu-standard-v1`。父级再次运行其只读校验：HCI 通过 5,705 源／159 输出／188 工具身份，CPU 通过 9 源／181 最终证据／5 工具身份；原包未改动。

新的父级证据目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/hci-classic-main-parent-v1`：保存 56 项输入／导入源码快照、原始验证 JSON、命令日志、作者回执、工具版本和独立 PCM 数值复算，绑定 282 项外部固定文件；80 个包内 payload 文件由 `seal.json` 固定。`python3 -B <该目录>/verify.py` 已真实通过。

- 父级 seal SHA256：`337b7c140d1c982f2e7dea95477cae47925dff680b5cc70cc331a66ef757d823`。
- [机器收据](workstation_task_20261030/b04_foundation_main_parent.json) SHA256：`723f797701bba426df5ce00ec90e66e953c375744159ca2f5ec5a7db4525a9b2`。

## 父级实际离线结果

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_owner.py \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/hci-owner-main-verification-v1
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_classic_service.py \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/classic-main-verification-v1 \
  --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

| 验证范围 | 本次结果 |
|---|---|
| 实际 HCI flow RTL | 116,780 checks；15 场景、10,000 步独立随机模型 |
| 原始事件＋实际 flow | 9,174 checks；1,830 events，其中 1,806 个 schema 长度负测 |
| HCI 行为负控／参数／lint | 11 个突变全部拒绝；4 个非法参数组合拒绝；两模块严格 Verilator `-Wall` 通过 |
| CPU 实际 C 字节向量 | 原生、ASan＋UBSan 各 44,612 checks 通过 |
| CPU 行为负控 | 15 个突变全部拒绝，包括 SDP32 位长度回绕、旧 generation、uncertain 重放、队列溢出、RX 覆写、实际控制器容量和配置调整 |
| 实际协议至 SBC 解码 | 11 组 ACL→L2CAP→RTP→帧队列→Apache OI 解码；118,784 scalar samples；原生／sanitized PCM 逐字节相同 |
| 独立数值复算 | 逐组重读真实 PCM 与 BlueZ 参考，样本数、PCM SHA256 和报告误差全部一致；最大绝对误差 6，门限 8 |
| accepted 输入保全 | 17 项通过；没有从本轮未选择组件切换 accepted 输入 |

HCI 父级输出清单的每项哈希已复核；CPU 原始运行日志、变异源码／执行文件、实际 PCM、编译输出及适配解码器均由新包的外部哈希绑定。测试是有限向量与确定性随机覆盖，不是协议或内存安全的穷尽证明。

## RV32 大小差异与范围

父级使用 xPack GCC15.2.0，作者使用 Homebrew GCC16.2.0。两者的源码输入哈希相同，编译器路径、版本和二进制 SHA256 分别封存；不能把两个编译器的代码大小当作同一输出。

| 测量项 | 父级 xPack15.2 | 作者 Homebrew16.2 |
|---|---|---|
| `.text` | 14,072 bytes | 14,212 bytes |
| 全部只读数据 | 273 bytes | 273 bytes（265＋8） |
| `.text`＋只读数据 | **14,345 bytes** | 14,485 bytes |
| 调用方分配的 service 对象 | 2,848 bytes | 2,848 bytes |
| 最大单函数 stack frame | 480 bytes | 480 bytes |

该 TU 的全局 data／BSS 为零，仍依赖调用方状态及 `memcpy`／`memset`。上述测量仅为一个目标对象的增量；尚无与现有服务、SBC、启动、共享队列合并后的完整固件链接、ILM／DLM fit、调用链总栈或实际 CPU 周期证明，也没有净 CLS／BSRAM 收益结论。

## 待完成与回退

HCI 尚缺 host RX bootstrap／物理 packet lease／return、真实 0x0c35 参数构造、raw router／CPU mailbox、native 组合，以及既有两处 BLE 控制器 credit 权威的实际退休和功能保留。此源阶段仅提供统一账本与事件校验，不表示以上路径已完成。

CPU classic 尚缺 A2DP1.4 Sink mandatory Delay Reporting、配对／安全／可发现与连接策略、超时恢复、完整协商、真实音频 rate grant、有界 PCM 硬件队列和长期时钟漂移处理。实验 SDP 仍标识目标 profile1.4；存在这些缺口时，不能对手机发布或宣称标准 Sink 已完成。

后续须在同一新身份候选中完成实际 HCI／CPU／BLE／音频组合，再取得完整固件存储／周期／最长服务间隔、并发资源、P&R／CDC／PLL、手机及物理声音证据。本阶段没有新综合、P&R、SRAM、Flash 或板上状态变化；回退是撤回尚未被 profile 选择的新增源码，不涉及板端恢复。
