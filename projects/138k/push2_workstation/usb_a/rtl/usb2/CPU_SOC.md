# 原生 CPU／USB2 组件

`workstation_usb2_soc.sv` 只组合锁定的 VexRiscv、第一方总线及原生 USB2 MMIO，不复制工作站业务或公共参数。它是新板整机的待集成组件，不是当前已接受配置的自动替换，没有包含 PLL、板级 IO、DDR、音频或 BLE 业务。ROM 可显式选择枚举 probe 或真实工作站业务固件；后者的 [USB2 backend](../../drivers/usb2/WORKSTATION_BACKEND.md) 已覆盖 25K MIDI／PL 与 Push 软件分包。默认 SoC 保留外部服务端口；显式的 [workstation-input 组件](../workstation/USB2_INPUT.md) 接入原 owner／事件 FIFO，但仍不代表新板整机完成。

## 时钟、复位与启动

输入分别为 CPU 48 MHz、参考 50 MHz、USB3300 ULPI 60 MHz。组合根必须提供实际时钟及符合参考域要求的复位，不能把三个端口当作已实现的 PLL／CDC 门禁。CPU 复位异步置位、两级 CPU 时钟同步释放；相同本地复位由锁定 CPU 的同步逻辑和总线异步复位逻辑使用，lint 单列这一条 `SYNCASYNCNET`，不屏蔽其他第一方警告。

锁定 VexRiscv 是 RV32I，复位 PC 固定 `0x80000000`，而锁定链接脚本的 `_start` 在零地址。总线对指令侧 `0x80000000..0x8000003f` 返回固定 `jalr x0, x0, 0`（`0x00000067`），容纳启动跳转前的预取，然后从零地址执行真实 ROM。该窗口不是高地址 RAM 镜像：数据侧访问仍报错，窗口以外的高地址取指仍报错。vendor 字节、复位向量和链接脚本均不改写。

RAM 为 16,384×32 bit、同步读、四个独立字节写使能，初始化文件为 `usb2_cpu.hex`，复位不清 RAM 内容。两个 profile 沿用锁定的清 BSS 启动代码；不能据此保证业务程序在 warm CPU reset 后自动恢复可变 `.data` 的初始值。当前验证为配置 ROM 后单次启动；板级业务配置须明确并验证启动／重启契约。

## CPU 地址与总线顺序

| 地址 | 功能 |
|---|---|
| `0x00000000..0x0000ffff` | CPU 程序与数据 RAM；高位必须为零，不任意截地址形成镜像 |
| `0x02000010` | UART divider，按字节写使能 |
| `0x02000014` | UART 数据；TX 满时等待，不静默丢字节；空 RX 沿用锁定 simpleuart 返回值 |
| `0x02000050` | 连续 32-bit 毫秒计数，只读；每 48,000 CPU 拍推进一次 |
| `0x02000054` | 连续 32-bit CPU 拍计数，只读 |
| `0x02000058` | sticky fault，低四位 W1C |
| `0x0200005c` | 最近故障地址，只读 |
| `0x02000060` | 系统 ID `0x55324301`，只读 |
| `0x02000100..0x020001ff` | [USB2 MMIO ABI](CPU_MMIO.md)，低八位传给寄存器组件 |
| `0x02000200..0x020002ff` | 外部工作站服务接口；不在 CPU 总线内保存业务参数副本 |
| `0x80000000..0x8000003f` | 仅指令启动跳转窗口，不允许数据访问 |

RAM 数据请求优先于同拍取指，两者共用同步读端口。等待外设时仍可取指。VexRiscv 写命令在接收后是 posted store，但总线在真实目标完成前阻止后续数据请求，所以后续 fault 读取不能越过该写操作。USB CS 保持到 ACK，随后至少有一个 CPU 拍撤销 CS，再接受下一个请求；不重复执行副作用。

外部服务为单个 `valid/ready` 请求，地址／写数据／字节使能在等待时保持；读值和 error 在握手时采样。UART、USB 与服务请求默认都最多等待 480,000 个 CPU 拍（10 ms）。目标不答复时撤销请求，置 fault，不无限阻塞主 CPU。服务实现必须自行定义命令接受／应用与取消契约，不能把一次总线 ACK 冒充业务已经应用。

fault 位依次为：0 非法数据访问／只读寄存器写入，1 目标 ACK 同时 ERROR，2 目标超时，3 越界取指。数据错误读返回零并置 sticky fault，不交给未安装的数据异常处理器伪装恢复；第一方 I/O 回调在真实访问后读取 fault，向驱动返回失败。越界取指同时送入 CPU 的指令错误输入；本组件未安装通用异常恢复程序，不能把该诊断能力当作业务继续运行保证。

`drivers/usb2/workstation_usb2_cpu_port.c` 绑定这些地址。回调不偷偷清其他故障；失败后的 disable 写仍尝试发出，若本身失败则不能宣称硬件已关闭。当前 CPU 中断输入关闭，驱动轮询；以后增加 IRQ 必须同时实现实际服务和中断处理契约。

## 显式组件准备与综合

从仓库根目录执行，输出目录必须不存在：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-usb2-soc --usb2-soc-output /tmp/usb2_cpu_component
gw_sh /tmp/usb2_cpu_component/synthesis.tcl
```

该分支在旧整机流程之前显式返回；默认 `--usb2-firmware-profile probe`，也支持显式 `workstation`、业务诊断的 `--usb2-full-speed-only` 和可选 `--riscv-prefix`。拒绝与 accepted／resource／pinout、综合复用、UserCode 或其他发布选项混合。它不更新 latest，不自动执行综合、不产生 CST 或整机位流，更不操作硬件。

`tools/workstation_usb2_soc.py` 为构建和 CPU 仿真提供同一份 14 项 RTL 清单：12 个第一方原生文件及锁定的 VexRiscv、simpleuart。先核对固定 vendor 描述清单及其全部 20 项输入，再检查原始来源和暂存副本；缺失、篡改或准备期间变化均失败，不回退到历史私有目录。

probe 只编译明确的启动文件、第一方 Host 驱动、CPU port 与 `sim/usb2/cpu_enumeration.c`。`workstation` 显式增加现有生产 `firmware.c`／panel、第一方 backend、锁定 minlibc／USB core，不编译旧 USB 硬件驱动；来源清单按 profile 分开，缺失不回退。两者均用 `rv32i/ilp32`、显式 `_start` 链接入口并保留 60,000 字节静态上限。记录工具链版本、输入、ELF／二进制／ROM 哈希，再补零为完整 64 KiB ROM。此静态门禁不是运行期栈峰值证明。

默认固件仍是**仿真枚举 probe**：外部服务 `f0` 告知预期伙伴速度，`f4` 控制 PHY 故障注入，`f8` 发布测试阶段，`fc` 发布 PASS／FAIL。这些不是生产服务寄存器分配；不得由板级组合根伪造 PASS／业务状态来迁就 probe。业务 profile 使用原 `00h..6ch` 服务合约，不需要 probe 服务；选择生产 ROM 并不代表已经接好真实服务、音频或板级硬件。

生成的 `component_inputs.json` 绑定全部来源、暂存 RTL、三条原频率时钟约束、工程／Tcl 与 ROM。综合后可在 `usb_a/` 下核验实际映射：

```sh
python3 -c 'from tools.workstation_usb2_soc import audit_component_synthesis; print(audit_component_synthesis("/tmp/usb2_cpu_component"))'
```

核验输入身份、38 个指定 SDPB、寄存器预算及全部 16,384 个 ROM word；按目标工具 SDPB 的 32 个 16K×1 bit-plane 初始化值重建，不以“综合成功”推断 ROM 正确。38 个 SDPB 是组件综合原语数，不是整机 P&R 后物理 BSRAM 使用量，不能直接叠加到旧整机资源表。

## 集成与退出条件

业务后端已处理 Push 软件分包、FS 回退、端点 MPS／toggle／NYET 与实际 25K MIDI／PL CPU 仿真，见 [本轮应用证据](../../reports/CUSTOM_BOARD_USB2_WORKSTATION_20261022.md)。进入真实新板配置前，仍必须接入现有工作站服务，补板级时钟、复位、IO 和完整物理门禁。临时 probe／综合工程不得成为唯一生产输入；业务配置落地后保留必要的独立 CPU 回归，退役 probe 作为部署入口的可能性。

回退仍是原有显式整机配置，不选择新 SoC 即可，不需要恢复 vendor、旧基线或刷板。本阶段证据见 [CPU 实际执行记录](../../reports/CUSTOM_BOARD_USB2_CPU_20261022.md)。
