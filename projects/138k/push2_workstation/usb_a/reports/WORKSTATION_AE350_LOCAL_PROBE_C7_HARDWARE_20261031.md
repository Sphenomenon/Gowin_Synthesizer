# C06 C7 上板失败证据与 C8 观察修订

本轮按用户授权执行独立探针 SRAM 操作。操作前读回器件 `0001081B`、原 `C11028E5`／`00022020`；核对 [C7 物理产物](WORKSTATION_AE350_LOCAL_PROBE_PHYSICAL_20261031.md) SHA256 后，operation 4 实际写 SRAM。厂商返回 18／`Verify Failed`；随后独立 operation 0 读到 `C21031C7`／`00022230`。这不是完整硬件接受。

115200 8N1 只读打开 `/dev/cu.usbserial-21201` 五秒，没有收到 UART bytes。GAO 正常导出 128 个有效样本，packed bus 与 512 个单独 bit 逐项一致，全部诊断摘要为零；只观察到这一结果，尚不能区分 CPU 复位、启动／总线、观察链或 UART 物理通路故障。

独立 operation 3 读回 21,872 行、每行 1,513 bit，与当前 FS 的 1,584-bit 主矩阵行 `[7:1520]` 切片比较，共 33,092,336 bit、零差异。该经验比较不覆盖 FS 的 5,889 行 496-bit BSRAM，也不替代失败的厂商 Verify。原始读回 SHA256 `bbcec2d55becb08cf338dc96a8c49b56bb2c434f1de4e62837de4a4a27f3673b`。安装目录生成的读回文件已移入证据缓存。

已执行 operation 1 重载既有 Flash；两次中间读数为 `00000000`／`00000460`，第三次独立读回确认原 `C11028E5`／`00022020`。没有写入 Flash，板卡现已回退。

下一身份 `C21031C8` 只扩展探针观察：GAO 高位新增 32-bit reference 域 power-on／PLL qualification／复位／UART 状态与两级同步 ROM sticky，保留低 512-bit 软件摘要及 UART 280-byte 格式。实际七项回归与新 prepare 审计通过，正式固件／100 MHz core／50 MHz bus 保持；C8 尚无物理或硬件接受。字段见[探针维护说明](../rtl/probe/AE350_LOCAL_MEMORY_PROBE.md)，非零平台观察不能代替软件 PASS。

机器记录见 [ae350_local_probe_c7_hardware.json](workstation_task_20261030/ae350_local_probe_c7_hardware.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-local-probe-c7-hardware-parent-v1` 保存源码快照并绑定 55 项外部文件，seal SHA256 `4072993d44fd0e37deb08a2a2c64d2f426bbc9be4e662012c0e84d2bce106478`，`verify.py` 可只读复核。ILM/DLM 容量、Cache、计数器或整机功能均未获得该次硬件接受。
