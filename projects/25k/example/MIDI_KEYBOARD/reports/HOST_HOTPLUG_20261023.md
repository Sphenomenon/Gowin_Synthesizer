# 25K 适配 138K 热插拔（2026-10-23）

本轮按用户明确授权修改 25K 面板工程、综合并固化。远端 `origin/main` 与本地 HEAD `f502f28f329c6665e4a6150583e390b2c9611cef` 一致，`git fetch`／`git pull --ff-only` 没有待导入提交；完整设备工程已在 `projects/25k/example/MIDI_KEYBOARD`。本轮不提交、不推送，不覆盖其他人的 138K／BLE 工作区修改。

## 当前交付状态

**25K 已固化 `0xC1251031`。** 完整综合、布局布线、最终时序及 39 个 HDL／25 项 Python 完整回归通过；Flash 写入校验成功，重载稳定后两次读取均为 UserCode `0xC1251031`、状态 `0x70022020`。原 `0x0000A25D` 的两份完整 Flash 备份保持不变。仅完成 25K 固化与配置读回，未完成断电冷启动或触摸板至 138K 的整机实物验收。

机器记录及逐文件哈希见 [release.json](host_hotplug_20261023/release.json)，构建、回归和部署阶段分别见 [build.json](host_hotplug_20261023/build.json)、[validation.json](host_hotplug_20261023/validation.json)、[deployment.json](host_hotplug_20261023/deployment.json)。本轮未提交或推送代码。

138K 新板当前依据为 [a13 蓝牙接入记录](../../../../138k/push2_workstation/usb_a/reports/CUSTOM_BOARD_NATIVE_BLUETOOTH_20261023.md)：已完成完整综合和针对性离线验证，实际物理任务使用经审计的 a12 网表和 a13 约束，仍待最终 STA／CDC／PLL 及实物验收。USB3300／TXS 的已知 1.8 V 电平冲突尚未修正，不能放行板间 USB 实测；25K 固化成功不消除该硬件阻断。不能把旧原生装配候选的 SRAM 核心检查当作当前新板部署。本轮只操作用户接好的 25K，不操作 138K。

## 最终候选身份与物理结果

配置为 `midi_keyboard_top`、`HOST_PANEL_CONTROLS=1`、`GW5A-LV25MG121NC1/I0`，工具为 Gowin V1.9.12.03。输入清单 SHA256 为 `b04c0264653c9e9644cee94a2bb238a98e6c6422ddcee8672e06c890ce76d406`；逐项输入哈希及来源 HEAD／diff 见构建清单，完整源码快照保存在 `../results/hotplug_20261023/build_romstream/source_snapshot/`。

位流为 `../results/hotplug_20261023/build_romstream/impl/pnr/midi_keyboard.fs`，SHA256 为 `809f93e1c548e6700e2721dafd5f44cb0cb54a35f33a3e466603deeeb26383a1`，UserCode `0xC1251031`，SecurityBit／Encryption 均 OFF、CRCCheck ON，无 GAO。

| 最终物理检查 | 结果 |
|---|---|
| 逻辑／寄存器／CLS | 21,396/23,040；10,166/23,280；11,262/11,520 |
| BSRAM／DSP | 物理 54/56；3/28。综合等效 BSRAM 为 40，不与物理数混用 |
| setup／hold 违规端点 | 0／0 |
| 最差 setup／hold | +0.031／+0.210 ns |
| 最差 recovery／removal | +3.964／+0.851 ns |
| 50 MHz／ULPI Fmax | 50.079／67.828 MHz，保持 20.000／16.666 ns 原约束 |

完整 [P&R 资源报告](host_hotplug_20261023/routed_resources.txt)、[时序报告](host_hotplug_20261023/routed_timing.tr) 及 [综合资源报告](host_hotplug_20261023/synthesis_resources.xml) 已归档。setup 余量很小，不能把本次结果外推为其他输入或布局的时序通过。

## 最终实现

- 保持 16 键、触摸条、两个编码器、灯光、NV3007、USB MIDI、PL 显示及 BLE MIDI；USB 接 138K USB-A，Push／25K 轮流使用。
- 恢复并重新验证设备侧三个缺陷修复：加入 BLE 同拍不吞 USB 短按；物理持音目标独立于移调临时 Note Off；队列满时保留尚未发送的最新弯音，单次释放也最终回中。新连接不继承旧消息或持音，存活链路保留自己的目标。
- 64 项队列载荷改为八银行同步 BSRAM、六个固定写入槽、互斥银行选择和下一读地址预取。队首未提交或刚发生同址写入时等待读取稳定，避免依赖 BSRAM 冲突行为；空队列首项最多增加两拍等待。保留同拍多控件接受、按键释放优先和稳定输出槽；不靠缩队列、移除外围或放宽时钟／例外实现资源收敛。
- 256 个弯音位置按原分段整数公式在展开时生成查表，输出逐点一致。
- 队列内部压为 32 位，保留原时间戳、通道、完整弯音值、Program 及 CC7／88／89，出队重建原 MIDI 字节及长度；未改变 USB／BLE 协议。限制及仿真断言见维护入口。每银行单个 SDPB，减少物理 BSRAM 碎片。
- BLE HCI 初始化去除 260 字节寄存器发送缓存，复用原补丁 ROM 和 H5 连续复制地址进行提前一拍读取；短命令参数按地址生成。完整固件、配对、广播、重传、超时及版本拒绝行为保留，不修改独立 BLE 业务协议工程。
- 沿用既有构建入口，支持 Linux 工具包装器／系统临时目录，要求新 UserCode，并为每次运行独立保存源码快照、输入哈希、综合／P&R／时序和位流身份。历史清单、vendor、冻结输入及导入报告保持原样。

公共参数由 138K 统一初始化和应用；25K 不盲发初始化或重连回放。USB／MIDI／PL 线规、端点、键序、管脚和约束未改。维护入口及容量／故障规则见 [HOST_HOTPLUG.md](../docs/HOST_HOTPLUG.md)。完整双向参数同步、4×4 专有效果上下文和 D 整机接入仍按根接口规划单独完成。

## 验证依据

本机完整证据位于 `../results/hotplug_20261023/`，生成网表、数据库、位流和 Flash 原始备份留在忽略目录，不进入源码变更。

| 检查 | 结果与边界 |
|---|---|
| 修复前缺陷复现 | 三场景分别失败，见 `baseline_scenario_1.log` 至 `baseline_scenario_3.log` |
| 最终设备完整回归 | `romstream_final_regression/validation.json` 通过：39 个 HDL 测试台、25 项 Python 测试、USB HS／FS、错误 BLE ROM 拒绝及原始清单完整性，共 90 项检查；`inputs_changed_during_run=[]`，无失败项。共享输入逐项与最终构建／当前源码一致 |
| BLE ROM 顺序预取 | `romstream_ble.log` 通过全部 30,147 个补丁字节、120 个分片回显、UART8E1／H5、UUID 发现、通知／读／写、RX 背压、重连及复位；`romstream_wrong_rom.log` 通过不兼容 ROM 在下载前拒绝 |
| 控件与队列定向回归 | 16 键、256 弯音位置、48 混合控制、持音移调、满队列 68 条已受理短按后回中、旧会话作废、存活 BLE，以及同拍五事件的 25 批保序／两次回绕通过 |
| 同步存储映射与网表行为 | `probe_word32/` 小模块综合实际生成 8 个 SDPB，2,615 LUT／143 ALU／793 寄存器；相同输入的 RTL 与 GW5A 原语网表运行 12,000 周期，19,087 行输出逐字节一致，两个轨迹 SHA256 均为 `b6e6437a1af6249fd6fc96bdde8a2090f7e151fe0cb2c7587f55fce431624d33`。包含连续多事件、满队列、背压、按键、移调、链路变化和同址读写；不是物理时序仿真 |
| 138K 生产 Host＋真实 PL 端点 | 1019 次请求、两次完整重画、manual／恢复和心跳通过，见 `host_pl/` |
| 原生 USB2 生产应用 | FS／HS 两种软件／RTL 模型通过，见 `native_application/`；不是实物 High-Speed 验收 |
| 138K 输入组件追加回归 | FS／HS 真实 owner／FIFO／CDC、136 个事件、丢弃 20 个旧事件及 detach／reattach 通过；8 项测试中另有 1 项 lint 警告数量断言失败：当前他人改动的 CPU bridge 多一条 `SYNCASYNCNET`。保留 `native_input_console.log`，不修改 138K 代码或放宽断言 |
| accepted 输入边界 | 10 项通过，见 `source_boundary_console.log` |

资源失败记录保留：`0xC1251023` 为 34,497 逻辑单元，`0xC1251024` 为 27,016，`0xC1251025` 为 25,203，`0xC1251026` 为 25,608，`0xC1251027` 为 23,369，`0xC1251028` 为 23,141，均超过 23,040 上限，未生成可交付位流。`0xC1251029` 综合通过（20,626 LUT＋1,955 ALU），但 P&R 指出物理 BSRAM 为 70/56，不能用综合等效 48 块掩盖超限；此候选同样未生成可交付位流。最终 32 位载荷据此减少银行 RAM 的物理碎片。

`0xC1251030` 物理 BSRAM 降至 54/56，但 P&R 为 22,814 逻辑、11,520/11,520 CLS，787 条网络未布通；保留 `build_word32/` 的诊断清单和暂存路径，不发布该候选。`0xC1251031` 以减少 HCI 寄存器缓存及其宽译码来继续收敛，不放宽时钟或例外。

小模块探针确认应使用 Gowin `syn_ramstyle="block_ram"`，并据此改为固定事件槽、互斥写选择和同步读取等待；后续将目标掩码也改为按银行单写口提交，并去除受 valid 保护的暂存载荷复位。`blockram_regression/`、`fixed_regression/`、`readwait_regression/` 与 `mask_regression/` 各自的完整回归通过；另两次中间回归因运行期间修改源码被输入稳定性门禁拒绝，不能算最终通过。最终通过记录为 `0xC1251031` 的未变化输入及其独立完整回归。

## 固化与回退

目标板 JTAG ID 已确认 `0x0001281B`、原运行 UserCode `0x0000A25D`、状态 `0x70022020`，Flash 为 `0x0B4017`。当前 Linux 上使用 Gowin libusb cable-index 5、location 54、2.5 MHz；此前 FT2CH 通道探测的失败日志保留，退出码为零仍须检查输出错误和实际读回。

原 Flash 从地址 0 独立读出两次，每次 8,388,608 字节，SHA256 均为 `83bbe0251e2494238c8c1832cc9f1b1b2d4d2ef1c2bef0982880dc4cbb9c670f`。备份为 `../results/hotplug_20261023/hardware/before_flash.bin` 和 `before_flash_repeat.bin`，机器记录为 `hardware/backup.json`。Flash 探测后已重载原配置并读取原身份。回退以此完整原始镜像恢复；不能依赖导入报告里不存在于本机的 macOS 位流路径。

本次先校验构建／完整回归／当前源码／快照的哈希一致，核对位流型号、未加密／未保护状态、UserCode 及 SHA256；确认当前板仍是已备份的 `0x0000A25D` 后，执行一次 Flash 擦写与校验，工具报告 `Program and Verify Flash successfully.`，耗时 21.54 秒，随后从 Flash 重载。

紧接重载的首次读取早于配置完成，返回 UserCode 0、状态 `0x30000460`；原始失败门禁记录保留在 `../results/hotplug_20261023/hardware_c1251031/deployment.json`，没有因此重复擦写。配置稳定后另行执行两次只读复核，两次均返回 `0xC1251031 / 0x70022020`；完整延续记录为 `hardware_c1251031_verified/deployment.json`，已归档为上方部署清单，并保留首次读取日志。原脚本与延续验证脚本的身份分别记录，不把首次读取改写为通过。

回退可用原始备份执行 `openFPGALoader -c ft2232 --freq 2500000 --write-flash --file-type bin --offset 0 --verify <before_flash.bin>`，随后重载并核对 `0x0000A25D`；该回退写入未在本轮执行，不能称为已演练。生成位流及两份原始备份均留在忽略目录，不混入源代码。

最终部署记录与构建阶段分开，不能将任何阶段的 `passed` 当作实物音频／屏幕验收。未进行物理断电冷启动、实际触摸至 138K 发声及 LCD 全链路验收；这些不由离线测试或 JTAG 配置读回代替。完整双向参数同步、4×4 专有效果上下文与 D 整机接入仍是根规划中独立的未完成范围。
