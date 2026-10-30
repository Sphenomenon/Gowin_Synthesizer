# HCI host RX 主线独立复验

2026-10-31，作者 `4a7600cb0f83ab3a5c275d789f44cda5e086db93` 的七文件阶段精确导入为 `753f4e9`。父级对比工作区、提交 blob、固定作者树逐字节相同，实际测试的全部输入与作者最终输入相同；未选择进生产 profile。功能、握手和限制见[原阶段报告](WORKSTATION_HCI_HOST_RX_SOURCE_20261031.md)。

父级阅读精确 RX RTL 及 flow 仅增加只读 LE 分类输出的改动，核对控制器预算守恒、稳定 return snapshot、断连隐式退款与 RAM quarantine、release token、错误优先级；未发现此独立组件契约内的阻塞。真实 reader completion、H5 不可撤回接受和顺序交接仍是组合必须落实的边界。

实际执行 `sim/run_workstation_hci_host_rx_owner.py --output /Users/sphenicidition/.cache/gw138k-task-20261030/hci-host-rx-main-verification-v1`：

| 检查 | 父级结果 |
|---|---|
| 实际 RX＋共享 flow RTL | 160,228 checks，12 场景，10,000 随机步 |
| 行为突变／非法参数 | 13 项突变、8 个非法参数全部拒绝 |
| 原共享 flow／event | 116,780／9,174 checks，原 11 突变全部拒绝 |
| 工具检查 | 实际 Icarus 仿真、严格 Verilator `-Wall` 无豁免 |
| accepted 来源 | 17 项通过，生产选择未改变 |

结果与作者最终数据一致，父级重新核对所有输出及工具哈希。新父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/hci-host-rx-main-parent-v2` 已实际运行 `verify.py` 通过，绑定 157 项外部文件，seal SHA256 `538718d7f7777082d86757e8643c46c1333416f514a2fc13f723e94ef9040c20`。机器记录见[父级收据](workstation_task_20261030/hci_host_rx_main_parent.json)。早期封存脚本 v1 因假定作者包存在 `seal_verification.json` 而停止，保留未封存输出；v2 改绑真实 `verify_seal.py`，不重跑或改写已通过的 RTL 结果。作者原 seal `9f7b4aad3d1a98af004cd5942e0e059fd2397e3c5fff22f8b1d1682faa023d5d` 已另行只读复验。

本组件没有 payload RAM／copy／DMA／CPU 邮箱、bootstrap 或 native 组合；inflight 0x0c35／disconnect 竞争尚无控制器实测。原 BLE credit owner 尚未退休，没有整机资源、EDA、手机、物理声音或部署接受。本阶段未操作板卡，回退仅撤回未选择的组件及只读分类端口；后续须以新来源身份重新组合验证。
