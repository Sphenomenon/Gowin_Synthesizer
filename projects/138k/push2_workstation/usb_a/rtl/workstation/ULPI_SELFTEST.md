# 独立 ULPI 时钟与 PHY 自测

用于区分 USB3300 时钟未到、时钟中途停止和 ULPI 寄存器初始化失败。顶层为 `workstation_ulpi_selftest_top.sv`，仅组合原生 USB3300 link、初始化器和时钟监控；没有 CPU、DDR、HDMI、音频、USB MAC 或枚举固件。下载期间没有 HDMI 输出，结束后恢复组合诊断镜像。

## 检查内容

- 以板上 50 MHz 为独立参考，每 500000 拍更新一次测量，即每 10 ms 一个窗口。
- 外部 `usb2_ulpi_clk` 直接驱动独立计数器；通过寄存后的 Gray 码和两级同步送回参考域。60 MHz 对应每窗约 600000 个边沿。
- 频率须在 60 MHz 的 ±1% 内；即使 PHY ID、Scratch 和控制寄存器初始化成功，约 300000 边沿／窗仍报告 `ulpi_frequency_out_of_range`，不算通过。仿真分别验证 60 MHz 与 30 MHz，不以读到寄存器代替频率验证。
- 时钟启动超时为 100 ms。故障码 1 表示启动期间未取得时钟，2 表示运行后停钟；没有时钟时保持 DATA 高阻、STP 高。
- 只有取得有效 ULPI 域快照后，才判定 PHY ID、Scratch 的 AA／55／清零检查，以及控制寄存器初始化是否通过。没有有效快照的零 ID 不算 ID 不匹配。
- `passed` 只代表上述 PHY 自测通过；本程序没有 USB 枚举器，`enumeration_tested` 始终为 false。

新候选GAO使用 `standalone-ulpi-selftest-input-sampler-v3`，采样时钟为缓冲后的 `clk_50m_d`，深度1024，共274位；解码器仍严格支持原v2的236位布局，不接受schema与信号列表混用。实际综合网表必须证明每一位观察寄存器由参考时钟驱动、独立计数器由物理ULPI输入驱动；两个sticky标志核对实际单一寄存器驱动，不依赖被优化掉的RTL别名。

v3另由50MHz域两级同步直接采样物理CLK输入，统计每窗的样本翻转次数和高样本比例；结构审计核对首级D接物理输入、CLK接参考域。该统计存在混叠，不直接等同于物理ULPI频率或占空比。对理想60／30MHz输入，250个50MHz参考拍分别约见100／200次翻转，已加入RTL仿真；结合原Gray计数器用于交叉检查计数或时钟树疑点。只豁免采样首级，后级仍检查2ns跨级延迟，不放宽原50／60MHz时序。

Gray 码最高位会与二进制计数器最高位合并。该位使用与其余 Gray 码位相同的、明确到首级同步器的跨域约束；同步器后级仍受时序检查约束。完整 setup、hold、recovery、removal 报告和检查保留。

## 构建与读回

从仓库根目录运行，输出目录必须不存在，`NEW_USER_CODE` 必须是未用于其它候选的八位十六进制身份：

```sh
FPGA=projects/138k/push2_workstation/usb_a
OUT="$HOME/.cache/fpga-ulpi-selftest/新的独立输出目录"
python3 "$FPGA/build.py" --ulpi-selftest --ulpi-output "$OUT" \
  --netlist-dir "$HOME/Documents/fpga补充文档" --user-code "$NEW_USER_CODE"
```

可用 `--prepare-only` 或 `--synthesis-only` 分开阶段。入口不切换 accepted、timing85 或 resource profiles，也不编程板卡。引脚约束按哈希锁定网表生成在输出目录，ULPI 使用旁路后的 LVCMOS33；不新增仓库内 `.cst`，不改球位或其它端口。

定位时钟连接时，可显式使用 `--ulpi-clock-pull NONE`、`UP` 或 `DOWN`，只改变C18输入的内部弱拉配置，并在输入清单记录。默认不改变原IO属性。每种配置须使用独立目录和新UserCode，保留50／60MHz约束及全部审计；不反向驱动USB3300的CLKOUT，也不把弱拉配置当作永久修复。

板卡经授权下载对应 SRAM 镜像后，只读采样：

```sh
PYTHONPATH="$FPGA" python3 -m tools.workstation_ulpi_selftest "$OUT" \
  --capture-output "$HOME/.cache/fpga-ulpi-selftest/新的采样目录"
python3 "$FPGA/sim/test_workstation_ulpi_selftest.py"
```

## 第二输入对照

`--ulpi-clock-probe` 只在独立自测中将 `usb2_ulpi_clk` 的生成约束从C18改到C17，默认仍走原C18；不改锁定网表、公共端口方案、任何RTL或其它IO球位。C17由锁定网表明确连接 `FPC2.8--J1.15`，封装数据库标为Bank2的MGCLKC_1输入。准备阶段检查该网仅有这两个节点，默认禁用内部弱拉，输入采用LVCMOS33；实现审计还核对实际Pin Report的球位、输入方向和IO标准。时钟计数器与50MHz直接采样器均复用原逻辑，原50／60MHz约束保留。

这不是整机空闲脚：完整工作站将C17用于 `dac_pdn_n`。测试前完全断电、拔掉FPC2功放排线，再用尽量短的临时探线将USB3300的CLKOUT节点（U2.14／U5.2）接到FPC2.8或同网J1.15。不接晶振XI／XO，不接地，不反向驱动CLKOUT。只运行本独立诊断镜像；在恢复非诊断固件之前必须拆掉探线。

先完成新候选构建和输入方向审计，再接探线。使用相同探线接法依次运行C18原路径和C17探线候选，可区分原路径／输入相关的差异。若C17约60MHz而C18约30MHz，优先检查原路径或C18输入；若两路都约30MHz，只能说明异常未因换输入而消失，不能据此直接判晶振或USB3300损坏。临时探线的负载和信号完整性也是测试条件，不能把新增路径本身造成的异常当作原故障。

探线候选示例：

```sh
python3 "$FPGA/build.py" --ulpi-selftest --ulpi-clock-probe \
  --ulpi-output "$OUT" --netlist-dir "$HOME/Documents/fpga补充文档" \
  --user-code "$NEW_USER_CODE"
```

读回校验 UserCode、暂存输入、GAO 工具与采样布局；保存原始 CSV、前后身份、解码结果和哈希。支持工具实际导出的 `Data:` 前导行，仍严格检查信号顺序、连续样本编号、位值和完整深度。

本实验定位完成后退役，不成为生产输入。当前实板记录与回退身份见 [2026-10-28 自测记录](../../reports/ULPI_SELFTEST_20261028.md)。
