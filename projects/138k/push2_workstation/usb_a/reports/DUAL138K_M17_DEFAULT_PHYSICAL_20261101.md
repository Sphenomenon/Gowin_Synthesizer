# M17 默认完整物理结果

M17 `custom138k-workstation-m-demo-v1-234d2c6a3ef6abac`／`D2110112` 完成全量 P&R，退出 0 并生成位流；完整 STA 失败，未部署 SRAM，不是合格声画镜像。

| 实测项 | 结果 |
|---|---|
| P&R 时间 | 381.908 秒 |
| 物理 Logic／FF／CLS | 67,671／46,932／50,863 |
| 物理 BSRAM／DSP | 235／119 |
| LUT／ALU／SSRAM | 53,723／13,102／141 |
| setup 负端点／最差 | 3,821／−1.945 ns |
| hold 负端点／最差 | 1／−3.392 ns |
| recovery／removal 最差 | +2.571／+0.278 ns |
| 音频域 setup 负端点／TNS | 3,171／−2310.511 ns |
| DDR UI 域 setup 负端点／TNS | 649／−374.089 ns |
| 四张 clk50 专项报告最差 | +0.393／+0.183／+0.393／−3.392 ns |

最差真实同域路径为 `config_accept_pending/Q` 返回自身 D，另到 vector envelope CE 和 reverb RAM 地址，不能以握手例外豁免。TF 仍有 `available_bytes[6]→accepted_used` 负路径（−1.824 ns）；M17 的组合改写已进入实际网表，但没有闭合这些反馈链。四张 clk50 专项表各最多 100 条，不能用报告条数推断完整全局计数。

唯一 hold 为 DDR 初始化 `ddr_init_internal→wloadn3`。原要求仍为 3.500 ns：arrival 2.041 ns、required 5.433 ns，实际 R68C10→R68C5。独立 `D2110113` far 对照仅追加既有两条远区 CST，完整 VG／SDC 保持，另记其物理结果；这里不回填 far 的裕量。

六组物理审计均退出 0：原生 VO CLI、58 项真实网表回归（55 通过／3 跳过、71 负控全拒绝）、边界 7 项／69 负控、官方六 PLL／启动检查及 7 负控通过。held v2 在实际物理入口通过，PC 仍只证明 power-up-only，不声明 warm reset。三项原生跳过对应此网表没有的两种 APB CE 变体和反相 LUT1 映射；子门通过不等于完整 CDC／时序接受。

主线程逐项重验 30 份物理输入／输出及 2947 份证据，包含 1381 冻结工具、588 staged、875 prepare 来源及 681 项 PLL 依赖。来源、配置、位流、完整资源／时序、命令与负控范围见[机器报告](dual138k_m17_default_physical_20261101.json)。位流 SHA256 `bb2e0478a140f26e9b81e30a57ea29f8fb797d4d6b2f8a71e95ffc71eced7d11`；物理 manifest SHA256 `29cb5d05f50502bdeaf77b03fb6a0d8505e04941b6109cda059e800d57331eb4`。根复核记录 SHA256 `c1b822156fae399587a2d2cd722b9981dbe076f0f69903302ef60be0971eed6d`。

本候选仍无 CNN，真实 HDMI／DAC／Push／25K／TF 声画没有完成实板验收。当前未枚举到 HDMI 采集卡或立体声线路 ADC；连接准备另有只读记录，不能将其视作功能通过。没有烧录 SRAM 或写 Flash，板上原镜像保持。继续修复实测音频／TF 同域控制链，原冻结候选与失败记录保持。
