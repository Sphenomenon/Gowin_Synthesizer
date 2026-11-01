# PCM 输出 context 许可维护阶段

实际PCM owner将不含context的输出许可保留为独立组合项，再把context_ready_i放到最终PCM零化门。上游DSP即时fault仍同拍撤销输出；legacy选择、X/Z、采样周期及全部NBA保持。bitmap清理与资格逻辑未改。

W16far真实overflow→共享usable许可→D处理及effects输入DSP路径为15级／−5.166ns；相关bitmap CE链17级／−5.155ns。TR／VG／VO和许可LUT真值已封存，本次只针对输出许可前缀，bitmap及其他违例仍待后续实际实现量测。新owner SHA256 `1c575c3fd39d73c795cb7e49c075a1b5848be90d3cccd57e24db991a9071649b`，精确inverse恢复`574c6e…b71e`。

源码表达式四态Z3 UNSAT＋3 SAT反例，实际完整owner786,432四态／即时撤销检查＋3源码负控；完整owner逐拍比较所有状态、512 RAM字及bitmaps。全部8项owner回归含4×576,000帧频差；原bitmap7217 cycles／3负控、bitmap四态1,048,576／5负控、descriptor／4负控，以及实际APB／CDC→D完整效果／I2S双率／PANIC通过（1918物理帧、1913 snapshots、12 PANIC／10 in-flight；均为离线仿真）。普通PCM runtime另行通过。初始runner因重复负控锚点失败，原v1 passed=false保留；修正测试锚点的v2通过，期间RTL不变。

主线程重验108包内文件、238外部测试产物、93当前输入版本及6owned。逐文件身份、具体命令及限制见[机器报告](DUAL138K_PCM_OUTPUT_CONTEXT_20261101.json)；seal `fe3c4a21c2aafb38919d51ba3b428fae50297498d4308c21398849d01210c309`。旧oracle／fixture不改，测试inverse不参与生产构建。

物理收益需新候选全量综合/P&R；未预记资源、未进行硬件声画验收，未写SRAM／Flash。完整HDMI、D处理、唯一录音对象及所有现有功能保留。
