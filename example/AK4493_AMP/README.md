# AK4493 音频与功放测试

适用于 Hardware 中的本版主板、音频子板和 GW5AST-LV138PG484AC2/I1 核心板。默认通过 SRAM 下载，下载它会替换当前 FPGA 运行逻辑。2026-10-24 按用户要求，已将左右隔离诊断镜像固化到板载 Flash，断电后可重新加载。

**当前固化镜像：UserCode `0x13802401`，静音 3 秒 → 仅左 1kHz 3 秒 → 静音 3 秒 → 仅右 1.5kHz 3 秒，12 秒循环，峰值 −42dBFS。** 位流来自 `builds/20261024_023144_617877/impl/pnr/ao_0.fs`。Flash 写入校验、独立校验、清 SRAM 后从 Flash 重载及 JTAG 数字检查均通过；未做物理断电重启测试。记录见 [Flash 固化报告](reports/flash_channels_20261024/result.json) 和 [启动后 JTAG](reports/jtag_flash_channels_boot.json)。耳机仅右耳发声、噗嗤和断音的问题仍未解决。

**2026-10-23 验证结果：修复硬件虚焊并重新下载后，用户确认 CN 扬声器接口成功发声，基本听音验证通过。** 使用 UserCode `0x13802302` 的现有音频镜像和 −42dBFS 循环测试音。CN1/CN2 的逐口结果、声道分离及输出波形未单独确认。成功记录见 [speaker_success_after_repair.json](reports/speaker_success_after_repair.json)，调试过程见 [扬声器无声定位](docs/扬声器无声定位.md)。

2026-10-24 开始 [3.5mm 输出测试](docs/3.5mm输出测试.md)：用户说明已修改使能电路，要求直接听音。原镜像已发声，但反馈“先左然后一直两边都有声音”，声道分离尚未通过。随后下载 UserCode `0x13802401` 的隔离诊断镜像：静音 → 仅左 → 静音 → 仅右，各 3 秒，峰值仍为 −42dBFS，没有双声道同时播放段。仿真、时序和 JTAG 数字检查均通过，听音结果及后续记录于 `reports/headphone_3p5mm.json`。

隔离诊断使用 `build_channels_gao.tcl` 构建，仿真命令为 `python3 example/AK4493_AMP/tests/check_audio.py --isolate`。原 `build_gao.tcl` 仍构建以下描述的 8 秒标准循环，已验证的 CN 发声镜像保留在原构建目录。

隔离模式续测为仅右耳发声，伴随周期性噗嗤与断音，静音段也有噗嗤。用户确认使用三段 TRS，左右输入/反馈电阻已补齐，SHUTDOWN 直接拉高。三组 JTAG 内部计数未见复位或明显停顿；随后下载 `0x13802402` 连续双声道镜像，取消周期切换，左 1kHz、右 1.5kHz 持续播放，仍为 −42dBFS。构建脚本 `build_continuous_gao.tcl`，仿真参数 `--continuous`；仿真、时序与下载后 JTAG 均通过。用户确认连续音仍有噗嗤、断音且只有右耳响，模拟测试未通过；该镜像用于对照诊断，随后按用户要求改为上述交替镜像并固化。后续可观察 U4 的 PVDD/PVSS 是否随噗嗤波动，并沿左声道模拟输入、输出及插座定位。

## 硬件模式和管脚

已放大核查音频图：U1 的 PSN 与 DIF0、DIF1、DIF2 均接 DVDD_3V3；ACKS 经 R10=0Ω 接 DVDD_3V3。DAC 使用**引脚控制、32 位 I²S、自动时钟检测**。INV 接地。SSLOW/SD/SLOW 是滤波选择，SMUTE 是软静音，不能按 SPI CSN/CCLK/CDTI 使用。

| 功能 | 主板 FPGA 球号 | 音频子板引脚 |
| --- | --- | --- |
| 50MHz / 12.288MHz | V22 / K18 | 主板时钟 |
| 低有效重启 | V13 | DIP_SWITCH_0，正常 OFF |
| PDN | C13 | U1.2 |
| MCLK | B13 | U1.46 |
| BICK | A13 | U1.3 |
| SDATA | A14 | U1.4 |
| LRCK | B15 | U1.5 |
| SSLOW | B16 | U1.6 |
| SMUTE | A15 | U1.7 |
| SD | A16 | U1.8 |
| SLOW | D17 | U1.9 |
| PLUG_DET（RTL 名） | C17，输入 | FPGA_DET，经 R43 读 Q2 集电极 / SHDN_SPK |

球号沿主板 FPC2→J1、官方 SOM BTB 实际位置核对；音频子板网络名里有旧球号，不能直接复制。排线应满足主板 FPC2 n→子板 FPC1 (25−n)。

格式核对参考公开 AK4493 手册 `017012230-E-00`（2017/12），模式表 22、时钟表 9 及引脚表。LCSC 以 AK4493SEQ 名称提供的 PDF 实际为这份旧版，**不是 AK4493S 新版 `211100143-E-02`**；新版官方获取页需要邮件申请，本任务没有提交申请。当前例程采用引脚模式，没有未经确认的寄存器写入；最终 DAC/功放功能仍以本板模拟实测为准。

## 音频晶振实测（2026-10-24）

使用核心板 V22 标称 50MHz 时钟作为参考，独立计数两个音频晶振的上升沿。每窗口 500,000,000 个参考周期，连续 6 个窗口，累计名义 60 秒：

| FPGA 输入 | 标称频率 | 实测折算频率 | 相对标称偏差 |
| --- | ---: | ---: | ---: |
| K18 | 12,288,000Hz | 12,287,945.73Hz | −4.416ppm |
| J19 | 16,934,400Hz | 16,934,270.15Hz | −7.668ppm |

各输入的六窗口读数跨度均为 0.1Hz；参考晶振未外部校准，因此上述 Hz/ppm 为相对 50MHz 假定的结果，不能视作绝对频率或抖动标定。本音频例程使用 K18，J19 的标称 16.9344MHz 对应 44.1kHz 的 384fs，未用于当前 48kHz 测试音。

测频仅临时下载 SRAM；完成后已从原 Flash 恢复左右交替镜像 `0x13802401`，读回身份及音频数字检查通过，未写 Flash。方法见[双晶振测频说明](../CLOCK_MEASURE/README.md)，数据见[测量记录](../CLOCK_MEASURE/reports/measurement.json)，恢复证据见[部署记录](../CLOCK_MEASURE/reports/deployment.json)。以下时序中的 12.288MHz、3.072MHz、48kHz 仍表示标称设计值。

## 输出和时序

- 上电保持 PDN=0、SMUTE=1 约 20ms；这期间 MCLK/BICK 不运行。
- PDN 释放后开启完整 MCLK 脉冲；MCLK=12.288MHz，BICK=3.072MHz，LRCK=48kHz。
- 32 位二补码、MSB 优先；LRCK 低左高右，MSB 在 LRCK 翻转一个 BICK 后出现；下降沿改变数据，上升沿采样。
- 先输出 4096 帧零数据并保持软静音，再解除静音。
- 8 秒循环：静音 2 秒 → 左声道 1kHz 2 秒 → 右声道 1.5kHz 2 秒 → 双声道 2 秒。
- 正弦峰值 −42dBFS；SSLOW、SD、SLOW 均低。硬件插座检测、继电器及功放使能由子板电路处理；本例只读取 PLUG_DET。

音频子板还需要 12V、5V 和模拟电源链路；FPGA 数字状态不能证明这些电源正常。扬声器跨接 CN1/CN2 各声道的 +/−，桥接负端不是 GND。耳机和扬声器路径取决于插座触点与继电器实物状态。

## 构建与验证

从工作区根目录执行：

```sh
python3 example/AK4493_AMP/tests/check_audio.py
python3 example/RTL8723DS/tools/gowin_build.py example/AK4493_AMP/build_gao.tcl
python3 example/RTL8723DS/program_sram.py --manifest example/AK4493_AMP/reports/last_build.json --allow-gao --check-only
python3 example/RTL8723DS/program_sram.py --manifest example/AK4493_AMP/reports/last_build.json --allow-gao
python3 example/AK4493_AMP/tools/jtag_status.py
```

仿真从实际 BICK/LRCK/SDATA 输出解码 2000 个样本，检查复位时钟、48kHz 帧周期、左右声道隔离、1kHz/1.5kHz 频谱及幅度。不是直接读取内部正弦表验证自身。

JTAG 在 50MHz 域读取两次同步后的 Gray 计数，以参考时钟差值计算音频时钟及帧速率。只对第一同步级取消异步 hold 关系并施加小于源周期的最大延迟，第二级及后续路径仍检查 setup/hold。GAO 定义与对应位流一起保存在 builds 中。

`reports/jtag_status.json` 的 `digital_passed` 只说明 FPGA 时钟和生成器状态满足预期。`analog_verified` 和总体 `passed` 仅在模拟功能实测通过后才可置 true；AK4493 的引脚模式没有寄存器回读，子板也未向 FPGA 引出功放 FAULT。当前用户已反馈 6.35mm 耳机无声，模拟功能未通过。


## 本板实测记录（2026-10-23）

- SRAM Program+Verify 通过，UserCode `0x13802302`。
- 布局布线 setup/hold 违规均为 0；50MHz 域 Fmax 129.561MHz。
- JTAG 连续两次捕获有效；按 FPGA 50MHz 参考计数测得音频时钟 **12,287,951.66Hz**、帧率 **47,999.84Hz**。
- PDN=1、SMUTE=0、restart_n=1；观察到测试阶段由左声道切到右声道。PLUG_DET 原始电平为 0，未据此推断插座是否插入。
- 数字检查通过；后续用户确认 6.35mm 耳机无声，功放功能未通过。主机麦克风权限状态为 denied。

原始捕获见 `reports/jtag_status.0.csv`、`.1.csv`；解码及计数差值见 `reports/jtag_status.json`。以上频率相对于核心板名义 50MHz 参考，未校准到外部频率基准。


## 内部 VCCIO5 电源监测

后续镜像保留上述音频功能，加入 Gowin 工具生成的 ADCLRC IP（`rtl/vccio5_adc.v`）。仅启用 BUF_BK5_EN[5]，静态 VSEN_CTL=111；未分配外部 ADC 引脚。参数为内部 2.5MHz OSC /2、SAMPLE_CNT_SEL=4、RATE_CHANGE_CTRL=4、FSCAL=653、OFFSET=0。配置文件保留在 `ip/vccio5_adc.mod`，其中生成输出路径可按本机修改。

GAO 扩展为 352 位；前 5 个字仍为 AMP1，后 6 个字依次为 ADC5 签名、最小值/末值、转换耗时低位/最大值、转换次数、超时次数、样本年龄低位/标志。脚本兼容此前 160 位捕获。电压换算采用手册的 VCCIO /8 通道及 `raw/2048` ADC 标度，即 `raw×8/2048 V`；使用典型校准参数，读数未校准到外部仪表。

2026-10-23 新增实测：`reports/jtag_vccio5.json`。VCCIO5 最小 raw=864、最大 raw=871，对应约 **3.375～3.402V**；累计 1418 次有效转换、0 次超时。两次捕获间转换计数增加 204，排除复用旧结果。50MHz 域 Fmax 202.721MHz、setup/hold 违规均为 0，新镜像 SRAM 校验通过。音频实测帧率约 48,000.07Hz。

该项只验证核心板 Bank5 IO 电源，不能证明无线子板 3.3V、使能电压、FPC 顺序或模块本身正常；BLE/SDIO 协议状态仍以无线专用镜像的实测为准。

ADC 数字采集测试：

```sh
iverilog -g2012 -s tb_vccio5_monitor -o /tmp/vccio5.vvp example/AK4493_AMP/rtl/vccio5_monitor.v example/AK4493_AMP/tests/tb_vccio5_monitor.v
vvp /tmp/vccio5.vvp
```

模型验证有效结果、min/max、持续高的旧 ready 信号不得计为新转换、50ms 超时及复位；不模拟 ADC 模拟精度。`board_power_passed` 独立于音频 `digital_passed`，两者通过仍不等于模拟功放通过。

## 6.35mm 耳机无声后的定位

用户确认 U4 为 **MAX9722A**。官方手册要求 A 型每声道外接输入、反馈电阻，但图中 C90/C91 直接接反相输入，R41=1kΩ 跨左右输出，缺少正常闭环。另有 PLUG_DET 与 Q1/Q2 基极直接共用 SHDN_EAR 的问题：若为普通 NPN，可能把使能钳在约 0.7V，达不到 2V 高电平要求；Q1/Q2 具体型号待确认。

`reports/jtag_no_sound.json` 复核 FPGA 数字状态仍通过，帧率约 48,000.20Hz；`plug_det=false` 读取的是 FPGA_DET / Q2 集电极，并不能证明耳放 SHDN 状态。用户反馈单独保存在 `reports/user_feedback.json`，不改写原始 GAO 捕获。

详细依据、原图局部、每声道 10kΩ 输入/10kΩ 反馈的修正草案和 D4 方向更正见 [6.35mm 无声定位](docs/6.35mm无声定位.md)。这些是图纸问题和条件性分析；尚未核实实板 PCB 与模拟电压，不能将其当作已完成的硬件返修或功放通过结论。

## CN1/CN2 扬声器调试续测

用户要求改测两个扬声器口后，重新加载原音频 SRAM 镜像，数字检查仍通过。两个口均被用户确认无声；用户实测 AVDD_12V=9.1V、U2.1 SD#=0V。9.1V 在 TPA3140D2 允许的 4.5–14.4V 范围内，SD#=0V 则明确使功放关断。R40 的 +5V / SHDN_SPK 两端为 5V / 0V，PLUG_DET 为 0.657V，与 Q2 导通拉低一致，具体插座检测或焊接根因仍待查。

重新上电下载后的 `reports/jtag_speaker_repower.json` 数字检查仍通过。用户随后反馈 DAC 输出约 0V，DVDD=1.8V、PDN=2.4V（第二输出原文标为 RL，待确认是否为 RN）。正在核查 DAC 端 VDDR、AVDD、TVDD 与实际 MCLK；PDN 2.4V 不能在未知 TVDD 时直接判为复位低。FPGA 内部状态不证明这些物理侧条件正常。

续测用户回复 5V、3.3V、DAC 端无 MCLK。此时 JTAG 复查签名无效；重新下载原音频 SRAM 后，`reports/jtag_dac_mclk_reload.json` 捕获恢复有效，内部时钟约 12.287980MHz、帧率 47,999.73Hz。当前等待重新测量 U1.46；若仍无时钟，沿 B13 → 主板 FPC2.16 → 子板 FPC1.9 → U1.46 分段定位。TVDD 未单独确认，尚未证明 DAC 端时钟或模拟功能恢复。

原始数据见 `reports/jtag_speaker_resume.json`、`reports/speaker_resume.json`。测点图、判定依据和调试过程见 [扬声器无声定位](docs/扬声器无声定位.md)。上述无声及电压读数为修焊前记录；修复虚焊并于 23:05 重新下载后，用户已确认 CN 接口成功发声，听音验证通过。当前仍运行 −42dBFS 测试音；最终成功证据见 `reports/speaker_success_after_repair.json`。
