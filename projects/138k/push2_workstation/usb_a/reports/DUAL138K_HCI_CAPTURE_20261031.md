# 双 138K：W-DEMO HCI 能力捕获综合缺陷修复

2026-10-31。范围为维护 HCI bootstrap RTL、真实 Gowin 综合回归及原生 HCI 源码回归。本记录不表示 W 整机 P&R、板上蓝牙、D 音频或录音下载验收通过。

## 实际故障与定位

W5（`custom138k-workstation-w-demo-v1-13cd785895ee9996`）整机综合返回成功，但严格网表审计找不到真实 `flow/generations*`、`flow/is_le*` 会话键。未退休这些约束。对 W5 VG 的完整 32-bit `hci_pcm_transport_generation` 布尔追溯证明各位恒零，见 [W5 原始证明](hci_capture_20261031/w5_generation_proof.json)；故障 VG SHA256 为 `4647aa544a7b4ccd590bad2d43f36907b216aef782667b0c72f4b6ef6b0422b7`。

最小复现将问题定位到 Gowin V1.9.12 对 bootstrap 能力捕获的优化：单独固定 `host_data_length_i=276` 或 `host_packet_count_i=4` 均保留 32 位计时器；同时固定 276／4 时，未经保护的能力捕获只剩 1 个 FF、计时器全部消失，`pool_config_valid_o`、`ready_o`、`command_valid_o` 和 `activate_host_rx_o` 的真实 OBUF 输入均为 GND。独立 flow owner 本身可以正常综合。复现、真实单元实例与原始哈希见 [最小诊断](hci_capture_20261031/minimal_diagnostic.json)。

此前的函数参数显式化与本故障不能混为因果：本次证据由相同 binding、仅移除能力捕获保护属性的负例重新复现故障。

## 维护源码改动

在 [workstation_hci_host_bootstrap.sv](../rtl/bluetooth/hci_owner/workstation_hci_host_bootstrap.sv) 的两个 16-bit 捕获寄存器添加 `(* syn_preserve=1 *)`。维护源码 SHA256：`d09aa877116e97035e4d7f705484c7c20b4e0c27569e662dbd1b1755aa1d6cad`。

动态能力接口、复位值、start 边沿捕获、能力漂移失败、真实控制器查询、时限和 host RX 激活契约均保留。没有把动态端口改成静态捷径，也没有删除会话键约束。实际小型综合中能力捕获为 32 FF、计时器为 32 FF，整个 bootstrap 为 141 FF；不把故障设计的错误删除统计成有效资源收益。

## 可重复的真实综合门禁

[run_workstation_hci_bootstrap_synthesis.py](../sim/run_workstation_hci_bootstrap_synthesis.py) 从维护 RTL 生成临时 binding，使用实际 Gowin V1.9.12 综合三例。证据必须写入源码树外的新目录，既有证据不覆盖。命令：

```sh
python3 -B projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_bootstrap_synthesis.py --output /tmp/new-hci-capture-evidence
```

已通过 v3 输出 `/tmp/dual138k-hci-bootstrap-capture-gate-v3`，[完整核验 JSON](hci_capture_20261031/bootstrap_synthesis.json) SHA256 为 `c017419130c622a0e975ad8ef0a8622d679e183b0a52c37916ccb9de8b09fa53`。脚本 SHA256 为 `0888d9df0febb49d244c59b87019e62bf02036175e79b3a61d7394e9f0e45134`。

| 实际综合例 | 捕获 FF | 计时器 FF | POOL／ready／command valid |
|---|---:|---:|---|
| 动态能力端口 | 32 | 32 | 三者真实布尔函数均非常量 |
| 固定 276／4，维护 RTL | 32 | 32 | 三者真实布尔函数均非常量 |
| 固定 276／4，仅移除 `syn_preserve` | 不满足门禁 | 0 | 三者 OBUF 输入均直接 GND，门禁拒绝 |

门禁逐位核对捕获和计时器寄存器及其真实时钟，通过已有严格网表解析器追踪输出并构造 BDD。仅在本测试中为 GW5A `ALU_MODE=3` 的 COUT 增加已有不等比较链所用的精确公式 `(I0 != I1) OR CIN`，限定 I3=GND，其他 ALU 模式／端口失败。动态例 BDD 变量数为 102／69／102，节点数为 1907／1196／1893；固定例为 70／37／70 和 717／242／719。这里证明编译结果没有恒零坍缩，未声称完整时序等价。

负例必须同时出现精确的 `elapsed register inventory lost` 拒绝及三个实际输出直接为零；通用编译错误不能充当成功负例。工具、维护输入、binding、Tcl、日志和 VG 均记录哈希，并核对综合期间维护输入未变。

v1 因工具版本头解析失败，保留为失败证据；v2、v3 均成功。v3 为本报告引用版本。

## 源码与原生组合核验

[原生回归证据](hci_capture_20261031/native_regression.json) 使用上述维护源码，主集成 268 项检查、11 个 mutant 均通过／被拒绝；前置 bootstrap 418 项检查及 17 个负控也通过／被拒绝，其中覆盖能力漂移与超时。UART8E1／H5 源码链结果为 `patch=253 bootstrap=4 hostreturns=10 notifications=3 reconnect=1`。这是串口位级仿真，未连接真实板卡。

[独立原生 HCI 综合诊断](hci_capture_20261031/native_synthesis.json) 中 `flow/configured` 为 1 FF、`flow/is_le` 为 2 FF、`flow/last_generation` 为 32 FF、`bootstrap/elapsed` 为 32 FF。该诊断快照的 bootstrap 与最终维护 RTL 仅相差三行解释性注释，分别记录哈希，不能冒充 W6 整机网表。

## 后续门禁与回退

W6 将以独立新候选重新冻结这份维护 RTL，继续真实整机综合、所有约束端点审计、P&R 和板测。W3／W5 及此前失败准备路径保留原身份、原网表和原证据。本修复通过源码与小型真实综合，不提升 W5 为可部署候选。整机实际资源、布线及时序在对应候选报告登记；SRAM 和 Flash 状态均未因本报告改变。

如后续工具升级需要删除属性，先在该新工具上通过相同正例、提供旧工具负例的变化说明，并完成整机门禁。当前回退是使用原失败候选诊断，不将未经保护的固定能力路径作为有效 W-DEMO。

所有随源 JSON 的 SHA256 与原始本机证据位置见 [索引](hci_capture_20261031/index.json)。网表、实现数据库和位流仍位于源码树外。
