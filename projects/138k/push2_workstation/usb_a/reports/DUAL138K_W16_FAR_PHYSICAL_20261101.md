# W16 far 完整物理结果

W16 `D2110119` 完成全量 P&R，退出0，用时 430.582 秒。DDR定向布局保持同VG、完整SDC和3.500ns要求，仅追加两条opposite-corner CST。完整STA仍失败，未部署SRAM。

| 实测项 | 结果 |
|---|---|
| Logic／FF／CLS | 73317／45092／53333 |
| 物理BSRAM／DSP | 293／66.5 |
| LUT／ALU／SSRAM | 57147／14382／298 |
| setup负端点／最差 | 6810／-5.168 ns |
| hold负端点／最差 | 0／+0.103 ns |
| recovery／removal | +1.966／+0.278 ns |
| DDR指定hold | +0.622 ns |
| 四张clk50表最差 | -4.536／0.138／-4.536／0.138 ns |

最差DDR路径为arbiter `read_pointer1/Q → recording_ble_store/memory_failure1/CE`（−5.168ns）；同源到`write_address19/D`为−5.145ns。D效果`overflow_sticky/Q → effects DSP B[12]`为−5.166ns，同源到PCM `written[2] CE`为−5.155ns。它们均是真实同域路径，需修改实际消费的RTL。clk50最差仍为HCI相关链（−4.536ns）；每张专项表最多100条，不能据此宣称全局违例数。

DDR hold实际从 `R104C175[0][A]` 到 `R2C2[0][A]`，arrival 6.036／required 5.414ns，要求仍3.500ns、clock skew 0.47ns。default的−3.683ns变为far +.622ns；其余布局也改变了setup，不能把这一局部成功当作整机接受。

六组审计全部退出0：native VO58项44通过／14跳过、60负控全拒；boundary7项／69负控；官方六PLL、7负控及实际held-v2通过。boundary实测fault FF／RAM消费者663／8，queue139／2。PC仅power-up-only。冻结W16原SDC的9632返回邮箱资格路径缺口未在本候选修复，完整CDC仍未接受；维护W-v3需新来源、新候选和新物理时序验证。

主线程复验32份物理文件、1395冻结工具、645 staged、951原始prepare来源及PLL的913输入／915证据；合并去重 3273 文件，全部SHA256匹配。summary `7b6fdecd00dd3dde52f60ddbb5627dff3f0446cace65d99df8234e0ca535adf1`，seal `e118e71df91d9880c5d89bd0a803f2ab88e74d420a17171e94a0ad4912c2589a`，root review `5f175ff8d8993a4cec3942ab6dd0f743268b83adbb4bd30656ebab342a4085bd`。位流 `5e153aa4eb7100f26711b5e43a6f1021568c89dfd770fbb5226001bb5e0ea18a`；来源、命令、完整时序和逐文件身份见[机器报告](DUAL138K_W16_FAR_PHYSICAL_20261101.json)。

本阶段未启动新EDA或操作硬件，未写SRAM／Flash。真实HDMI／DAC、25K、手机A2DP／BLE／D处理及持续声画中的录音下载尚未验收；唯一对象仍16,384帧／64KiB约.341秒。回滚不涉及板上变化，保留现有镜像与全部冻结候选。
