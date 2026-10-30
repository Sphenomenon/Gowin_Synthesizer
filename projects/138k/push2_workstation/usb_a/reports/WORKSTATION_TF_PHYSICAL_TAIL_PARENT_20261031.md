# TF LAST／物理尾帧组件父级复验

从 `db3d852c41be20d78f766b02af39bff0722cf958` 精确导入十三份新增源码／契约／fixture／报告，旧 bridge、四份 selected profile、builder 和已有音频 owner 均未改变。新增 LAST／命令身份与 PCM 原子过浅队列；独立 tail endpoint 只把最终路由实际接受的 LAST 与真实 serializer 完成及观察 FIFO 收据匹配，不自行生成音频或选择音源。完整实现与原作者十八组结果见 [source 报告](TF_PHYSICAL_TAIL_SOURCE_20261031.md)。

父级重放完整 sealed delivery 语义及 hash-only seal 成功。最初工具选择 PATH 不一致使 dependency hash 被正确拒绝，后以作者绑定的 miniforge Python／Homebrew Git 路径复验通过，没有删除字段或修改封存文件。父级再运行：

- 两种采样率实际 SPI→FAT16→WAV→LAST FIFO→最终 router→PCM bridge→serializer／I2S→observation，每率连续两曲，各曲 97 帧。合计 864 物理帧、112,153 次 BCK 检查、876 次 LRCK 周期检查，四次真实 EOF；无欠载或观察丢帧。完整 case metrics 与 sealed 作者结果相等。
- 11 项 endpoint 协议情形及七种行为破坏负控通过；bridge 的零和近回绕两个 seed、四种行为破坏负控通过。所有实际输入逐一映射到本次主线字节，生成 WAV 数据另按实际文件验证；初次把生成文件误当仓库路径的映射检查失败，修正映射后全量验证，未更改测试输入。
- 真实 elaborated component closure 为 18 个 RTL instance、零 DDR 请求端口；它没有证明整机 owner4 已退出，也不是整机资源／时序结果。八分钟 FAST12 向量的 sealed 结果完整复核，本次没有重复运行该未变向量。

`fence_i` 的契约和实现把每个 asserted compute cycle 当作事件；源码注释的 “high edge” 表述不精确。为保留本次十三份原始字节，实际组合时需提供单周期事件，并在下一源修订纠正注释。派生 `.patch` 有一条标准空白 context 行（单个空格），父级检查确认只有该行触发普通 trailing-whitespace 规则；其余新增源无尾空白，patch 字节保持并已由 derivation／reverse 验证。

机器记录：[tf_physical_tail_parent.json](workstation_task_20261030/tf_physical_tail_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/tf-tail-parent-v2` 含十三份源快照及 91 项证据绑定；seal `f618334b2e6f2f09969cdfd4214261058d2c2af74b02370c8522148c964d0f70`，receipt `233783a1c300e4f67b5752fb4f49c89c14289d8bf125e308b4a1afac62a9a236`。不完整的父级 v1 因预期错 seal 文件名而失败，保留，未覆盖作者包。

本阶段组件尚未由整机选择，没有新综合、P&R、routed CDC／Gray skew、真实卡 50 ms 预算、板测、SRAM 或 Flash 接受。下一步接唯一 `workstation_runtime_audio`，补真实整机流量与生命周期／物理门禁；需回退时删除本次新增文件即可，旧 selected 字节和证据保留。
