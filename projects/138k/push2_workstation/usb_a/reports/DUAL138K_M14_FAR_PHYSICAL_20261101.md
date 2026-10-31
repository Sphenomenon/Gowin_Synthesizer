# M14 D2110109 远区完整物理对照

2026-11-01。M14 far 全量 P&R 和完整 routed 子门禁已完成。全局 hold 0 违例、最小 +0.135 ns，原 DDR 3.500 ns 路径 +0.620 ns；setup 仍有 4251 个违例 endpoint、最差 −2.526 ns，相较默认 −1.940 ns 回退。recovery +2.428 ns、removal +0.278 ns。时序未闭合，不能部署。

候选继续为 `custom138k-workstation-m-demo-v1-0e7a7f996619ed83`，新物理身份 `D2110109`。VG `414081bc…a6db78`、完整 SDC `6fa398b1…1562c` 与默认 `D2110108` 逐字相同，只在原 CST 末尾追加两条 DDR launch／capture 远区约束，并使用新 UserCode；保持 DDR minimum 3.500 ns、place=2、route=0、replicate=false。未加入 reference-monitor 区域、未删除功能或放宽时钟／例外。

实际原 DDR launch 位于 `R104C175[0][A]`、capture `R2C2[0][A]`，均命中要求的远区；arrival 6.038 ns、required 5.418 ns、skew 0.474 ns。全量 P&R exit 0、378.446 s，FS SHA256 `becf25b441b4dea3483a09d222395ce7a403f95c064a7daac026330717e1a493`。

物理 Logic 66,295、LUT 52,031、ALU 13,418、FF 46,932、CLS 50,303、BSRAM 235／340、SSRAM 141、DSP 119。综合 BSRAM equivalent 仍为 195，不能把两者混算。最差 setup 是 USB online 同步状态至音频事件队列；chorus LFO 至读地址和 HDMI waveform poles 之间也有真实违例。50 MHz 最差 setup 按实际表另记于机器记录，不能只关闭 DDR hold 就宣称完整时序通过。

固定 M14 的 1207 文件快照和 588 staged 输入在每组分析前后复验；32 份物理文件在六组独立审计前后保持。Native 实际 VO CLI 与 54 项回归（51 通过／3 跳过）、46 负控通过；DEMO boundary 7 项及 61 负控通过；官方 6 PLL／3 shared tuple／7 负控通过，685 份依赖重新核验。源证明、阈值与历史审计保持，当前 PCM／raw／TF 后续维护源没有混入本候选。

[机器记录](dual138k_m14_far_physical_20261101.json)绑定完整输入、资源、四类 STA、实际路径、执行命令及封存身份。本次无 SRAM／Flash 或板操作；M 基础 CNN、完整 HDMI／DAC／Push／25K 声画实板和双板并发仍未验收。下一 M 候选按新的来源身份重新综合，不继承本位流的接受状态。
