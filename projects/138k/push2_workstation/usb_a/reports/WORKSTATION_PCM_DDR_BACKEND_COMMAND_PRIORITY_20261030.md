# R00：PCM DDR 后端同拍命令修正（2026-10-30）

本修订仍是默认未选择的有界 PCM DDR 存储机制，只修正 owner 命令的接受边界，并补充同拍生命周期回归。没有新增录音业务 owner、实际 DDR client、PCM CDC、BLE/Android 接入或物理验收；R00/R01/R02 仍未完成。原[首阶段报告](WORKSTATION_PCM_DDR_BACKEND_20261030.md)及其 JSON 保留为旧输入快照，不能用旧身份代表本修订。

## 问题与接受规则

独立 review 对提交 `06b391e9df1a4aa9328b5e161c7fdc9481f42c5e` 复现了两个真实同拍漏洞：EMPTY 的 create 与 clear 同时显示 ready，两个请求都被接受但 clear 覆盖了创建；READY 无引用时 acquire 与 release 同拍，新引用被 grant，release 因读取旧 held=0 而被忽略，导致 clear 被卡住。补审还发现 READY/quiescent 的 unexpected response 与 download 同拍时，download_ready 未关闭，已接受请求随后被 fault 作废。

修正全部发生在 admission：clear 抑制 create_ready；release 抑制 reference_ready；download_ready 统一受完整 invalidate 条件约束。调用方仍可同时提出请求，不能靠要求其额外保证互斥规避漏洞。有 ready 的命令按采样沿 `valid && ready` 接受；未接受请求可以保持或重试。完整优先级见[当前契约](../rtl/audio/PCM_DDR_BACKEND_CONTRACT.md)：

- cancel／soft_reset／fault 关闭新采样、命令 admission 和下载输出；非终态同时出现时 soft_reset 优先于 cancel，cancel 优先于 fault，已有终态保持。
- EMPTY 的 clear 优先于 create；READY 无引用时 clear 优先于 acquire。
- release 阻止同拍 acquire／download 及输出交付，有旧引用才按既有账本排空释放。已有引用时 clear 仍被阻止。
- acquire 不使无旧引用的同拍 download 追溯为已接受；create 同拍 seal/PCM 也不追溯作用于新对象。

已发布 native 命令的稳定性、真实接受通知、已接受读排空、引用保护和旧返回隔离均保持原规则。没有通过取消 in-flight 账本、放宽 clear 或伪造 native 接受来解决碰撞。

## 新身份与验证

```text
identity: native-pcm-ddr-backend-v2-d92df483e5ebf74b
source_set_sha256: d92df483e5ebf74ba44b4b2dd4084ece688cbf9e443779cb538bcba00753649f
superseded source snapshot: native-pcm-ddr-backend-v1-66ecd8645a54c7af
```

完整来源、原未修改依赖哈希、配置、命令、日志和当前来源测试见[新 JSON 证据](workstation_task_20261030/pcm_ddr_backend_command_priority_v2.json)。cache 封存为 `/Users/sphenicidition/.cache/gw138k-task-20261030/r00-collision-v2-seal-final/verification.json`。本轮不覆盖原证据。新源码身份覆盖当前 RTL、契约、fixture、runner、地址图及原实际依赖；运行期间输入哈希保持一致。

24项均符合预期：14组正向配置、10个行为负控；严格 Verilator lint 零 warning，`test_current_workstation_sources.py` 10项通过。正向合计66次封存前缀核验、26个明确失败、28次取消／soft reset、56项同拍优先级核验、141,128个下载字节对照，以及4,484次 native 录音写、4,446次读。原双速真实采样周期、完整64 KiB容量、尾mask、故障和取消矩阵全部复跑。

新增 CASE4 在48 kHz／44.1 kHz各运行直接控制器与实际未修改 timing queues/core 竞争，共四配置；每配置检查14个真实边界。检查先在采样沿前观察 `valid && ready`，再核验对象／引用回执、终态和实际 native 读次数，包括：clear+create及held-create重试，release+acquire的正确／错误ID，acquire+download，release与最后一个已预取输出同拍，以及 clear/acquire/create、create/seal/PCM、cancel/reset/fault 与新命令的碰撞。release取消最后输出时不交付字节，也不产生done；禁止的新下载不产生native读。

fixture 中 new_object/clear_object helper 在刚解除 clear 或 invalidate 的同一 negedge 后等待1 ns再读取组合 ready，避免采样旧 delta 值；这不是增加 RTL 接受延迟。其真实 PCM 采样周期和100 MHz UI基准保持原定义。unexpected response 的测试注入同时支持直接路径和竞争路径，仅注入被测后端，不改真实仲裁器。

三个新负控分别恢复旧 create_ready、reference_ready 和 download_ready 表达式，均在对应真实请求同拍被拒绝，检出点为 `clear admitted simultaneous create`、`release admitted new reference`、`fault admitted simultaneous download`。原七个负控全部继续拒绝。竞争 fixture 仍只借用 MUSIC owner5并替代NN；没有新增生产owner8或证明NN并发、任意流量下的服务保证。

复现（output须不存在）：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_pcm_ddr_backend.py \
  --output /tmp/workstation_pcm_ddr_backend_priority_fresh
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

本修订未运行综合/P&R/JTAG，没有 SRAM/Flash 操作，不宣称物理资源节省或录音硬件通过。下一阶段接入及回滚边界沿用首阶段报告；回滚本修订应同时撤回三处 gate、同拍契约、fixture/runner 与新增报告/JSON，旧快照继续保留用于追溯缺陷。
