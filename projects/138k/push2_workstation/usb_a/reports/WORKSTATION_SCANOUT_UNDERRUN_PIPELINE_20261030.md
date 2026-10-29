# 扫描欠载诊断事件流水，2026-10-30

F3 的 HDMI `v_counter` 到扫描 `under_count` 使能路径有 −0.944 ns setup。维护的 `video_ddr_scanout.v` 增加默认关闭的 `REGISTER_UNDERRUN_EVENT`：显式开启时，把完整的行首欠载事件先寄存，再驱动 32 位计数器；行数据选择、tag/epoch、取行、RGB 与同步输出不等待该诊断。计数及后续 Gray/CDC 发布因此多一个 pixel clock 延迟，累计数量不变。参数放在既有参数列表末尾，保留位置参数顺序。

这只是明确候选可选择的源码修复。当前 top、profile、锁定来源与所有既有物理候选均未改选；F3/F5 的旧 revision 2 网表不包含它。本阶段未运行综合、P&R、SRAM 或 Flash，也不宣称 −0.944 ns 已由实物理结果关闭。

## 验证

扩展既有 `sim/display/run_scanout.py`，默认仍读 prepared source；只有 `--scanout-source` 才显式覆盖，且 `--register-underrun-event` 需要该覆盖。原 frame-publication 路径保持独立。runner 记录完整输入哈希，结束后拒绝输入漂移。

复用真实 1920 像素行宽、148.5 MHz pixel / 100 MHz memory 的 TB，逐像素核对 RGB、同步延迟、完整行一致性、frame swap 和晚响应恢复。新增断言从实际 RGB 输出统计黑行，待诊断 CDC 稳定后与公开欠载计数比较，不读取 DUT 的事件谓词作为答案。

四组各三用例全部通过：prepared 原来源、维护源码默认 0、维护源码显式 1，以及显式 1 接真实 native queues/arbiter 和背景写。前三组的全部输出指标一致；带背景流量时像素/黑行/计数指标也一致。

| 用例（每组） | 对照像素 | 彩色行 | 黑行 / 欠载 |
|---|---:|---:|---:|
| 稳定帧及双 bank 切换 | 61,440 | 32 | 0 / 0 |
| 晚行恢复 | 61,440 | 29 | 3 / 3 |
| 旧 epoch 晚响应恢复 | 76,800 | 33 | 7 / 7 |

native queues 三例各实际接受 103,030、103,134、129,102 次背景写。12 例共逐像素检查 798,720 次，各阶段开始/结束输入及日志哈希均已复核。完整命令、输入和结果见 [scanout_underrun_pipeline.json](workstation_task_20261030/scanout_underrun_pipeline.json)。这不替代真实 DDR 电气、整机竞争期限或路由时序验证。

复现时 `--output` 必须是新目录：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_scanout.py \
  --project <prepared Prj1> --output <new-output> \
  --scanout-source projects/138k/push2_workstation/usb_a/rtl/display_data/video_ddr_scanout.v \
  --register-underrun-event --native-queues
```

回退只需撤回本阶段源码/runner/TB；尚无部署需要回退。下一显式整机源码候选应选择此参数，重新测真实关键路径和全局门禁。
