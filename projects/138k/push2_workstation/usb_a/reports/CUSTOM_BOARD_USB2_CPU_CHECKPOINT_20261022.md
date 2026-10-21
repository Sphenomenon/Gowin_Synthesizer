# 新板 USB2 CPU 接入开发快照

日期：2026-10-22。应用户“现在先 push 上去”的要求保存当前进度；这是开发中快照，**不是可上板候选、发布或硬件验收**。

## 来源与选择边界

基于 `e88fc9c5565b53e5556329fb954735b8fc26b95e`；本次 Git 提交树标识保存的第一方源码。包含此前尚未提交的 MMIO 邮箱、驱动及回归，以及本轮 VexRiscv 原生总线、SoC 组合、CPU I/O 适配、显式 RV32I 固件暂存函数与 CPU 仿真入口。

未改变已接受整机 profile 的来源选择，也未修改冻结基线或 vendor。新 SoC 由独立测试显式选择，尚未成为新板整机配置；不能把它与已有工作站业务、25K MIDI／PL 后端或 Push 接入合称完成。

[MMIO 阶段报告](CUSTOM_BOARD_USB2_MMIO_20261022.md) 与其 JSON 保留原始验证快照。本轮为独立 RV32I 链接将驱动中的结构体赋值改成逐字段赋值，避免隐式 `memcpy` 依赖；历史报告的输入哈希不代表本次全部源码，不能据其组件综合结果宣称新 SoC 已综合通过。

## 当前验证结果

推送前针对性回归发现 71 项，70 项通过、1 项跳过，耗时 7.191 秒：

- CPU 总线单元测试通过 25 个检查，覆盖 RAM 字节通道、仲裁、posted-store 错误及超时。
- MMIO 时钟故障、驱动 ASan／UBSan、RISC-V 对象编译、双时钟邮箱与同步 RAM 推断检查通过。
- current-workstation sources 10 项、firmware staging 6 项、pinout 25 项、baseline 23 项通过；baseline 启用 `GW138K_VERIFY_CLEAN_PREPARE=1`。
- 本次环境的 PATH 中没有 `gw_sh`，目标 RAM 映射综合检查跳过；未将跳过记为综合通过。

复现针对性回归，在 `usb_a/sim/` 执行：

```sh
GW138K_VERIFY_CLEAN_PREPARE=1 python3 -m unittest -v \
  test_workstation_usb2_soc.NativeCpu.test_cpu_bus_memory_ordering_and_faults \
  test_workstation_usb2_mmio.CpuBoundary.test_live_reference_diagnostics_without_phy_clock \
  test_workstation_usb2_mmio.CpuBoundary.test_first_party_driver_with_bounded_io_model \
  test_workstation_usb2_mmio.CpuBoundary.test_first_party_driver_compiles_for_workstation_riscv \
  test_workstation_usb2_mmio.CpuBoundary.test_mmio_gowin_component_uses_four_block_rams \
  test_workstation_usb2_mmio.CpuBoundary.test_dual_clock_packet_mailbox_and_cancellation \
  test_workstation_usb2_mmio.CpuBoundary.test_bridge_buffers_have_separate_synchronous_clocks \
  test_current_workstation_sources test_stage_usb_firmware \
  test_workstation_pinout test_workstation_baselines
```

独立固件已用 `rv32i/ilp32` 编译链接，二进制 5,176 字节、静态 RAM 结束位置 6,280；这仅证明链接和静态空间检查通过，不证明 CPU 执行正确或运行期栈安全。记录的 ROM SHA-256 为 `4bc8d6ed012ea09685fc905f8baf81d19137a132f42a1d58aaa6cd80e36b6d43`。

## 已知未通过项

真实 CPU 执行测试 `NativeCpu.test_actual_rv32i_firmware_with_high_and_full_speed_25k` 最近一次运行 **HS 与 FS 均失败**，不是 skip。两个子场景都报告：

```text
CPU stage 00000003
firmware failure bad00003 pc=80000048 fault=b addr=80000054
Ran 1 test in 7.620s
FAILED (failures=2)
```

复现：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_soc.py \
  NativeCpu.test_actual_rv32i_firmware_with_high_and_full_speed_25k
```

故障根因尚未定位，不能把总线单元测试、固件链接、历史寄存器主机到 25K 的通过结果替代真实 CPU 枚举。后续先修复该测试，再补显式整机来源配置、业务固件接入、完整综合／P&R／时序／CDC／PLL 和硬件验收；不放宽现有门禁来消除失败。

## 集成与回退

临时固件及仿真输出不是生产输入，未提交生成的 ROM、位流或实现数据库。暂存函数与独立 CPU probe 的退出条件是由版本化新板配置选择真实业务固件并通过 CPU 到设备回归；保留必要的独立边界测试，不把临时目录当作长期构建来源。

现有显式工作站配置仍按原路径构建；不选择新 SoC 即保留当前回退路径。此次没有 SRAM 下载、Flash 写入或其他板端操作，未产生新的部署身份。
