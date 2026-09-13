# GW5AST-138C 音频迁移候选

## 2026-09-11 当前状态

当前 FPGA 已恢复为完整工作站 **93D0**，控制值及电脑键盘窗口恢复；音频 48 kHz、AE350、DDR／显示数字回读通过。精确工作站绑定仍见 `AE350_CURRENT.json`。此次 CH569 诊断之后的恢复证据在 `ch569_midi_probe/results/restore_20260911_154508_303412/`。

网口旁 P1 USB-C → CH569 已实际以 480 Mbps 枚举 Push 2，并收到 301 对按下／释放、旋钮 CC 和弯音，三分钟记录未见传输错误。CH569 保留测试固件，**其 MIDI 尚未接入音源**；USB 运行在 CH569 CPU，因此不计入纯 RTL Host 验收。详见 [CH569 真机记录](ch569_midi_probe/results/acceptance_20260911_154402_306213/README.md)。J18 纯 RTL 高速 PHY 工作仍独立待完成。

## 2026-09-10 16:29 历史状态

当时 SRAM 是 **259B**（SHA-256 `360a9d64…`），同一个完整138K工程已接原合成/效果/录音/曲谱、AE350硬核、CPU共享DDR和双页UI、队友HDMI/左右FFT/波形/结像。完整布线setup/hold 0/0，最小裕量+0.096ns；数字真机CPU/DDR/音频服务/四次UI帧界提交PASS，连续48k音频与60Hz扫描、故障0。新增电脑V14/115200原始MIDI，与G1/CPU三路仲裁；三图与25个黑白琴键同屏。电脑演奏/控制及UI持续提交已数字板验，发送方法见 [PC_MIDI.md](ae350/PC_MIDI.md)。

自动启动失败位随厂商SRAM下载流程复现，重新加载既有Flash时清除；未写Flash，未验断电冷启动。HDMI/耳机已接，用户此前对9630基本试用反馈正常；259B长按手感/波形平滑度待查看，G1/触摸/实体LED仍未验。查看[当前版本绑定](AE350_CURRENT.json)、[AE350证据](ae350/README.md)、[完整能力清单](../CAPABILITY_MIGRATION.md)。

基础`rtl/gw138k_managed_audio.sv`仍作为独立验证入口；真实CPU控制及UI候选在`ae350/integration`、`ae350/ddr`、`ae350/ui`，没有覆盖原工程和队友Prj1顶层。下文基础音频适配器/旧独立构建的接口与流程保留，不能代替当前完整AE350版本的绑定证据。

波形增加AUTO ×1…×64显示缩放；电脑补齐VIBR/GLIDE/BEND/ROUTE/SNAP，按钮/实际PCM路由和快照已数字板测，[本次记录](ae350/EXPRESSION_CONTROLS.md)。本次频谱改为1像素独立柱＋1像素间隔，取消插值；左右各2048点FFT。相对6DA7 BSRAM +7到204/340、Logic −388、FF −82、DSP不变，频谱新数据23/24次每秒；[改动与对应证据](ae350/video/SPECTRUM_BARS.md)。旧版长时间演奏后声部未归零的观察仍待排查，不能以下载复位后的正常状态认定修复。

259B修复电脑长按误重触发，波形采用平滑触发/512点有界捕获，取消自动无限HOLD，与FFT结果双缓冲解耦。真机控制消息连续输入时仍60次每秒渲染，音频48k/故障0；BSRAM207/340，DSP不变。[本次证据](ae350/LIVE_WAVEFORM.md)。ABC固定余量差已记录，响度后续单独校准。

2026-09-11 USB引脚已修正为H13/G13，完整工作站93D0已SRAM恢复；布线与音频/AE350/DDR/UI数字运行通过。独立Host识别罗技，纯RTL探针完整读取其84字节配置。Push 2在12Mbps下为2982:9999、9字节配置/0接口，两套Host一致；继续直连需要480Mbps PHY及纯RTL后端，USB MIDI演奏尚未验收。详见[USB Host](usb_host/README.md)、[板测记录](usb_host/HARDWARE.md)，精确版本以`AE350_CURRENT.json`为准。

## 以下为第一阶段基础音频适配器说明（不代表当前完整顶层）

目标：GW5AST-LV138PG484AC2/I1＋NEO Dock 31005。此目录独立引用两套工程，不覆盖原音频接口、G1、Prj1 顶层或历史位流。当前候选只加载SRAM，未写Flash。

```text
G1 31,250 MIDI → 50MHz UART → 字节邮箱
                              ↓
50MHz → 音频PLL 76.8MHz → 原 audio_workstation / 48kHz
                              ↓ 左右Q1.31
                         原PT8211立体声发送器（半BCK=25拍）
                              ↓ 16位右对齐 / BCK=1.536MHz
                         最终串行PCM观察器 → 原子邮箱 → 50MHz
                                                         ↓
                                          队友FFT/波形/结像 → DDR/HDMI
```

采样率保持准确**标称**48kHz：每帧1600个76.8MHz时钟。实际频率继承板载晶振误差；PLL锁定、分数输出分频抖动与模拟音质仍须测量。`RATE_SCALE`仍为4。音频域不等待DDR、显示或录音，失锁复位由音频PLL独立处理。

数值边界：原核心三模式、五种音色、力度/弯音/滑音/颤音与延迟/合唱/混响保持；原控制增益Q1.15、包络Q0.24及内部舍入规则保持。最终左右Q1.31直接交给队友PT8211模块，量化为PCM16时最近舍入、中点远离零并饱和。没有把队友Q1.31控制字当作原Q1.15寄存器，也没有增加固定除32。

第一候选合并原音频核心与队友显示/输出平台。115200自定义32槽控制仍保留在Prj1；该候选只接受独立G1 MIDI输入，不支持Prj1 GUI命令包。DAC没有ADC输入，原外部PCM入口在候选中接零。波形采用最终PCM过零触发/整段匹配，收到MIDI字节时更新重捕获版本；尚未移植ACX720的平滑触发参考。48kHz频率映射与仪表盘文字仅在构建副本中生成，修改补丁与输入哈希一起保存。

`gw138k_audio_adapter`保留录音、原256点FFT及曲谱接口用于验证和后续总线接入；物理显示顶层暂不连接这些接口，所以综合会移除这三个未使用旁路。HDMI使用队友的左右1024点FFT。录音写DDR、LED实体驱动和AE350/UI尚未接入；PicoRV32继续留在ACX720。

复现（任意工作目录）→ 输出必须是新目录：

```bash
python3 /home/sphenicidition/Documents/fpga/migration/gw138k_audio/scripts/run.py
python3 /home/sphenicidition/Documents/fpga/migration/gw138k_audio/scripts/build.py
python3 /home/sphenicidition/Documents/fpga/migration/gw138k_audio/scripts/check_audio_build.py \
  /完整路径/构建结果/Prj1 --output /完整路径/新的音频路由审核.json
```

`build.py`先生成完整冻结副本，再综合、布局布线并执行原DDR/视频检查器及新增音频PLL/邮箱审核；最后一条命令可单独复核既有输出。构建输出中的文件名仍为`Prj1.fs`，须通过**完整目录和SHA-256**识别，不能与原Prj1位流混用。失败构建、仿真及历史日志保留。

接线候选：G1 F12 → **P16／J9第7脚**，GND → J9第3或4脚。P16同时连到J14第6脚，连接G1前确认两处没有其他驱动；Bank4为3.3V，TP22可测。J9第1/2脚是电源。V14已接BL616，不能并接。当前同一块C版板身份已由用户确认，SRAM加载使用指定哈希的候选；换板或新增外设接线时重新核对对应实物。资料与AE350后续接口见[硬件核对笔记](../HARDWARE_ADAPTATION_NOTES.md)。

仿真、构建和真机结果分别记录；最终状态见[迁移总记录](../MIGRATION_PROGRESS.md)。
