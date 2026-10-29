# 独立双时钟／I2S 数字探针离线检查点（2026-10-30）

最终候选 **`custom138k-muted-audio-probe-C11030B7`** 已通过来源闭包、实际 top 仿真、综合／P&R、真实 routed VO／SDF 定量检查及 SRAM `--check-only`。物理 SMUTE 恒高、SDATA 恒零已由网表确认。此记录截止时尚未下载 SRAM、采集实体 GAO 或写 Flash；它只支持独立数字实验，不是整机或模拟验收。

当前机器证据为 [audio_probe_offline.json](workstation_task_20261030/audio_probe_offline.json)，包含 B0～B7 逐代输入身份、失败／替代原因、最终每 bit 路由数据、时钟、例外、复位、测试及回退。原 [audio_probe_prepare.json](workstation_task_20261030/audio_probe_prepare.json) 仅是 **B0 历史准备材料**，保持原样；它不能用当前工具重新验证，也不绑定最终 B7。

## 输入与观测链

入口 [workstation_audio_probe.py](../tools/workstation_audio_probe.py) 仅直接消费版本化 top、domain、monitor、transaction、serializer 五份 RTL；复用原 `example/RTL8723DS/tools/gowin_build.py`，不改变 accepted／pinned／resource profile、历史例程、冻结来源或 `build.py`。完整字节哈希在最终 `inputs.json` 及机器证据中。输出根为 `/Users/sphenicidition/.cache/fpga-audio-probe/20261030-C11030B7`。

CST 只使用已核对的 V22／K18／J19／V13 和 C13／B13／A13／B15／A14／A15 数字音频输出，3.3V、DRIVE4。默认 monitor 1ms×4、PDN4／startup1028、每事务等待阶段40ms。50MHz 注册 POR 后启动48k epoch0，hold50ms→44.1k epoch1，hold50ms→48k epoch2，hold50ms→COMPLETE，最终继续48k；任何 fault／reject／failure 锁存 ERROR。

GAO 是50MHz、Standard post-synthesis、128点、800bit／25字。192bit 音频统计在 selected 域寄存保持，再发 ACK；两级 payload／ACK 同步后才捕获，单一未完成请求，flush 清除并撤销有效。保留三个 epoch 的完整物理帧数和两模式 selected 测频值，使稍后 COMPLETE 窗口仍能核对历史44.1k阶段。它不实现计算域 DSP 桥。

## 仿真及物理检查

三项回归 exit0（1.996s）：实际 top／官方 GW5A DCS 完成两次切换、epoch2、607个原子快照、17个物理完整零帧；观察到三个代次，核对帧标签、I2S分频、SMUTE及 stopped-high→ERROR／fault6。此次缩短 monitor／hold／startup，397周期的故障观察不冒充默认500周期界限；默认1028帧真实预算由 [I2S组合检查点](WORKSTATION_I2S_TRANSPORT_20261030.md)独立覆盖。准备测试拒绝输出复用、保留身份、篡改／额外RTL、未知SDK启动EDA。

[check_workstation_audio_probe.py](../tools/check_workstation_audio_probe.py) 读取最终真实 routed `.vo`／`.sdf`／`.tr`／资源报告，重新核对来源及位流／GAO CRC。它验证每个 SDC 对象非零匹配、全部命令 Actived、8条 setup max-delay 实际有路径；逐位遍历含 LUT 的路由图，保留首级之后的同步级和所有内部 reset 检查。`physical_checks.json` 仍是要求清单，不作为通过证据。

| 路径 | 实际数量 | 最坏定量结果 |
| --- | --- | --- |
| raw48 Gray→首级 | 32bit，无优化 | 源输入根→D 4.750ns；跨 bit／corner 保守 skew2.414ns |
| raw44 Gray→首级 | 32bit，无优化 | 源输入根→D 4.963ns；skew2.580ns |
| selected Gray→首级 | 32bit，无优化 | DCS CLKOUT→D 3.810ns；skew2.328ns |
| 保持 snapshot→payload首级 | 192bit | CLK→Q 加组合／布线≤2.084ns |
| 保持 epoch／mode→serializer | 32+1个FF目标 | CLK→Q 加布线≤1.719ns；`mode_44k1_s3` 实际为INV，不是额外FF |
| control／ACK首级 | 8组，全部寄存源根 | CLK→Q 加组合／布线≤4.306ns；后级仍在 |
| source level首级 | 3组 | 输入根／DCS输出→D≤4.072ns |

全部上述数据界限低于20ns；Gray使用 min／max rise／fall 的跨 corner 最保守跨度，不宣称抖动实测。checker 还检查五组三个真实边沿复位释放链以及全部3377个主设计FF的 async reset根：POR、50MHz control、本地 raw、selected release、serializer／response／snapshot、返回 payload／ACK。控制释放、raw计数器释放、selected资格后的释放各有独立归属。

实际时钟共6条：reference50、raw48、raw44、同一DCS输出上的 selected48→raw48／selected44→raw44，以及SDK GAO `tck_pad_i` 20MHz。单个真实DCS为FALLING／SELFORCE0，两参考输入及输出均 PRIMARY，select由50MHz共使能FF驱动且复位为48 onehot。网表检查和实际官方DCS仿真共同覆盖结构与切换行为。

全局 setup／hold违规端点0；所请求最差表 setup +10.358ns、hold +0.250ns、recovery +7.714ns、removal +0.373ns。SDK对共享DCS输出的 mode-specific hold／recovery／removal 查询会显示同一条较快 selected44 关系；实际同路由端点的最坏余量分别 +0.275／+54.284／+0.387ns，较慢selected48由该保守条件覆盖，不伪称两份独立物理实现。held配置setup明确列出两模式，targeted MPW明确列出 selected44 +28.079ns、selected48 +39.243ns（全局GAO最差 +7.265ns）。复位同步首级是异步断言的亚稳态隔离点；相位相关STA不能代替真实异步同步协议或硬件实验。

资源：主设计逻辑2514、FF3377、DCS1／20、PRIMARY4／8；GAO另列逻辑1160、FF3416、BSRAM46，不替代整机资源预算。保留 PA1015（GAO sample-clock别名）和PR1014（仅50MHz有通用路由段）；音频DCS两输入／输出PRIMARY已单独核对，不隐藏50MHz警告。

checker在真实模型上注入25ns Gray布线、删去首组第二级、添加零匹配约束，三者均拒绝。CSV解码器另拒绝 flush、物理帧错误及旧epoch；这些是离线负例，尚无本候选实体CSV。

## EDA迭代与最终身份

B0因本机不支持 `-opt_goal` 在综合前失败；B1综合通过但P&R拒绝源级对象零匹配。B2按真实网表绑定，B3把单bit hold例外缩至 `/D`，B4生成 routed VO／SDF。B3／B4的 selected clock-group 形式使7条setup CDC界限没有实际路径；B5仅保留两方向精确 selected48↔selected44 false-path，8条界限均恢复实际路径。B6补mode查询，B7补目标MPW表。各输出／身份均保留，不改 vendor／历史输入来通过。

B7不可变构建清单：`reports/build_20261030_053313_154092.json`。位流为 `builds/20261030_053313_154092/impl/pnr/ao_0.fs`，SHA256 **`2e27afccd217074b8278e5a7ab75bde08060d14484d3d1ff191c53dc8819565f`**，UserCode **`0xC11030B7`**。helper只声明其自身门禁通过；`probe_build_result.json` 保持 physical_audit_complete／accepted_for_sram=false；独立checker及本次离线证据才给出物理审查结果，供主线程复核后执行已授权SRAM。

```sh
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_audio_probe.py
python3 projects/138k/push2_workstation/usb_a/tools/check_workstation_audio_probe.py --output /Users/sphenicidition/.cache/fpga-audio-probe/20261030-C11030B7 --json /Users/sphenicidition/.cache/fpga-audio-probe/20261030-C11030B7/physical_audit.json --self-test
python3 projects/138k/push2_workstation/usb_a/tools/decode_workstation_audio_probe.py --self-test
python3 example/RTL8723DS/program_sram.py --manifest /Users/sphenicidition/.cache/fpga-audio-probe/20261030-C11030B7/reports/build_20261030_053313_154092.json --allow-gao --check-only
```

## SRAM／GAO交接与回退

主线程05:31:19只读 operation0 为 GW5AST-138C／ID0x0001081B、UserCode0xC11028E5、status0x00022020；原JSON和哈希纳入机器证据。操作前仍应独立确认目标、保存新身份日志；下载后及每次GAO前后再次operation0确认C11030B7。扫描必须使用当前Mac FT2CH channel0的唯一真实location，不沿用历史WINUSB位置54。

主线程复核后执行SRAM（本子任务未执行）：

```sh
python3 example/RTL8723DS/program_sram.py --manifest /Users/sphenicidition/.cache/fpga-audio-probe/20261030-C11030B7/reports/build_20261030_053313_154092.json --allow-gao
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli --device GW5AST-138C --operation_index 0 --cable-index 1 --channel 0
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli --scan-cables
```

将实际扫描 location 代入下列 `<current-location>`；先把不可变build的GAO定义拷到独立采集目录，保留原定义不被GAO改写。`gao_sh`默认立即采集，预计下载后自动序列在约250ms内完成，可在主机可用后采COMPLETE。原始CSV需要永久保留于ignored输出，不能只保存解码结果。

```sh
mkdir -p /Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7
cp /Users/sphenicidition/.cache/fpga-audio-probe/20261030-C11030B7/builds/20261030_053313_154092/debug/audio_probe.gao /Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7/capture.gao
env DYLD_LIBRARY_PATH=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib DYLD_FRAMEWORK_PATH=/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/lib /Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gao_sh -gao /Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7/capture.gao -device GW5AST-138C -cable FT2CH -location <current-location> -out /Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7/capture
python3 projects/138k/push2_workstation/usb_a/tools/decode_workstation_audio_probe.py /Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7/capture_core0_window0.csv --json /Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7/decoded.json
```

有效终态须签名APB1、128个有连续50MHz heartbeat的样本、COMPLETE、epoch2、completed1／accepted2／applied2／reject0／failed0、snapshot_valid且无flush、各三代次都有完整帧、最终帧标签epoch2／48模式、错误／underrun／rejection均0，两种保留selected测频和两参考计数符合1ms窗口。解码器同时验真这些条件；导出CSV或programmer exit0各自都不是实体验收。

完成诊断后可用既有Flash重载恢复E5，**没有Flash写入**：

```sh
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli --device GW5AST-138C --operation_index 1 --cable-index 1 --channel 0
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli --device GW5AST-138C --operation_index 0 --cable-index 1 --channel 0
```

重载可能数分钟才完成；早期UserCode0／status0x460是历史已记录中间态，须稍后再独立读回ID0x0001081B／E5／configured状态，不能立即补下SRAM冒充Flash启动。原Flash固化、镜像e723f82f…及恢复依据见 [USB2_HDMI_FLASH_20261028.md](USB2_HDMI_FLASH_20261028.md)。若失败保留原始证据并定位，不改写Flash或沿用10-24旧音频身份。

AK4493S的SMUTE是数字软静音。即使PCM零、SMUTE高，PDN边沿仍可能click；无外部模拟mute不能保证无pop或模拟无声。MCLK变化须在PDN低／RSTN低；PDN4帧和startup1028帧保留数字下限余量，但strap、ACKS／384fs识别、电气及模拟输出仍待整机硬件验收。本实验不扩大A03／A05／A06整项完成状态。完整双率DSP／时基桥／最终PCM／routed门禁及实体声画通过后，本探针退出集成输入角色，不转为生产profile。
