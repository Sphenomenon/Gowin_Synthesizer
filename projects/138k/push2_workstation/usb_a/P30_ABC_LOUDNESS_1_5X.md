# P30 A/B/C 响度 1.5 倍源码变更

本阶段只修改 A/B/C 共同的最终 PCM 缩放：在现有 P24 模式平衡之后乘以 `3/2`，再进入原来的有符号 32 位限幅器。这样不会改变五种音色的谐波比例，也不会破坏 A/B/C 之间已经校准好的 A 计权平衡；Push、MIDI、声部分配、连续压力、HDMI、耳机、效果链和 USB 诊断路径没有改动。

修改位置是 `rtl/audio/unified_oscillator_engine.sv` 的 `rounded_magnitude` 计算。没有把 ROM 每个系数直接乘 1.5，因为 A 行已有接近 Q15 满量程的系数，逐项放大会饱和而不能得到真实的 1.5 倍。

## 当前离线检查

使用 `build.py --prepare-only --user-code 0000002B` 生成的工程做 Verilator 检查。单音五种音色的 A 加权 RMS 都约为原 P24 结果的 1.5 倍；常规 32 音和弦没有满量程帧。32 个同音的极限压力测试触发了原有 32 位硬限幅，这是因为 P24 原始极限已经几乎达到满量程，不把这组极限写成“无削波”。

本阶段没有完成 Gowin 综合、布局布线、时序审计、SRAM 下载或实体验收。UserCode `0x0000002B` 只是为你后续手动构建预留的编号；P29A 的 `0x00000029` 和未来 USB IN 诊断重建使用的 `0x0000002A` 不重复。

## 你在 Gowin IDE 中的操作

### 1. 准备一个可打开的 IDE 工程

在仓库根目录执行下面这一条。它只复制冻结工程、叠加当前源码和生成固件，不调用 Gowin 综合器，也不连接下载器：

```sh
cd /home/sphenicidition/Documents/fpga
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py \
  --prepare-only --user-code 0000002B --no-update-latest
```

命令最后会打印一个新的 `build_YYYYMMDD_HHMMSS_ffffff` 目录。进入该目录下的 `Prj1/`，打开 `Prj1.gprj`。不要打开受保护的 Xilinx 工程 `/home/sphenicidition/Documents/fpga/fpga`，也不要打开 `Mega_138K/Dev/Prj1`。

打开后先确认：

- Device 是 `GW5AST-138C`，封装 `GW5AST-LV138PG484AC2/I1`；
- Top Module 是 `gw138k_push_workstation_top`；
- 工程树中有 `constraints/tang_mega_138k.cst`、`constraints/tang_mega_138k.sdc` 和 `constraints/p11.gsc`；
- `legacy_audio.sv` 已包含当前 A/B/C 音频源；
- 输出 User Code 是 `0000002B`。

如果要重新改源码，修改仓库里的源文件后重新执行 `--prepare-only`，不要直接改 `results/build_*/Prj1` 里的临时副本。

### 2. 综合

在 Gowin IDE 左侧 Process 面板中运行 **Synthesis**。完成后查看综合报告，确认没有 Error；Warning 要结合源代码判断，不能把 Warning 当作时序通过。

### 3. 布局布线和时序

继续运行 **Place & Route**。当前工程的约束和 Tcl 选项已经写入准备好的工程：时序驱动布局、hold 修正、place option 2、route option 1，以及文本时序报告。不要删除或添加全局 false path，也不要为了通过报告降低时钟频率。

完成后在 `Prj1/impl/pnr/` 检查：

- `Prj1.tr` 的 Setup Violated Endpoints 和 Hold Violated Endpoints 都为 0；
- 最差 setup slack 为正数；
- Logic、Register、BSRAM、DSP 没有超出器件容量；
- `Prj1.rpt.txt` 中 User Code 仍为 `0000002B`。

如果布局布线失败，先保存完整报告和工程目录，不要删除结果；把错误位置和 `Prj1.tr` 发回来，再决定是否修改约束。

### 4. 生成位流

运行 **Generate Bitstream** 或 **Generate Programming File**。位流应位于：

```text
<本次 build 目录>/Prj1/impl/pnr/Prj1.fs
```

在下载前记下这个文件的 SHA256，并保留同一个 `build_*` 目录。位流、实现数据库和结果目录不要覆盖 P28、P29A 或其他已验收目录。

### 5. 只下载 SRAM

保持 138K 上电，将调试 USB/JTAG 线接到板上的 138K 下载接口；Push 仍接 138K 的 J18 USB-A，HDMI 和耳机保持原接线。不要把网口旁 USB-C/CH569 当作 Push 或音频路径。

在 Gowin IDE 打开 **Tools → Programmer**（也可以启动 Gowin Programmer）：

1. 选择检测到的 Sipeed/Gowin 调试器，执行扫描，确认目标 ID 是 `0x0001081B` 或界面显示 GW5AST-138C。
2. 先做一次只读的 ID/UserCode 检查，记录当前板上版本；如果不是你预期的版本，先停下，不要覆盖它。
3. 添加刚刚生成的 `Prj1.fs`。
4. 操作类型选择 **SRAM Program / SRAM Configure**。
5. 确认 **SPI Flash / Program Flash / Master SPI** 没有勾选。
6. 执行下载，等待 Programmer 报告成功；如果工具提供 UserCode 读回，再确认是 `0x0000002B`。

这一步只改变掉电前的 SRAM 配置。不要选择 Flash 下载；项目的 Flash 写入状态仍应记录为未写。

### 6. 实体验收

下载后先检查单音 A/B/C 和五种音色的音量，再检查普通和弦。重点听极端 32 同音，因为那里可能触发 32 位限幅；如果出现明显失真，先降低总音量或减少同音叠加，再把现象和 UserCode/SHA256 记录下来。随后按原顺序复测 Push pad/连续压力、Push 屏幕与灯光、电脑键盘、MIDI、HDMI、耳机和效果链。

只有当你把 Programmer 的 SRAM 写入结果、写后 UserCode、位流 SHA256 和上述实体结果发回来，P30 才能记录为实体通过。
