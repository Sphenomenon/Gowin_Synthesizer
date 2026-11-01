# M18 far 完整物理结果

M18 `custom138k-workstation-m-demo-v1-0fcc5e52da20b9d1`／`D2110117` 完成全量 P&R，退出 0 并生成位流；完整 STA 仍失败，未烧录 SRAM。本候选从默认 `D2110116` 的 hash-bound routed VO、同一 VG 和完整 SDC 严格派生，只追加两条既有 DDR 远区 CST 并使用新 UserCode。

| 实测项 | 结果 |
|---|---|
| P&R 时间 | 482.268 秒 |
| 物理 Logic／FF／CLS | 67,682／46,932／50,884 |
| 物理 BSRAM／DSP | 235／119 |
| LUT／ALU／SSRAM | 53,725／13,111／141 |
| setup 负端点／最差 | 1,093／-0.866 ns |
| hold 负端点／最差 | 3／-0.113 ns |
| recovery／removal 最差 | +2.222／+0.281 ns |
| 音频域 setup 负端点／TNS | 852／-268.087 ns |
| DDR UI 域 setup 负端点／TNS | 240／-87.478 ns |
| 四张 clk50 专项报告最差 | +0.487／+0.164／+0.487／+0.164 ns |

全局最差 setup 为 `online_sync_1_s0/Q → config_state_0_s1/CE`（−0.866 ns）；`config_accept_pending_s0/Q → delay underflow_sticky_s1/CE` 为 −0.864 ns。TF 最差为 `available_bytes_7_s0/Q → accepted_used_30_s0/D`（−0.864 ns），都是真实同域链。三个 hold 负端点全部位于 `reference_48_monitor` 的 `source_binary → source_gray`：−0.113、−0.061、−0.059 ns，仍需修复；不能因 DDR hold 转正而宣称 hold 闭合。

原 DDR 初始化 `ddr_init_internal_r_s0/Q → wloadn_3_s0/D` 的 3.500 ns 最小延迟要求保持。实际 launch `R104C175[0][A]`、capture `R2C2[0][A]` 均在指定远区；arrival 5.948 ns、required 5.414 ns、clock skew 0.470 ns，hold 为 +0.534 ns。对照默认的 −3.638 ns，这只是同一 RTL 的本次布局结果，不预记资源收益。默认／far 物理 BSRAM 均为 235，DSP 均为 119。

TF 路由细节来自原 `.tr` 第 8761–8831 行的唯一匹配路径：16 级，data delay 10.817 ns（cell 6.259、route 4.252、C2Q 0.306 ns），arrival 13.773 ns、required 12.910 ns。实际链为 `available_bytes[7] → ring_upper_equal_0 → available_full_group_0 → available_full_binary → read_response_bytes[5] → occupancy_read_delta → occupancy_input_read_delta[4:5] → accepted_after_input_read/COUT → accepted_without_write[9,31,30] → accepted_pending_only[30] → n7749 → accepted_used[30]`。构建消费的冻结 TF 源码第 199–201 行仍以 generic `occupancy_read_delta`／`occupancy_input_read_delta` 计算 accepted 响应分支；这支持继续对该分支做等价改写，但未证明任何新改写的物理收益。完整原文、节点延迟、来源 SHA 和 staged 源码第 199–249 行保存在机器报告与 `m18-far-tf-critical-path-v1` 缓存证据中。路径 summary 的 skew −0.004 ns 与 detail 的 clock skew +0.004 ns 原样分别记录，不混用符号约定。

六组审计均退出 0：原生 VO CLI、58 项真实网表回归（55 通过／3 跳过、71 负控全拒绝）、边界 7 项／69 负控、官方六 PLL／启动检查及 7 负控通过。边界正例 fault FF／RAM 消费者 663／8，queue FF／RAM 消费者 140／2。held v2 在实际物理入口通过；PC 仅覆盖 power-up-only，不声明 warm reset。三项跳过对应该网表不存在的两种 APB CE 变体及反相 LUT1 映射。四张 clk50 专项表各最多 100 条，不代表完整全局计数。所列 setup 域端点与全局总数按原报告分别保留，不推断其他端点归属。

独立重验 32 份物理输入／输出、30 份封存审计文件、1395 份冻结工具、588 份 staged 输入、875 份原 prepare 来源快照及 PLL 683 项输入依赖／685 项证据；加入 dispatcher、TF 路径和默认对照后去重共 2971 个缓存文件。只读取冻结来源，没有用正在修改的维护树替代旧输入。初始 dispatcher v1 因 schema 锚点断言退出，发生在写 runner 或审计执行之前；失败目录及记录保留，实际执行的是已通过输入预检的 v2。

完整来源、配置、资源、时序、测试跳过、负控、命令和逐文件 SHA256 见[机器报告](DUAL138K_M18_FAR_PHYSICAL_20261101.json)。summary SHA256 `9a2f8f499cad7d3dcde94d583bf97b0b1d30a6cfdcdaed8bcac0b537478eac14`；final-seal SHA256 `e054403cd7588f9d23945334bcf68ba86f7d5820fe5bf0fa97f4bfd809d3db27`；独立复核记录 SHA256 `aeddc1c77d00bdaf870e6defff26feea2cf837ee967c65df1fb98cdfb12a7b9f`；位流 SHA256 `8269c46556aeefded63b8a3087e202b4901356a2ae3e40530f72248751c130e4`；far manifest SHA256 `8d7258d6014c48758022128ab7bcf762fdb5d813ed71e746147defe0508b49de`；完整 SDC SHA256 `73105b6007550a223db8520667a7d7e7af2d2247af9f235a8a6a13e37d3e61e5`。

本 M 基础候选没有 CNN；真实 HDMI、I2S／DAC、Push／25K、TF 声画未完成实板验收。六审计和 selected PLL／held 子门通过不覆盖完整 STA 失败。本阶段没有启动综合／P&R、烧录 SRAM 或写 Flash；现有板上镜像保持，不宣称双板并发验收。

主线程再次独立重读全部 2971 个证据文件并逐项核对 SHA256；root review SHA256 `ff92c75adbe3b4aedba969554874bcffb3e6e886294c51dcc73de23827034713`。
