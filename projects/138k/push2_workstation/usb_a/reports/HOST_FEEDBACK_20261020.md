# 138K真实音源状态接入PL基础页（2026-10-20）

本轮按“继续138K上的功能接入”实施。修改138K生产Host的页面生成和对应仿真，25K工程只读。HEAD与本轮fetch后的`origin/main`均为`5a4bd71011fcf1c19a2a996428603d7b41b4d86a`；保留既有未提交功能、时序修改和他人的根目录《工程架构报告.md》。本轮未提交或推送。

## 代码依据与实现

原`gw25k_panel.h`已经从0x10／14／1c／20／24采集并冻结每帧音源快照，但第三行仅显示`MODE A  USB MIDI INPUT`，第四行固定`LIVE MIDI`。实际活动声部数、输出路由、滑音和延音已在原MMIO中回传，却没有进入页面。因此本轮复用这些字段，不添加寄存器、MIDI消息、设备菜单或PL命令。

| 页面字段 | 既有来源 | 实际含义与本轮处理 |
|---|---|---|
| MODE | 0x10[4:3] | 保持显示实际已提交A／B／C；CC89有待提交请求时继续显示当前模式，不提前显示目标模式 |
| ACTIVE | 0x10[15:10] | 新增显示非空闲声部数，包含ADSR释放尾音；不是物理按键数、加法分量数或可闻谱峰计数；MUTED时仍可能非零 |
| OUT | 0x10[6:5] | 新增显示STEREO／LEFT／RIGHT／MUTED，分别对应CC82=0／1／2／3的实际路由 |
| GLIDE | 0x14[17:11] | 新增显示CC5滑音控制量0–127；没有把它换算为毫秒 |
| SUSTAIN | 0x14[3] | 新增显示实际延音状态ON／OFF，沿用CC64原语义 |

已有NOTE／VEL、有效GAIN、五个TONE profile、MOD、BEND IDX、有效FX DCR和MIDI48–63的16个held键格保留。GAIN是CC7×CC11得到的有效音量，BEND IDX是14bit弯音右移6位后的索引，FX DCR是Delay／Chorus／Reverb的实际生效位；这些字段不能替代原始CC7、原始14bit弯音或独立effect_master的完整参数同步。FX DCR也不表示独立D的CC20／21／22。

每帧仍使用开始绘制时捕获的同一份scene，tile和重试共享该帧数据，后续变化在下一帧重画。新增字段已经包含在原dirty比较中，稳定时只发送心跳。本轮没有加入整屏缓存、DDR客户端或新的刷新协议；未声称五次MMIO读取构成新的原子总线事务。首帧等待与音频初始化继续独立。

生产代码只改[`gw25k_panel.h`](../gw25k_panel.h)。测试改[`test_gw25k_panel.c`](../sim/test_gw25k_panel.c)、[`tb_workstation_attach.sv`](../sim/tb_workstation_attach.sv)和[`run_workstation_attach.py`](../sim/run_workstation_attach.py)。生产音频RTL、`firmware.c`入口、MMIO布局、端点和PL会话／序号／重试／心跳机制未改。本轮相对于接手输入的四份补丁在[patches](host_feedback_20261020/patches/gw25k_panel.h.patch)。

## 离线验证

最终汇总为[`passed=true`](host_feedback_20261020/verification.json)。下表均为本轮最终输入运行的结果；原2026-10-18失败记录及2026-10-19已撤回25K边界候选保持原状。

| 验证 | 本轮结果与证据 |
|---|---|
| full83当前整机功能门禁 | 18／18通过，包含TF音频16项、Delay DDR等价与DDR隔离；[verification](host_feedback_20261020/full83/verification.json) |
| 接入、仲裁和演奏链 | 6处默认值边界、满队列背压、初始化PANIC、断开／快重连作废、实际模式提交、Push首操作、TF／现场矢量／演示退出、无首帧仍发声均通过；[日志](host_feedback_20261020/attach/tb_workstation_attach_test.log) |
| 真实音频状态到生产Host | 从真实MMIO桥读取12组状态，交给生产C Host生成页面；确认模式请求尚未提交仍显示原模式，held已清但两声部仍处于包络尾音，四种路由与实际PCM左右非零情况一致，重连恢复C／GLIDE0／SUSTAIN OFF；[原始快照](host_feedback_20261020/attach/audio_feedback.txt)、[Host消费日志](host_feedback_20261020/attach/feedback_host_test.log) |
| 生产PL Host | ASAN／UBSAN通过；64种活动计数编码、4路由、128个滑音值×2延音状态、帧冻结／下一帧更新；13种独立MMIO变化各触发一次整帧，稳定只保活。30帧／7580tiles／260469次MIDI轮询，BUSY／NAK／重复包／11种应答故障及普通generic、Push热插拔通过；[日志](host_feedback_20261020/panel/test.log) |
| 真实25K显示端点只读闭环 | 使用现有`projects/25k/example/MIDI_KEYBOARD/rtl/control/panel_display_endpoint.v`，1019个PL请求、2帧通过；[verification](host_feedback_20261020/panel/verification.json)。这是RTL仿真，没有板间USB或SPI实测 |
| Push引导及25K隔离 | 85条普通事件通过；保留普通generic原能力，明确识别的25K不消费曲谱、不推进判定、不显示谱页、不接收引导MIDI；[日志](host_feedback_20261020/guide/test.log) |
| CNN输入来源边界 | 10项测试通过；[日志](host_feedback_20261020/logs/sources.log) |
| 裸机固件准备 | 交叉编译通过，固件19788bytes，静态RAM25548bytes，栈余量39988bytes；两个ROM副本同哈希；[metadata](host_feedback_20261020/build/usb_firmware_metadata.json) |

渲染产物为[428×142基础页](host_feedback_20261020/panel/renderer.png)，已进行图片检查。它显示主机音源状态，不代表25K本地控件状态或专有效果上下文已经完成。音频RTL取值、CDC与生产Host页面在本轮按“实际捕获→实际消费”联动验证；没有用手写期望值替代12组实际MMIO输入。

## 构建输入与复现

先检查相应脚本`--help`。本轮在`usb_a`下使用`python3 tools/build_current_workstation.py --prepare-only`生成：

```
results/workstation_scope83_20261020_003048_847857
```

策略为`accepted_full83`，从验收清单选择73个CNN文件；活动目录9个修改／11个新增仅记差异，未覆盖入构建。602项暂存输入、73个选中CNN和5项冻结依赖再次核对一致，145项回归记录输入运行后哈希一致。25K的1064项非results文件集合及内容、根目录他人报告、原`GW25K_PANEL.md`、`LATEST_WORKSTATION.json`、25K导入清单均未改变。检查见[scope_checks.json](host_feedback_20261020/scope_checks.json)，构建元数据与输入清单在[build_metadata.json](host_feedback_20261020/build/build_metadata.json)。准备脚本沿用工作区已有改动；本轮未新增时序实验或启动综合／布局布线。

最终各项命令、起止时间和返回值保存在[jobs.json](host_feedback_20261020/jobs.json)。将下列`PREPARE`替换为上述暂存目录，各输出目录独立且放在`results/`：

```sh
python3 sim/test_current_workstation_sources.py
python3 sim/scope_vec/run_current.py PREPARE
python3 sim/run_workstation_attach.py --baseline PREPARE/Prj1 --out results/host_feedback_attach_new
python3 sim/run_pl_guide.py --baseline PREPARE/Prj1 --out results/host_feedback_guide_new
python3 sim/run_gw25k_panel.py --endpoint-rtl ../../../25k/example/MIDI_KEYBOARD/rtl/control/panel_display_endpoint.v --output results/host_feedback_panel_new
```

原始产物位于`results/host_feedback_20261020_002153_999689/final/`；可跟踪证据目录只保存JSON、日志、快照、图片和补丁，未放入可执行文件、Verilator对象或预编译头。2026-10-19的32音串行FFT、完整独立采样器和完整25K设备回归本轮未重跑，不将其计作本轮新结果。

## 仍待接入及验收

已落实的是138K音源实际状态到既有PL基础页的反馈。25K本地音量／音色完整双向同步、移调后物理键位显示和专有页面仍未完成；目前不能从有效GAIN恢复原始CC7，也不能从BEND IDX恢复全部14bit弯音。25K上一轮撤回的连接／排队三处问题仍是建议项，主机没有补造设备漏发消息。

已确认的EP-133式“4×4演奏／效果组合”方向保持；效果上下文进入／退出、16键分配、按住或锁定规则、作用音频路径仍待产品决定。D整机模式／DDR／UI／切入清零留后续批次，本轮未接入。D与TF PCM路径按用户补充口径保留。Push专有CNN扒谱与谱面引导分工保持。

未板测、未烧录、未修改硬件或引脚、未运行新的综合／P&R或时序实验。传感器到模拟输出延迟、实际串行音频格式及现场多频验证仍待验收；时序未闭合。
