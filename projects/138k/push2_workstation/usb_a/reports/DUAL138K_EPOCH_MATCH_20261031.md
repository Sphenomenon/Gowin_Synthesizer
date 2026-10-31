# 双138K：M8取消epoch控制路径收敛

日期：2026-10-31。修改基于 `2e273da8f05ecd9e17ce1e8dc4ca1b60a347a39a`。
本阶段为维护RTL及离线功能验证，尚未对改后源码运行整机综合、P&R或板测。

## 实际路由后因果

M8实际完整P&R的 `m-demo-base-v8-physical-v1/impl/pnr/custom_138k_integration.tr`
Path2由 `service/workstation/panic_epoch_o_1_s0` 到混响
`reverb_stage/g_fdn[0].ram/g_bank[2].ram/ram/CEA`，setup −1.717 ns，15级逻辑。
cell delay 3.492 ns、route delay 10.875 ns（74.116%）。网表确认首段ALU链是
10 bit `panic_epoch_o != request_cancel_epoch`，随后经过 service 自动切率许可、
`runtime_configuration.config_accept` 和全局效果清理，终达RAM写使能。
相邻Path3有相同取消前缀、542／407／198扇出，route 11.360 ns。

本修改只把这一精确相等关系寄存，不改效果RAM策略或音频采样调度。
event→expression CE是另一路：7 bit音高比较之后的最低声部优先归约；它不经过本取消前缀，留待后续实际STA定位。

## 实现及等价关系

`gw138k_event_workstation.sv`新增内部只读 `panic_accept_o`，直接投影已有真实
`panic_accept`；唯一10 bit epoch计数器及其原有写入仍由event workstation拥有。
未扩展外部18 bit事件，也未引入第二个取消计数器。

`workstation_audio_render_service.sv`保存一位 `request_epoch_match`。每个稳定时刻
它精确等于旧公式 `panic_epoch_o == request_cancel_epoch`：

| 边沿输入 | 原epoch／snapshot下一个值 | match下一个值 |
|---|---|---|
| reset | 0／0 | 1 |
| accepted，无PANIC | epoch／epoch | 1 |
| accepted且PANIC | epoch+1（10 bit）／epoch | 0 |
| 仅PANIC | epoch+1（10 bit）／原snapshot | next epoch == snapshot |
| 其余 | 均保持 | 保持 |

取消判定替换为 `!request_epoch_match` 加原有intentional-mute子句。
比较只进入match寄存器的D锥，不再直接进入自动切率／效果清理许可。
这保留1023→0回绕及1024次取消后重新相等的旧语义；sticky cancel不能替代它。
请求接受、PCM返回和已受理配置的提交没有新增时钟延迟。

两维护源码原本由原生composition/runtime profile直接复制并记录哈希；不存在需要
改写的冻结provenance尾。原DSP算术、reverb、chorus及delay provenance均未动。

| 维护源码 | 修改前SHA256 | 修改后SHA256 |
|---|---|---|
| `rtl/audio/gw138k_event_workstation.sv` | `d238ed4147ae6167ebc7e6adf803891816f5a2bc5dda0498b1a533a9179ea213` | `1357ed198223734c10fafe7bbf0155d784ee35050db742c65df36c0526820706` |
| `rtl/audio/workstation_audio_render_service.sv` | `a9b8138e8b40a85a98ab1b3ed769c99ff9ee342a2cd168cb40877bb2383cc979` | `4ed2b2bb66581071647cb632778b96a33f75a0630aaea6224d1b0aa3faded974` |

## 验证

完整真实service回归使用M8准备工程的锁定支持源码和当前维护音频源码：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_service.py \
  --project /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v8/workstation/Prj1 \
  --output /tmp/dual138k-epoch-match-runtime-service-v1
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_epoch_match_equivalence.py \
  --runtime-verification /tmp/dual138k-epoch-match-runtime-service-v1/verification.json \
  --output /tmp/dual138k-epoch-match-next-state-v3
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

结果：

- 全service 48,655请求／48,655响应，48,645帧与独立定点wet PCM模型一致（48 kHz 24,323帧、44.1 kHz 24,322帧）。原A/B/C 32声部、矢量、六效果顺序×八mask、配置／history、PANIC、迟到结果、ordered DDR fence、故障及共同复位场景继续通过。
- 真实时钟前／后合计115,902,546次旧epoch公式与新match、真实计数器／snapshot next-state检查；1,038真实epoch推进、1次1023→0、1组1024次真实USB lifecycle后恢复同epoch、1次真实accepted与lifecycle同拍。intentional mute与新取消仍保持区别。
- 实际矢量2058 dispatch周期、10次接受事件、2种释放／取消交叠继续通过；无UNOPTFLAT。
- 穷举直接编译从维护RTL抽取的原样reset／update语句，以独立旧counter／snapshot作为oracle：全部1024×1024×4组合加3个边界，4,194,307 trials通过。
- 三种投影负控均被旧公式拒绝：忽略accepted+PANIC、sticky cancel、扩大位宽丢失modulo wrap。
- 另从完整service通过记录核对每一输入哈希，复用实际引擎、DDR和逐拍oracle，只插入一个真实accepted+USB lifecycle边沿：正对照通过；将实际service的accepted更新错改为常真后，于第一个post-edge被旧next-state公式拒绝。无需跑完PCM主段才检出。
- accepted来源边界17项通过；直接调用原生USB2 audio bundle核对event当前SHA256，并核对runtime profile选择维护service。`git diff --check`通过。两次运行均记录输入未漂移，最终负控链额外复核完整参考闭包共59个输入哈希。

归档证据为 [runtime_service.json](dual138k_epoch_match_20261031/runtime_service.json)、
[next_state_and_negative.json](dual138k_epoch_match_20261031/next_state_and_negative.json)，
以及真实service负控最早失败文本。

## 本阶段范围及回退

未启动新候选，未写SRAM或Flash。改后资源、物理扇出及setup／hold收益尚未知，
必须由新身份整机综合和完整路由后门禁判定，不能把局部功能等价当作时序闭合。
原M8位流身份及全部原物理证据保持不变。

回退仅需将上述两维护源码恢复到本阶段父提交，并回退本阶段测试／报告；
不修改冻结baseline、原manifest、历史候选或主检出目录的任何未提交工作。
