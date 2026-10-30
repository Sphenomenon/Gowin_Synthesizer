# 运行时音频算术流水线

`workstation_runtime_render_engines` 在 `RUNTIME_RATE_ENABLE=1` 时显式为 oscillator 选择 `PIPELINED_RATE=1`、`PIPELINED_ENVELOPE=1`，为 vector 选择 `PIPELINED_RATE=1`。独立模块的新增参数默认仍为 0，保留原周期行为。accepted full83／pinned timing85 的源选择不由本文改变。

## 精确数值和寄存边界

44.1 kHz DDS 保留原式 `floor((product*160+77070336)/154140672)`。令 `D=147*2^20=154140672`，对非负整数 `N=qD+r`、`0<=r<D`，有 `floor(N/2^20)=147q+floor(r/2^20)`，末项在 0～146，因此可精确改写为 `floor((N>>20)/147)`。必须先加舍入偏置再移位。

54-bit product 的最大值为 18014398509481983；乘 160 加偏置的结果至多 2882303761594187616，能由 62 bit 表示；移位后至多 2748779069513，能由 42 bit 表示；商至多 18699177343，能由 35 bit 表示。oscillator 的 48 kHz 分支仍按原 bit19 舍入，vector 的 48 kHz 分支仍截断，二者没有合并成同一种舍入策略。

共享 `workstation_runtime_div147` 是无符号 radix-4 精确整数除法。最高 6 bit（奇数宽度为 7 bit）先寄存为余数，其值小于 147。每级处理两位；若旧余数 `R<147`，则 `X=4R+b<=587`，以并行减 147／294／441 的借位选择两位商，余数继续小于 147。每级只包含有限宽比较／减法，输出进入实际寄存器。42-bit 输入有 18 个商级，32-bit 有 13 个商级；输入在 edge0 接受，结果分别在 edge18／edge13 后有效。输入 seed 也是一个寄存位置。可每拍接受一个有效输入，支持任意 valid 空泡。

oscillator 的原 pitch product、乘 160、加偏置／右移、每个商级、phase write／sine launch 分别以寄存器交接。161-bit tag 携带帧采样率、48 kHz 舍入步长、slot index、旧 phase 和 slot 尾部、gain、envelope、last；phase 写回和 sine／gain／envelope／last 使用同一返回 tag，不能读取后来变化的索引或帧上下文。截止值仍为 1932735283。

ADSR 的三个 32-bit numerator 先寄存，再经三个 13 级 divider。44.1 kHz 仍为 `floor((canonical*160+73)/147)`；48 kHz 用 `canonical*147` 得到原值。最大 numerator 分别为 2684354473／2466250605，均在 32 bit 内。oscillator 的 44.1 kHz cap 保留 `0xffffc0`，vector cap 保留 `0xffffff`；48 kHz 不额外限幅。oscillator 的后续 scale／parallel math／select／write 寄存级保留，ADSR tag 绑定 index、state、level、sustain 和 rate。

vector 在 phase numerator 与移位结果后寄存，state19 等待 42-bit 商，7-bit tag 绑定 frame rate、voice index、own-pitch overflow 和 product 高位。NoteOn 的三个系数在 state18 等待 32-bit 商，voice 分配保留原接受边沿；等待时不再接受样本或事件。

## 接受、完成和取消

新增 arithmetic valid 与 numerator valid 都由 reset／PANIC 清零，PANIC 当拍还禁止 divider 输出 valid。无有效 tag 的 data 不参与写回，不需要为每条宽 data 总线增加复位 mux。quiescent 覆盖所有有效寄存位置，不能用较早清零的 mix_busy 代替。

oscillator 的既有 `sine_interp` 继续自然排空；独立的 live token 在 PANIC 时清零，阻止旧 ROM 结果进入新的 accumulator 或完成后来的帧。自然尾部仍计入 quiescent。事件、表达、模式和采样只有在新流水线真实空闲时才能接受，PANIC 后立即重用全部声部须等待此条件。

`gw138k_event_workstation` 的运行时 NoteOn／Off 必须等待实际 engine ready 才更新 held／deferred 并弹出事件；历史 `TIMING_OPTIMIZED` 的旧 busy 近似不足以覆盖新增算术尾部。CC120 的接受条件直接展开为 `event_valid && !releasing && dispatch && kind==2 && a==120`（另保留 USB lifecycle），与原 control-event 分支等价，避免取消经过 engine-ready／sample-ce／配置 ready 的组合环。18-bit 事件布局与 PANIC／held 生命周期不变。

## 验证和预算

维护入口不需要私有暂存目录：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_arithmetic_pipeline.py \
  --output <不存在的新目录>
```

它校验 native hash，仅反转 provenance 的 arithmetic 尾部得到精确旧 oracle；依赖和 ROM 从版本化 `resource_rework_route0` 基线及现有 vector ROM 重建。可选 `--reference-project` 逐字核对独立冻结工程，但不作为必要输入。三套独立 fixture 比较整数商、固定延迟、空泡、tag、reset／flush、PCM、slot／phase、ADSR 状态及重用；四个 helper 和四个消费者故障注入必须能编译并被相应 oracle 检出。完整 composition／service／I2S 回归另见日期报告，不能用 helper 通过替代。

32 声部／五音色／A/B/C 的独立比对，在 48／44.1 kHz 下 A/B/C 最大完成延迟均为 69／165／1061 clocks；8 声部 vector 最大 284 clocks。76.8 MHz 下 48 kHz 间隔为 1600 clocks，44.1 kHz 最短间隔为 1741 clocks。完整 service 的稳定最大延迟为 1168、loader 重叠为 1204；首次自动 44.1 kHz 配置加渲染为 1620，须按 1741 的该率预算核对。上层实际串行槽与配置排空还有独立开销和验证，不能把 engine 预算当成整机时限证明。

本契约只描述源实现与 RTL 仿真。新综合、布局布线、所有 STA 类别、CDC／PLL／资源检查和实板音频仍分别验收；不修改时钟、SDC、false path 或 multicycle 例外，不继承任何旧候选的物理接受身份。
