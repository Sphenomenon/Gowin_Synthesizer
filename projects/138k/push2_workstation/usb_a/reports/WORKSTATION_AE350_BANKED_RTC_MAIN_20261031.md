# 分页 GAO 与 RTC 分层门禁父级集成

导入 `fe8e44b`、`693d6ab` 与 `a4e5fb3`，主树来源分别为 `d7e9eae`、`30f0f89`、`68ce3ed`。
GAO 增加显式 `banked4` 选项：每页 16 个诊断字，四页输送完整 64 字；观察总线 704 位，
完整模式仍为 2208 位。冻结 UART 序号、身份、数字 I/O 与健康状态后翻页，
页间序号必须相同，每页至少两次相同采样；未知采样会使已完成的 latest 结果失效，
必须重新取得四页才能解码。C11 与 C12 的固件 ELF／BIN／ROM 和五份固件源码保持一致。

RTC 修复只区分综合 wrapper 与 routed hard macro 的可见证据，物理门禁不接受 wrapper。
源码和实际 VG 检查同时拒绝额外驱动／消费者、错误时钟、标量冒充向量和空端点集合。
维护者独立复现的 `[1:0]`、`[0:0]`、`[0:1]` 源向量漏检均已关闭。

六个 native profile 各刷新四个已核对来源键：构建入口、RTC helper、RTC 回归和时钟 helper。
accepted／pinned／frozen baseline 不变。重新实际准备得到：

| profile | 新身份后缀 | staged／enabled |
|---|---|---:|
| business revision 4 | `b552eccbad9c5b0a` | 614／272 |
| 默认 revision 5 | `4e5dfeea3cc39ed2` | 581／261 |

两份新准备与此前 `0981b403`／`36edc576` 的全部声明编译输入逐字节一致，仍登记新的来源身份。
父级 73 项成功、三项 opt-in 跳过，包括 banked／accepted、RTC、默认和业务 prepare、
实际 VG 时钟五项／28 负控以及最终 PCM 正向检查。作者 v2 seal 独立校验 325 个文件通过，
此前完整／本地 probe／accepted 的 39 项父级回归也保留。

`C21031CE` 的独立物理进程使用固定 `fe8e44b` RTL／固件和新输出目录；
本阶段不继承或预报其物理、SRAM、Cache 或硬件结果。
父级包 `~/.cache/gw138k-task-20261030/banked-rtc-main-parent-v1` 保存 468 份源码快照、
1,679 个固定外部文件，seal `f4c875500942c9ae28b988892837c2961f1b5684467dd5ffc42bc3a4e37c3d43`。
机器索引见 [ae350_banked_rtc_main.json](workstation_task_20261030/ae350_banked_rtc_main.json)。
回退为本批前的固定 profile；没有主树新综合或板卡操作，不升级整机接受状态。
