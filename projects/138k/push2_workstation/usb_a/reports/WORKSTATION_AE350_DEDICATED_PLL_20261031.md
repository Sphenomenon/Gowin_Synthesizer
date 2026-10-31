# 原生工作站 AE350 专用 PLL 约束与校验（2026-10-31）

本批把官方要求的 `PLL_R[0] > CLKOUT1` 纳入原生 prepare 与物理 PLL 子门禁。源码父提交为 `20633651136c8a919ad2c647c7556ac98e89fa37`，分支为 `codex/native-ae350-pllr0`。本批没有运行综合、P&R、烧录或板上操作，也没有取得整机物理或硬件验收。

## 版本化边界

- `boards/custom_138k/ae350.cst` 只有一条 `INS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];`。所有新原生 prepare 将它作为第八个组件加入唯一启用的 combined CST，并记录组件、合并前后约束和手册依据的哈希。
- 依据为 `docs/ae350/manuals/MUG1031-1.3.1_Gowin_RiscV_AE350_SOC硬件设计用户手册.pdf`，SHA256 `0f357e21c8341a23a399a32a54bc706de953767235826ed39886924549756dc3`，PDF 第 54、56 页（印刷页 46、48）。既有顶层已把 `u_cpu_pll/PLL_inst/CLKOUT1` 直接连接到 AE350 `CORE_CLK`；本批不改 RTL、时钟速率、复位或固件。
- `workstation_ae350_clock_placement.py` 分开验证 requested CST、实际 TR 位置和 post-PNR 硬宏连接。位置摘要不能代替物理路径行；全部实际 CPU PLL 位置必须为 R0，必须存在 CLKOUT1 位置证据。核心时钟必须由该输出直接驱动，允许的其他端点仅为 DFF 的 CLK。
- 小型网表解析器现在完整检查模块端口声明、命名绑定和模块语句覆盖。嵌套表达式、遗漏的单行实例、端口空格形式、ANSI 声明、连续赋值、初始化 wire、重复 formal、buffer 与额外驱动均不能被静默忽略。转义标识符按 `(scope, scalar name)` 比较，避免 `\\core_clk` 别名和转义斜杠造成误判。
- profile 验证器与通用源码审计器都重新计算组件和元数据，prepare 不能声称已布局或已上板。物理 PLL 审计把该独立子门禁的失败计入总失败，封存 CST/TR/VO 和校验源码，并增加 requested/actual site 负例。
- 物理审计的无本地面板分支只允许三个显式 profile：原 R00、LOCAL_BOOT64、AE350 business；三者均核对当前 specification 的 revision、完整配置、profile 来源和退役面板元数据。历史默认分支仍要求 LCD。

业务 profile 升到 revision 3，增加 `ae350_core_clock_policy=pll_r0_clkout1_v1`，整合身份为 `custom138k-native-ae350-business-revision3`。其他五个 profile 的功能配置、revision 和 source_sets 保持原值，只刷新共享工具/测试源码锁并加入新依赖。accepted、pinned、frozen baselines 与旧生成证据没有改变；旧候选应继续使用其固定版本工具。

## 实际 prepare 与字节对照

使用 xPack `riscv-none-elf-gcc-15.2.0-1` 的显式 prefix 和已锁定的 `.tel` 缓存执行真实 prepare。业务输出目录为外部缓存 `native-ae350-pllr0-source-v1/prepare-business-final5`、`prepare-business-final6`，候选分别为：

- `custom138k-workstation-ae350-business-v1-8c0ef557459188f4`
- `custom138k-workstation-ae350-business-v1-7a8f1f13ff44073c`

两次全部 613 个 staged 文件逐字节相同，启用输入仍为 271 项。相对前业务候选 `custom138k-workstation-ae350-business-v1-fa5d45ee77c98b1d` 的 612 项，只增加 `constraints/custom_138k.ae350.cst` 并改变 combined CST；另一个原始文件差异是 USB 固件 build.log 中的绝对源码目录，替换目录前缀后字节相同。全部编译输入清单、RTL、SDC、固件、USB ROM 和 AE350 ROM 字节保留。

两个业务候选编号不同来自现有栈分析的等成本调用链 tie：末端可能为 `business_mmio_read` 或 `business_mmio_write`，其 `build_metadata.json` 哈希随之不同。候选身份保留实际元数据；不把它们说成同一个 artifact。完整原始数据及差异在下方 JSON 索引指向的外部比较结果中。

默认运行时 profile 也真实 prepare，候选为 `custom138k-workstation-v1-0d440146e9b35242`（260 个启用输入），revision 仍为 5。全部新输出的 routed/hardware/deployment 字段仍为 false。

## 校验结果

| 范围 | 结果 |
| --- | --- |
| 新专用门禁、C8/C9 固定输入、真实 prepare 篡改 | 8 项通过 |
| 默认 profile 源码与真实闭包 | 21 项通过，1 个未选择的历史 prepare 测试跳过 |
| 业务 profile 源码与真实闭包 | 8 项通过 |
| 物理 PLL 审计单元回归 | 21 项通过，1 个未选择的完整物理测试跳过 |
| implementation 准备边界 | 22 项通过 |
| accepted/current 输入边界 | 17 项通过 |
| 通用原生 prepare、HS/FS、TMDS、CLI 等无综合回归 | 7 项通过；第八项发现旧七组件重建遗漏，修正后单独重跑通过 |

新门禁覆盖 9 组 CST 负例、27 组实际位置/输出/连接负例，以及转义别名、scope 分离、组件和元数据篡改。独立只读 peer review 重现过解析绕过，修复后再次检查八类绕过均被拒绝，最终 helper SHA256 为 `91406aea69b47f415062900e29fd0f3345cf688da89d65aa3c88240e920979b7`。

固定 C9 的 4107 条实际位置行全部为 R0，另 16 条无位置摘要仅记录而不计作布局证据；直接端点为 CPU、PLL 与四个 reset-pipe CLK。C8 在内存中补入 requested R0 后仍因实际 B2 位置失败。六个原始 CST/TR/VO 文件校验前后哈希相同。它们只验证新门禁如何判读既有路由输入，不向本批完整工作站继承任何物理或板上结论。

默认闭包负例还修正了一处既有测试文案：破坏 ROM 时，先发生的严格 ROM 行数拒绝现在也被断言接受；拒绝条件和生产代码没有放宽。

## 证据、后续与回退

机器可读索引：[ae350_native_pll_r0_source_20261031.json](workstation_task_20261030/ae350_native_pll_r0_source_20261031.json)。它记录全部成功命令/日志哈希、真实 prepare 身份、固定输入哈希、完整 staged 对照和六个 profile 的配置对照。外部交付封存目录为 `~/.cache/gw138k-task-20261030/native-ae350-pllr0-delivery-v1`；源码提交及 seal 将由集成阶段引用。

下一步必须把源码合入当时的主线，刷新同期变动涉及的 source locks，重新 prepare 并使用新的候选身份，再进行整机综合、实际布局和完整时序/CDC/硬件验收。本批没有 bitstream 或可部署验收结果。回退为撤销本批源码提交并使用原候选的固定源码/工具/约束；不得以删约束的方式把新候选复用为旧身份。
