# USB2 MIDI 调试配置

保留完整 MIDI_KEYBOARD 应用、USB MIDI／vendor／PL 描述符、端点、控制队列、触摸、灯光与屏幕，只添加独立 50 MHz JTAG 观察路径。不替换为 CDC，不强制全速。默认构建不定义 MIDI_USB2_DIAGNOSTICS，观察逻辑不进入默认硬件；USB1 配置与此选项互斥。

## 构建与采样

在工程目录使用现有 builder：

```sh
python3 tools/gowin_build.py build.tcl --usb2-debug --user-code C12528DA --output /absolute/new/candidate
```

示例身份属于 2026-10-28 调试候选，改变输入后另选 UserCode。Linux 通过 GW25K_IDE_DIR 选择 IDE，TMPDIR 应指向有空间的 ASCII 目录。编程是独立步骤，builder 和采样工具都不自动下载。

Gowin 配置通过 staging 中的 usb2_debug_profile.vh 生效：builder 要求原始头文件严格匹配空配置，只在 staging 中插入调试宏，并记录原始及生成哈希；默认头文件与默认源策略不变，不依赖未支持的全局 Tcl 宏选项。

调试 SDC 与原有板级 SDC 在 staging 合并成唯一生效的约束文件，顺序为原约束在前、调试 CDC 约束在后；记录两个输入及合并结果哈希，原文件不改，不让第二个 SDC 覆盖板级时钟与 I/O 时序。

时序门禁默认要求两个板级时钟；此调试配置额外要求 GAO 的 `tck_pad_i` 为 20 MHz。三个时钟都必须满足各自约束与 Fmax，并通过 setup、hold、recovery、removal 检查；未知、重复或缺失时钟均拒绝。

按候选哈希下载 SRAM 后，使用实际扫描得到的线缆 location：

```sh
python3 tools/capture_usb2_debug.py --manifest /absolute/new/candidate/build.json --location 53 --output /absolute/new/capture
python3 tools/decode_usb2_debug.py /absolute/new/capture/capture_core0_window0.csv
```

采样工具只读取 FPGA 身份与 GAO，不编程。要求候选 routed timing、位流 SHA256、GW5A-25A 型号、UserCode 和 GAO D2B8 一致，采样前后核对板上身份。Linux WINUSB 适配绑定已验证的 Gowin 1.9.12.03 gao_sh SHA256；GDB recipe 在 tools/ 下版本化，不依赖 138K 历史 out 目录。使用独立临时 IPC 目录与共享硬件互斥锁。

## 字段与时钟边界

GAO 使用 50 MHz、128 samples、32 bit 状态总线；高 24 bit 为页载荷，每页连续八拍，四页组成一次提交的快照。缩减的是可选观察字段与寄存器，不扩张业务缓存，也不削减键盘、BLE、显示或 USB 功能。物理资源以该候选实际实现结果为准。

| 页 | 内容 |
| --- | --- |
| 0 | PHY 状态、设备地址、boot error／done、DIR/NXT/STP、LineState 与 UTMI 握手 |
| 1 | boot stage 与 50 MHz 应用侧 MIDI 发送受理 USB-MIDI 字计数（16 bit） |
| 2 | MIDI 接收受理 USB-MIDI 字计数（16 bit）与 1 ms 分频时钟计数（8 bit） |
| 3 | ABI 标记 0x55aa33 |

低 8 bit 分别为页号 [7:6]、online [5]、hs_active [4]、control_online [3]、clock_alive [2]、提交 cohort [1]、心跳 [0]。16 bit MIDI 计数从配置开始并回绕，属于应用侧受理历史，不等于主机已收到，不定义新在线协议字段或业务权威。boot_done 仍来自既有 USB3300 ID、scratch 与配置寄存器校验，不另设成功条件。

原生时钟每 256 拍产生一个 Gray 分频计数，经两级跨域，在 50 MHz 域每 1 ms 求模 256 差值，不依赖 USB 初始化。正常 60 MHz 对应 234／235，量化频率为 count×256000 Hz；该小计数器不用于判定超出 65.536 MHz 的时钟。源快照由 request/ack mailbox 保持，ACK 经两级与额外稳定拍后，只在四页开始前提交，同时冻结本地 MIDI 计数及标志并翻转 cohort。专用 SDC 仅约束 Gray、握手首级及受协议保护的 bundled-data 目的寄存器和现有 hs_sync 首级，保留同步级间与普通业务时序，不使用异步时钟组或整域 false path。

停钟时 50 MHz 心跳及页号仍运行，clock_alive 在完整窗口后归零，源快照保留；旧 boot 状态不表示新读取。解码要求四页各八个连续样本、同一 cohort 和标志，以及正确 ABI 标记；窗口边缘半页、更新中的页和环形回绕不算完整快照。初始化通过、应用 online、主机收到 MIDI、PL 握手成功分别核对。

定向回归为 tb_usb_board_debug、test_usb2_debug.py，以及 run_checks.py 的默认／调试顶层展开。实板证据见 reports/USB2_LINK_DIAGNOSTIC_20261028.md。

## USB-only 快速定位配置

`--usb2-probe` 与 `--usb2-debug` 互斥，选取 `midi_usb2_probe_top`，不是完整键盘或发布配置。它复用同一个 `midi_usb2_link`、USB MIDI 描述符、端点、FIFO 与 HS／FS 状态机，只把应用替换成 MIDI OUT→IN 回送；不带触摸、BLE、屏幕、MK／PL 业务响应。此配置用于定位枚举及实体验证 USB MIDI，不能据此宣称完整25K或138K业务握手完成。定位后将必要修复接回完整键盘，并重新验证真实业务路径；不保留新的编号生产入口。

```sh
python3 tools/gowin_build.py build.tcl --usb2-probe --user-code C12528DC --output /absolute/new/probe
python3 tools/capture_usb2_debug.py --probe --manifest /absolute/new/probe/build.json --location 786 --output /absolute/new/capture
```

此配置在 PHY boot 完成后，继续运行 ULPI wrapper，但将协议 bridge 保持复位250 ms。wrapper 因而实际写入 detached Function Control，随后再释放 bridge，写入 attached Function Control；区别于只复位并停掉 wrapper、未证实改变物理终端的旧 D5 实验。`ATTACH_DELAY_CYCLES` 默认0，不改变完整键盘的既有行为；只有 probe 显式启用延迟。

当前GAO D2BD为256 bit，替代旧DB候选的D2BC／64 bit。解码器拒绝旧宽度；如需读取旧DB，应使用其冻结 `source_snapshot/` 中的工具和配置。最低32 bit沿用完整键盘观察格式，接着32 bit是同格式传输的原生事件历史：PHY状态掩码 [31:24]、有效RXCMD的LineState掩码 [23:20]、rxerror／txvalid／rxactive／txready曾出现标志 [19:16]、UTMI RX字节饱和计数 [15:8]、最后RXCMD [7:0]。不把DIR turnaround当RXCMD或有效数据，不把boot寄存器读回当USB收包。

其余六个32 bit观察流分别携带下表的原生60 MHz统计，每流保持原四页mailbox格式：

| 流 | 原生载荷低24 bit | 高8 bit |
| --- | --- | --- |
| 2 | 原生RXCMD线态最长连续SE0周期数 | SE0连续段数 |
| 3 | wrapper输出UTMI线态最长连续SE0周期数 | SE0连续段数 |
| 4 | 有效RXCMD周期数 | 最后RXCMD |
| 5 | DIR连续为1且NXT=1的PHY输入数据周期数 | 最后PHY输入字节 |
| 6 | UTMI RXVALID字节数 | 最后UTMI输入字节 |
| 7 | DIR连续为0且NXT=1的link确认周期数 | 原生线态[7:6]、UTMI线态[5:4]、原生有效[3]、原生计时已arm[2]、UTMI计时已arm[1]、协议已释放[0] |

累计计数只在boot完成且bridge释放时更新；方向切换首拍不计作数据或link确认。SE0计时还要求PHY处于WAIT_RST／FULLSPEED，并在该阶段先看到有效idle J才arm，排除未知启动线态、250 ms延迟、chirp和HS idle。原生计时保持最后有效RXCMD的LineState，因此即使DIR已经回到0也继续计时；UTMI独立计时，可直接对照wrapper前后。最长周期和累计计数在24 bit饱和，段数在8 bit饱和，USB总线reset不清历史；仅全局reset清除。60 MHz名义换算为周期数÷60微秒，0xffffff表示至少279620.25微秒，不能当成精确时长。

每流快照自身一致，但各流使用独立mailbox，不保证同一原生采样沿；解码明确返回 `statistics_snapshot_atomic_across_lanes=false`。历史计数适合比较一次停止活动后的捕获，不把正在变化的多流瞬时差值当成丢包证据。

builder对probe仅在staging按精确边界裁剪不存在的机械／BLE／显示约束，保留两个原时钟、原ULPI I/O时序、FIFO CDC、观察mailbox及attach_ready首级CDC约束，并记录输入／生成哈希。该USB-only配置明确不要求BLE initializer；完整键盘仍要求原16块ROM，且probe若意外带入initializer会拒绝。定向用例包括 `tb_usb_board_events`、`tb_usb_board_bus_statistics`、`tb_usb_board_attach`：分别检查粘滞历史、原生／UTMI复位时长及方向统计、实际detached／attached寄存器写入；解码回归覆盖256 bit、分流统计及不完整流拒绝。
