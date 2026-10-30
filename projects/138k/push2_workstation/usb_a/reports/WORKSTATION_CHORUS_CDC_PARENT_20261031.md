# Chorus 新候选 CDC 父级组合（2026-10-31）

显式范围 `runtime-r00-no-local-panel-ble-ddr-chorus-v1` 已由主仓库重新验证，只接受实际 `6b9610324164f0c9`／VG `2cfe81e5…`。四个 dispatcher 增加显式选择；旧 serial、c7 scope 与端点表字节保持，仍拒绝新候选。新门禁校验全部 596 staged、269 enabled、实际编译顺序与 Chorus 可逆 provenance。13 个 phase1、42 个 raw 完整生产者闭包重新从新 VG 提取；新视频 `u_video/front_valid_Z` 的唯一 memory 域生产 FF 和两级接收关系单独核对。

父级重新运行六个公开 CLI：clock、shared、USB2 owner reset、phase1、raw inventory、paired-nextq-v2 PCM 均通过；另有 14 项新 scope 测试、19 项实际 VG 负控全部通过。共享保留 88 行安装约束，phase1 为 425 FF／42 Gray／82 payload，raw 为 13 普通对／50 Gray／528 逻辑 payload、524 映射源 FF，PCM 为 229 源位。phase1 的新输出仍只是外部提案，没有安装 SDC。

四份 fresh prepare 分别为 enabled `7bb700193cd38e3c`、no-CNN `a1b04c71ed0cffeb`、R00 `9a8372c55b9b31a3`、no-panel `1ae395f109778ee2`，各 12 项来源测试通过，全部 staged 字节及编译清单与前序相同。enabled profile 20 项通过（一项旧 prepare 跳过），accepted 来源 17 项通过。新来源快照不能继承 6b 综合或物理接受。

父级逐项核验独立 seal 的 12 源码、72 证据和 17 外部依赖，并确认 12 份导入源码一致；自己的回归／公开审计另行封存。详细路径与 SHA 见[机器记录](workstation_task_20261030/chorus_cdc_parent.json)。seal code 消除、完整 CDC／reset、held payload／RAM 物理时序、Gray 位飞行、PLL 和 routed STA 仍未接受。本阶段无 EDA 或板卡操作，无 SRAM／Flash 部署。
