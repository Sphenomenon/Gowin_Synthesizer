# 新板 USB2：真实 CPU 执行与组件综合

日期：2026-10-22。基于已推送的 `adc035f4b95b890376174377631589845a040d60`，本轮新增修复仍在工作树中。输入、工具、ROM／网表身份和结果见 [verification.json](custom_board_usb2_cpu_20261022/verification.json)。这不是新板整机候选、P&R 或部署记录。

## 1. 本轮实际解决的问题

[推送快照](CUSTOM_BOARD_USB2_CPU_CHECKPOINT_20261022.md) 的真实 CPU 测试在 HS／FS 都失败，带有 `pc=80000048 fault=b`。根因是锁定 VexRiscv 从 `0x80000000` 启动，而新总线只允许零地址开始的 64 KiB RAM。原来的越界取指诊断从启动时就被触发，不能通过弱化 fault 检查来消除它。

现增加仅指令可见的 64 字节固定启动窗口，返回 `jalr x0, x0, 0`，然后运行零地址的真实启动代码和固件。高地址数据访问、窗口以外的取指和低 RAM 上界仍报错，单测增加对应检查。没有把所有高地址映射回 RAM，没有改 vendor、锁定链接脚本或已接受工作站来源。

真实固件的 ELF、二进制及 ROM 哈希与失败快照相同；修复的是 CPU 启动总线行为，不是换掉测试程序或绕过初始错误检查。

## 2. 实现与可复现输入

- [CPU／SoC 边界文档](../rtl/usb2/CPU_SOC.md) 明确启动窗口、同步 RAM、UART、真实计时器、posted store 顺序、目标 ERROR／超时与外部服务接口；业务参数仍由既有工作站所有者负责。
- 构建与 CPU 仿真统一使用 `tools/workstation_usb2_soc.py` 中的 14 项 RTL 清单。固定 vendor 清单及其全部 20 项输入校验，原始与暂存文件身份校验，缺失／篡改／准备期间变化失败，无私有历史 fallback。
- 现有 `build.py --prepare-usb2-soc --usb2-soc-output <新目录>` 仅准备组件与仿真 probe。拒绝与原整机／pinout／综合复用／UserCode 混合，允许明确指定 RISC-V 工具链；不更新 latest、不自动综合、不提供板级 CST 或位流。
- 固件按 `rv32i/ilp32` 编译，显式链接 `_start`，不使用不匹配的 `rv32im` 对象检查代替实际执行。记录 GCC 13.4.0、输入和产物哈希；60,000 字节静态上限保留。
- 新 probe 为 5,176 字节，静态 RAM 结束于 6,280；补齐 ROM 的 SHA-256 为 `4bc8d6ed012ea09685fc905f8baf81d19137a132f42a1d58aaa6cd80e36b6d43`。静态剩余空间不代表运行期栈峰值已经验收。

当前 probe 使用专用外部测试服务反馈预期伙伴速度、控制故障注入及报告阶段／结果。它不是生产业务固件，不能在板级用常量伪造这些结果来冒充集成。

## 3. 真实 CPU 到真实 25K USB 核

Verilator 中执行锁定 VexRiscv 的实际 RV32I 指令、初始化 ROM、第一方 Host 驱动与 CPU I/O 回调；另一端使用仓库 25K 真实 CDC／SIE，经过同一物理 ULPI 数字模型，不强制 CPU PC、寄存器或协议状态。

HS 和 FS 两条路径均通过：

| 场景 | 覆盖 |
|---|---|
| 启动与错误回报 | 系统 ID、真实未知寄存器读／posted 写、sticky ERROR 与地址、W1C、无残留启动 fault |
| 枚举 | 原生 PHY 自检和协商、GET_DESCRIPTOR、HS EP0 64／FS EP0 8 字节分片、SET_ADDRESS 在 ACK 后提交、再次描述符及 SET_CONFIGURATION |
| 数据 | HS 512／FS 64 字节 bulk OUT／IN 完整逐字节回环、调用方 canary、容量不足在命令前拒绝 |
| 调度与会话 | 真实毫秒计数及 SOF 保活、密封 CPU 结果时根复位、代次变化、旧 RX／DONE 清除、地址归零后重新枚举 |
| 故障恢复 | 通过测试服务令 PHY NXT 停滞，真实驱动收到取消且不发布数据；明确重启重新自检／复位／枚举，最终 CPU fault 为零 |

标称 CPU／参考／ULPI 时钟为 48／50／60 MHz；只缩短接入去抖到 100 µs，50 ms 根复位、10 ms recovery 与真实 SOF 不加速。HS／FS 本轮模拟约 192／188 ms，完成条件还检查设备地址／配置／FIFO、PHY、traffic、实际速度、包数与 SOF，不只看固件 PASS 字样。

这证明真实 CPU 执行链路，不证明 25K MIDI／PL 应用、模拟电气、USB 合规或实板互通。

## 4. 综合、初始化与警告边界

实际 GowinSynthesis V1.9.12.03、`GW5AST-LV138PG484AC2/I1`，14 项明确 RTL 加本轮 ROM，三条原频率 SDC 时钟，无 false path，执行 `run syn`：

- 38 个 SDPB 原语：CPU RAM 的 32 个 bit-plane、锁定 CPU 寄存器文件 2 个、MAC／邮箱 4 个。
- 1,922 个寄存器，低于组件 2,304 的预算；这不是完整工作站的资源检查。
- 从实际网表的 SDPB `INIT_RAM_*` 重建全部 16,384 个 32-bit word，与本轮 64 KiB ROM 逐字匹配；测试还确认修改 INIT 或替换暂存 ROM 会被拒绝。
- 五条综合警告均来自未修改的 VexRiscv／simpleuart。`-Wall` SoC lint 的 134 条 vendor 警告保留；第一方仅一条已明确的 CPU 本地复位同步／异步使用 `SYNCASYNCNET`，回归拒绝其他第一方警告，不宣称完整 SoC 零警告。

独立最终暂存工程为 `/tmp/workstation-usb2-soc-20261022-final`，仅作本机复现；版本化来源与准备入口才是权威。网表 SHA-256 为 `48e9f5ade022791ef436c83fb9e5051993ee5ceaf87422bc0dab1ea6237df7bd`。初始化核对不是综合网表的完整 CPU 仿真，也不是布线后物理 BSRAM／时序／CDC／PLL 证明。

## 5. 本轮完整回归

```sh
GW138K_VERIFY_CLEAN_PREPARE=1 python3 -m unittest discover \
  -s projects/138k/push2_workstation/usb_a/sim -p 'test_workstation_usb2_*.py' -v
```

20 项全部通过，430.596 秒，无 skip：MMIO 7、组件准备 10、CPU 3。包含真实寄存器主机到 25K 的 HS 2,683／FS 4,970 检查，MMIO Gowin 4 SDPB／1,073 寄存器、双时钟邮箱三种 CPU 时钟、真正缺钟／停钟、驱动 ASan／UBSan、RV32I 对象及实际 CPU、来源漂移与配置混用拒绝、真实 CPU ROM 综合核对。

另在 `usb_a/sim/` 执行 `GW138K_VERIFY_CLEAN_PREPARE=1 python3 -m unittest -v test_current_workstation_sources test_stage_usb_firmware test_workstation_pinout test_workstation_baselines`，64 项全部通过，6.661 秒。三条 accepted／resource clean prepare 没有改用新 SoC。两组共 84 个独立 Python 测试，不把速度／时钟／负例子场景或额外重复执行再计数。

## 6. 剩余范围与回退

下一步是把真实工作站固件／服务、Push preload、端点 MPS／toggle／NYET 与 25K MIDI／PL 接到本组件；随后完成新板组合根、时钟／IO／复位、完整 P&R 及各项物理门禁。任意业务程序的 warm reset `.data` 恢复与运行期栈安全还须在业务 profile 明确验证。

功放型号／排线、电平转换器实装问题、HDMI、TF、138K BLE 实际业务／音频路径及实体外设验收仍按 [整板范围](CUSTOM_BOARD_BRINGUP_20261022.md) 推进，不能由 CPU 组件通过替代。没有新的完整工作站位流、UserCode、硬件验收或部署身份。

旧显式工作站配置仍是回退路径；本轮不选择新组件即保持原来源与板上内容。没有 SRAM 下载或 Flash 写入，也未再次自动提交／推送。临时 probe 与综合工程不成为生产唯一输入，业务配置完成后保留边界回归并退出 probe 的部署用途。
