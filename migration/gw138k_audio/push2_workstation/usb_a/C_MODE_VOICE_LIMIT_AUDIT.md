# C 模式声部限制审计

审计输入为当前 P13 构建冻结的 `results/build_20260915_005824_693914/Prj1`。本记录只说明现状，不改变当前 P13 SRAM。

## 结论

C 模式（`mode=2`）当前确实被限制为 4 个声部，而且限制来自引擎的分配、slot 存储和上层满载判断三处。`partial_step_generator_variable` 已支持 32 个 partial，32 位 active mask 和声部状态数组也已存在；因此不能只把一个比较常量改成 31 就恢复 32 声部。

## 直接限制点

| 文件/表达式 | 当前行为 | 影响 |
|---|---|---|
| `legacy/rtl/audio/unified_oscillator_engine.sv` `maximum_voice_index = current_mode_o == 2'd2 ? 5'd3 : 5'd31` | C 模式分配/同音释放只扫描 index 0～3 | 第 5 个 NOTE_ON 被 `allocation_found` 拒绝 |
| 同文件 `logic [79:0] slot_mem [0:127]`、`logic [6:0] slot_read_index`、`last_slot_index = ... ? 7'd127` | slot 总数固定 128 | C 模式 4×32 partial 正好占满 128；32×32 需要 1024 slot |
| 同文件 C 模式 `issued_voice_index = {3'b0, slot_read_index[6:5]}` | 128 个 slot 映射到 voice 0～3 | 即使分配掩码放宽，计算仍只访问 4 个 voice |
| `src/ae350/gw138k_event_workstation.sv` `full = mode_o==2 ? &allocated[3:0] : &allocated` | C 模式上层在 4 个 bit 全置时就拒绝 NOTE_ON | 引擎外还有第二个 4 声部闸门 |

已有对应逻辑无需重做：`current_partial_count` 在 C 模式为 32，`load_slot_address` 的 C 分支按 voice×32 计算，`partial_step_generator_variable` 的输入宽度和 32 上限均已覆盖；包络、active mask 和 voice state 数组按 32 声部存在。

## 恢复 32 声部所需的最小改动

1. 将 C 模式 slot 地址和 RAM 深度扩为 10 bit/1024 项；保持 A/B 模式的 32/128 slot 语义不变。`slot_read_index`、`issue_index`、`last_slot_index`、读写地址和 pipeline tag 需要统一宽度，避免只扩大 RAM 而截断地址。
2. C 模式 `issued_voice_index` 改为 `slot_read_index[9:5]`，得到 0～31；上层 `full` 改为检查完整 32 位 `allocated`。
3. 保持 mode2 的 32 partial/voice 和现有 Q1.31、ADSR、音高、效果链接口；不引入新的音频 CDC，也不改变 Push/HDMI 协议。

## 时序与资源待验证

当前 C 模式每个样本遍历 128 个 slot；恢复 32 声部后为 1024 个 slot，混音扫描约增加 8 倍。48 kHz 音频时钟间隔为 76.8 MHz / 48 kHz = 1600 个 UI 周期，能否在该预算内完成还需用真实 `sample_ce_i`、声部全开和效果链输入测试确认，不能从 RTL 位宽推断通过。1024×80 slot RAM 也会明显增加 BSRAM，需在新构建中记录 Logic/Register/BSRAM/DSP 和 setup/hold；P13 的 +0.024 ns 余量不能直接沿用。

验证顺序：先做 C 模式 32 个 NOTE_ON/NOTE_OFF、32 个独立相位与满载混音的 RTL 测试；再做真实 48 kHz sample_ce 的 deadline/欠载计数；最后在独立结果目录综合和布局布线。任一阶段失败都保留 P13 作为 SRAM 回退版本。
