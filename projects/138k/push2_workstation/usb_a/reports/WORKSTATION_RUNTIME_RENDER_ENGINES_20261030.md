# 原生 render engines 组合与显式 48 kHz 接入（2026-10-30）

本阶段完成 `workstation_runtime_render_engines`：原生 pitch／oscillator／vector 共享唯一 committed rate，在真正排空后原子接受 48／44.1 kHz。它只交付 effects 之前的真实 engine PCM。event/service 增加默认关闭的 `RUNTIME_RATE_ENABLE`，显式启用时复用该组合并用真实 quiescent 替换 legacy 取消尾窗。默认分支继续使用旧源及 40 时钟尾窗，默认 48 kHz 输出逐拍保持一致。

完整 effects 尚未双率适配，因此 event 对 44.1 的 `rate_ready_o` 恒低，service 继续显式返回零／error、不发 sample-ce。没有把 standalone 两率引擎误当作完整两率工作站，没有新增公共参数副本、自由运行采样 tick、源选择器或最后一级 CC7。

## 源、配置与回退

- 前一阶段为 `fc37f27`（独立请求驱动 48 kHz render service）。本阶段不修改 profile、top、locks、冻结 baseline 或 vendor 来源，不生成或部署 bitstream。
- 新组合 SHA-256：`f3cf2a42c49838e0d44e5a00c27b50ceab1d18724ccf0be7d7bc680a98f15931`。
- event SHA-256：`db400b9903b8d805858c0aa89f8712fb78afb81395ed3b5c023baaa1981e19e3`。
- service SHA-256：`59c3c66a5b8b59a4fa8e1fcf669bba28bb13d11ca8abf4dbc918a240120a1f35`。
- 参考为实际 F03 revision3 prepared `custom138k-workstation-v1-d23d498ea824c9f9` 的旧引擎／控制／ROM；只在测试输出目录给参考 event 唯一模块名换名。新组合不从历史私有目录生成代码。
- 回退是保持参数默认 0；必要时回到前一阶段源码 `fc37f27`。已接受整机 profile 与板上状态没有改变。

完整已消费输入、配置、命令、SHA-256、缓存日志和结果见 [runtime_render_engines.json](workstation_task_20261030/runtime_render_engines.json)。接口合同和后续退出条件见 [RUNTIME_RENDER_ENGINES.md](../rtl/audio/RUNTIME_RENDER_ENGINES.md)。

## 已通过的离线验证

| 范围 | 实际结果 |
|---|---|
| 三引擎原生组合 vs 实际 prepared 48 kHz | 181950 个计算时钟、390 帧逐拍相等；A/B/C 各 32 声部，加 8 个 held vector 音符；五音色、glide／vibrato／pressure／release |
| 独立组合两率与切换 | 3718 帧，50 次原子提交；提交前后检查全部 1024 partial、32 envelope 和 8 vector 的 phase／envelope 及 pitch 控制状态未被重置 |
| 碰撞、背压与真排空 | 1327 次忙／事件／sample／loader 碰撞拒绝，48 个 PANIC 偏移；检查真实 sine／quantizer 内部 valid，quiet 后再等待 24 时钟无旧输出 |
| 保持按键的真实 vector PCM | 48→44.1→48 kHz 各 1024 点；拟合 439.999983451／440.000177306／439.999898832 Hz；44.1 的 synth 也有 1024 个非零有效结果 |
| 默认 event/service，不加入 native engine 源 | 16 相位回归，8650 requests = 8650 responses，最大 1183 时钟；默认事件与 untouched prepared event 全运行逐拍相等 |
| 显式 native event/service，全部 1600 取消相位 | 59360 requests = 59360 responses；6400 CC120、6400 lifecycle、205 load-cancel；最大 1183 时钟；每请求至多一个响应，无旧结果串帧 |
| 原效果链的实际非零 wet/feedback | 960 正常组合，4096 warm 帧，六种顺序、三条 wet 路径和 FDN 均非零；7395 memory-side wet returns；4096 控制事件压力 |
| 来源与编译 | 三个最终运行的全部输入 hash 运行后再次复核；`test_current_workstation_sources.py` 10/10；Python syntax 和 `git diff --check` 通过；两类 service 编译均 `UNOPTFLAT=0` |

正常完整链 A/B/C/vector 分别为 222／249／1145／1145 计算时钟。native 服务完整运行中仍观察到最长 33 时钟自然取消尾部，但 admission 根据实际流水 quiescent 判断，不依赖这个观察上限。31174 个取消零响应和 25621 个已响应后的旧结果排空是显式隔离行为。

组合模块与 service 没有新增实现警告；event 的既有 cue-speed 宽度警告和 oscillator 的既有 unsigned 优先逻辑警告保留，机器证据保留全量 warning counts，未宣称整项目无警告。

legacy 实例进入 `legacy_engines` generate 命名空间后，同步了当前 contest／scope TB 的两个只读内部探针路径；使用实际 prepared 依赖完成 lint/elaboration，仅此不宣称重跑了它们全部业务用例。历史 p22 等按其旧 prepared 树运行的探针和证据没有改写。

## 重放

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_engines.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output <不存在的新目录>
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_render_service.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output <另一个不存在的新目录> --phases 1600 --runtime-engines
```

默认来源隔离的重放去掉 `--runtime-engines`，本次额外默认回归为 `--phases 16`；上一阶段的默认 full1600 原始证据保留在其日期报告中。

## 仍未完成

这一步是功能接入，未满足 12 μs 指标：在 76.8 MHz 下，独立组合最大 1039 时钟约 13.53 μs，完整链最大 1183 时钟约 15.40 μs。1600 时钟名义帧距仍有 417 时钟余量，但尚未包括跨域桥和最终输出成本，也不是 routed timing 证据。

完整 effects 的两率系数／history 清理、原子配置／故障处理仍需单独接入，之后才可开放 event 的 44.1 请求。测试的 echo ring 明确为 32 帧，生产默认 9600 不变；memory-side ordered FIFO/history/flush 模型没有证明物理 DDR fence 延迟或带宽。源选择、最终 CC7／PCM16／I2S、CDC／PLL／资源／P&R，以及硬件接受、SRAM／Flash 部署都没有由本阶段离线结果推导。
