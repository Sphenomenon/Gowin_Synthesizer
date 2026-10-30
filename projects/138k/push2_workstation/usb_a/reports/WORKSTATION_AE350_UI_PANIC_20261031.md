# C02：PANIC 与快照撕裂组合修正

日期：2026-10-31。这是 `350e8c1` 分步服务交付的后续修正；原提交、证据和
封存文件保持原字节。父级独立审查新增了原矩阵未覆盖的组合：模式释放等待中，
真实声部归零、PANIC epoch 已改变，同时触摸 sequence 撕裂。

原实际 `ui_service_step` 只在触摸 sequence 稳定时调用 `read_model`，却仍推进
控制 job，可能提交旧的排队 Note On。只在原 fixture 最后的 PANIC 用例打开
`touch_torn`，原源码即在 step 2887／check 33653 失败；外部证据目录
`/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-ui-panic-torn-v2/failing-old`。

本修正把 `read_model`／PANIC 观察与模型 revision 推进移出触摸稳定条件，
触摸撕裂只放弃该次触摸输入。PANIC epoch 位于单个原子 32-bit pitch 寄存器，
`read_model` 在复核音频 snapshot sequence 前应用这个事实；若音频快照撕裂，
返回其 `changed` 值，其余快照字段全部弃用。这样 PANIC 同时清除排队 gate、
推进 revision 并触发重画；没有引入另一份参数真值。旧 `draw_cancel` 语义保留：
未发布 partial page 的 valid 清零，下一 job 完整分步重画。

实际主循环 fixture 分别覆盖触摸撕裂、音频快照撕裂以及两者同时撕裂，均在
PANIC 前建立排队 gate／真实 release 等待与 partial draw，要求无补发 Note On、
revision 更新、新目标 epoch 正确以及失效 back cache 的 full 重画。新增两项
突变分别恢复触摸门控和音频快照门控，均必须被实际入口用例拒绝。

运行 `sim/run_ae350_ui_service.py --output <新目录>`：原生及 ASan／UBSan 各
**34867 checks／2889 steps／5 publications**，12 项行为突变全部拒绝。
真实锁定 UI APB 回放各 **7252 reads／15 writes／5 commits／5 resets**。
固件测试 10 项、accepted 来源测试 17 项通过；四 profile 的 ui_main SHA 同步。
最终 ui_main SHA256：
`dcbbb89209eaa43ca4cf7a2eb1ac7dcb04853f03c73b2c46263bb5c1b4cb4573`。

旧 pl16k_8k 实际默认构建 **14504 bytes**，加真实 recording API 为
**16280／16384 bytes**，`services_main` 编译器单帧仍 **1008 bytes**。
本阶段没有修改 C06 的 stage／startup／linker；根级须在其当前 boot64 配置
重新验证本地存储、调用链和整机来源，不继承此小配置的物理接受结论。

最终证据位于上述外部目录的 `host-final-v2`／`default-final`／
`recording-final`，独立只读 verifier／seal 绑定源码及输出。不调用综合、P&R、
板卡或推送；物理服务间隔、总线期限和完整可见显示路径仍未验收。
