# M9／W8 及独立 DDR 布局变体的实际物理结果

2026-10-31。四次完整P&R均布通并生成位流，但完整STA均失败，未部署。每个变体有独立UserCode／位流hash；默认两套保持原CST／SDC，far变体只追加两个已声明的placement region，不修改父VG／SDC及3.500 ns DDR hold要求。

| 候选 | UserCode | CLS | 物理BSRAM | DSP | setup违例／最差ns | hold违例／最差ns | recovery／removal最差ns |
|---|---|---:|---:|---:|---|---|---|
| M9 默认 | D2103107 | 49,962 | 235 | 120 | 6,772／−3.643 | 1／−3.506 | +0.251／+0.275 |
| W8 默认 | D2103108 | 57,653 | 293 | 68 | 8,325／−9.674 | 2／−3.686 | −3.183／+0.281 |
| M9 far | D2103109 | 49,996 | 235 | 120 | 5,316／−3.671 | 0／+0.140 | +1.291／+0.278 |
| W8 far | D2103110 | 57,775 | 293 | 68 | 9,430／−10.657 | 5／−0.179 | −4.302／+0.278 |

M9默认的物理Logic65,854、FF46,930，W8为84,242、45,048；W8物理BSRAM293／340，与综合257分列。far实测DDR目标分别为+0.755／+0.633 ns，launch均在R104C175、capture均在R2C2，逐项落区及新VO双FF／CLKDIV4／direct50／Q→D／reset／CE拓扑检查通过。W8far剩余hold来自4条reference48计数／Gray路径及1条midi acknowledge首级；performance三拍释放的recovery仍失败，旧far未安装后续窄约束。局部DDR成功不转授整机通过。

M9默认与W8默认六PLL／serializer／AE350时钟及RTC来源门均通过；M9另有7个真实破坏负控全部拒绝。W8首次PLL调用因未指定模型路径失败，原记录保留，明确实际GW5A模型后的新workspace正门通过。原生局部CDC v3在实际routed VO和被P&R消费的SDC上通过；M9实际VO的41项及36个网表负控通过，W8 VG为30通过／11跳过和25负控，VO为31通过／10跳过和26负控。它们仅证明已声明局部边界，不是完整CDC或时序接受。

M9最差路径来自TF同域占用增量及PANIC高扇出／最终增益；W8最差来自PCM描述符掩码与许可控制。后续已分别完成[TF](DUAL138K_TF_SMALL_DELTA_20261031.md)、[音频取消交付](DUAL138K_AUDIO_CANCEL_DELIVERY_20261031.md)、[W描述符](DUAL138K_PCM_DESCRIPTOR_GATE_20261031.md)及[窄复位／专项报告](DUAL138K_DEMO_TIMING_INTEGRATION_20261031.md)的维护源修改与离线验证；资源／slack收益仍待新整机重测。[机器证据](dual138k_m9_w8_physical_20261031.json)保存四份完整测量索引、所有来源与位流hash、目标DDR数值、真实时序分类、局部门禁与父候选保护封口。未操作SRAM／Flash，原Flash回退保持，T2-D1／D2仍未通过。
