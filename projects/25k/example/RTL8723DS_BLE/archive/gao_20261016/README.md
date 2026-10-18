# 2026-10-16 原 GAO 镜像归档

此目录保存原 `prj/ble_bringup` 实板验证镜像及其生成资料，作为 BLE 成功收发的历史证据。当前例程的构建和下载入口采用不含 GAO 的普通镜像，不使用此目录。

| 项目 | 原记录 |
|---|---|
| 位流 | `pnr/ao_0.fs` |
| SHA256 | `d77d8d990ab3afcef082396464d59717b6053e025dee82acbb3dfb36a0526592` |
| UserCode / Status | `EEDB` / `70022020` |
| GAO ID | `4C64` |
| setup / hold 违规端点 | 0 / 1 |
| hold slack | -0.606 ns，50 MHz 采样域到独立 JTAG TCK 域 |

原镜像已通过 SRAM Program+Verify，随后完成广播、连接、FFF1 读取和 3 个有效通知，原始记录位于 [reports/hardware_20261016](../../reports/hardware_20261016/ble_hardware_20261016.json)。50 MHz 核心 Fmax 为 54.156 MHz、同域核心 setup / hold TNS 均为 0；GAO 内部跨时钟 hold 仍有上述违例。受保护模块的后继同步链无法从现有文本输出完整确认，未添加 false-path 或其它例外，不将其视为完整时序或 CDC 签核通过。详见 [gao_cdc_review.md](../../reports/hardware_20261016/gao_cdc_review.md)。

`build_gao_original.tcl`、`ble_status.rao`、SDC 及 PnR 输出原样保留；脚本包含原工程布局中的相对路径，仅供追溯，不能作为本独立例程的构建入口。安全构建工具拒绝沿用旧 RAO 重建，`program_sram.py` 也明确拒绝 GAO 镜像，不绕过时序检查。当前可运行命令见 [例程 README](../../README.md)，历史 CSV 的离线解码见 [debug/README.md](../../debug/README.md)。
