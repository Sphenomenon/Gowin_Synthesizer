# I²C 引脚监听与 GPIO 对照诊断 — 2026-10-13

**结果：触摸乱跳尚未修复。** 异常原始值和全键状态已经出现在 FPGA 的 SCL/SDA 输入端，现有接收器与独立监听器在成功事务中一致。未确定唯一故障器件，不把通信通过当成触摸通过。

## 当前板上状态

已恢复普通监测镜像 SRAM `0x54420109`，独立JTAG读回通过，Flash未写。GUI PID `223960`，确认进程存活且日志持续更新。最新日志：`/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/gui_20261013_031812_wire_handoff/capture.jsonl`。

最新1000帧截至 `2026-10-13T03:22:58.035979+08:00`：U1通信/配置通过 1000帧，带按键位 795帧，全16键 783帧；U2 READY 0帧，U3地址0x40应答 0帧。硬件触摸仍未验收。

本轮开始前1000帧中U3曾在0x40应答1000帧（同时有默认0x70应答）；恢复后上述窗口没有0x40应答。因此不能继续写“U3始终不应答”，也不能说U3已经修好。不同时间窗的变化不足以证明某个配置是原因。

## 方法和实际证据

新增 `rtl/tb_i2c_listener.sv`，只读取物理SCL/SDA，不连接主机状态机、接收数据或采样脉冲。独立同步输入、识别START/STOP、在SCL上升后及下降前分别重建字节，并保存每个ACK/NACK。`touchboard_wire_top.sv`比较主机期望寄存器指针与线上实际指针，按状态/配置/32个原始数据字轮流抓取，避免UART忙碌造成只采到固定寄存器。

| 实测配置 | 采集时长 | 完整事务 | 成功且逐字节一致 | 地址NACK | 全键状态抽样 |
|---|---:|---:|---:|---:|---:|
| E003：原初始化 | 45秒 | 524 | 524 | 0 | 1/15 |
| E004：闲置GPIO设输出 | 60秒 | 644 | 643 | 1 | 7/19 |

两组均实际覆盖所有32个原始数据字（16 signal + 16 reference）；成功事务中，现有驱动、监听器上升沿采样、监听器高电平后段采样全部一致，寄存器指针与ACK/NACK序列正确。**真实硬件最大抓取59字节（地址+58字节配置）；65字节完整事务另由独立仿真覆盖，不能混为实测。**

K0 signal：E003为0–2044，16次抽样中5次为0；E004为0–2050，19次成功抽样中3次为0。两组都不是稳定有效的触摸信号。图见 `引脚监听诊断_20261013.png` / 本证据目录 `wire_compare.png`。

最短STOP→START间隔5998个50MHz时钟，约119.96µs；超过QT2160勘误要求的50µs。没有因两组成功事务的接收采样点不同产生字节差异。

E004有一次真正的读地址NACK：寄存器指针102，线上仅一个地址字节0x1B，ACK位为1；主机正确报告error=1。此前接收缓存内的两个旧字节不属于这次失败事务，分析器已明确不拿它们与线上数据比较。原始分类另存 `capture_original_classification.jsonl`，原始UART保留在 `raw.txt`。

GPIO对照按手册§6.23/§8.9把GPIO1/2/3设成输出（寄存器73=0x1C），并在校准前读回验证。原理图中这三脚未接线，驱动值采用软复位后的默认低电平。该对照仍出现零值、大跳变和全键状态，因此没有把此选项默认为“修复”。普通监测镜像已恢复原冻结09版。

## 证据边界

- 证明异常值到达FPGA引脚，显著降低GUI解析、UART字节拼接和主接收器误采样导致这些异常的可能性；没有测量引脚模拟电压，不能排除电气层通信干扰。
- 全键状态是低频选定事务抽样，分母15/19不是完整事件数或按键时间比例，不能据此声称GPIO配置使问题变好/变坏。
- 无触摸条件沿用用户此前说明，没有独立手指真值记录。
- signal/reference分时读取，并非同时锁存快照；图中连线仅帮助观察。
- 初次捕获含旧TB2串口缓冲；E004还剔除了最后一次sequence回退前的15条旧TW1记录。所有原始字节仍保留。读入片段的不完整边界与真实CRC错误不能混为一谈。

## 仍需的电气证据

1. U1供电：在C1两端检查实际VDD及纹波；U2对应C3。供电数值和噪声必须在板上得到，现有FPGA连接没有ADC能力。
2. U1共同采样路径：VREF.8与地的实际连接、SMP.9到R32/R33公共端、R32/R33实际1MΩ值及C7/C8实际4.7nF装配。多个通道同时异常时优先关注共同节点；没有证据可直接指定某个元件损坏。
3. U2通信：U4.4→RN1.8/1→U2.23；U4.6→RN1.7/2→U2.24。另核对U2实际电源/复位及U3 SDA3/R20通路。原理图连接正确不等于实物通路正确。

没有通过提高阈值、滤波、禁用部分键或压制全键来伪造通过。

## 源码、验证与复现

- 监听RTL：`rtl/tb_i2c_listener.sv`、`rtl/touchboard_wire_top.sv`。
- 事务只读调试端口及可选GPIO初始化：`rtl/qt2160_probe.sv`。
- 构建参数：`build.py --wire-trace`，GPIO对照另加 `--safe-gpio`。TW1用 `wire_trace.py`读取，不能用普通TB2 GUI读取。
- 独立测试：`test_wire_trace.py`；覆盖手动位流、65字节、ACK/NACK、STOP/START、溢出、完整225字节UART/CRC、32原始字、两种读取方式及CRC正确但主机数据被篡改的负例。真实地址NACK另有分析器负例。
- UART由大动态读MUX改成移位发送后，逻辑量由约5422降到3476；route_option=0的E003/E004通过setup/hold 0/0。较慢旧构建已停止并标记superseded，均未烧录。
- 常规 `test.py`回归通过；首轮60秒墙钟超时，增加到180秒后原断言全部通过，没有放宽功能断言。
- 官方依据：AT42QT2160 9502C手册§6.23、§8.9、§10；持久副本 `docs/AT42QT2160_9502C.pdf`。

实测证据目录：`/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/wire_audit_20261013_025343`。

E003构建：`/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/build_20261013_030810_176440`。
E004构建：`/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/build_20261013_031024_802996`。
恢复09下载：`/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/sram_20261013_031755_054279`。
