# 运行时采样率下的滑音与颤音控制

日期：2026-10-30。新增原生 `workstation_rate_pitch_expression.sv`，仅处理 A07 的 pitch 控制子块。来源为实际启用的 locked `resource_rework_route0/legacy/rtl/audio/pitch_expression.sv`（SHA256 `f91e15e3a8768a8bfd86877dc1fd8b6e50a0e9f8a8a8e56c5541cbdaae098591`）；测试从版本化 baseline 重建原字节，不读取私有暂存。原 baseline／模块不改，新模块尚未选入任何 production profile。

保留 Q20 glide ratio、LFO phase 和原来的单计算周期 modulation pipeline。48k 使用原始 floor LFO step447392，保持 clamp、深度变更和 sample enable 当拍语义；44.1k step486957，实际分别约4.9999915／4.9999924Hz。采样率只在外部 render 的 sample enable 上消费，不独立创建节拍，也不拥有公共参数。

44.1k 滑音每帧 canonical 增量乘160/147，并保留分母147的余量，累计取整误差小于一个 Q20 单位。不能把最小 CC5 增量2每帧单独 round 回2，那会使物理速度偏慢。余量初值73使累计结果取 nearest；48k 路径不使用该余量，切换保留 phase／glide state。17-bit 有效增量支持完整16-bit输入的上界，不在65535截断。

`sim/test_workstation_rate_pitch_expression.py` 对锁定参考执行16000个计算周期逐拍比较，覆盖不规则 sample enable、非帧边界深度更新、上下滑、零及完整16-bit增量和输出 clamp，全部一致。44.1k 的8820帧（0.2s）使最小增量2累计前进19200 Q20单位，LFO接近一整圈，误差仅由所列 floor 常量决定。65536 Q20距离的最慢生产滑音在48k为32768帧、0.682666667s，在44.1k为30106帧、0.682675737s，相差9.070µs，小于一个44.1k帧。全范围增量和往返切换状态保持亦通过。

机器结果／全部输入SHA256：[rate_pitch_expression.json](workstation_task_20261030/rate_pitch_expression.json)。Verilator `--lint-only -Wall`、Python编译和diff检查通过。定分母除法／取模的实际综合资源和路由时序尚未验证；不得据本子块测试宣称完整DSP、效果历史、44.1k音频、SRAM或DAC验收。回退为不选择该独立模块，原有48k路径保持其来源。
