# M19 default 完整物理结果

2026-11-01。`custom138k-workstation-m-demo-v1-3b42d2cc55cc70d5`完成全量P&R并生成`D2110120`位流，**完整STA失败，未上板**。来源、配置及综合见[M19／W17综合检查点](DUAL138K_M19_W17_SYNTHESIS_20261101.md)；本次不转授历史声画接受。

| 实测项目 | 结果 |
|---|---|
| P&R退出码／耗时 | 0／312.620秒 |
| 物理Logic／FF／CLS | 67771／46932／50976 |
| 物理BSRAM／DSP | 235／340；119／298 |
| LUT／ALU／SSRAM | 53795／13130／141 |
| setup负端点／最差 | 5710／−3.450 ns |
| hold负端点／最差 | 1／−3.617 ns |
| recovery／removal最差 | +3.233／+0.275 ns |
| 四张clk50表最差 | +0.782／+0.144／+0.778／−3.617 ns |

最差setup从delay `transaction_fault`到`config_state` CE，随后是同一故障至矢量DSP输入。DDR UI仍有824个setup负端点，audio域有4885个，不能以clk50本域已正裕量推断整机闭合。唯一hold是原DDR reset路径，3.500ns要求保持，arrival1.924ns、required5.541ns；实际R68C9→R68C2。未放宽时钟或hold要求。

actual VO原生58项55通过、3个具名映射不适用，71项负控全拒；边界7项与69项负控通过；官方六PLL、7项负控及held-v2检查通过。六组进程退出0只证明相应子门和测量成功，完整STA、物理CDC及整机接受仍为false。PC复位范围仍是power-up-only，不继承warm reset验收。

实际TF核对确认新`31dcb…07b7`被消费。available_bytes7→accepted_used30的组合图最长18→12 primitive，ALU6→0，仅是图结构过近似；该bit直接扇出12→13，仍可到32个accepted端点。新VG的四种pending／partial各有6个具名低位ALU，两个full名字未保留，不能据此声称六个完整加法器映射等价。实际routed报告仍有13条available→accepted路径，最差bit8→accepted_used29为−2.175ns，经过ring比较／地址选择／accepted_without_write，不能将图深度变化记为routed收益。

主线程独立复验30个物理文件和2968份来源／工具／审计证据。[机器记录](DUAL138K_M19_DEFAULT_PHYSICAL_20261101.json)绑定完整VG／VO／FS／SDC／manifest及审计hash。位流SHA256：`9da9fd915664cba9f4f594e79f341c0914402b9a75752a84915912f31320d0ce`；root复核SHA256：`8881f6994933a7f0d16a662811b94ba1895e513fe782453ba3eb9e8d1d26cd04`。原始结果位于cache的`m19-default-physical-audits-v1/results/M/`。

已从这份actual DDR测量和VO派生相同VG／SDC、原3.500ns要求的独立far布局`D2110121`，结果另记。默认失败输入及证据保留。M基础无CNN，真实HDMI／DAC／Push／25K／TF尚未验收；未执行SRAM或Flash，保留原板及Flash回退，T2-D1／D2未完成。
