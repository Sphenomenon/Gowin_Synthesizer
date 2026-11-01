# W15 默认完整物理结果

W15 `custom138k-workstation-w-demo-v1-3b7fddfa2d0ff574`／`D2110114` 已完成全量 P&R，退出 0 并生成位流；完整 STA 仍失败，未部署，不作为合格 D 声画镜像。

| 实测项 | 结果 |
|---|---|
| P&R 时间 | 621.061 秒 |
| 物理 Logic／FF／CLS | 73,336／45,092／53,325 |
| 物理 BSRAM／DSP | 293／66.5 |
| LUT／ALU／SSRAM | 57,163／14,385／298 |
| setup 负端点／最差 | 5,935／−4.089 ns |
| hold 负端点／最差 | 1／−3.454 ns |
| recovery／removal 最差 | +1.685／+0.278 ns |
| 50 MHz setup 负端点／TNS | 1,310／−1637.842 ns |
| 音频 setup 负端点／TNS | 3,260／−5379.921 ns |
| DDR UI setup 负端点／TNS | 1,361／−2573.205 ns |
| 四张 clk50 专项报告最差 | −3.340／+0.132／−3.340／−3.454 ns |

本轮最差 DDR 路径为 `ui_reset_sync_2/Q→recording_ble_store/memory_failure/CE`（−4.089 ns），同源还进入 256bit 返回载荷 CE；音频域为 delay 的 `underflow_sticky/Q→cpu_pcm.owner/written/CE`（−4.088 ns）。它们都是实际功能同域路径，未增加 false path 或放宽时钟。下一修复以这些实测路径为依据；已封存的 completion 组合提案尚未采用，不能预记其收益。

唯一 hold 仍是 DDR 初始化 `ddr_init_internal→wloadn3`：原要求 3.500 ns，arrival 1.979 ns、required 5.433 ns，实际 R86C158→R86C153。保持本轮完整 VG／SDC 的独立 far `D2110115` 已启动，只有两条既有远区 CST 追加，另测其实际结果。四张 clk50 专项表各最多 100 条，不以条数代替完整计数。

六组物理审计全部退出 0。原生 VO CLI 和 58 项回归为 44 通过／14 跳过，60 个破坏负控全拒绝；跳过项为 W 已退出的十项 TF，以及此映射不存在的四种 APB 变体。held v2 的 25 个破坏检查全部执行。边界 7 项／69 负控、官方六 PLL／启动和 7 负控通过，held v2 实际物理入口通过；这些是子门通过，完整 STA／CDC／硬件接受仍未通过。

主线程逐项重读 30 份物理文件和 3253 份证据，含 1381 冻结工具、645 staged、951 prepare 来源及 911 项 PLL 依赖。完整配置、来源、命令、资源／时序与负控范围见[机器报告](dual138k_w15_default_physical_20261101.json)。位流 SHA256 `d9f34e33121ecb0006d36d95788de21a1b0a996cd2f366444d36b525895d3327`；物理 manifest SHA256 `13567451ce9aa75587f689d851c5c607a9e33ec85e0342a784df51801fab6228`。根复核记录 SHA256 `396c6f76fc25c44e8a9d91e97aac0aa133d9eab832e749158295c05df086f469`。

唯一录音对象仍为 16,384 帧／64 KiB，非长录音；完整 HDMI、真实 DAC、D 蓝牙流、25K 调参及手机下载尚未实板验收。手机只有模拟器，真机稍后；不把模拟器或单板分时当作无线／双板并发接受。没有 SRAM／Flash 写入，板上原镜像保持。
