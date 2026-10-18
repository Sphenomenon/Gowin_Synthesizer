# USB3300 驱动检查与实板总线自检

检查时间：2026-10-16，Asia/Shanghai。18:21–18:26 修后复测结论：用户报告硬件已修复；重新加载后 PHY LineState 为正常 FS 空闲 `01`，不反相三线 CDC 镜像成功枚举为 12Mbps，1,848 字节二进制回环全部一致，FPGA 收到/回送计数均为 1,848、溢出为 0。证据见 [修后综合报告](../prj/usb2_device/reports/usb2_postrepair_20261016.json)。源码默认 `SERIAL_D1_INVERT` 已恢复为实板通过的 `0`，四组合串行集成仿真通过；当前板上为已有验证镜像 `093824_666534`，只写 SRAM。

下文保留返修前诊断历史：断电 R7–R8 读数 0.42Ω、两线约 2.6V、LineState11 指向 D+/D− 低阻短接。用户未报告具体短点、返修方法或修后电阻值，因此不补写物理定位结论。修后证据验证本次 FS CDC 通路，未测试 480Mbps 或长期稳定性。

依据为 Microchip USB3300 官方手册 DS00001783C（本地缓存 `/private/tmp/usb3300_official.pdf`、`.txt`）、本工程 RTL、独立行为模型和实板记录。未访问手册禁止使用的测试/扩展寄存器；只操作 SRAM，未写 Flash。

## 逐项检查

| 项目 | 实现与手册对照 | 结论及边界 |
| --- | --- | --- |
| 寄存器地址与命令 | 地址 04=Function、07=Interface、0A=OTG、15=Debug、16=Scratch；写命令高两位 10、读命令高两位 11。对应 §6.1.4、Table 6-4。 | 未发现地址/命令编码错误。 |
| 写入握手 | `usb2_serial_init.v` 与 `usb2_termination_probe.v` 均保持命令到 NXT 接受，再保持数据到下一次 NXT 接受；随后发送一拍 STP 并驱动 Idle00。对应 §6.1.5.1、Figure 6-4。 | 未发现写数据提前结束或 STP 与数据同拍的错误。 |
| 读取与换向 | 命令接受后，首次 DIR 高只作为换向，下一拍读取数据；DIR 下降后再留一拍。对应 §6.1.2、§6.1.5.2、Figure 6-5。 | 未发现固定错一拍的读取错误；ID、Scratch 与配置回读进一步提供实板证据。 |
| FS/LS 终端配置 | FC45/OTG00 为 Peripheral FS，FC46/OTG00 为 Peripheral LS，FC41/OTG06 为无设备上拉、双下拉。对应 §6.1.4.5、.7、Table 6-8。 | 不能以需要不同 OpMode 为由任意修改已符合表格的 FC45。 |
| 线态解码 | Debug15[1:0] 为 Linestate，Status13[2]/[3] 为 SessValid/SessEnd，RxCmd[1:0] 也是 Linestate。对应 §6.1.4.10、.12、§6.1.6。 | Debug 与非请求 RxCmd 都曾上报 11；降低了单个寄存器读取/解释错误造成 SE1 的可能。 |
| 三线模式进入 | 先写并回读 IF08，再写 IF0A；最终写入结束后撤销 ULPI DATA 驱动，连续 DIR 高 16 拍后交接。对应 §6.1.10。 | IF0A 是成功写入影子，没有模式后读回。16 拍不是手册给出的进入最大延迟保证。 |
| 三线收发方向 | DATA0=高有效 TX_ENABLE；DATA1=差分数据，DATA2=SE0，均只在发送时由 FPGA 驱动；串行运行 STP=0，未用 DIR 仲裁串行发送。对应 Table 6-7。 | 修后 `SERIAL_D1_INVERT=0` 已由真实主机枚举和 1,848 字节回环确认。返修前的两种极性失败记录仍保留。 |
| 时钟和协议核 | PHY 的 CLKOUT 作为 FPGA 60MHz 输入；核使用该时钟，保留两秒接入延迟及原 SE0 复位检测。 | 仿真可验证数字协议，不证明模拟质量、实际模式切换或主机枚举。 |

对应源文件：

- [USB3300 初始化驱动](../prj/usb2_device/rtl/usb2_serial_init.v)
- [三线收发与 pad 交接](../prj/usb2_device/rtl/usb2_serial_top.v)
- [ULPI 终端和总线自检](../prj/usb2_device/rtl/usb2_termination_probe.v)
- [先前的三线模式规范记录](USB2_SERIAL_REVIEW.md)

## 新增总线自检及实板结果

`FULL_SCRATCH_TEST=1` 在 ID 检查后，对文档允许访问的 Scratch16 依次写入 `00..FF`，每次立即读取并比较。通过计数达到 256 后，再运行原 55/AA、IF08、PHY 软件复位及四阶段终端诊断。第一个不符值会锁存期望/实际字节并在 stage11、error_code5 停止；超时有界退出。默认参数为 0，保留旧诊断流程。

- [构建清单](../prj/usb2_device/reports/build_20261016_103555_918776.json)，FS SHA256=`85cd88587f65f9e8e3f648febcc33dee377647af2704c3efd21453d7d2372461`，GAO=`D2AC`。
- [SRAM 下载及回读验证](../prj/usb2_device/reports/sram_usb2_buscheck_20261016_103627_285505.json)：通过，UserCode=`4032`，Status=`70022020`。
- 50MHz、60MHz、TCK 的 setup/hold 违规均为 0，最差 setup slack=`0.348ns`。
- [实板采样解码](../prj/usb2_device/reports/usb2_buscheck_status_20261016_103646_478172_core0_window0_decoded.json)：四页 `01000000 / 41080600 / 600C1891 / 10900800`，Scratch 验证计数 **256**，stage60，done=1、id_ok=1、error=0。
- Debug15 在稳定等待后的四阶段样本：双下拉 `[00]`、FS `[00,11]`、LS `[11]`、双下拉 `[00]`。本次两个上拉阶段均未见单线高 `01/10`。
- 采集时全局 RxCmd=8、RxData=0。RxCmd 阶段 mask=`1090`：无事件 / `[00,11]` / 无事件 / `[00]`。零 mask 表示没有记录到事件，不能解作 SE0。

全字节写读通过证明该次测试中的数字寄存器往返一致，不能单独排除所有对称映射、共同模型假设或时序裕量问题。VID/PID、命令地址以及其他配置回读是额外证据。不能把此结果写成“驱动完全无问题”或“三线数据通路已经验证”。

RxCmd 历史包含阶段配置、临时 detach、settle 和采样间隔；没有事件时间戳，不能将配置过渡直接当作稳定采样窗口的线态。Debug15 mask 则来自每阶段 100ms 等待后的 16 次读取，间隔 10ms。DONE 后阶段历史冻结，全局 RxCmd/RxData 计数仍可能增长。

## 验证与保留状态

[新仿真报告](../prj/usb2_device/reports/buscheck_sim_20261016_103606.json) 覆盖 `FULL_SCRATCH_TEST=0/1` × `PHY_SOFT_RESET=0/1` 的 15/19/17/21 个场景，共 72 个场景及官方 primitive pad 真值表，全部通过。故障注入包含位交换、位卡高、读写超时、复位位不清零、错误回读、抢占和换向。新增 Scratch 读返回未被记为 RxCmd/RxData。

复现入口：

```sh
sh prj/usb2_device/run_termination_sim.sh
sh prj/tools/gowin.sh prj/usb2_device/build_buscheck_gao.tcl
python3 prj/usb2_device/program_sram.py --image buscheck --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image buscheck --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image buscheck <capture.csv>
```

上述 buscheck 与下述 lowpower_pd、measure 均为历史诊断镜像，不运行 CDC。修后最新加载与通过的 FS CDC 镜像见本文开头及修后综合报告。

## 低功耗直接 LineState 实测

依据 §6.1.9、Table 6-6：清除 SuspendM 后，PHY 拉高 DIR 并停止 CLKOUT；低功耗 DATA0/1 是 FS 模拟接收器的异步 LineState 输出。独立 50MHz 域以 Gray 计数器确认 CLKOUT 连续 1ms 无变化，要求 DIR 高，再等待 10ms 后采样 16 次、间隔 1ms。采样完全绕过 Debug15 和 RxCmd，也不进入三线模式。结束后保持 STP 唤醒至时钟恢复、DIR 低以及 master 重获总线，再回读 FC/IF。

实现见 [低功耗诊断 RTL](../prj/usb2_device/rtl/usb2_lowpower_diag.v)、[独立 50MHz 快照顶层](../prj/usb2_device/rtl/usb2_lowpower_top.v)、[专用时序约束](../prj/usb2_device/constraints/usb2_lowpower.sdc)。四阶段为双下拉、FS 上拉、LS 上拉、双下拉；常规镜像上拉阶段 OTG00。

| 实测 | 构建 / SRAM验证 / GAO采样 | 原始 DATA[1:0] | 时序 |
| --- | --- | --- | --- |
| lowpower，FS/LS 均 OTG00，GAO D2AD，User1585 | [build](../prj/usb2_device/reports/build_20261016_104925_911273.json) / [SRAM](../prj/usb2_device/reports/sram_usb2_lowpower_20261016_104951_948417.json) / [decoded](../prj/usb2_device/reports/usb2_lowpower_status_20261016_105008_081620_core0_window0_decoded.json) | `00 / 11 / 11 / 00` | setup/hold 0违规，最差setup 0.320ns |
| lowpower_pd，仅 FS 改 OTG04，GAO D2AE，User42D5 | [build](../prj/usb2_device/reports/build_20261016_105341_951862.json) / [SRAM](../prj/usb2_device/reports/sram_usb2_lowpower_pd_20261016_105409_157050.json) / [decoded](../prj/usb2_device/reports/usb2_lowpower_pd_status_20261016_105426_066407_core0_window0_decoded.json) | `00 / 11 / 11 / 00` | setup/hold 0违规，最差setup 0.128ns |

两轮都得到四页 `04240004 / 41000600 / 1881FFFF / 10101010`，done=1、id_ok=1、error=0、stage60；四阶段均完成停钟确认、16 次有效采样、唤醒和醒后 FC/IF 校验，flags=FFFF。两次 FS SHA256 分别为 `51fa21675314cdc0c05eb4c5078099293acc077e04b39c4e084ba6c0b77b62a0`、`b43b7a719e1bfbd28f1402388efb2bcc1a18474d17c01cf551813260897f2b74`。FC/IF/OTG 是最后读取的影子值，不是睡眠瞬间寄存器读取。

第二轮使用 Table 6-8 明确列出的 OTG Peripheral FS/Suspend 组合：FC45（入睡 FC05）、OTG04、IF00，保留 DP 上拉并启用 DM 15kΩ 下拉；LS 仍 OTG00。不能用 OTG06 代替此对照，因为该表的双下拉组合会关闭内部上拉。增加 DM 下拉后 FS 仍为 11，只说明此次操作没有让 DM 接收器报告低；不能据此确定 DP/DM 短路、PHY 损坏或主机下拉是否存在。

低功耗与同步 ULPI 路径都读到原始 11（按 UTMI 编码为 SE1），进一步降低单独 Debug/RxCmd 解释错误的可能。仍未通过独立电气测量确认实际 DP/DM 电压，也未验证成功的 USB 协议通信，不能将诊断通过写成“驱动完全无问题”。双下拉时回到 00、上拉时转为 11 是后续隔离的主要依据。

[低功耗仿真报告](../prj/usb2_device/reports/lowpower_sim_20261016_105200.json) 包含 FS_OTG_CTRL=00/04 各 17 场景，共 34 场景全部通过；模型真实停止 CLK60，并覆盖唤醒失败、停钟失败、异常采样、配置错误、握手超时和抢占。官方 LUT2/IOBUF 的八路物理 pad 真值表、即时 DIR 释放，以及 CLK60 恒停期间的 50MHz 完整快照均通过。模型只验证数字握手和寄存器序列，不模拟上拉/下拉电阻的电气行为。

复现低功耗 DM 下拉对照：

```sh
sh prj/usb2_device/run_lowpower_sim.sh
sh prj/tools/gowin.sh prj/usb2_device/build_lowpower_pd_gao.tcl
python3 prj/usb2_device/program_sram.py --image lowpower_pd --manifest <成功构建清单>
python3 prj/usb2_device/debug/capture_status.py --image lowpower_pd --manifest <同一清单> --location 4273
python3 prj/usb2_device/debug/decode_status.py --image lowpower_pd <capture.csv>
```

## 实际电压及原生 PCB 进一步隔离

[原生 PCB 审查](USB3300_PCB_AUDIT_20261016.md) 找到确定的设计偏差：U2.15/26 的数字 VDD18 网络只有 C13/C14 各 100nF，缺少 DS00001783C Table 3-1 pin26、§6.4.1 要求的 4.7µF 低 ESR 电容。模拟 VDDA1.8 的 C11=4.7µF 属于另一路，不能代替数字稳压输出的稳定电容。此偏差需要修正，但尚未以实物补偿及复测证明它就是当前不枚举的原因。

PCB 辅助几何检查未发现设计中的 DP/DM 铜短接，四段网络各自连通；最小 DP/DM 设计铜间距约 0.152mm，U2.7/8 与官方 DP/DM 定义一致。该检查不是正式 DRC，也不能排除实际焊桥、实装连接器与库不匹配、制造版次差异或 PHY 内部故障。R10 设计值 12kΩ，实装值与精度未测。

用户确认目前从 USB2 供电、有万用表；对 C15/C13/C11 的三路直流电压检查回复“没问题都”。这是用户的定性正常反馈，没有具体数值，不能据此证明数字稳压输出没有瞬态波动。

为将 PHY 报告与实际引脚电压对应，新增 [固定 FS 测量顶层](../prj/usb2_device/rtl/usb2_measure_top.v)：验证 ID、Scratch55/AA、IF00、OTG04、FC45 回读后持续轮询 Debug15，不进入低功耗，不自动 detach。D+ 上拉及 D− 下拉持续保持。DONE 表示配置和至少一次 Debug 读取成功，不代表枚举或正常线态。

- [构建](../prj/usb2_device/reports/build_20261016_110634_656420.json)，FS SHA256=`e68f7a5ae74924116a32e0a4513b73701327e2e03026ec6c119eeef63679f148`，GAO D2AF、UserB07F。
- [SRAM 回读验证](../prj/usb2_device/reports/sram_usb2_measure_20261016_110704_205357.json) 通过；setup/hold 违规 0，最差 setup slack 0.115ns。
- [采样解码](../prj/usb2_device/reports/usb2_measure_status_20261016_110729_115936_core0_window0_decoded.json)：四页 `04240004 / 45000400 / 03905388 / 00000000`，ready/id_ok=1、error=0、stage20h；最新 Debug03，Debug 读取计数 21384。mask9 从第一笔读取起累计，包含配置后的过渡，不能当成稳定窗口的两种线态。
- [独立仿真](../prj/usb2_device/reports/measure_sim_20261016_110548.json)：10 场景及 10401 个四页状态周期检查通过，包括运行后停钟/事务超时撤销驱动。模型未模拟 USB 电气负载。

[用户万用表测量记录](../prj/usb2_device/reports/usb2_multimeter_20261016.json)：在固定 FC45/IF00/OTG04 的测量请求下，R7（D+）和 R8（D−）被反馈为“都在2.6V附近跳动”。两根线的近似直流读数均高，与 PHY 的 11 相符，使单纯 Debug 解码错误不足以解释现象。万用表没有提供波形、最小/最大值，不能将这个近似反馈解读为两根线每一瞬间都精确相等或直接确认短路。

用户针对“拔掉板上全部 USB 和下载器、确认断电后，测量 R7 与 R8 间电阻”的请求回复 **0.42Ω**。这是接近短路的低阻值，正常独立 DP/DM 信号不应出现这种连接；与两线电压均约 2.6V、PHY 报告 11 的三项证据形成对应。它足以将 D+/D− 低阻短接定位为必须先排除的直接电气故障，尚不能确定短路发生于 USB-C 焊盘、R7/R8 周边、U2.7/8 焊桥，还是 PHY 内部。

下一项物理隔离：先目视/放大检查上述相邻数据焊点；若看不到桥接，可在保持完全断电时抬起 R7 的一端，再分别测两个 R7 PCB 焊盘到 R8（公共 DM）的电阻。R7.1 是 USB-C 一侧、R7.2 是 U2.7 一侧，低阻仍保留在哪侧即可据此二分；若两侧仍都低阻或两侧都恢复高阻，需按实测重新分析，不能先断言只有一处故障。尚未执行此拆分，未声称修复或重新枚举成功。

断电操作可能丢失 SRAM 镜像，后续通电后需要重新核实/加载；最新成功下载身份不代表断电后仍保留。数字 VDD18 缺 4.7µF 是另一个明确设计偏差，不能用它替代对已测得 DP/DM 低阻短接的定位。
