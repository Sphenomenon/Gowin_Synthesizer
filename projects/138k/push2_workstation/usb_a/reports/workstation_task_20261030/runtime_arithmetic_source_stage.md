# 2026-10-30：运行时音频算术流水线源码阶段

产品提交：`a80a72a`。本阶段实现并验证 oscillator DDS、oscillator ADSR 与 vector 的精确寄存流水线，修复运行时音符的上层接受握手；未做综合、布局布线、SRAM／Flash 或硬件操作。机器证据与逐文件 SHA256 见 [runtime_arithmetic_source_stage.json](runtime_arithmetic_source_stage.json)。后续整机源锁、候选身份和物理门禁由主任务独立处理。

## 触发依据与修改范围

冻结 FC 候选 `custom138k-workstation-no-cnn-v1-525ffff10d622031` 的真实 76.8 MHz 路径中，oscillator pitch 为 122 logic levels／129.728 ns／slack −116.645 ns，vector pitch 为 115 levels／119.233 ns／−106.464 ns，envelope 为 115 levels／96.685 ns／−83.682 ns。原时序报告 SHA256：`b067e49508035940b66fa6ab610dfa844611fdec061841c3be5c548126bf3e82`。这些是触发问题的旧候选证据，不是新实现的物理结果。

- 新 `workstation_runtime_div147.sv` 用 radix-4 精确除 147，每级两位商并在真实寄存器处结束；42-bit 为 seed 加 18 个商级，32-bit 为 seed 加 13 个商级。数据、tag、valid、空泡和 flush 都有独立 oracle。
- oscillator 把 product、乘 160、加偏置／右移、商、phase 写回与 sine launch 分开。161-bit tag 绑定 slot、旧 phase、rate、gain、envelope、last；ADSR 三条 32-bit 除法 lane 绑定原声部状态。
- vector 的 phase 与 NoteOn 系数使用同一精确 divider，并由各自 FSM 等待有身份的返回。保留 oscillator 舍入、vector 截断及各自不同的饱和值。
- runtime composition 显式选择新 `PIPELINED_RATE`／`PIPELINED_ENVELOPE`；独立模块参数仍默认 0。数值上界、舍入等价证明、取消与时限说明见[算术契约](../../rtl/audio/RUNTIME_ARITHMETIC_PIPELINE_CONTRACT.md)。
- 新 helper 仅加入既有 runtime 源清单及相关仿真编译清单。三个 profile lock 未在此工作树修改；没有改变 frozen baseline、vendor、时钟、约束或例外。

## 音符接受与取消

首次真实 I2S 回归发现 `TIMING_OPTIMIZED` 原旁路会在新增算术尾部未排空时确认 NoteOn：公共 held60 变为 1，引擎拒收，192 帧后 active／nonzero 仍为 0。运行时分支现在等待实际 engine ready；旧 `RUNTIME_RATE_ENABLE=0` 分支保留原旁路。

直接读取 engine ready 的中间修复曾暴露 PANIC→配置→sample-ce→event-ready 的组合环；其日志保留。最终 CC120 接受条件按原 control-event 分支精确展开为 `event_valid && !releasing && dispatch && kind==2 && a==120`，另保留无条件 USB lifecycle。独立穷举 327680 组分支组合确认与原 CC120 接受语义等价；最终完整编译没有 `UNOPTFLAT`。PANIC 清理全部新增 valid，原 sine ROM 自然尾部继续计入 quiescent，live token 阻止已取消结果重新进入 accumulator。

维护入口 `run_runtime_audio.py --negative-legacy-note-admission` 仅在 cache 修改一处旁路，要求能够编译、没有组合环，并准确命中 `startup real voice is silent`。该负控已检出上述 held／active 不一致；固定版 startup 和完整 I2S 均通过。

## 验证结果与身份

| 验证 | 结果及边界 |
|---|---|
| 最终源码 portable regression | 无 `--reference-project`，从版本化基线和精确 provenance 重建旧 oracle；helper WIDTH42／32／43／25 共 26661 个返回，每宽度 52 次 flush；4 个 helper 故障注入全部编译后被检出 |
| 最终 oscillator 独立比对 | 672 帧、606 非零、688128 slot 比对、34 次 PANIC；五音色、A/B/C、32 声部、双率，PCM／phase／ADSR／重用一致；slot／gain 两个故障注入被检出 |
| 最终 vector 独立比对 | 664 帧、524 非零、6368 voice-state、19104 coefficient 比对、40 次 PANIC；phase／coefficient 两个故障注入被检出 |
| 最终 default0 vector resource 回归 | 严格零警告 lint、完整反向 provenance、default／stress ADSR 双率逐拍比较通过；保留其原资源优化 oracle |
| 旧默认兼容 | oscillator 4 项、ADSR 3 项通过；旧 vector 1 项通过；accepted input-boundary 10 项通过 |
| render composition | 3718 帧、780 个 48 kHz 有序完成输出、50 次切率、48 次 PANIC；由逐拍完成改为有序 PCM／排空状态／帧 ledger 比对，默认独立 oscillator 仍逐拍比较 |
| 完整 render service | 48652 请求／响应、48644 modeled frames、16 configs、25 histories、4 cancels；独立 effects PCM 每率 24322 帧，49780416 pitch checks |
| **最终准确源码完整 I2S** | **20192 帧、20061 非零、8 次帧中切率、768 pressure、26 NoteOff；双率 wet=7、FDN=3；max render=1204、max serial slot=1229；无组合环、新 composition／fixture 警告 0、输入前后哈希不变** |
| production startup／负控 | 1028 startup frames／生产参考时钟配置，211 个物理帧、127 非零、0 error、切率通过；旧旁路负控准确检出失声 |

helper 最终 SHA256 为 `cd45ffd4eb301966956d0acbe233703693ec25e95368679ef0d9ffeb36d17bdc`，oscillator 为 `f78307b44c346a52cc53334b20d3f507684511097c242d9cf1d8aeec866cb2cc`，vector 为 `b856010542da0ad3e946cbf3e3ead6e3cb974c76deb273140451155302b4ca97`，event owner 为 `292a2fb8b790aa05607d7e9fd03cc12cf0170ad4c2ab0ebd5bd9b310ed1b39ef`。

最后一次 vector 改动仅把 phase-invalid 组合表达式移入选中的 generate 分支，未选分支置 0，消除 default0 对常量零作无符号比较的严格 lint 警告。最终 b856 身份已重跑 portable、default0 resource 和完整 I2S。较早 composition／service／production startup／负控及独立九消费者故障注入使用 6cee 身份；机器报告明确区分，未把旧运行身份改写为最终运行。独立审查另对最终 vector 再比对冻结 FC oracle。

两个采样率下 A/B/C 32 声部的最大 engine 延迟均为 69／165／1061 clocks，vector 为 284。48 kHz 帧间隔 1600 clocks，最终串行槽最大 1229；service steady／loader 最大 1168／1204。首次自动 44.1 kHz 配置加渲染为 1620，按该率最短 1741 clocks 检查，不能声称所有配置渲染都小于 1600。完整 I2S 的 6 个 error 帧来自预期 TF mismatch 故障注入；时钟停止、超时和 sticky DSP fault 都按各自场景验收。

## 后续门禁与回退

维护回归入口可以从仓库独立运行，cache 只保存本轮证据，不是生产输入。主任务需刷新三份 runtime profile source lock、以新来源生成候选身份，并做新综合、P&R、setup／hold／recovery／removal、CDC、PLL 与资源检查。任何 RTL 仿真或工具 exit code 都不代表板上验收。后续如获准下载，须另记位流身份、SRAM 读回和实际音频／外围验收；本阶段没有修改当前板卡。

产品更改可通过撤销 `a80a72a` 回退到 `a620707` 的原 runtime 算术与接受策略；报告保留。原 FC 物理时序缺陷随原实现恢复，不能把回退视为时序通过。原 accepted／pinned profile 的冻结来源、历史证据和既有 Flash 留存不在此提交内。
