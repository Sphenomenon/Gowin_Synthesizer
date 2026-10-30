# 原生双率 render engines 组合

`workstation_runtime_render_engines.sv` 只组合既有 native pitch、oscillator 和 vector。其输出是合成单声道与矢量立体声 engine PCM，不含 effects、外部 PCM 混音、音源选择、最终 CC7、PCM16 或串行输出。没有自由运行 sample tick、第二份公共参数或工作站业务状态；音符／表达／mode 的原握手直接进入原 owner。

运行时分支显式选择精确常数除法的寄存流水线；数值证明、tag、取消、事件握手与延迟预算见[运行时算术流水线契约](RUNTIME_ARITHMETIC_PIPELINE_CONTRACT.md)。独立模块默认参数保留旧周期行为，运行时组合按有序完成事务及排空后的状态比较。

## 采样率提交和排空

- `RUNTIME_RATE_ENABLE=1` 显式启用两率；默认 0 固定 48 kHz。`rate_44100_i=0/1` 分别表示 48／44.1 kHz。
- `rate_commit_i && rate_ready_o` 在上升沿接受一次提交。忙时的单拍请求不生效；若必须完成，调用者保持请求和值直到 ready。仅 oscillator 保存 committed rate，`applied_rate_44100_o` 直接连接其输出，pitch／vector 同用这个值。
- `quiescent_o` 是存储流水状态的只读组合：oscillator 的 loader、ROM／mix／quantizer、envelope 更新全部排空，vector FSM 空闲且无 valid。它不引用本拍 sample/event，适合外层请求槽的排空检查。`rate_ready_o` 另要求本拍无 sample、事件、expression、mode 或 PANIC，从而避免提交和新工作碰撞。
- PANIC 保持既有音符清除语义，不清 committed rate、控制 LFO 或公共参数。自然 ROM 尾部仍然流尽；必须等待真实 quiescent，不能把公开 busy 清零当作完成。
- 提交不清 oscillator partial phase、envelope、表达值或 vector phase／envelope，不重触发 held 音符。三个引擎在接受 frame 时使用同一已提交值；不允许在流水中途切换。

调用者仍负责完整帧的请求／返回及 epoch／sequence，等待桥和 effects/history 的独立契约后才允许跨域切率。此组件没有将 rate metadata 塞入现有 18 位事件，也没有引入 DMA history 协议。

## 工作站接入范围

`gw138k_event_workstation` 和 `workstation_audio_render_service` 的 `RUNTIME_RATE_ENABLE=0` 默认仍选旧源，旧实例仅移到 `legacy_engines` generate 命名空间。显式设为 1 后复用此组合，而不复制工作站；取消后的 admission 使用实际 engine drain。

仅启用 engine 参数时，完整工作站中的旧 effects 仍按 48 kHz 处理，event 背压 44.1，service 返回显式零／error。完整两率需额外显式启用 `RUNTIME_EFFECTS_ENABLE=1`，由 event 同时提交 native engines 与 native effects/history，在全部确认后更新公共 applied rate。详细事务、失败和排空合同见 [AUDIO_RENDER_SERVICE.md](AUDIO_RENDER_SERVICE.md)。

完整 service 的独立回归不构成 profile、clock、bridge、最终输出、CDC／PLL／timing／资源或硬件接受。显式选源仍需新 profile 身份与对应验证；不改变冻结来源。
## 校验

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_engines.py \
  --project <实际 prepared Prj1> --output <不存在的新目录>
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_render_service.py \
  --project <实际 prepared Prj1> --output <不存在的新目录> --runtime-engines
```

第一项把组合的有序完成 PCM 和排空后的状态对照实际 prepared 三个旧引擎，覆盖五音色、A/B/C 32 声部加 8 个 vector held 音符、pitch／glide／vibrato、poly pressure 和 release。帧 ledger 检查无丢失／重复，不要求新增流水级与旧引擎逐拍完成。随后检查保持状态的正反切换、忙时／事件／采样／PANIC 碰撞拒绝、取消尾部排空，以及从真实 vector PCM 独立拟合 440 Hz。默认独立 oscillator 回归继续检查原 48 kHz 逐拍兼容。

第二项运行完整既有效果链、真实 wet/feedback 与取消／load／事件压力，使用原 prepared event 作等价参考，同时确认完整 event 始终不承认 44.1。默认编译仍单独运行；两种编译都禁止 `UNOPTFLAT`。来源与结果见日期报告。
