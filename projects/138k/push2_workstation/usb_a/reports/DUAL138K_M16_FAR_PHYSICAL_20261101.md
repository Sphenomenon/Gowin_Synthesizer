# M16 far 完整物理对照

M16 `D2110111` 已完成完整 P&R 和六组子审计。原 DDR 3.500 ns hold 路径余量 +0.682 ns、全局 hold 0 个违例／+0.123 ns；setup 仍有 583 个违例端点，最差 −1.221 ns。recovery +1.745、removal +0.278 ns，整机仍未闭合，未上板。

候选仍为 `custom138k-workstation-m-demo-v1-5f5ba9978313e96b`，保持默认完整 VG／SDC，只追加两条 DDR 远区域 CST，无 monitor 区域或时钟／例外放宽。physical manifest SHA256 `59af3212489ada8505b886930ed72b20cdd4ac05bd962ad059b04a2baf6df0f2`；FS `0998f4db006264de9908b36b86c9a8e82bb1a2bf1a5785a5bdc6680c7d6cfec6`。Gowin V1.9.12、place2／route0、关闭资源复制，P&R 566.554 秒、退出 0，布线和位流完成。[机器报告](dual138k_m16_far_physical_20261101.json)绑定全部输入、配置及审计命令。

物理 FF 46,932、LUT 53,812、ALU 13,090、CLS 51,028、BSRAM 235、DSP 119、SSRAM 141。DDR launch R104C175→capture R2C2，arrival 6.044、required 5.362、skew 0.418 ns，原要求保持。四条实际 clk50 专项 setup／hold 为 +2.223／+0.123 ns，全来源为 +0.792／+0.123 ns；报告各限 100 条，不冒充完整端点统计。最差仍为 PC held_data→destination_data 的跨域握手数据路径，且仍有真实同域负路径；相关源码及窄 CDC 正核对，不能据 DDR 子路径通过转授全机接受。

实际 VO native 54 项（50 通过／4 跳过）及 45 破坏负控、boundary 7 项及 61 负控、官方六 PLL／三 shared tuple／7 负控全部通过。全部任务退出后，主线程重验 32 物理文件及 2939 项证据，包含 1374 冻结审计输入、588 staged、875 prepare 来源及 685 PLL 依赖。完整 seal `m16-audits-v1/far-complete-seal-v1.json` SHA256 `4a926e0a6bf43efa63f5ed93af97aefc8e4664a44104d98569c1e5dfd92d13e9`。

本基础 M 无 CNN；后续 TF cofactor 与 boundary 审计修复没有混入原候选。无 SRAM／Flash 或板卡操作，完整 HDMI／DAC／Push／25K／TF 实板声画、CNN 跟奏、手机和双板联合验收均未完成。
