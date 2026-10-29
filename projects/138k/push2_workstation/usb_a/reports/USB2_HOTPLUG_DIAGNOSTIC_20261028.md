# USB2 热插拔轻量诊断（2026-10-28）

## 目标与配置

用单独的 `workstation-hotplug` 配置快速迭代同一 USB-A 口上的 25K／Push 交替接入，不再每次带整机综合。入口复用 `build.py --prepare-usb2-soc`，没有新增编号生产 builder，也不切换 accepted、timing85、resource-timing 或 HDMI 配置。[操作说明和串口字段](../rtl/workstation/USB2_HOTPLUG_DIAGNOSTIC.md)。

- 保留生产 VexRiscv、工作站固件、USB3300／ULPI、HS／FS Host、输入 owner、服务适配器、会话取消以及 Push LED／屏幕传输。
- 事件接收端为始终 ready 的 18-bit 观察器，记录事件、生命周期、取消及最后事件；不改事件格式，不作为音频或公共参数的第二权威。
- 反馈通过原生 76.8 MHz→48 MHz 快照通路，held-note 区域仅发送事件计数测试图样，其余为零。此图样不是实际保持音符或发声状态。
- 不包含整机音频引擎、DDR、CNN、板载 HDMI、BLE、TF、LCD、AE350。Push 自身屏幕的 USB 传输和板载 HDMI 是不同边界，后者继续使用独立显示配置。

## 实际执行结果

证据根目录：`~/.cache/fpga-usb2-hotplug-diagnostic/20261027-234417-first/`，最终候选 `candidate-v5/`。Gowin `V1.9.12.03`，目标 `GW5AST-138C`，配置身份 `custom138k-usb2-hotplug-C127E205`，UserCode `0xC127E205`。

`execution-v5.json` 记录本轮准备、综合、布局布线实际退出 0，总耗时 **91.811 s**。整机 C127E103 的实际 **P&R 单阶段**为 **3685.888 s（61 分 25.888 秒）**；本轻量完整离线构建约为该阶段的 **1/40**。不把这两个计时描述成相同范围的基准测试。

| 路由后检查 | 最差裕量 |
| --- | ---: |
| setup | +0.771 ns |
| hold | +0.194 ns |
| recovery | +9.576 ns |
| removal | +0.261 ns |
| pulse width | +2.684 ns |

四个实际时钟保持 50／60／48／76.8 MHz。对应报告 Fmax 分别为 236.633／115.212／63.571／197.171 MHz，全部高于原要求。`hotplug_audit.json` 的 `timing_closed=true`；原生 USB bridge CDC、注册 Gray 指针事件 FIFO、原生复位链、诊断复位合并别名与 PLL 频率／静态模式检查均通过。ULPI 外部板级 IO 延迟仍未补齐，此处时序结果限定于已有约束覆盖范围。

实际资源：Register **4295**、LUT **7554**、ALU **930**、SSRAM **12**、物理 BSRAM **41**（40 SDPB＋1 SDPX9B）、DSP **1**（2 MULT12X12）。省略整机音频 DSP 子系统不等于完全不使用 DSP 原语。

## 来源与适配

35 个编译来源由既有 `workstation-input` 组件、独立诊断顶层／UART 和锁定时钟实现组合。`component/component_inputs.json` 原样保留。根 `hotplug_inputs.json` 记录所有实际暂存文件、原始配方、子组件、基线、配置、来源和引脚哈希。

事件 FIFO 显式复用完整原生 resource-timing 构建的同一个 `event_fifo()` 注册 Gray 指针适配，选择独立 `support/src/usb_host/gw138k_usb_event_fifo.v`，不编译子组件旧副本。适配后 SHA256 为 `2084bead34bf421610fd20489ece66601823b87f72887228be25de5374a956c6`，与整机原生暂存版本逐字节一致。

Gowin 把诊断 link mailbox 的前两级复位与已有原生复位前缀合并；SDC 只选择真实存在的合并后对象，并在综合网表中检查第二级 Q→第三级 D、时钟和异步清零一致性。没有降低频率、添加整域 false path 或删除原生 CDC／时序检查。对共享审计函数只增加可选顶层／反馈源时钟参数，默认仍为完整工作站。

| 证据 | SHA256 |
| --- | --- |
| `hotplug_inputs.json` | `3a54b841b783b78215f08999633a984ef0ff93ef17d8263305012060a3112179` |
| `hotplug_audit.json` | `52605886e5a067dfcb94a4e5543f6ab3eca6775c31c7618eb51b4a15a07f255e` |
| 工作站固件 ROM | `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457` |
| 实际综合网表 | `ab364a6125a9513b69b61aa67a2c5fcb88060db5d6415db4ee351495f5dafedf` |
| 详细路由后时序报告 | `61bf52bd4cc6a154cc2308a16960f9805d8a5218278084359a52ce92f784aa14` |
| `.fs` 位流 | `b33f54ef54782e98bd836d57dd723fede1eb69c615361379b6baa95e10f78b2e` |

## 引脚与电气

15 个引脚仅含 50 MHz、UART RX／TX 和 ULPI。生成的 ULPI 位置如下，球位解析算法及其它端口／retired_ports 均不改动：

```text
usb2_ulpi_data[0..7] = A21 B21 A20 B20 A19 A18 B18 B17
usb2_ulpi_clk       = C18
usb2_ulpi_dir       = F16
usb2_ulpi_nxt       = D16
usb2_ulpi_stp       = E17
```

位置沿用原 resolver，独立诊断的生成输出为 12 个 ULPI 信号补充 `IO_TYPE=LVCMOS33`，没有新增受版本控制的 `.cst`。U4／U5 旁路声明与 B 侧 3V3 证据沿用同一 pinout，`electrical_check.status=no_voltage_domain_conflict_detected`。旁路电气唯一待实测项为 **USB3300 ULPI IO 是否确由 3V3 供电**；`actual_board_measured=false`、`full_electrical_acceptance=false`。

## 回归与失败保留

准备／真实 UART、旧组件准备、pinout、accepted 来源边界、原生时序、USB CDC、事件 FIFO 回归合计 **81 项通过，107.971 s**，日志为 `targeted-regression-v5.log`。其中诊断准备六项另有 `preparation-regression-v5.log`，检查真实业务固件、精确 FIFO 来源、复位别名约束、15 引脚边界、CLI 隔离、拒绝覆盖和暂存篡改，以及实际 vendor UART 发出的原子 16-word 十六进制行。FIFO 行为回归还覆盖三组时钟比、满／回绕、停钟及复位清空。收尾时再次核对候选清单与当前配方／组件源码，全部来源哈希保持一致。

既有 HS／FS 混合设备交替和 Push 完整帧验证见 [混合热插拔报告](USB2_MIXED_HOTPLUG_20261027.md)。本候选 HS ROM 与其中 HS ROM 相同；本轮没有重新执行那些耗时约十分钟的设备级仿真，也不把旧结果记为新顶层实测。

保留全部尝试，不覆盖旧日志：C127E201 因未被消费的反馈区被优化，原 SDC 对象消失；C127E202 工具成功但真实时序失败；C127E203／E204 因诊断复位合并别名使 SDC 找不到原对象失败。最终 E205 在诊断监测输入补齐同步链、使用真实复位别名及原生 FIFO 适配后通过上述审计。

## 集成与回退

USB 侧后续修改仍落在既有 USB owner／驱动／固件内；独立顶层只做时钟、复位、组合、观察和 CDC。USB 与 HDMI 分别稳定后，再跑原生混合热插拔、真实音频及整机验证。回退只需不再选择 `workstation-hotplug`，不改 accepted 配置或冻结来源。

当前未下载 SRAM、未烧写 Flash。任何下载或烧写先向用户询问，获得明确同意后再执行；该离线候选不登记为板上当前状态。
