# BLE DDR 原生组合父级检查点（2026-10-30）

父级接入 [revision2 原生组合](WORKSTATION_BLE_DDR_NATIVE_COMPOSITION_20261030.md)，只在 no-local-panel provider 选择 `native_raw_ddr_v1`。实际 CPU 和 BLE 分别使用唯一 map 的原／新 64 KiB 窗口，共用带读归属的 owner8 mux；bridge 只以已寄存 protocol fault 汇聚故障，authority 关闭全部 admission／native-accept／return 路径。mux／CPU runtime 使用 root-only 两级 memory release，ledger loss 不重置 owner；BLE 使用 grant 的独立 50 MHz 同步投影。格式1仍限 48 kHz、16,384 帧。

父级直接编译真实 selected top 和录音 owners，通过三场景／119 checks、五个地址几何负控，覆盖并发 PCM／mask／snapshot／cache、迟到返回、首次 ready 前 ledger loss，以及停钟时 root 释放的顺序。无关整机模块被黑盒、native DDR 为边界模型；它不代表完整控制器或实际 BIST 验证。CPU 真实 runtime 14 场景／五负控、旧 provider 八项、accepted 来源 17 项均通过。上一阶段真实 BLE owner／protocol／五层适配的父级与独立证据继续分别保留。

父级补齐其余三份 profile 的七个既有来源锁，不改变其配置或选择。四份新 prepare 的来源回归各 12 项通过；BLE integration 五项、no-panel 六项、原 R00 七项均无跳过，enabled Profile 20 项通过（一个历史 legacy prepare 可选项跳过）。所有 767 项主候选 source snapshot 与当前源码匹配。

| 配置 | 父级新候选尾号 | staged／enabled |
|---|---|---|
| enabled | `b1f901dad8195bef` | 571／260 |
| no-CNN | `dd95c9ff07ff2981` | 572／260 |
| R00 | `4cd2ba5d0e291f0e` | 584／267 |
| no-local-panel revision2 | `27732817b67e21ac` | 591／269 |

独立顶层审重新运行三场景／119 checks，并核对隔离候选 `cd44adf6419fcc0c` 的 269 enabled／591 staged 字节；其 31 个封存文件已由父级核验。父级候选与该隔离候选的 enabled 输入逐字相同，仅三份旧 profile 来源快照及含 checkout 路径的 USB firmware build log 不同，因此分别保留身份，不继承候选名。四份父级 prepare 都再次验证全部 staged 字节及 profile evidence。完整来源、变化清单和日志见 [机器证据](workstation_task_20261030/ble_ddr_native_parent.json)。

已把主候选完整复制至独立综合目录，逐项核对 591 输入及四份元数据后启动综合；本源码检查点尚未声明综合结果。后续必须核对实际 BLE 原始 RAM 退休／缓存映射、resource 净值、新 CDC／reset／clock／RAM 数据与物理时序。旧 revision1 检查器的配置拒绝保持，不能改写旧接受范围。R00／R01／R02、完整 CDC／reset 与硬件接受均未完成，无板卡操作或部署。

回退可选择本轮仍保留原 BLE RAM 的 R00 profile，或恢复本阶段 provider／top／policy／配置和对应来源锁后重新 prepare。PCM v2 的旧综合及 FE 失败目录保持原身份，不能用于新候选部署。
