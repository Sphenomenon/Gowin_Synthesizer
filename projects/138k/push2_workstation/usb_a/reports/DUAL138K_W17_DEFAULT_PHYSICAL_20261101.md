# W17 default 完整物理结果

2026-11-01。`custom138k-workstation-w-demo-v1-518b142532fd5352`完成全量P&R并生成`0xD2110122`位流，**完整STA失败，未上板**。来源与综合见[M19／W17检查点](DUAL138K_M19_W17_SYNTHESIS_20261101.md)。

| 实测项目 | 结果 |
|---|---|
| 物理Logic／FF／CLS | 73464／45220／53457 |
| 物理BSRAM／DSP | 293／340；66.5／298 |
| LUT／ALU／SSRAM | 57282／14406／296 |
| setup负端点／最差 | 6774／-4.737 ns |
| hold负端点／最差 | 6／-3.683 ns |
| recovery／removal最差 | +2.169／+0.275 ns |
| 四张clk50表最差 | -3.495／+0.189／-3.495／-3.683 ns |

最差setup为delay overflow_sticky→PCM owner written bitmap CE，当前输出context修复没有消除bitmap长链。DDR另有ui_reset_pipe2→memory_failure CE −4.656ns，clk50为tx_header0→host_rx lease_handles CE −3.495ns。原DDR3.500ns要求保持，hold −3.683ns；其余5个hold负端点是44.1k参考计数器binary→Gray／binary，最差−0.406ns。新owner预译码实际把2个RAM16SDP4换为128个DFFRE，新增存储／mux成本如实保留，不以局部结构推断收益。

actual VO原生58项47通过、11个具名不适用，63项负控全拒；边界7项与69项负控通过，官方六PLL、7项负控及held-v3通过。六组进程退出0不覆盖完整STA失败；物理CDC和整机接受仍为false。PC仍只接受power-up-only范围，无warm reset接受。

主线程独立复验30个物理文件和3275份来源／工具／审计证据。机器记录见[DUAL138K_W17_DEFAULT_PHYSICAL_20261101.json](DUAL138K_W17_DEFAULT_PHYSICAL_20261101.json)；原始cache为`/Users/sphenicidition/.cache/gw138k-dual-20261031/w17-default-physical-audits-v1/results/W`。位流SHA256：`4642a1f2cf4be4fd8a86254c6edd7300cd2e2672a5c85b1a4bc9efa04c9eb55c`；root复核SHA256：`20736d8eaf9b53725f9254db12b423e9c0f940211afc2a3dc3a47a1693d0c285`。不修改默认／历史失败输入、原SDC、时钟或证据。

W新v3的actual VO确认296个payload源、301个资格端点、9928对10.000ns及hold-only覆盖，19负控全拒；完整映射native-response可达性归纳证明和whole-source／physical CDC仍未接受。同VG／SDC、原3.500ns要求的独立far `D2110123`继续实测，结果另记。

M基础无CNN，W唯一录音对象仍为16384帧／64KiB；真实HDMI／DAC／USB／25K、手机A2DP／D处理／BLE下载和双板并发未验收。未执行SRAM或Flash，原板及Flash回退保留，T2-D1／D2未完成。
