# USB1 第一阶段：被动线态观察

当前阶段不驱动 USB1、不添加 FPGA 内部上拉，也不声称能够枚举。**用户已回复：不确定实板是否加装外部上拉。** 原图只画了 D+ / D− 经 R5/R6=0Ω 直连 FPGA。USB 全速设备需要 D+ 通过 **1.5kΩ 电阻上拉到 3.3V**；FPGA 内部弱上拉不能替代这个器件或作为符合 USB 电气要求的依据。上拉及板级条件确认前，保持两脚纯输入。

## 已落实的工程

- `rtl/usb1_passive_monitor.v`：可直接实例化到综合调试顶层，50MHz 工作，USB 两脚是纯输入。经过两级同步后输出 `{DP,DM}` 线态、饱和的 32 位变化次数、变化历史、持续 SE0 / SE1 的历史。
- `rtl/usb1_monitor_top.v`：独立诊断顶层，通过 U5 的 PWM1～7 输出 7 个逻辑分析仪信号。**只用于 U5 没有其它驱动器的情形**；综合联调时优先直接实例化监测模块，避免占用其它功能脚。
- `usb1_monitor.gprj`、`build.tcl`、CST、SDC：型号为 `GW5A-LV25MG121NC1/I0`，Gowin 器件名 `GW5A-25A`，内部器件 ID `gw5a25a-002`；时钟 E2、50MHz；D+ L6、D− K6；3.3V LVCMOS，USB 输入 `PULL_MODE=NONE`。

构建以 `build.tcl` 为准，选择 `gowinsynthesis`，并打开 `use_cpu_as_gpio`、`use_sspi_as_gpio` 以释放 E2 的复用功能；当前独立工程同时启用 `use_i2c_as_gpio`，保留 JTAG。直接在 IDE 打开 GPRJ 时也要设置这些 GPIO 复用选项，GPRJ 的文件清单本身不保存这些构建开关。本工程不设置该器件不支持的 `use_reconfign_as_gpio`。

独立顶层诊断输出如下，逻辑分析仪共地、仅连接 3.3V 输入：

| 信号 | FPGA 球号 | U5 脚 | 含义 |
| --- | --- | --- | --- |
| `debug[0]` | D1 | 2 / PWM1 | 同步后 D− |
| `debug[1]` | E1 | 4 / PWM2 | 同步后 D+ |
| `debug[2]` | A1 | 6 / PWM3 | 复位以来观察到过变化 |
| `debug[3]` | F1 | 8 / PWM4 | 当前 SE0 持续至少 3µs |
| `debug[4]` | F2 | 10 / PWM5 | 复位以来出现过至少 3µs SE0 |
| `debug[5]` | C2 | 12 / PWM6 | 复位以来出现过至少 3µs SE1 |
| `debug[6]` | B2 | 14 / PWM7 | 约 0.745Hz 的运行心跳 |

`line_state={DP,DM}`：`00` 为 SE0，`10` 为 FS J，`01` 为 FS K，`11` 为 SE1。持续 3µs 是诊断门限；这里只叫“持续 SE0”，**不能根据它单独判断 USB reset、VBUS 存在或线缆接入**。没有 D+ 上拉的设备和无连接设备都可能观察到 `00`。未接主机且无外部偏置时，引脚也可能浮空。

变化计数是同步采样得到的数字线态变化次数，不能当作 USB 包数。两个单端同步器可能受引脚间偏斜影响；本模块不能测差分电压、上升沿、阻抗或解码 USB。

## 验证和本板边界

2026-10-15 已用 Icarus Verilog 13.0 运行定向 RTL 仿真，覆盖：上电同步过渡忽略、J/K 变化、短 SE0、3µs SE0 门限及释放、SE0/SE1 历史保持、短 SE1 抑制、长 SE1、变化计数饱和、复位清历史。

```sh
iverilog -g2012 -Wall -s usb1_passive_monitor_tb \
  -o /tmp/usb1_passive_monitor_tb.vvp \
  rtl/usb1_passive_monitor.v tb/usb1_passive_monitor_tb.v
vvp /tmp/usb1_passive_monitor_tb.vvp
```

另对独立顶层进行了 Icarus elaboration 检查。**截至 2026-10-16，USB1 独立工程已完成 Gowin 综合、布局布线及 bitstream 生成，产物为 `impl/pnr/usb1_monitor.fs`。** `impl/pnr/usb1_monitor.log` 明确记录 `Placement and routing completed`、`Bitstream generation completed`，构建使用的 SDC 已修正为 `get_ports {clk}`。

**USB1 独立镜像尚未下载实板，没有完成 USB 枚举测试，也没有通过本次工作确认外部上拉是否存在。** bitstream 生成通过只证明该被动观察工程能构建，不代表 USB 硬件或协议通过验证。当前不主动驱动 D+ / D−；后续应先确认实际硬件条件。

## 可以落地的下一步

1. 断电测量/检查 USB1 D+ 到 3.3V 有没有约 1.5kΩ 电阻、是否另有开关控制。5.1kΩ CC 下拉承担 Type-C 角色检测，不能替代 D+ 上拉。
2. 若未装上拉，补充 USB FS 设备所需的 1.5kΩ D+ 上拉方案。若板子可能由其它接口供电，应以 USB1 的 VBUS 存在为条件控制上拉；本图没有给 FPGA 提供独立 USB1 VBUS 检测线。
3. 评估 R5/R6 串阻：公开 GPIO USB IP 常用约 27Ω，但最终值需要结合 FPGA 输出阻抗、走线、边沿及波形验证确定，不能只改成固定值就视为达标。
4. 选择协议 IP、生成对应时钟并仿真/综合，再临时下载 SRAM，以主机日志核查 device/configuration descriptors。USB GPIO 直连即使成功枚举，也不等于 USB 电气合规；产品化需要满足差分接收等 PHY 要求，或采用适当外部 PHY。

## 公开 IP 核查（本工程没有复制其 RTL）

| 项目 | 许可/移植 | 所需时钟 | 选择影响 |
| --- | --- | --- | --- |
| [avakar/usbcorev](https://github.com/avakar/usbcorev) | [No-notice MIT](https://github.com/avakar/usbcorev/blob/master/LICENSE)，纯 Verilog transaction core | **48MHz** | 需要另做设备类/控制端点描述符集成；README 明确要求 1.5kΩ 上拉、输出串阻，并指出单端 GPIO 接收不满足 USB 差分接收规范 |
| [WangXuan95/FPGA-USB-Device](https://github.com/WangXuan95/FPGA-USB-Device) | [LGPL-2.1](https://github.com/WangXuan95/FPGA-USB-Device/blob/main/LICENSE)，纯 Verilog，已有 CDC 类 | **60MHz** | CDC 接口更接近下一阶段串口回环；将例程 Altera PLL 换成 GW5A PLL，并履行许可。README 要求独立 1.5kΩ D+ 上拉，不能直接给它 48MHz |

这些文档/许可在 2026-10-15 从各仓库读取；上游主分支可能变化。当前没有将第三方 RTL 合入工程，后续选定时应固定 commit 并保留许可和来源。

48MHz 不能从 50MHz 做整数分频得到，也不要用分数使能脉冲代替 USB 采样时钟。GW5A 需采用 **PLL IP** 将 50MHz 转为 48MHz（比例 24/25），并以 `LOCK` 同步释放 USB 核复位。Gowin 当前 GW5A 仿真库具有 `PLL` / `PLLA`，采用 `IDIV_SEL` / `FBDIV_SEL` / `MDIV_SEL` / `ODIV0_SEL` 等参数；应在目标器件的 IP Generator 中设置 50MHz 输入和 48MHz 输出，按器件允许的 PFD/VCO 范围生成，检查生成的时序约束、抖动和布局布线报告。上述被动观察模块直接用 50MHz，当前不需要 PLL。若选择 CDC 项目，则相同方法生成 60MHz。
