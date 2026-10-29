# HDMI：已验收 D5 显示与 DDR 路径

## 已跑通的程序

用户接受的独立显示候选 **`C11028D5`**：1920×1080 UI、波形／效果状态更新及现有 DDR 数据路径。原验收及剩余物理记录见 [`verification.md`](verification.md)，位流和输入清单身份见 [`module.json`](module.json)。

保留原 D5 来源与验收记录，包括历史 hold −0.251 ns，不修改原约束或报告。

## 源码与来源

- [`rtl/`](rtl/)：显示、共享数据、帧写入、DDR scanout、DVI provider 等现有第一方源码入口。
- [`prepare.py`](prepare.py)：现有 `build.py`，使用显式 `--hdmi-isolation` 配置。
- [`display_sources.py`](display_sources.py)：准确选择锁定依赖、第一方输入和受检适配；[`baseline.json`](baseline.json)：依赖的资源源码基线。
- [`compose_usb.py`](compose_usb.py)：USB＋HDMI 组合时严格核验 D5 manifest 和位流哈希的原有入口。
- [`constraints.cst`](constraints.cst)：D5 显示物理约束的来源入口。

**不能把 `rtl/` 目录全选当成 D5。** 编译闭包还包含锁定 baseline 的 DDR/IP／渲染源码和受检适配，以 prepare 的 `enabled_inputs`、适配记录和哈希为准。

## 离线检查与新候选准备

```sh
python3 example/CUSTOM_138K/check.py --module HDMI
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_hdmi_isolation.py
python3 example/CUSTOM_138K/HDMI/prepare.py --hdmi-isolation \
  --hdmi-input dynamic --hdmi-output /tmp/custom138k-hdmi-NEW \
  --netlist-dir /path/to/locked-netlists --user-code NEW8HEX --prepare-only
```

从仓库根目录执行，将 `NEW8HEX` 换成新身份。当前源码重新 prepare 得到的是新候选，不自动继承 D5 的输入身份或验收。准确复用 D5 时必须提供原工程并通过现有 `validate_d5()` 检查。

## 装配与后续 UI

D5 独立配置排除了 AE350，当前画面主要由 RTL 绘制。保留已验证的 DDR 取数、取行缓存、换帧和 HDMI 输出；复用整机已有 AE350 软件绘图入口，逐步迁移布局、文字与控件。数据仍读取既有 DDR 快照，DDR 分配以工作站 `rtl/ddr_address_map.vh` 为准，不重复维护业务状态。

已知本机原 D5 工程：`projects/138k/push2_workstation/usb_a/out/hdmi_isolation_20261028_d5/`，其 `inputs.json`、位流和 `.p/.pr` 不随 Git 提交。新克隆不依赖此目录。
