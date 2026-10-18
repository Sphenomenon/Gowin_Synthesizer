# 片内 ADC 供电诊断 — 2026-10-13

**乱跳仍未修复。** 本轮继续核查可通过当前接线完成的供电诊断，实测片内ADC后，已恢复普通SRAM09与GUI。没有把测到的FPGA电源误当成触摸板供电。

## 结果与范围

GW5AST-138C支持ADCLRC片内ADC；以内部VCCIO4通道（vdd33_1）、分压系数8、默认FSCAL=653、OFFSET=0采样。手册公式：电压=adcvalue/2048×分压系数，因此这里为raw/256 V。没有用外部仪表独立校准，绝对电压是默认系数估算值。

**电源拓扑的重要限制：DOCK31005原理图第2页显示，PMOD的3V3来自DOCK的外围DC-DC；FPGA VCCIO4来自SOM的3.3V稳压，经BTB/滤波分配。两者是不同稳压支路。** 该ADC只说明FPGA侧状态，不能排除触摸芯片VDD欠压/噪声、线缆压降、焊点问题，也不能用过采样读数排除高频纹波。

| 诊断版 | 请求脉冲 | 实际ADC完成计数 | ADC超时 | 引脚核对成功事务 |
|---|---|---:|---:|---:|
| E005 | 160ns | 248 | 954 | 659 |
| E006 | 20µs | 5665 | 0 | 672 |

E005有大量超时，不作为稳定供电证据；短脉冲跨异步ADC时钟可能漏掉请求。延长请求脉冲后，本轮E006无超时。两次都仅写SRAM，Flash未写。

E006原始ADC范围864–871，估算 **3.375–3.40234375V**，范围约27.34mV。5665是FPGA自复位后的累计成功转换数；主机保存672个事务时点的ADC记录，并非保存了全部5665条ADC样本。内部最小/最大值由每次成功转换更新，协议仿真检查过该逻辑。典型转换完成时间约407xx个50MHz时钟（约0.815ms），与配置的1024采样点相符。请求间隔约10ms再加转换时间，不宣称严格100Hz。

全部672个完整成功I²C事务中，主接收器和独立物理引脚监听的字节一致，覆盖32个原始数据字。状态抽样19次，18次全16键。K0 signal抽样20次，范围0–1932，仍不合格。这些是选定事务的抽样，不是完整事件率；无独立手指真值记录。

图见 `片内ADC诊断_20261013.png` / 证据目录 `power_audit.png`。

## 串口记录完整性

原始UART重组时恢复了sequence304的一条合法TA1/CRC记录，原先因read_until在无换行的超时返回时提前解析而漏掉。原始字节一直保留；补回后的完整事务数由671改为672，没有改变任何值。该条原始接收时间无法还原，timestamp置null并标注recovered_from_raw_uart，绘图不使用这条，不编造时间。

`wire_trace.py`已加入跨读取片段的换行缓冲，测试同一合法记录分3段仍完整解码；没有把这是诊断读取器的问题说成GUI的触摸根因。旧会话14帧按最后sequence回退剔除，原始UART及恢复前JSONL均保留。

## RTL与验证

新增 `rtl/touch_power_adc.v`（Gowin工具生成的ADCLRC配置）和 `rtl/tb_power_monitor.sv`，在 `touchboard_wire_top.sv`以可选POWER_ADC开关接入。没有修改PMOD模拟接法，其他两条I²C总线保持释放。新增 `build.py --power-audit --route-option 0`，串口前缀TA1、249字节载荷；普通GUI仍使用TB2。

ADC请求状态机使用ready低→高门控、同步采样、超时计数及最小/最大值。模型仿真覆盖这些数字协议行为，不验证真实模拟精度。冻结E006输入hash与源文件对照通过，完整UART/CRC、两种原始读取方式、全部32原始数据字与负例测试通过。setup/hold违例0/0。

E006构建 `/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/build_20261013_035329_075024`，位流SHA256 `1b2baae30ddf96a973034e8a20054168b32b7c6ab2df984c8def3337cdfa4a71`。

官方资料：持久副本 `docs/Gowin_ADC_UG299_1.0.8.pdf` §2.2（转换公式）、§4（138K通道/分压）；工具支持列表 `IDE/ipcore/ADC/adc.ipspec`含GW5AST-138C；DOCK31005原理图第2页供电树。

## 恢复及尚缺证据

SRAM已独立读回`0x54420109`；Flash未写，GUI PID 227682存活并持续收数。最新1000帧截至2026-10-13T04:02:50.687525+08:00：U1配置通过1000，带按键822，全16键807；U2 READY 0，U3 0x40应答0。CRC计数0、丢帧0。这些仍不能证明可靠触摸。

进一步需要 **C1、C3两端的板上电压/纹波和采样节点连通性**。当前接线和可用接口没有提供这些节点的实际测量能力；片内ADC也不是这条触摸供电。新增 `触摸板测量点_20261013.png` 标出C1、VREF.8、SMP.9、R32/R33及C7/C8，U2供电对应C3。最少先取得C1/C3的上电直流电压，再决定测纹波或查采样通路。没有凭猜测指定某个坏件。

证据目录 `/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/power_audit_20261013_034735`。
恢复下载 `/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/sram_20261013_035818_928153`。
