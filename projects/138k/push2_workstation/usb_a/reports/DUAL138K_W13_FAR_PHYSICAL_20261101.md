# W13 D211010B far 完整物理对照

2026-11-01。W13 far 全量 P&R exit 0、402.312 s，真实 VO 的独立子门通过，STA 仍失败。原 DDR 3.500 ns 路径 hold 为 +0.473 ns，全局 hold 0 个违例、最小 +0.135 ns；setup 仍有 6,750 个违例 endpoint、最差 −5.562 ns，不能部署，未上板。对应[机器记录](dual138k_w13_far_physical_20261101.json)；默认父候选见[默认完整物理结果](DUAL138K_W13_DEFAULT_PHYSICAL_20261101.md)。

## 来源与实际配置

候选仍为 `custom138k-workstation-w-demo-v1-bc065b3de8977725`，本次物理 UserCode 为 `D211010B`。直接复用默认 `D211010A` 的真实 VG 和完整 SDC，逐字节相同；不重综合，不消费当前工作树的新 HCI／显示／CLEAR 实验。唯一布局变更是在父 CST 后追加两条 DDR launch／capture far region：`ddr_init_internal_r_s0` 放于 `R[104:110]C[175:181]`，`wloadn_3_s0` 放于 `R[2:10]C[2:20]`。原 ULPI IO type 适配、DDR 3.500 ns、自动 hold repair、place=2／route=0／replicate=false 保持，没有放宽时钟或例外、没有追加 reference-monitor 区域。

| 身份 | SHA-256 |
|---|---|
| 原 W13 prepared manifest | `78c2602862e32ecc193c475f156d0ba58b164220f7ebeb84777fa26b997468cd` |
| 本次 physical manifest | `f5779937407b38694ad56098de5c3d69d7cd36a60064fd2c02493666129dfd21` |
| 实际 VG | `3c7866321188f7b36dc601c36f6b572b04ee5c5f7786f434a10a1b0d2bb4a787` |
| 完整 SDC | `fa6bfc049f6a1f4910d8c4391f04457534ef67deeb5eccb5d4f38aaaef704f65` |
| 本次 FS 位流 | `ae3973bc6aaa69d1ed0ced09da78f52ffb1da3c9845fb08fa245f5763859811f` |
| 实际 routed VO | `9ccdcc203133a13d9180951d1762139fed478409461f30e0904b563bb5837a33` |

完整输入及输出位于缓存 `w-demo-d-v13-physical-far-v1`。来源 manifest 的 commit／revision 字段为空，来源身份依靠上述候选、完整封存输入及哈希确定，不补造 commit 来源。独立复验确认 CST 的父字节完整保留、只追加所述两条区域约束。

## 实测资源与四类 STA

物理 Logic 71,643、FF 45,092、LUT 55,137、ALU 14,718、CLS 52,497、BSRAM 293／340、SSRAM 298、DSP 66.5。综合 BSRAM equivalent 257 单列，不能与物理块数相减。两份 W13 的来源相同，本次小幅映射／放置差异不作为新 RTL 的资源收益。

| 检查 | 默认 D211010A | far D211010B |
|---|---:|---:|
| 最差 setup／违例端点 | −5.765 ns／6,829 | −5.562 ns／6,750 |
| 最差 hold／违例端点 | −3.537 ns／3 | +0.135 ns／0 |
| 最差 recovery | +2.468 ns | +2.202 ns |
| 最差 removal | +0.281 ns | +0.281 ns |

far 最差 setup 为真实 `u_video/u_arbiter/g_recording.u_core/g_recording.read_pointer_1/Q → recording_ble_store/fetch_address_9/CE`，同域 DDR UI 10.000 ns 关系，数据延迟 15.302 ns、报告 skew +0.011 ns。该项及后续 `memory_failure`、`memory_generation` 等 CE 路径仍失败；不能把此前 write-address CE 的局部缩短扩展成全部录音许可已闭合。CACHE-only CLEAR 候选未包含在本位流内，`fetch_address` 的实际写入支路仍须单独核验。

原 DDR hold 的 arrival 5.887 ns、required 5.414 ns、relationship 3.500 ns、报告 clock skew 0.470 ns；launch `R104C175[0][A]`、capture `R2C2[0][A]` 均落入各自区域。该路径转正不代替全局 setup 验收。

## 50 MHz 报告与独立子门

`clk_50m` 要求仍为 50 MHz，工具报告实际 41.425 MHz；完整 setup 表为 823 个违例 endpoint、TNS −1515.549 ns，默认父候选为 728 个／−1102.284 ns。本次 far 的全局最差 setup 略好，50 MHz 域的整体 setup 却恶化，两者分别记录。

| 实际 report_timing 表 | 最差余量 | 表内负路径／已报告路径 |
|---|---:|---:|
| `clk_50m → clk_50m` setup | −4.140 ns | 100／100 |
| `clk_50m → clk_50m` hold | +0.135 ns | 0／100 |
| `→ clk_50m` setup | −4.140 ns | 100／100 |
| `→ clk_50m` hold | +0.135 ns | 0／100 |

以上各表限制为 100 条，不把采样路径数写成完整违例端点数。最差 50 MHz setup 为 HCI `decoder/handle_o_0/Q → transport/retry_timer_2/CE`，20.000 ns 关系、数据延迟 23.944 ns；维护源后续修复不回填本候选。

Native VO CLI、54 项实际 VO 回归（41 通过／13 跳过）与 36 个破坏负控通过；DEMO boundary 7 项／61 负控通过；官方 6 PLL、3 shared tuple、7 负控通过。PLL 完整证据 915 份依赖及 913 份输入快照均复验，不能把这些有范围的子门通过称为完整 CDC、全部 IO、电气或板级接受。

完整 seal `w13-audits-v1/far-complete-seal-v1.json` SHA 为 `2f2f9a3a1924a7fc8b200b74f6fb537098a8579810bcbccf516c9f9c0ac57b64`。本报告独立读取实际字节，复验 32 份完整物理文件、36 份封口证据、1,365 份冻结工具／源码／测试输入、645 staged 输入及 915 PLL 依赖；六组 job 的退出、来源前后稳定性和物理目录封口均通过。机器记录绑定完整四类 STA、clk50 四表摘要、子门及每份证据哈希。

## 回退与剩余缺口

本阶段未操作板卡，未烧录 SRAM／Flash，原板上镜像不因本阶段改变。保留默认 `D211010A` 与 far `D211010B` 的完整输入、位流和失败证据作离线回退／比较；两者均不是已接受部署对象。

仍需闭合完整 setup、CDC／外部 IO／电气，完成真实手机 A2DP／BLE／D 效果、25K 实际控制、完整 HDMI 与 I2S／DAC、唯一 DDR 录音与手机下载，以及业务期间连续声画验证。独立或单板分时运行不能替代 LCD 互通与双板并发；CAM／YOLO 仍按真实实现／模型缺口另记。本次不转授上述接受状态。
