# 共享 HCI host bootstrap 主线独立复验

2026-10-31。作者 `37973f1b89c867fe2e9ea195b66d5f79cfaffbab` 的10文件源码阶段精确导入为 `7aa9180`。父级逐字节核对作者树、导入提交和当前工作区，并重跑实际 RTL；仍未由整机 profile 选择。接口及剩余条件见[原阶段报告](WORKSTATION_HCI_HOST_BOOTSTRAP_SOURCE_20261031.md)。

该组件在 initializer 交接且没有任何 link 时，串行发送真实 BR ReadBufferSize、LE ReadBufferSize、HostBufferSize、ACL controller→host flow enable 命令，实际容量经唯一 flow owner 配置后才激活 RX owner。命令字节持有到 transport_done，普通 quota 为零会等待；offer、response、transport和pool各阶段有常开时钟期限，失败不猜测成功或重放。event decoder／flow增加明确 Complete／Status 元数据，四条 bootstrap 命令拒绝把成功 CommandStatus 当完成。

父级阅读精确状态机、命令字节及元数据修改，检查 handoff／link-idle 前提、真实容量、稳定 payload、期限优先级、Complete 区分及一次性激活，未发现此未选择组件契约内的阻塞。完整运行入口为 `sim/run_workstation_hci_host_bootstrap.py --output /Users/sphenicidition/.cache/gw138k-task-20261030/hci-bootstrap-main-verification-v1`。

| 检查 | 父级实际结果 |
|---|---|
| bootstrap＋实际 flow／RX | 418 checks，32场景，四个命令、两个pool配置、五类timeout阶段 |
| bootstrap负控 | 17个行为突变、3个非法期限参数全部拒绝 |
| host RX回归 | 160,228 checks，13突变拒绝 |
| flow／raw event回归 | 116,780／9,174 checks，原11突变拒绝 |
| lint／来源隔离 | 严格 `-Wall` 无豁免，accepted17项通过 |

父级全部测试输入与作者最终报告相同，输出和工具哈希逐项核验。新包 `/Users/sphenicidition/.cache/gw138k-task-20261030/hci-bootstrap-main-parent-v1` 的 `verify.py` 已实际通过，240项直接外部文件；seal `a188ae30341c8a8a1e78d1124596ef1fc65de2921861e0ee2c0df0a08dec2fa9`。机器收据见[父级记录](workstation_task_20261030/hci_bootstrap_main_parent.json)。作者原 seal `6401a53f8b6a1064f58c69b2bb6719ea200b9852964c760072326cdebeb8d8ab` 已另行只读复验。

当前原 initializer 在 advertising 后才结束，不能直接冒充安全 handoff；真实组合必须在 advertising／建立link之前明确交接。payload RAM／raw router／CPU邮箱、旧 BLE 双credit owner退休、controller实际命令支持、security／DelayReporting、并发期限和完整BLE行为保留仍待完成。该源码阶段没有生产选择、EDA、净资源收益、手机或物理音频接受；上述离线结果不转授给任何整机或 SRAM 探针身份。
