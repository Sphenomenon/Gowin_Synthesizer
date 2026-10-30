# no-CNN FC：完成路由，整机 STA 失败（2026-10-30）

`C11030FC` 在 17:10:04—17:16:00（Asia/Shanghai）完成 P&R，返回0，耗时355.414秒，并生成位流。与[FA](WORKSTATION_NO_CNN_FA_RESOURCE_FAILURE_20261030.md)相比，原 VG／SDC／CST 不变，仅 placement2→1 和新 UserCode，556条未布通网络已消除。但路由后 **setup −116.645 ns、hold −0.718 ns、recovery −8.899 ns**，完整物理门禁失败，未部署。

| 物理资源 | FA place2 | FC place1 |
|---|---:|---:|
| Logic | 102,591 | 102,593 |
| Register | 51,122 | 51,122 |
| CLS / 69,120 | 61,804（90%） | 61,810（90%） |
| 物理 BSRAM / 340 | 272 | 272 |
| DSP / 298 | 126.5 | 126.5 |
| PRIMARY、LW | 各8/8 | 各8/8 |
| PLL | 7/12 | 7/12 |

综合 BSRAM 245 不能替代这里的物理272。完成路由不代表整机时序或功能接受；本轮没有削减其它功能、改频率、增加 false path 或关闭 hold 修正。

| 路由后全局检查 | 最差余量 ns | 实际最差路径 |
|---|---:|---|
| setup | −116.645 | runtime oscillator DSP `n39121_0_s/DOUT[28]` → slot RAM `DI[13]`，audio76.8，数据延迟129.728ns |
| hold | −0.718 | DDR `ddr_init_internal_r_s0/Q` → `wloadn_3_s0/D`，原0.800ns要求保留 |
| recovery | −8.899 | `u_reset/started_s0/Q` → USB input owner `feedback_divider_0_s0/CLEAR` |
| removal | +0.262 | 48k参考监视器 source reset → source Gray CLEAR |
| minimum pulse width | +0.641 | 报告最差为 video pixel148 低脉宽 |

维护 `audit_workstation_timing.audit()` 解析本轮真实 HTML，显式核对14个有数据路径的实际时钟名称和原频率；video reference49／serial742另在完整16时钟表中列明无数据路径，不据此接受PLL。父级另外解析TXT的四类全局2000行路径表，最差值与HTML结果完全一致。工具汇总分析342,577条路径／176,476个端点，setup违反端点21,620、hold违反端点189；这些工具汇总与各时钟TNS、截断详细表分别保留，不混称同一计数口径。

clock50、ULPI60、audio76.8、LCD31.5、USB48、DDR UI100均有setup失败。audio76.8的实际Fmax仅7.712MHz，逻辑深度122；矢量 `pitch_product` 到 phase CE 的路径也约−106ns。需要依据真实网表和路径细节拆分计算／控制锥，再重做数字等价、周期预算及整机综合/P&R；不能用多周期例外、降频或只跑行为仿真掩盖。两个selected音频时钟都出现在原约束和报告中，仍不等于两种模式、切换或复位的完整物理接受。

父级重hash全部23登记输入、13项runner输出、实现目录全部20个文件、工具及日志，保持原身份；物理目录 `/Users/sphenicidition/.cache/gw138k-task-20261030/no-cnn-physical-C11030FC` 封存。FS SHA256为 `3186acb21329fba7019fd0440cee9912f5df3a7174310cc45d203e00c96d2cf3`，文件头UserCode为 `0xc11030fc`，仅离线身份，不是板端读回。原runner的初始 `bitstream_sha256` 汇总字段仍为null，已完成的 `bitstreams` 映射及父级FS哈希明确记录实际产物；不追改原process。完整证据见[机器记录](workstation_task_20261030/conditional_no_cnn_fc_routed_sta_failure.json)。

本结果只绑定 `custom138k-workstation-no-cnn-v1-525ffff10d622031`，不改名为随后新prepare或R00候选。全部CDC／复位、观察RAM数据时序、runtime PLL／DCS、双模式STA、功能／电气与硬件仍未接受。SRAM授权仍在本会话范围内，但本候选尚不满足部署门禁；未做JTAG、SRAM或Flash操作。既有部署与回退不变。
