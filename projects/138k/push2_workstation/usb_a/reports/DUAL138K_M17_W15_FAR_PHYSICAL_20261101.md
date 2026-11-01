# M17／W15 far 完整物理对照

两套 far 均完成全量 P&R 及六组物理审计。原 DDR 3.500 ns 要求保持，两条明确远区 CST 使本轮目标 hold 为正，全局 hold 无违例；完整 setup 仍失败，不能部署或当作声画演示通过。

| 实测项 | M17 far | W15 far |
|---|---|---|
| UserCode | `D2110113` | `D2110115` |
| P&R 时间 | 404.157 秒 | 533.032 秒 |
| Logic／FF／CLS | 67,674／46,932／51,003 | 73,332／45,092／53,252 |
| 物理 BSRAM／DSP | 235／119 | 293／66.5 |
| LUT／ALU／SSRAM | 53,723／13,105／141 | 57,163／14,381／298 |
| setup 负端点／最差 | 2,614／−1.767 ns | 6,813／−4.798 ns |
| hold 负端点／最差 | 0／+0.134 ns | 0／+0.151 ns |
| DDR 目标 hold | +0.565 ns | +0.679 ns |
| DDR arrival／required | 5.983／5.418 ns | 6.093／5.414 ns |
| clk50 四表最差 | −1.114／+.134／−1.114／+.134 ns | −4.298／+.196／−4.298／+.196 ns |

每套仅从自己的默认候选派生，完整 VG／SDC 逐字保持，CST 仅追加既有两条远区约束。实际 launch R104C175、capture R2C2 都位于指定区域。每份 clock 专项表最多 100 条，不能当作全局违例计数。配置及来源身份与各自默认候选相同，改变的物理输入、运行脚本和位流另立身份。

M 的最差音频同域路径为 USB `online_sync_1/Q→config_accept_pending/D`（−1.767 ns），DDR 为 TF `available_bytes[6]/Q→read_buf/CE`（−1.766 ns）。50 MHz 另有 stream epoch 至 booting 的 −1.114 ns。W 的最差 DDR 为 recording arbiter `read_pointer[0]/Q→raw memory_failure/CE`（−4.798 ns），return token 仍接近 −4.792 ns；音频欠载至 PCM written 为 −4.693 ns，50 MHz boot ID 至 CPU mailbox 为 −4.298 ns。继续按这些真实路径修复；W far 比默认 setup 更差，不据目标 hold 改善推断整机收益。

两套原生 VO 回归各 58 项：M 55 通过／3 跳过、71 负控全拒绝；W 44 通过／14 跳过、60 负控全拒绝。两套边界各 7 项／69 负控，官方六 PLL／启动各 7 负控及 held v2 实际入口均通过。所有跳过及映射范围列于[机器报告](dual138k_m17_w15_far_physical_20261101.json)，子门通过不替代完整 STA／CDC／硬件接受。

主线程分别逐项重读 32 份物理文件和 2949／3255 份证据，含各 1381 冻结工具、588／645 staged、875／951 prepare 来源及 683／913 PLL 依赖。M 位流 SHA256 `667789c2581271bfe3c5f02d0b762565635dc3cf1eb7e108c210fe38cff8aea2`，W 位流 SHA256 `3b79eb7b446b2f2544a23f4c05a6b4327f771fd6976a5b2fa10f5f553cc223b7`。物理 manifest SHA256 分别 `78a677c27b3faaac1d08212b78ec91b307dc4654c2a6c1eb57d878e5a081f45d`、`e3045696a159fe43a2c0c2a427f2fa7a6bb30f3f33e9d4c3bddd9aee3405ca67`。

本阶段未烧录 SRAM 或写 Flash。M 仍无 CNN，W 仍是 64 KiB 唯一短录音对象；两套真实 HDMI／DAC、Push／25K、蓝牙 D／下载均未实板验收，真机手机稍后。没有双板并发证据，板上原镜像保持。
