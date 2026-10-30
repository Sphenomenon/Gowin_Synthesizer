# R00 tag RAM＋无本地面板：整机综合与 C11030FE 准备（2026-10-30）

明确选择 `custom138k-workstation-r00-no-local-panel-v1` 后，tag RAM 整机综合成功，实际网表确认 pitch 与 attack 的宽 tag 均进入 BSRAM。`C11030FE` 物理资源实验已完成独立输入封存并由主任务启动；本报告仅接受综合与准备边界，不评估其 P&R 结果。完整 PCM reply closure 与当时安装版本的 shared CDC 审计仍失败，因此完整 CDC、reset、时序、硬件与部署均未接受。详细配置、路径与哈希见[机器记录](workstation_task_20261030/r00_no_panel_synthesis_fe_prepare.json)。

候选为 `custom138k-workstation-r00-no-local-panel-v1-e855a1e8a8e6f181`，输入 SHA256 为 `e855a1e8a8e6f1816e3fce69baa24fc00aa2988973da792c12779a513920651c`。配置保留 HDMI 1080p60、native dual-rate、owner8 R00；本地 LCD 明确禁用、touch 未选入，CNN／follow 沿用先前授权禁用。维护 div147 helper SHA256 为 `359350552b6aa00a512068bd68a35cda7a15fad52faf5b23a0f91a893eca1d63`。此身份不替代接受过的 complete-workstation profile 或板上部署身份。

综合退出 0，用时 353.649 秒，584 个 staged 输入、266 个 enabled 输入保持无漂移。4 个登记输出重新核对一致，Gowin 未报告 AG 结构环诊断；该项只覆盖工具发出的 AG 诊断，不代表完整 lint 或所有组合环接受。实际 VG SHA256 为 `086d2504f1287e226fd55641a3e68c52f632dd91e87044b849a7a29af38ba02e`。

| 整机综合资源 | 旧 b9a2 | 新 e855 | 差值 |
|---|---:|---:|---:|
| Logic | 104,321 | 103,147 | −1,174 |
| LUT / ALU | 79,957 / 15,982 | 78,801 / 15,964 | −1,156 / −18 |
| Register | 63,006 | 58,602 | −4,404 |
| 综合 BSRAM | 246 | 253 | +7 |
| RAM16 | 1,397 | 1,397 | 0 |

该比较同时包含 tag RAM 与 no-local-panel 改动，不能把整机差值全部记作 tag RAM 的孤立收益。独立按实际 `DFF*` 原语计数为 57,547→53,143，同样减少 4,404；两版 XML Register 与可见 DFF 之差均为不透明 DDR 的 5,459。直接子树变化为：宽 helper 合计 −3,849，本地 LCD 子树 −554，delay stage −1；其余 6 个 div147 helper 的实际 DFF 数保持。这里的综合 BSRAM 不作为物理 BSRAM／CLS 打包计数。

| 实际 helper 子树 | 旧 DFF | 新 DFF | 差值 | 新 tag RAM |
|---|---:|---:|---:|---|
| oscillator pitch，161-bit tag | 3,886 | 832 | −3,054 | 5×`SDPX9B`，36-bit 端口 |
| oscillator attack，57-bit tag | 1,265 | 470 | −795 | 2×`SDPB`，32-bit 端口 |

两处宽 helper 均没有残留 `tag` 命名 DFF；pitch 保留 5 个、attack 保留 3 个地址／控制命名 DFF。小 tag 的 vector phase／attack 仍保留 114／42 个 tag DFF。7 个 RAM 原语全部为 `READ_MODE=0`，`CLKA`／`CLKB` 均精确归一到 `audio_clk`，原 SDC 已声明 `audio_76m8`。这些结果证明实际映射及静态时钟连接，不证明 RAM 数据弧、CLK-to-DO、routed setup／hold 或物理打包已通过。

实际 clock 审计确认 6 个 PLL、15 个 clock 声明、DCS 选择与 runtime audio 静态拓扑。本地面板层级未出现，21 个 LCD 输出位均静态低电平。独立 raw braced SDC 文本检查有 1,775 个可见选择器匹配、16 个不透明 DDR 选择器暂缓、0 个可见空选择器；仅 `*`／`?` 作为通配符，名称内方括号按字面处理。该检查不执行 Gowin Tcl，也不证明异常覆盖的语义与完整性。

现有 partial CDC 审计仅覆盖 21 组、400 个 Gray 首级位及其登记的 BLE release／media stop／USB queue fence；候选约束已安装，剩余与 reset inventory 均不完整。owner audio reset 的 3 个实际 DFF 阶段及 `audio_clk`／异步 clear 源已核对，但 assertion pulse／flight、亚稳态余量、routed recovery／removal 均未验证；有限 owner-reset 源核对不升级为完整 reset 接受。

完整 PCM 审计失败原文为 `runtime PCM CDC audit: complete payload consumer closure changed: reply`。预期与实际各 263 个端点，消费者 FF 集合相同，但有 29 个缺失／29 个新增端点：`underrun_count_o[0]` 为 D→CE，`wanted_sequence[1,4..30]` 共 28 位为 CE→D。所选原始 50 行 PCM SDC 仅覆盖旧 D／CE 端点；不能只改变 auditor 预期来认定通过，也不能凭选择器不为空认定 closure 完整。后续约束与同拍 Q 更新语义的修复必须另列源码阶段与实际网表验证，本 FE 实验不豁免此失败。

本次封存所用 installed shared helper（SHA256 `966d6b4c200fd0e6372a26329c2f3cc013bc1ac007478b468970c94a67f1cb55`）失败原文为 `installed runtime shared CDC review: first D producer changed: u_video/flags_meta_3_s0`。cache 中的精确别名提案核对到 BIST done／failed 及 scanout front_valid 的 memory-clock 源，并通过 9 项负控；当时仍须 root import 与公开回归，故本阶段 `installed_shared_audit_passed=false`。后续安装源码修订不回写此旧版本失败记录；原 VG／SDC 未被提案改写。

物理输出身份为 `custom138k-r00-tag-ram-no-local-panel-resource-experiment-C11030FE`，UserCode `0xC11030FE`，place=1／route=0／replicate=false／timing_driven=1／correct_hold_violation=1。实际准备重新核对 584 个源输入、266 个 enabled 输入、5 个 metadata、4 个综合输出与 27 个物理输入；34 项实际负控全部拒绝。VG 与所选原始 SDC 字节保持；SDC SHA256 为 `876d01ba2ddcb8f022cc2da9e9c4246bc7bc03014ab3798edd1289fd46e31afb`。CST 仅沿用维护工具对 12 个 ULPI 端口的 nominal LVCMOS33 appendix，位置不变；不是板级电气或外部 IO 时序接受。没有放宽 clock／exception、添加 DDR placement 或额外移除特性。显式删减特性在机器记录中逐项列出。

P&R 于 `2026-10-30T11:55:47.119238+00:00` 由主任务启动，当前报告的 physical-result scope 为未评估；准备验证器自身未启动 EDA。FE 封存的 `resource_route_exploration_only=true`，完整 source CDC／recording CDC／reset／full timing／physical gates、硬件、SRAM／Flash、部署与 release_ready 均为 false。本阶段不登记位流身份，也未操作板卡。只有后续独立物理与硬件证据可以提升对应状态。

| 本机 cache 证据 | SHA256 |
|---|---|
| `r00-e855-tag-ram-vg-review-v1/REVIEW_SEAL.json` | `8f0223d496f6b97ce5a34eb552248c8e2015f3681c517c8e50680b80c0f20297` |
| `r00-e855-tag-ram-vg-review-v1/verification.json` | `46e82d869693b31b86c1018c0de90764dd2bbcf75bda2ecf5be9fd453e08d76e` |
| `r00-FE-physical-preparer-v1/actual_prepare_verification.json` | `75eeaa031247381e6d0d6d9ba619074d45ac839b1fe37cfa4328f85d30853381` |
| `r00-FE-physical-preparer-v1/ACTUAL_PREPARE_SEAL.json` | `b95846c103207a976a7067ca20400b9947514355a29c2b8de811e68905a61811` |
| FE `physical_inputs.json` | `ec13652136902e316934fe2650f76fb0db28be3f06e64d5eb058914eb0434c64` |

以上目录均在 `/Users/sphenicidition/.cache/gw138k-task-20261030/`。报告前再次独立重算全部 584／4／5／27 项输入、输出及 metadata 与既有 FE 封存，均匹配。当前实验若不合适，回退操作是退役 C11030FE cache 输出；旧 b9a2 须使用其完整原始封存输入重建，不混用新旧源，也不等同于板上回退。既有接受与部署记录保持原身份，FD 历史失败证据不改写。
