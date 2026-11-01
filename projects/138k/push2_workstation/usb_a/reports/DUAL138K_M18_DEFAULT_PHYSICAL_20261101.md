# M18 默认完整物理结果

M18 `custom138k-workstation-m-demo-v1-0fcc5e52da20b9d1`／`D2110116` 完成全量 P&R，退出 0 并生成位流；完整 STA 失败，未部署 SRAM，不是已验收的声画镜像。本报告只描述默认布局，far `D2110117` 另行封存。

| 实测项 | 结果 |
|---|---|
| P&R 时间 | 479.336 秒 |
| 物理 Logic／FF／CLS | 67,681／46,932／50,920 |
| 物理 BSRAM／DSP | 235／119 |
| LUT／ALU／SSRAM | 53,725／13,110／141 |
| setup 负端点／最差 | 1,813／-1.652 ns |
| hold 负端点／最差 | 1／-3.638 ns |
| recovery／removal 最差 | +2.933／+0.278 ns |
| 音频域 setup 负端点／TNS | 1,294／-816.386 ns |
| DDR UI 域 setup 负端点／TNS | 475／-284.591 ns |
| clk50 同域 setup 负端点／TNS | 43／-15.767 ns |
| 四张 clk50 专项报告最差 | −1.309／+0.137／−1.309／−3.638 ns |

最差 setup 是 TF DMA 的 `available_bytes_9_s0/Q → accepted_used_22_s0/D`（−1.652 ns）；显示 `expected_sequence_0_s0/Q → context_unavailable_o_s1/CE` 为 −1.648 ns；音频效果 `transaction_fault_s0/Q → vector envelope[7] CE` 为 −1.639 ns。它们都是真实同域路径，不能用跨域握手例外豁免。四张 clk50 专项表各最多 100 条，报告条数不能代替完整全局端点计数。

唯一 hold 为 DDR 初始化 `ddr_init_internal_r_s0/Q → wloadn_3_s0/D`。原要求仍为 3.500 ns，arrival 1.970 ns、required 5.608 ns，clock skew 0.667 ns；实际 R68C9[1][A] → R68C4[0][A]，裕量 -3.638 ns。没有放宽完整 SDC 或门槛。

六组审计均退出 0：原生 VO CLI、58 项真实网表回归（55 通过／3 跳过、71 负控全拒绝）、边界 7 项／69 负控、官方六 PLL／启动检查及 7 负控通过。边界正例实测 fault FF／RAM 消费者 663／8，queue FF／RAM 消费者 140／2。held v2 在实际物理入口通过；PC 仅证明 power-up-only，不声明 warm reset。三项跳过对应此网表没有的两种 APB CE 变体及反相 LUT1 映射。子门通过不等于完整 CDC／物理时序接受。

主线程生成的 summary SHA256 `b466c0f20aaaf25d0070df3b85662cefa7326df1be1ab6d8a0a70a4035286d02` 与 final-seal SHA256 `4338d2c4ee7ad7993d3d1c09b08776efcb85bbbacf3c5ca3a8f89111cdaf5620` 已由独立子代理逐项复核。复核覆盖 30 份完整物理输入／输出、30 份封存审计文件、1395 份冻结工具、588 份 staged 输入、875 份原 prepare 来源快照及 PLL 的 681 项输入依赖；去重后共 2966 个冻结缓存文件。计数允许跨集合重叠，不相加冒充唯一文件数。原始工具与来源只读取冻结快照，未将正在修改的维护源码当作本候选旧输入。

来源、命令、配置、全部资源／时序、负控范围和逐文件 SHA256 见[机器报告](DUAL138K_M18_DEFAULT_PHYSICAL_20261101.json)。独立复核缓存记录 SHA256 `533a8e67a8d29c749378013aa1cd4ad492e52a1198cf07e54a60d1bd14ec80fc`；证据清单 SHA256 `1f420df71ff51b10382bdeb32227b9a07de5674b80eaf86f96903d314131dc22`。位流 SHA256 `dec4442a90d59f602afbc9b60da3f4193c511b7f74e1fe315374580ed13d018b`；物理 manifest SHA256 `8cd2aa68772ef4ba3a71d9180ea1a11db788c2bbfa6cb86c0012277bbd6fc21b`；完整 SDC SHA256 `73105b6007550a223db8520667a7d7e7af2d2247af9f235a8a6a13e37d3e61e5`。

主线程再次独立重读全部 2966 个证据文件并逐项核对 SHA256；root review SHA256 `280d06b56eaaf5d3ca19e6dc66bf49bedd24ba9e7de8229862c8f879954693a1`。

本 M 基础候选没有 CNN；真实 HDMI、I2S／DAC、Push／25K、TF 声画尚未完成实板验收。本阶段未启动 EDA、未烧录 SRAM、未写 Flash，不改变板上镜像，也不把单板分时验证视作双板并发验收。保留冻结失败证据，继续按真实同域路径和独立 far 对照推进。
