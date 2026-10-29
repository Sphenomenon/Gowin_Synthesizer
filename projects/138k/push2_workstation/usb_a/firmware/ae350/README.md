# AE350 工作站固件维护入口

这里维护 AE350 的 UI／服务固件，USB Host 的 VexRiscv 固件仍由 `stage_usb_firmware.py` 单独编译。实时合成、效果、分析与绘图不迁入此目录；这里保留现有 AE350 的辅助页面和请求语义，后续业务迁移另立任务。

`provenance.json` 记录从 `resource_rework_route0` 锁定基线导出的九项 C／头文件／启动汇编／链接脚本及其原始 SHA256。原始 `ui_main.c` 和 `ui_model.h` 实际来自基线对象，不能直接使用早期 `results/.../firmware` 中同名文件替代。旧 `projects/138k/ae350/scripts/build_workstation.py` 引用缺失的历史目录和 Linux 编译器绝对路径，不作为这里的构建依赖。冻结基线、原始清单和旧 ROM 保留原字节。

首次导入后，`ui_render.c` 中两个已停止调用的旧键盘绘制 helper 改为 `static inline`，使其在当前 GCC 的 `-Werror=unused-function` 下可编译；原有调用路径和界面行为不变。每次构建报告 `changed_from_import`，之后的维护修改直接落在本目录，不改基线对象。

从仓库根目录执行，输出目录必须不存在：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/stage_ae350_firmware.py \
  --output /tmp/ae350-new-candidate \
  --riscv-prefix /opt/homebrew/bin/riscv64-elf
python3 projects/138k/push2_workstation/usb_a/sim/test_stage_ae350_firmware.py
```

GNU bare-metal RISC-V 工具前缀也可由 `GW138K_RISCV_PREFIX` 或通用工具发现机制提供，需要 `gcc`、`objcopy`、`size`、`nm`。目标 ISA 为 `rv32im_zicsr`，ABI 为 `ilp32`，保持原固件的 `-O2`、freestanding 和不使用 small-data 假设。四份编译输入为 `start.S`、`ui_main.c`、`ui_render.c`、`ui_runtime.c`；头文件和 `boot.ld` 全部复制进独立输出，编译前后检查身份。

输出包含 ELF、原始 binary、4096 个小端 32-bit 字的 `boot.mem`、linker map、section size、符号表、编译日志、逐函数 `.su` 栈报告及 `build_metadata.json`。元数据登记工具版本、命令、所有维护输入 SHA256、ELF／binary／ROM SHA256，以及与锁定历史 ROM 的逐字比较。不同工具链或维护源码生成的 ROM 可以不同；只有真实字节相同才报告复现，不复用历史验收身份。

ROM 位于 `0x80000000`，容量 16 KiB；物理工作 RAM 为 8 KiB，前 512 bytes 留给启动诊断，globals 从 `0x200` 开始，栈顶 `0x2000`。链接与独立符号检查都要求 globals 不越过 `0x1000`，至少保留 4 KiB 栈；报告包含对齐／空洞在内的静态 RAM 占用和实际剩余容量。编译器逐函数栈值只用于检查单帧容量，不等于完整调用链上界或实板水位，后两项仍需 C04 验证。

调用接口为 `stage_ae350_firmware(root, output, riscv_prefix=None, *, reference_mem=None)`，其中 `root` 为 `usb_a`。函数仅生成候选固件和证据，不修改任何准备工程，也不操作板卡；显式选择此入口的配置须把新 `boot.mem` 安装到自己的 `stage/firmware/boot.mem` 并纳入整机 manifest。accepted／pinned／resource 的原锁定来源不会因为新增维护入口自动改变。`--reference-mem` 仅更换比较对象，不能借此变更输入来源或硬件验收结论。
