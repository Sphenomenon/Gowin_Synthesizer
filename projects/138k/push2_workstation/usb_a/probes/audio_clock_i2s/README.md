# 独立、静音的双音频时钟／I2S 数字探针

此实验直接消费版本化的 `rtl/audio/` domain／monitor／switch／serializer 和 `rtl/probe/workstation_audio_probe_top.sv`。它不属于完整工作站 profile，不修改 `build.py`、历史 AK4493／测频例程、冻结输入或已接受部署。配置权威为 `probe.json`；生成目录仅保存其逐字节快照和明确配置，不成为第二份源码权威。

外部 `ak_smute` 始终为 1，PCM 始终为零。本阶段验证数字时钟、完整帧事务和观测链，不验收 DAC 的 384fs 锁定、模拟输出或听音。只约束已有 V22／K18／J19／V13 和核对过的 PDN／MCLK／BCK／LRCK／SDATA／SMUTE 引脚；不驱动 sslow／sd／slow，不接入 USB、DDR、HDMI 或 CPU。

## 准备与来源校验

从仓库根目录执行；`<new-output>` 必须尚不存在，`<new-code>` 必须为新分配的八位十六进制 UserCode。仓库内输出只允许 `usb_a/out/` 或 `usb_a/results/`；推荐使用个人缓存目录。

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_audio_probe.py prepare-only --output <new-output> --user-code <new-code>
python3 projects/138k/push2_workstation/usb_a/tools/workstation_audio_probe.py verify --output <new-output>
PATH=/opt/homebrew/bin:$PATH python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_audio_probe.py
```

prepare／verify 不调用 EDA、不扫描 JTAG、不访问板卡。`inputs.json` 记录五份 RTL、配置、SDC、检查要求、准备工具、未修改 Mac builder、引脚证据和全部生成输入的 SHA256。准备输入变化、暂存内容变化、意外 RTL、UserCode／输出目录复用都拒绝；没有私有路径回退。

默认保留生产 monitor 的 1 ms 窗、连续 4 窗、500 周期失钟，serializer 的 PDN=4／startup=1028 和事务每阶段 40 ms。50 MHz POR 在 1024 周期后以寄存信号释放；domain 继续执行各自的三边沿释放。探针顺序为启动 48k epoch0→hold 50 ms→44.1k epoch1→hold 50 ms→48k epoch2→hold 50 ms→COMPLETE，最终继续 48k。任何 fault／reject／failed 锁存 ERROR，无自动重试；外部 restart 可重新实验。这是实验状态机，不定义产品切换入口或忙时策略。

测试可覆盖短 monitor／hold／startup 参数，快速核对实际 top 的序列、I2S 分频、零 PCM、SMUTE 和跨域快照；默认 1028 帧启动的真实预算另见 `reports/WORKSTATION_I2S_TRANSPORT_20261030.md`。

## GAO 和跨域观测

Standard、post-synthesis GAO、50 MHz 采样、128 点；单个 `audio_probe_debug[799:0]` 的 25 个 32-bit 字均已在 50 MHz 寄存。完整字段和状态位见 `probe.json`，低字为 `0x41504231` 签名。

原始两路和选中测频结果本来就在 50 MHz。quiet／prefill／running 为两级单 bit 同步。完整帧数／最后 sequence／epoch／错误计数由 selected-MCLK 域原子寄存为 192-bit 保持数据，再 ACK；50 MHz 两级同步 payload 和 ACK，看到 ACK 后才取稳定数据，前一条完成前不发下一请求。flush 清除两端并使观测失效；解码必须同时要求 snapshot_valid=1 且 flush=0。GAO 没有接入裸音频域宽总线。

50 MHz 另保留三个 epoch 各自从原子快照收到的完整帧数，以及 48k／44.1k 两种 selected 窗口计数。主机稍后只采 COMPLETE 窗口，也能核对两种模式确实完成了输出，不依赖主机正好在 44.1k 的 50 ms 内触发采集。此实验的零 PCM 响应只有一个 selected-MCLK 寄存延迟；它没有实现或证明计算域 DSP 桥。

## EDA 与物理门禁

本机 SUG940-2.0.1E 的 SHA256 由配置锁定。PDF 66–69 明确支持 `create_generated_clock -master_clock/-add`；PDF 73–74 的互斥语法为 `set_clock_groups -exclusive`。SDC 在同一个真实 DCS CLKOUT 上创建 selected48／selected44 两个时钟，并分别指定 raw48／raw44；只互斥这两个 selected 时钟。未核实 SDK 手册时仍可生成有 blocker 的准备材料，build 必须在 EDA 启动前拒绝，没有 falsepath 整个音频域的回退。

`audio_probe.sdc` 对三组 Gray 源寄存器→首级、单 bit 首级、保持 payload 首级及仅首边沿采样的配置给出 20 ns 限制和逐对象 hold 例外；第二级保留检查。没有对内部 reset 作整体例外。精确对象解析、所有存活位的 arrival／skew、DCS 专用路由、两种来源的 setup／hold／recovery／removal／pulse-width 和 reset 释放检查要求在 `physical_checks.json`。

仅在现有 EDA 工作结束后，才另行执行：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_audio_probe.py build --output <prepared-output>
```

该入口原样复用 `example/RTL8723DS/tools/gowin_build.py` 的 ASCII 暂存、进程锁、独立 syn／P&R、GAO CRC 和 setup／hold 门禁。它不具备编程操作；helper exit0 只表示该 helper 范围完成，`probe_build_result.json` 的 accepted_for_sram 仍为 false，须补齐全部物理检查。如果 SDK 报告不支持语法、约束对象零匹配或丢掉第二个 master，候选必须停下修正，不能隐藏时钟／CDC／reset 违规。

prepare-only 不执行 EDA／硬件；实际独立 EDA 结果见 `reports/WORKSTATION_AUDIO_PROBE_PREPARE_20261030.md`。本机 GAO 还自动生成 `tck_pad_i` 20MHz 时钟，实际清单须包含五个显式时钟及该诊断时钟，不能只核对五个名字就声称清单闭合。后续独立板测须记录新位流 SHA256／UserCode、写前身份、SRAM Program+Verify、写后及采集前后身份、原始 CSV 和回退；当前 E5 及其 Flash 重载证据应单独核验，不能照搬 10-24 测频报告中的旧音频回退身份。Flash 不属于此工具范围。

真实路由量化入口为 `tools/check_workstation_audio_probe.py --output <prepared-output> --json <audit-json> --self-test`；它解析实际 VO／SDF／STA及逐对象约束，检查全部存活位、复位链、DCS及负向突变。`physical_checks.json` 保持要求清单，不替代量化结果。最终 B7 及 B0～B7 的不可变来源记录见 `reports/workstation_task_20261030/audio_probe_offline.json`；原 `audio_probe_prepare.json` 只绑定历史B0，不能用当前工具验证或重绑。

CSV离线入口为 `tools/decode_workstation_audio_probe.py <capture_core0_window0.csv> --json <decoded-json>`。它要求128点、APB1签名、连续50MHz heartbeat、COMPLETE／epoch2／两次accepted和applied、全部三代次完整帧、正确原子快照和两率测频；拒绝flush、错误和旧代次。`--self-test`验证三个拒收分支。它本身不会访问硬件。完整SRAM、身份确认、GAO和E5重载命令见上述离线检查点报告。

SMUTE为数字软静音，零PCM和SMUTE高不能保证PDN边沿无click／模拟无声；本实验没有外部模拟mute、strap／384fs识别或电气验收结论。

## 实验退出标准

完整工作站完成输出时基请求／返回桥、双率 DSP、最终 PCM／tap、路由时序／CDC／reset 及实体声画验收后，此探针退出任何集成输入角色。保留其证据和有用回归；不得悄悄变成新的生产 profile 或唯一构建来源。
