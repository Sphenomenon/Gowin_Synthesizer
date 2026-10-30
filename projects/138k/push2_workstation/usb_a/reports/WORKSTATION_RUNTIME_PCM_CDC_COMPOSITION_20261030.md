# 原生 PCM/context CDC 维护检查与约束组合（2026-10-30）

本阶段将实际 PCM 请求/返回桥与配置邮箱的审查实现为独立版本化工具，并在显式 runtime profile 中安装 50 条约束。旧 Gray/media-fence 工具、测试和共享网表 parser 相对 `df2a822` 字节不改；旧 25/77 证据继续绑定原输入。没有改 RTL、冻结基线、vendor 或原 VG，也没有新增 builder。

## 检查范围

新工具及[来源策略](../tools/WORKSTATION_RUNTIME_PCM_CDC.md)检查 229 个发布位、862 个精确单 FF pin selector、16 组双级同步器、五组 global reset release 和 17 个实际 Boolean 契约。四组完整首级消费闭包为 65/263/139/205 pins，包含 current PCM bypass、比较器 CE、源域反馈和 ready 首级，额外消费者或未知 primitive 必须失败，不能按时钟/层级过滤。

请求的最早理想 capture 为两个 compute 周期，约 26.04 ns；采用 13.020 ns flight，不能套用较慢 source 的 59.051 ns 周期。reply/context 同样采用 13.020 ns，staged serial tuple 为 20 ns。50 行由四组 payload flight/hold、16 组首 D cut 与级间 2 ns，以及十条 release 内部 2 ns 组成，不新增异步 CLEAR/PRESET assertion、recovery/removal 或 pulse-width cut。source-domain 组合 level 的叶节点归属检查不等于无毛刺证明。

`PcmNetlist` 在原 instance 文本上严格补全 escaped named-port 的空白终止语法，更新共享 instance dictionary，并拒绝重复、漏解析和原 parser 不一致的绑定。原 VG 和共享 parser 不改。它同时核对已声明 scalar alias，不能把未解析的驱动当自由 Boolean 输入。工具的退出条件包含将此兼容层迁回具备同等回归的共享 parser。

## 父级验证与身份

独立交付 14 项/81 负控后，父级在主目录重新执行完整 **14 项/81 负控**，352.267 秒全部通过；实际 VG mutation 只发生在内存。CLI 再次独立核验 sealed f1be 的 570 输入、profile、process 和 VG 前后保持，得到 proposal 身份 `runtime-pcm-context-source-v1-753dc8eb415b8fe9`。VG SHA256 保持 `8fc53d099ebead55ca3926c8d4b2b45b3504fcb1ac1ed5dbcaa1b6e1a1834535`。首次父级调用误填 synthesis evidence 路径，已中断并用原 `runtime_synthesis_evidence/process.json` 完整重跑；不计作产品失败或通过证据。

维护 composition 保留原 53 行并追加独立 50 行，`runtime_pcm_cdc` metadata 单独登记。`profile._artifact()` 重算完整 metadata，并检查实际 SDC 每行恰好一次；真实 prepare 的删除、放宽 flight、重复行及伪造 physical metadata 均被拒绝。

```text
candidate: custom138k-workstation-v1-9993a3602be582fa
candidate_input_sha256: 9993a3602be582fa11d72fb709cee842fe7833628f59c7583616f057d04d7c7e
configuration_sha256: 87834cfcde020e7e0e162369135f66f22bb6aa98669211adc5ee8f6d45184216
prepare_artifact_sha256: 6379aefc5f0263a4b86e3402e49d2d5564a5bc8cd4e10af48654b31f96e9274d
SDC SHA256: 584a50b2de4b38159a05d7961441b3d0e7fc2f1c1e4e1ce5544fb1d73276af70
```

prepare 位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-pcm-cdc-v1`。来源为 **316 锁 / 739 snapshot / 570 staged / 259 enabled**。相对 `7ffad19cde578d67`，570 staged 只有 SDC 变化；删除本阶段精确 bundle 后与原 SDC 逐字节相同，enabled 映射完全相同。新 SDC 为 320 行。默认无 profile 来源保持原行为，accepted 入口隔离。

profile **20/20**、实际来源 **12/12**、accepted sources **10/10** 无 skip；预处理仍为 256 HDL units / 288 modules / 2 packages。旧 CDC policy 四项通过，actual-VG class 按本次未提供旧环境选择器而跳过，未冒充重跑旧 25/77。另外以旧 sealed endpoint 结果对新 SDC 作静态兼容扫描，原 53 行及 Gray setup 保护保持；该扫描没有为新候选建立旧 CDC 接受身份。完整交付 seal、父级 actual audit、负控、日志和输入比较见[机器证据](workstation_task_20261030/runtime_pcm_cdc_main_composition.json)。

## 未关闭门禁与回滚

旧 f1be CLI 是 proposal 审查；新 prepare 的 installed 检查是静态安装证据，尚无新候选 sealed synthesis，不能将二者合成已综合接受。Gowin 实际 query、双 selected 模式的 required/propagation、routed setup/hold、完整功能 reset/recovery/removal/pulse、observation FIFO RAM payload 和整机功能/硬件仍未接受。F8/F9 继续使用各自原约束和身份，不追改或转移结果。本阶段无 SRAM/Flash 操作。

回滚需一起撤回独立 tool/test/policy、runtime composition 的 import/追加/metadata、profile 重算/测试和五项来源锁变化，再形成新 prepare；保留旧 CDC 工具、原候选与实验记录。任何 RTL/网表别名或拓扑变化都须重新审查，不能用放宽 endpoint inventory 使新候选通过。任务与部署门禁保持未完成。
