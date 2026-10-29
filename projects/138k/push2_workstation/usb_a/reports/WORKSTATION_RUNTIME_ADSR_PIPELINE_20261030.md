# 原生ADSR显式流水候选（2026-10-30）

在`workstation_runtime_oscillator_engine.sv`增加`PIPELINED_ENVELOPE`，**默认0**保持现有迁移周期行为；新物理候选需要显式选1。本轮仅修改此原生owner、追加其可逆provenance及新增测试／报告，没有修改legacy／frozen／vendor、profile、render／event／service组件或F03锁定输入，也未运行综合／P&R或访问板卡。

[机器记录](workstation_task_20261030/runtime_adsr_pipeline.json)记录源码hash、原F02失败路径、寄存边界、验证范围和剩余缺口。新SV SHA256为`9950b3cd95dc7224158254bff05bfd2c8658b780a86e4cf4faecd3744a026705`；provenance追加6组精确可逆edit，反向仍恢复原prepared SHA256 `7afb67e8b92828b50e42fbdfa259bf5c5ec0b39d1104bc263c5072e93067859e`。

原F02的BSRAM DO→ADSR→32voice写回链为20逻辑级、13.783ns、setup−0.823ns。新opt-in路径形成真实数据寄存边界：同步voice读取→rate scaling寄存→并行25bit加减寄存→饱和／state选择寄存→索引写回。没有复制完整engine，也没有仅重命名旧寄存器。Decay判定由串行`level-sustain<=decay`转为等价25bit`level<=sustain+decay`，保留原`level<=sustain`及溢出情形的结果；attack／release的饱和、零step与borrow分别验证。

流水每拍处理一个voice，索引、valid、state及必要数据同步推进。全部新valid纳入真实quiescent和sample／event／expression／mode准入；写回仍在原共享过程、note-off与load-launch赋值之前，保留事件覆盖优先级。PANIC清除三个新增valid，并阻止同拍及后续取消写回；stage数据只在valid时更新，不添加全局PANIC数据复位mux。

| 观测 | 原default0 | opt-in1 |
| --- | --- | --- |
| 32voice ADSR最后写回 | 34clocks | 37clocks |
| A模式PCM延迟（两种rate） | 47clocks | 47clocks |
| B模式PCM延迟（两种rate） | 143clocks | 143clocks |
| C模式PCM延迟（两种rate） | 1039clocks | 1039clocks |

默认0的原4项回归通过，逐拍controls／PCM／voice state仍与精确prepared reference相等。Opt-in1新3项测试通过：264帧ABC模式、32voices、五profile与48↔44.1切换的逐输出PCM及排空后voice／slot状态相等；4096组包括零、饱和、减法borrow、decay边界和随机voice状态；47个ADSR／renderer取消时点并重新分配新note，验证valid排空、顺序32次写回和无取消后残留写入。

**Opt-in1内部ADSR写回晚3拍，不宣称逐拍状态等价。**44.1沿用原精确160／147与accepted-frame冻结rate，canonical step／phase／level语义保持。按76.8MHz计算，已测组件最差1039clocks，48k的1600clocks预算余561，44.1的最短1741clocks预算余702；这只属于组件采样用例，不是effects／最终串行或整机最坏调度证明。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_oscillator.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_adsr_pipeline.py
git diff --check
```

上述仿真与diff检查通过。新测试只有两条继承来源的UNSIGNED提示；原回归仍为刻意兼容调用的2条PINMISSING及4条继承UNSIGNED。任何其他warning class使测试失败。寄存切分的实际映射、物理资源增量和routed timing仍需独立综合／P&R验证；44.1常量有理数缩放仍可能成为单独关键级，不能据此宣称全音频时序闭合。
