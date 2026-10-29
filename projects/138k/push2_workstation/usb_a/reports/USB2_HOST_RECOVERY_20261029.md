# USB2 Host保留HS连接恢复与收包排查

日期：2026-10-29，UTC+08:00。用户明确授权自行修改、综合及下载，以定位并修复25K与138K连接问题。本轮继续使用25K完整DA与USB2，USB1保留供电；JTAG已按断电流程移回138K。不改锁定网表、冻结基线或两个板原Flash。

## 写前观察

03:29实际读取138K `GW5AST-138C / 0x0001081B / C11028E5 / 0x00022020`。原E5连续16窗中13窗为WAIT_ATTACH(7)，3窗为Host关闭后的重试等待；所有窗SOF0，端口失败码0，无CPU或PHY初始化错误。不能从这些短窗断言此前从未chirp。

接续25K端03:21的四窗原生统计：复位SE0已达约3 ms，设备状态经过chirp并进入HS，但PHY／UTMI接收累计均0、地址0。原始证据及DA恢复见 [25K诊断](../../../../25k/example/MIDI_KEYBOARD/reports/USB2_RXCMD_DIAGNOSTIC_20261029.md)。

本次证据根为 `~/.cache/fpga-usb2-hdmi/138k-handshake-fix-20261029_032945/`。`before_observation.json`及16个`before_*/`保留E5实际身份前后读回、CSV及解码。

## 可复现的恢复缺口

原Host启用时将PHY配置为FS检测，只在FS J接入后启动复位。对保留HS状态且没有新FS J沿的独立供电设备，WAIT_ATTACH无限等待，CPU每400 ms超时关闭Host，再于100 ms后重试，不能主动产生使设备重新协商的总线复位。

在现有 `tb_workstation_usb2_host_port.sv` 增加保留HS、FS检测侧仍为SE0的模型。原RTL在cycle200108仍停WAIT_ATTACH，测试失败，日志为 `retained_hs_before_fix.log`。修复是在HS允许、SE0持续200 ms时，每次Host启用最多调用一次原根端口复位，不凭超时宣告连接；只有合格设备chirp或复位后实际FS J才建立连接。无设备时恢复等待，不反复复位、不开放流量。FS-only、原有HS／FS协商、去抖、会话取消与超时门禁保留。

新增保留HS恢复及无设备单次恢复场景后，端口16个场景／23830个检查通过；这证明模型中的恢复缺口被修复，仍需本轮实际候选判断它与收包阻断的关系。

## 诊断观察器与候选

原软件重试会清空原生端口故障，短GAO窗口容易只看到下一轮WAIT_ATTACH。本轮增加默认关闭的 `PORT_OBSERVER`，只由独立hotplug诊断顶层启用；在全局ULPI复位域保存状态／故障历史、最后失败前状态和FunctionControl、PHY就绪次数、原生收发及SOF峰值。软件禁用Host不清除这些历史。新增仿真验证故障跨重试保留、下一次就绪计数以及全局复位清除。

新增显式GAO配置 `port`，schema `usb2-hdmi-hotplug-port-observer-v3`，674个物理信号；保留v1／v2布局和解码兼容。解码、原生端口及记录器首批12项定向测试通过，日志为 `targeted_fix_tests.log`。较大回归另记 `regression.log`。

候选 `C11029E7` 位于证据根的 `candidate-e7/`，使用现有准备／构建入口，不复制生产工程或新增编号构建器。71个编译来源；HDMI沿用逐字节核验的D5实现，原生产固件ROM仍为 `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457`。候选清单、综合／布局布线、审计及独立上板身份各自保存，不以准备或工具退出成功替代实际部署结果。

回退目标为本轮写前实际E5，位流SHA256 `e723f82f45e5807452125f8a3bb6429ec4955bce91c7770066586fb738c66703`，位于 `~/.cache/fpga-usb2-hdmi/20261028-020452-d5-hotplug/candidate-e5/impl/pnr/ao_0.fs`。25K继续完整DA，未切换USB1 FS。

### E7未下载，E8修正调试层级

E7综合成功，但实现阶段报告GAO无法找到generate块中的记录器信号；保留了失败构建清单及综合网表，未下载。实际综合网表将generate声明输出为转义的点分隔标识符，而不是模块实例层级。为避免依赖转义标识符的GAO／解析器差异，将观察寄存器声明归到MMIO模块层，条件generate只控制其实现；默认关闭时输出常零，不引入另一套状态权威。

重新准备独立 `C11029E8 / GAO29E8`，位于同一证据根 `candidate-e8/`。12项定向测试重新通过；全部122项暂存输入哈希一致，原PHY及新增PORT共30个寄存器字段均已绑定到实际FF和正确时钟，见 `port_probe_bindings_precheck_e8.json`。HDMI及生产固件ROM保持原来源。E8实际综合＋布局布线373.887秒，生成位流SHA256 `64cd42e92658088af7f753f286b5ec45b8f653a657aca18c87a632a553ebfbad`；部署和硬件定位结果另记，不把E7当作已运行候选。

## E8上板结果：未恢复枚举

E8结构、PLL、CDC、来源和GAO实际寄存器绑定审计通过，但路由时序未闭合：setup −5.804 ns、hold −0.157 ns。9条负裕量路径终点属于GAO，另1条为原HDMI DDR跨域hold路径；未放宽约束，也未将本候选标记为时序通过。完整报告保存在 `candidate-e8/integration_audit.json` 和证据根 `audit-e8-summary.json`。

04:00:40完成SRAM下载及独立身份读回：`0x0001081B / C11029E8 / 0x00022230`。04:00:42～04:01:04六窗的PHY就绪尝试数依次为6、14、22、30、38、46，但sticky状态历史始终为255，即仅经过状态0～7，从未进入根端口复位或chirp状态；收包、发包、SOF峰值全为0。PHY初始化到17，无CPU故障。原始窗口为 `e8_capture_01/` 至 `e8_capture_06/`，部署汇总为 `deployment-e8.json`。

因此，仿真中补齐的保留HS恢复缺口不是已完成的实板修复，实际25K仍未枚举。后续独立计数进一步发现了时钟问题，不能继续把阻断归因于板间业务协议。

## 独立计数：输入约29.86MHz而非60MHz

04:07临时在138K SRAM运行原F5独立自测。F5不含CPU、PLL、DDR或HDMI；原12项输入哈希与位流身份均核验一致。位流SHA256为 `34ec901f0f60ae74bed8b050bcf60bc4f6d0b044a8e36a2a3c8a6bb9adad50ee`。其24位计数器每个ULPI上升沿加1，没有二分频；每500000个50MHz参考周期锁存一次差值。F5原路由时序全部通过，未因本次实验修改RTL、约束或位流。

| 采样完成时间 | 参考周期累计 | 完成窗口数 | 当前10ms窗边沿数 | 按50MHz参考换算 |
| --- | ---: | ---: | ---: | ---: |
| 04:07:56 | 194767065 | 389 | 298594 | 29.8594MHz |
| 04:08:01 | 406690802 | 813 | 298664 | 29.8664MHz |
| 04:08:05 | 622021658 | 1244 | 298772 | 29.8772MHz |
| 04:08:09 | 831660121 | 1663 | 298668 | 29.8668MHz |

相同快照可读到USB3300 ID `0424:0004`，初始化阶段17、失败码0。四窗均为 `stage=ulpi_frequency_out_of_range`、`clock_frequency_ok=false`、`passed=false`，不是PHY自测通过。寄存器交互成功不能证明数据包时钟合格。

另用首末捕获时间中点的墙钟间隔12.76369秒核对参考累计计数，得到参考约49.899MHz；此方法只用于排除参考实际为100MHz等二倍频解释，不是校准测频。Gray计数器已在RTL仿真增加30MHz场景，约150沿／250参考拍；60MHz场景约300沿／250参考拍。解码回归也覆盖上述四个实测边沿值，即使寄存器初始化成功也不允许通过。

全部原始数据保存在 `f5_clock_capture_01/` 至 `_04/`、`absolute_clock_check.json` 及F5前后身份／下载日志。04:08:25重新独立读回E8，随后窗口仍为WAIT_ATTACH、历史255、收发和SOF均0；恢复日志为 `e8_after_clock_probe_*.log` 和 `e8_after_clock_probe/`。138K Flash仍为原E5，25K Flash仍为完整DA，本轮未写Flash。

当前端口定时仍按合格的60MHz计算：200ms恢复门限在约30MHz时钟下实际需约400ms，与CPU每400ms关闭Host重试相撞。这解释了E8为何未进入恢复状态，但把门限改短、改成30MHz或倍频内部逻辑不能修复不合格的物理ULPI输入，因此未如此规避。

## 物理定位边界与下一项

锁定载板网表SHA256保持 `deff91f6c48be8d66241e32107b88f7eea47ad2bf6c5b607b139c4b85c33a121`。它标注OSC3为24MHz，连接 `OSC3.1–U2.28(XI)`、`OSC3.3–U2.27(XO)`；时钟路径为 `U2.14(CLKOUT)–U5.2–旁路–U5.13–J1.92–FPGA C18`。RESET输入U2.9按该网表接地，并非FPGA可控复位脚。

本地Microchip DS00001783C表3-1和6.3节明确：USB3300需要24MHz晶体或参考输入，锁定后输出60MHz；不支持从CLKOUT输入外部60MHz。未驱动或反向注入该脚。

已确认FPGA收到的时钟边沿速率不合格，尚未区分USB3300晶体／时钟生成异常与CLKOUT连接路径丢沿，不能仅由此断言OSC3一定装错。下一项先核对实际OSC3顶面频率标记／BOM，并检查其焊点；如果24MHz料号无误，再分段检查上述CLKOUT路径。不要再用D+/D−的万用表直流读数判断HS数据活动。

## 离线验证

本轮原生ULPI、USB2 MMIO／真实25K交互、组合HDMI诊断和accepted输入边界共46项通过，日志 `regression.log`，耗时827.214秒；E8最终观察器布局与端口恢复另有12项定向测试通过，日志 `targeted_e8_tests.log`。独立自测9项通过，含7种RTL场景及新增30MHz计数／解码回归，日志 `half_rate_selftest_regression.log`。`git diff --check`通过；不把这些离线通过等同于实板枚举恢复。

04:20:41最后只读采样再次核对实际E8身份；自全局复位累计就绪1469次，状态历史仍为255，收包、发包、SOF峰值仍全0，`enumeration_complete=false`。证据目录 `e8_final_readback_20261029_042038/`。最终来源、位流、锁定网表及回归哈希索引为 `final_source_evidence_index.json`；E8的122项、F5的12项暂存输入最终复核全部一致。
