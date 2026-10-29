# B7 双时钟 I2S 探针：数字诊断通过，完整 Verify 失败

2026-10-30，本轮用户授权下执行 SRAM 探针、只读 GAO 采集和配置读回。探针为 `custom138k-muted-audio-probe-C11030B7`，始终输出零 PCM，物理 SMUTE 固定为高。两次数字采集均满足检查条件，但两次厂商 SRAM Program and Verify 均返回 18／`Verify Failed`，**不构成完整硬件验收**。已重载原有 Flash 配置，06:03:47 独立读回 `C11028E5`／`0x00022020`。本轮没有写 Flash。

机器记录：[audio_probe_hardware_diagnostic.json](workstation_task_20261030/audio_probe_hardware_diagnostic.json)。它绑定原始日志、CSV、读回文件、解码器、来源快照和回滚身份；大文件留在忽略的缓存目录，不进入源码提交。[先前离线证据](WORKSTATION_AUDIO_PROBE_PREPARE_20261030.md)保留当时状态，不追改成实板验收。

## 候选与操作

- UserCode：`C11030B7`；器件读回：`GW5AST-138C`／`0x0001081B`。
- FS SHA256：`2e27afccd217074b8278e5a7ab75bde08060d14484d3d1ff191c53dc8819565f`。
- 固定位流：`/Users/sphenicidition/.cache/fpga-audio-probe/20261030-C11030B7/builds/20261030_053313_154092/impl/pnr/ao_0.fs`。
- 不变构建清单：同一候选根目录的 `reports/build_20261030_053313_154092.json`。
- 实板证据目录：`/Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7`。

第一次使用既有 `example/RTL8723DS/program_sram.py --allow-gao`，第二次明确指定 `--location 8257`，均为 operation 4。请求 2.5 MHz，而日志均出现 `Frequency Updated: "15MHz"`；原因没有证据，不能据此认定为信号完整性问题。失败后读回 B7／`0x00022230`，其身份和运行状态不能替代完整 Verify。

`programmer_cli --scan-cables F` 可列出 FT2XX 的两个通道：channel 0／location 8257 是本轮实际 JTAG，8258 是另一个通道。GAO 使用 8258 曾报 `Unknown device error` 且返回 0，说明只看进程返回码不够。两次有效采集均使用 8257；第二次采集前后都独立核对 B7 身份。所有 JTAG 操作串行执行。

## 实际数字观测

| 项目 | 采集 1 | 采集 2 |
|---|---:|---:|
| 有效样本／连续 50 MHz 心跳增量 | 128／127 | 128／127 |
| 已提交 epoch／接受／应用 | 2／2／2 | 2／2／2 |
| 拒绝／事务失败／串行欠载／拒收样本 | 0／0／0／0 | 0／0／0／0 |
| 初始 48 kHz 完整帧 | 2398 | 2398 |
| 44.1 kHz epoch 完整帧 | 2203 | 2203 |
| 最终 48 kHz 完整帧 | 8318461 | 25719088 |
| 原始 48／44.1 参考的 1 ms 窗口边沿 | 12288／16935 | 12288／16935 |
| 保留的 selected 48／44.1 窗口边沿 | 12288／16934 | 12287／16934 |

两次记录都处于 COMPLETE、最终 48 kHz、无 flush、无内部静音的完整帧状态；物理 SMUTE 仍恒高。它们跨越了第二次重新烧录，不能把两次帧数之差当作持续运行时长。44.1 kHz 的保留计数及频率窗口是数字 epoch 运行证据；没有外部示波器／逻辑分析仪的引脚脉宽测量，也没有真实 DSP／模拟出声／无爆音验收。

本机 SDK 的 CSV 同时导出 800-bit packed bus、800 个单独 bit 和尾逗号，且有一个全 X 占位行和循环缓冲接缝。解码器现明确校验这种布局：逐 bit 对照 packed 值，仅允许指定的首行占位，将恰好一次 128 样本旋转恢复为连续时间顺序。两种 CSV 格式及 flush、帧错误、旧 epoch、bit 不一致、非法占位五个负例均通过。B7 的锁定位流输入没有改变。

## 读回比较与未解决项

两次独立 operation 3，分别请求 0.9 MHz 和 15 MHz，均正常结束，所得文件 SHA256 均为 `2b3f1f87a8ef315d1720fea5e345e5b2e205d59d7ababc897ed1cc8d5cac3a71`。各有 21872 行、每行 1513 bit，逐行恰好等于 FS 主矩阵每行的 `[7:1520]` 切片：每次比较 33,092,336 bit，零差异。

这是主配置矩阵的经验对照，**不能替代厂商完整 Verify**。FS 另有 5889 行、每行 496 bit 的 BSRAM 数据，这两次 SRAM Read 未覆盖；厂商验证掩码及失败根因仍未确认。主矩阵两次一致，也不能据此说明全部存储已经校验。

CLI 的 SRAM Read 忽略了所请求输出路径，实际保存到安装目录的 `Programmer/bin/sram_readback.txt`；每次已移入缓存保全，没有将读回产物留在安装目录。

## 回滚与复现边界

operation 1 仅重载既有配置 Flash，不写入 Flash。06:02:45 尚为 `UserCode=0`／`0x00000460`；等待加载完成后，06:03:47 独立 operation 0 确认为原 `C11028E5`／`0x00022020`。不能把前一次 Reprogram 返回 0 当成加载完成。

离线复核：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/decode_workstation_audio_probe.py --self-test
python3 projects/138k/push2_workstation/usb_a/tools/decode_workstation_audio_probe.py /Users/sphenicidition/.cache/gw138k-task-20261030/hardware/audio_probe_b7/diagnostic_capture2_core0_window0.csv
```

再次板测需先独立读取身份、复核固定清单／位流／离线门禁，并保存新的操作记录。当前工作站 profile 没有改选 B7。后续应定位完整 Verify 的失败、补外部数字测量，再接真实音频；AK4493S 的 SMUTE 是数字软静音，零 PCM 与高 SMUTE 不证明 PDN 边沿的模拟静音或无爆音。
