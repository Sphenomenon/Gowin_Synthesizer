# 双率渲染流水线接回整机并综合（2026-10-30）

音频算术流水线及真实引擎 ready 握手已由 `c736b87` 接入主任务分支。[源码阶段](workstation_task_20261030/runtime_arithmetic_source_stage.md)保留独立数值 oracle、故障注入、失声因果对照与最终完整 I2S 仿真身份。本阶段刷新 enabled、no-CNN、R00 三份来源锁，选入新的 divider 和相关维护入口；没有改变 accepted／pinned 的来源策略、冻结基线或已部署 Flash。

父级 portable 算术回归、17 项 accepted 来源检查和实际 1,028 帧启动配置通过；启动 fixture 交付 211 个物理帧，其中 127 个非零、错误 0。三份新 prepare 各通过 12 项来源检查，20 项 profile 与 7 项 R00 配置检查全部通过。录音配置测试继续使用冻结的 pre-R00 参考，只在临时 expected 顶层精确加入此前 `66bb45d` 的 USB 音频域复位参数；四种宏路径仍完整逐 token 比较。最初两次失败（旧环境变量指向已删除目录、旧 expected 缺该参数）及纠正后的日志身份保留在[父级机器记录](workstation_task_20261030/runtime_render_pipeline_parent_synthesis.json)。

实际综合候选为 **`custom138k-workstation-r00-v1-b9a2e0fdf36970be`**，GowinSynthesis 退出 0，耗时 368.979 秒，584 项输入前后不变，无 AG 组合环诊断。综合估算为 **Logic 104,321、Register 63,006、BSRAM 246**；LUT 79,957、ALU 15,982、RAM16 1,397。这些不是物理占用或录音存储净收益。原始诊断保留，不能称零警告。

实际 VG SHA256 为 `f71d0328da2a5dc2c5487ece298d38ab59761aa97ca76c6bdb80d6bce7f9dc80`。父级在新 VG 上重新运行维护时钟拓扑及既有 runtime CDC 检查：16 条时钟声明与实际 DCS／serializer 拓扑匹配，21 组共 400 位 Gray 首级及媒体／USB 子集的既有约束已安装。完整 reset、新增录音 CDC、DDR 不透明内部、物理传播与切换时序仍未接受。独立录音接线审查另核对实际完成 PCM、owner8 与 APB 页；它不能提升本阶段的物理或硬件门禁。

[新网表独立审查](workstation_task_20261030/runtime_render_pipeline_independent_review.json)重新验证 584 项输入和 4 项输出，核对六项完成 PCM 字段、256-bit 返回、实际 4-bit owner8 受理链及 8 个算术 helper。穷举 `paddr[31:12]` 的 2²⁰ 页与两种 PSEL 值，录音服务恰选 `0xf8040000–0xf8040fff`。1,780 个可见静态 SDC 查询匹配、16 个不透明 DDR 查询延期；没有运行工具时 Tcl 查询解析。全局仍有两条 EX1998，录音范围为零。此前 [no-CNN shared 审查](workstation_task_20261030/runtime_shared_cdc_independent_review.json)保持独立身份并明确拒绝 R00，不能挪作本候选的 shared／全 CDC 验收。

录音回归 expected 修复只改变测试与来源元数据。随后 R00 prepare 的新描述身份为 `2030fdf7a01ba140`，其 584 项 staged 字节逐项等于 b9a2。原综合的 descriptor／profile／process 保持原字节与原名，未将结果重绑定到新身份；后续物理实验明确引用 b9a2。enabled 新描述为 `cbe78d6684527158`，no-CNN 为 `93ccfa7f9c1fec9c`，同样分别保留自己来源与功能选择。

本阶段不包含布局布线、位流、SRAM／Flash 或板卡操作。旧 FC 的严重除法／包络时序是本轮流水线的触发依据，不能转移为新候选的时序结论；须以新 VG 的 `C11030FD` 实验重新核对 setup／hold／recovery／removal、资源、CDC／PLL 和双率路径。完整工作站及对应任务方框保持未完成。
