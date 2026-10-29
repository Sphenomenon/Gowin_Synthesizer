# 原生矢量合成器运行时双采样率检查点

日期：2026-10-30。新增 [workstation_runtime_scope_vec.sv](../rtl/audio/workstation_runtime_scope_vec.sv)，从实际启用的 `rtl/audio/scope_vec/scope_vec_engine.sv`（SHA256 `595f5c7842ebb43a3139b2f9603ed4d78778024f704ccaef0f9b3523860f32bf`）迁出。旧模块、默认调用、表、profile、冻结 baseline 和顶层均不改。相邻 [provenance](../rtl/audio/workstation_runtime_scope_vec.provenance.json) 可逐项反向恢复父字节；这是版本化原生实现，不由 prepare 或 builder 生成。

保持 canonical48k tuning、每声部 phase、base step、own pitch、ADSR state／level 和几何／速度参数。每次 sample enable 冻结本帧实际 rate，帧内上游 staged rate 变化不改变在途计算。44.1k 对最终 pitch product 乘160/147后一次舍入，35-bit结果先与对应2000Hz扫描阈值比较，再取安全32-bit相位增量。无效频率显式报告并静音该帧，保留声部及canonical参数以便恢复。48k仍保留原来的截断语义及每周期时序。

矢量使用原来的ADSR表，维持其与主引擎不同的历史时间语义；44.1k增量nearest缩放并饱和，不更改sustain。表中小增量的量化及终帧量化需按各音色评估，本阶段测量piano attack；没有据此接受任意替换ADSR文件的时间误差。Morph／scale的256/frame和rotation的1/512圈/frame通过分母147的余量累计保持物理速度，最后一步夹到目标，避免44.1k偶尔两格旋转时越过终点。

机器结果、数据表／测试哈希与完整摘要：[runtime_scope_vec.json](workstation_task_20261030/runtime_scope_vec.json)。命令：`python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_scope_vec.py`。

- 48k逐拍比较480帧／56,809个计算周期，覆盖五音色、8声部的不同相位／音符／力度／shape／own pitch、morph／旋转／校准／offset和逐音释放；所有输出、握手与逐声部phase／envelope／state一致。组件最大render115周期，不含主引擎或效果链。
- 同一持音48→44.1→48，切换拍不清phase／envelope。各段1024对实际Q1.31 PCM仅在测试进程内拟合，不保存音频采样文件。测得440.000184287／439.999820471／440.000115262Hz，三段均距440Hz小于0.002Hz。
- 44.1k每帧故意在render中改变输入rate，仍得到正确冻结频率；超限own/global pitch显式静音，恢复有效pitch后原声部恢复。PANIC清音、piano attack577/48000s与530/44100s（差约2.693µs），以及44.1k控制slew118帧对应canonical48k128帧均通过。

Verilator `--lint-only -Wall` 无告警，Python编译和diff检查通过。常量除法的资源、路由时序、完整逐帧预算、双率效果历史与最终PCM接入仍未验证；此阶段没有Gowin实现、SRAM、Flash或DAC操作，A02／A05／A07整项未完成。新旧模块暂为独立比较provider，完整48k等价及显式profile迁移后应收敛为一个原生实现；不得靠复制完整工程维护两个生产版本。
