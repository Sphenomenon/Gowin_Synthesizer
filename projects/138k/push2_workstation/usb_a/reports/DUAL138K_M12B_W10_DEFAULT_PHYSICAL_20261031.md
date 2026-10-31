# M12b／W10：完整默认物理实现

2026-10-31。两份完整候选均已全量综合、通过综合严格门，并完成 P&R 和位流生成。**完整 STA 均失败，尚不可部署**。本阶段没有下载 SRAM、写 Flash 或进行实体验收。

M12b 身份为 `custom138k-workstation-m-demo-v1-0af82c38b1902d92`，588 项封存输入、261 项启用源；W10 为 `custom138k-workstation-w-demo-v1-d1dddd2e83ad1cfd`，645 项封存输入、284 项启用源。两份全部封存输入、物理输入与测量记录的输出哈希均再次核对。未修改冻结候选或 accepted 基线。

| 完整默认 P&R | Logic | FF | CLS | 物理 BSRAM | DSP | setup 端点／最差 ns | hold 端点／最差 ns | recovery／removal ns |
|---|---:|---:|---:|---:|---:|---|---|---|
| M12b `D2103118` | 66,204 | 46,931 | 50,315 | 235／340 | 120 | 3,340／−1.656 | 4／−3.457 | +3.472／+0.281 |
| W10 `D2103116` | 83,724 | 45,073 | 57,462 | 293／340 | 67.5 | 5,750／−5.583 | 2／−3.652 | +2.313／+0.278 |

M12b 综合 LUT52,052、ALU12,890、BSRAM equivalent195；物理 LUT51,936、ALU13,422、SSRAM141。W10 综合 LUT60,993、ALU20,321、BSRAM equivalent257；物理 LUT60,853、ALU21,011、SSRAM310。W10 的真实 DSP 用量为 **67.5**，不是取整后的68。首次测量脚本仅因不接受该分数格式失败，原日志保留；新的 v2 测量保持分数。综合等效 BSRAM 与物理 BSRAM 分列，不据此预记资源收益。

M12b 最差音频路径为 `runtime/config_accept_pending`→效果 RAM CEA，−1.656 ns；TF DDR DMA `available_bytes`→占用更新为 −1.642 ns。四条实际 50 MHz 专项报告分别最多100条，同域 setup +1.360 ns、同域 hold +0.183 ns、to-clock setup +0.748 ns；to-clock hold 仍有 DDR 初始化路径 −3.457 ns。这些有限报告不代替完整端点统计。

W10 最差路径为 `recording_ble_store/published_valid`→录音写地址 CE，−5.583 ns，真实两端均为 DDR UI 100 MHz，不是异步例外。50 MHz 同域 setup 专项最差 −3.205 ns，来自 decoder handle 经关闭代次比较到 Host RX lease RAM WRE；同域 hold +0.201 ns。正在各自所属模块处理，不放宽时钟、同步 reference48 hold 或录音发布语义。

默认 DDR 初始化保持原 3.500 ns 要求：M12b 实际 R92C10→R92C6，arrival1.996／required5.453 ns；W10 为 R90C157→R90C156，arrival1.790／required5.442 ns。已分别从本次测量及其 SHA／VO 派生 `D210311A`／`D2103119` far 变体，VG／完整 SDC 不变，完整 P&R 结果另记。

W10 默认的实际 VG／VO 原生协议 CLI 和实际 SDC 检查通过；VO 回归54项中40通过、14按角色不适用跳过，35项破坏负控均拒绝。官方 simlib 的 PLL／selftest 子门及7负控通过；首次缺模型环境的日志保留。M12b 原生 VG 基线通过，路由后 VO／PLL 审计仍在进行，不能继承旧候选通过。

[机器证据](dual138k_m12b_w10_default_physical_20261031.json) SHA256 `96b1427082ff98d5ae676499f28a5b5dc1feee169c4ab2fd1cb897db821db7ce`，固定完整来源、配置、位流哈希、实际测量、四条专项报告和审计范围。W10 位流 SHA256 `338bebb18365354c5d8ec6e9bd6dd6ac6dae5113dba5652d73a96f532869b9a4`；M12b 位流身份同样绑定于机器证据，未部署。原物理清单中的否决状态不追改。

M 基础候选尚不含 CNN；W 唯一 DDR 录音对象仍为16,384帧／64KiB，非最终长录音。用户确认当前只有模拟器，真实安卓手机 A2DP／BLE 验收稍后进行；模拟器不计为无线验收。当前也没有真实 HDMI 像素／模拟 DAC 采集证据。完整独立演示、LCD 通信和双板并发均未结项，受保护单板主区及板上镜像保持原状。
