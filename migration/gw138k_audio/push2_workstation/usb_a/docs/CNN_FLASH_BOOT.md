# CNN 权重持久化与 Flash→DDR 启动

2026-10-10 当前实体结果：完整工作站AD已连续三次通过实际配置Flash重加载，完整模型从Flash自主搬入DDR，CRC32 AF01A61B、状态E/source1；现场三音、立体声、静音及Panic检查通过。诊断结束后已回写并校验full85，板上及LATEST仍为85。B3/B4完成路由且clk50/视频/PLL/CDC均通过，DDR UI仍有负slack，未烧录；B5/B6也因DDR UI负slack被拒绝且均未烧录；B7动态背景/BIST期望寄存正在布线，B8 TF读计数/并行频谱地址正在综合。B3含本地DDR就绪寄存的完整模型仿真已通过52239写/52239读CRC。物理断电/上电尚未执行。逐项证据见reports/CNN_FLASH_BOOT_CURRENT.md及CNN_FLASH_BOOT_IMPLEMENTATION.md。


完整工作站把 FPGA 配置位流和 Basic Pitch 模型分别保存在板载外部 Flash。默认构建采用 `serial` 兼容传输：CPU 完成 DDR/音频/UI 启动自检后，片内 Flash 控制器先完整读取并校验模型，再重新读取、产生内部 `BPN1` 8N1 数据流，交给 full85 原封不动的模型解析器和 DDR 客户端。它使用片内连线，不经过 PC、USB 或外部串口；115200 波特率下模型装载约 9 秒，另加校验和 DDR 回读时间。

此前 `direct` 方案仍保留为实验路径：直接 SPI→DDR、载荷 CRC、DDR 回读 CRC。0x95 完整工程虽然 clk50 收敛且正常从 Flash 配置，实体原有 UART 路径也停在 DDR 回读，CPU DDR/UI 自检出现失败；因此 0x95 没有提升为 LATEST。独立 0x96 SRAM 探针完整读出 Flash 模型并通过本地 RAM CRC，证明 Flash 接线、字节序和载荷有效；探针不代表完整工作站或 DDR 已验收。0x98 SRAM 探针进一步验证实际 115200 波特率的内部 BPN1 传输和原解析器，完整模型本地 RAM 回读 CRC 同样通过。

独立 0x9E 临时 SRAM 探针把传输接到真实板载 DDR，复用 full85 的 DDR 平台/加密 PHY、原模型解析器和 DDR16/CDC 端口，完整 52,239 字写入及 DDR 回读 CRC `AF01A61B` 均通过，来源为 Flash、状态为 E，没有 PC 模型上传。探针三种时钟的 setup/hold TNS 都为零：clk50 Fmax84.488、DDR UI Fmax290.638 MHz；物理 BSRAM32属于DDR控制器等基础资源，没有52,239字模型ROM。探针无CPU/显示/音频DMA并发，不代表完整工作站或物理断电重启验收。测试后 full85 配置与其易失模型已恢复。

默认 `serial` 方案保留 CNN、原模型解析器、DDR16 端口、CDC FIFO、命令缓冲的完整源文件和实例层级。空白/非法头或首遍载荷 CRC 错误时，模型解析器尚未接收任何数据，自动切回外部 UART。第二遍发生变化或 DDR 校验错误则显式失败，需要全局复位后恢复；不会把部分模型当成成功。

模型镜像是现有 `rtl/music/weights/cnn_ddr_blob.mem` 的 52,239 个 16-bit 系数，104,478 字节，CRC32 `AF01A61B`。它不含 PCM、音频文件头、演奏录音或推流内容。镜像构建工具只接受严格的 16-bit 十六进制字表并检查字数。该模型位于独立外部 Flash 分区，启动逻辑没有模型 ROM、没有新增 BSRAM。

## 分区与镜像

| 地址/大小 | 内容 |
|---|---|
| `0x000000..0x5FFFFF`，最多 6 MiB | FPGA 配置位流；当前 full85 二进制 5,283,212 字节 |
| `0x600000..0x60001F`，32 字节 | `BPF1` 模型头 |
| `0x600020..0x61983D`，104,478 字节 | little-endian 16-bit 模型字 |
| `0x10100000..0x1011981D`，DDR byte address | 模型启动后所在的已有 CNN DDR 区 |

模型镜像总长度 104,510 字节；完整打包镜像 6,395,966 字节（位流至模型分区之间填 `0xFF`）。构建器检查分区按 64 KiB 对齐、配置区没有侵入模型区、模型字数严格匹配、镜像没有超过 16 MiB/24-bit 地址范围，任何超限都报错。

头字段如下，所有整数均 little-endian：

| 偏移 | 长度 | 字段 |
|---|---|---|
| 0 | 4 | magic `BPF1` |
| 4 | 2 | 格式版本 `1` |
| 6 | 2 | 头长度 `32` |
| 8 | 4 | 载荷长度 `104478` |
| 12 | 4 | 标准 reflected CRC32（poly `EDB88320`，init/final xor `FFFFFFFF`） |
| 16 | 4 | 字数 `52239`，也是模型 ABI 长度检查 |
| 20 | 12 | 保留字段，必须为 0 |

`basic_pitch_flash_map.svh` 是 RTL 地址常量。打包器默认地址与此一致；调整分区必须一起调整 RTL 和镜像构建参数。

## direct 路径的启动与回退

1. 在 `clk_50m` 域同步 `memory_calibrated && memory_reset_n`，等待校准完成。
2. 拉低已注册的 CS；发送 `03 60 00 00`，用 SPI mode 0 读取头和载荷。50 MHz 时钟、半周期分频 4，SCK 为 6.25 MHz。
3. 在完整字边界暂停 SCK、保持 CS 低，等待现有 DDR 请求 FIFO 接收写入。地址和数据在反压期间保持稳定。
4. 校验 Flash 载荷 CRC；随后通过原有 DDR 端口逐字回读并独立计算 CRC。
5. 成功锁定模型。`basic_pitch_flash_io_guard` 仅在注册 CS 低时驱动共享 CLK/MOSI/CS/IO2/IO3；等待 DDR、复位、校验 DDR 和完成后均三态释放物理接口，由已有上拉/下拉维持闲置电平。`analysis_restart` 不会触发模型重载。模型更新后需要 FPGA 重加载或全局复位。
6. 头错误、Flash CRC 错误、DDR CRC 错误分别记为阶段 1/2/3；此时自动释放原有 `BPN1` UART 装载器。UART 上传仍执行自己的载荷/DDR 双 CRC。

UART 回退等待状态可继续运行原工具：

```sh
python3 tools/upload_cnn_ddr_uart.py \
  --port /dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0
```

成功的 Flash 模型不会被随后收到的 UART 字节改写。分析运行不依赖 PC 上传或 TF 卡内的模型文件。

B138 最后一字的原字段 `[5:2]` 仍是模型状态（`E` 成功）。新增 `[9:8]` 来源：0=Flash 启动中、1=Flash 双 CRC 通过、2=UART 路径、3=片内 ROM 配置。在 UART 回退等待状态 0，`[7:6]` 显示 Flash 失败阶段；UART 工作时恢复为 UART 校验失败阶段。

## 板级接口

| FPGA 端口 | PG484A 引脚 | 板级用途 |
|---|---|---|
| `flash_clk` | L12 | CCLK / MSPI_CLK |
| `flash_cs_n` | T19 | MCS_N |
| `flash_mosi` | P22 | D00/MOSI |
| `flash_miso` | R22 | D01/DIN |
| `flash_wp_n` | P21 | D02/IO2，事务内高、闲置三态 |
| `flash_hold_n` | R21 | D03/IO3，事务内高、闲置三态 |

完整工程保留 `-use_mspi_as_gpio 1`、`-use_cpu_as_gpio 1`。内部 Flash CS/SCK 由触发器输出，物理输出使用 CS 作为总线所有权；IO2/3 闲置时不能固定驱动，以便配置/其他主机使用。避免状态译码毛刺形成伪 SPI 事务。Flash 上电配置由 Gowin 配置逻辑接管，用户态启动搬运使用同一组物理走线。实际 IO 放置和 Flash 启动验收以构建/实体报告为准。

新增约束仅豁免启动就绪同步器（direct 为校准同步器）的第一采样级，并给 MISO 增加相对 clk50 的 15 ns 输入延迟约束。既有音频、DDR、HDMI 时钟和时序检查没有放宽。当前完整工作站基线的整体时序未闭合；完成 Flash 功能验收不等于整个工程时序闭合。

## 构建与验证

在 `usb_a` 目录：

```sh
# 无硬件操作；SYN 不分配 UserCode。
python3 tools/build_workstation_flash_boot.py --flow syn

# 完整候选必须使用全仓库未占用的新 UserCode。
python3 tools/build_workstation_flash_boot.py --flow all --user-code <八位新编号> --transport serial
# 可选实验预算；历史97/99此路线未满足完整时序门槛，不能据命令本身发布。
python3 tools/build_workstation_flash_boot.py --flow all --user-code <另一新编号> --route-option 0 --tighten-cache-reset

# 实验性增量候选：实际 0x93 参考复用产生 12270 条未布通网络，当前发布使用全量 P&R。
# 仍重新综合，仅把已验证 full85 的路由作为 P&R 参考。
python3 tools/build_workstation_flash_boot.py --flow all --user-code <另一新编号> --incremental-baseline

# SPI 物理端口模型、DDR 请求/响应反压、CRC 故障和 UART 回退测试。
python3 tools/test_cnn_flash_boot.py --output /tmp/cnn_flash_tests.json

# 默认兼容传输：完整首遍校验、第二遍变化、实际波特率、UART 回退、DDR CRC。
python3 tools/test_cnn_flash_serial_boot.py --output /tmp/cnn_flash_serial_tests.json

# 小型 Flash/local-RAM 探针的离线综合；无 UserCode、无硬件操作。
python3 tools/build_cnn_flash_probe.py --flow syn --transport serial --output <新目录>
# 探针全构建需新编号，仅用于临时 SRAM；不允许作为完整工作站固化。
python3 tools/build_cnn_flash_probe.py --flow all --transport serial --user-code <新编号> --output <新目录>

# 真实DDR隔离探针，prepare/SYN不分配UserCode；全构建必须新编号。
# 该工件只用于临时SRAM诊断，不得作为workstation固化。
python3 tools/build_cnn_flash_ddr_probe.py --flow syn --output <新目录>
python3 tools/build_cnn_flash_ddr_probe.py --flow all --user-code <新编号> --output <新目录>

# 离线部署/回滚故障测试：使用已完成候选的真实 hash，所有硬件 I/O 用测试替身。
python3 tools/test_cnn_flash_deploy.py --build <完整结果目录>

# 原 CNN 两配置逐层哈希/谱面结果等价回归。
python3 sim/music/run_bp_config_ab.py --simulator verilator --frames 3 --win-len 2048
```

完整构建保留部署 full85 的源文件快照。默认 serial 只叠加 Flash 传输模块、模型输入连线、B138 来源/错误字段、顶层六个 Flash 引脚与约束；CNN/DDR 客户端源文件不变。`--transport direct` 才叠加此前的模型内存端口方案。可选 `--incremental-baseline` 会复制并记录已验证 full85 `.p` 的 SHA256，按官方 SUG1220 使用 `inc_place` 保留布局参考，仍运行全新 RTL 综合和全新布线。此前 0x93 的 `.pr` 增量尝试因未布线网络失败，不再复用。官方手册存在冲突：SUG1220-2.0E将`inc_pnr`文件写为`.p`，较新的SUG100-4.4.6E第42页将布局+布线参考写为`.pr`；不能据此断言93的文件扩展名就是失败根因。当前`--incremental-mode pnr`默认采用`.pr`入口，两份配套参考均复制并核对SHA256；`--incremental-pnr-entry p`保留A0/A1的另一种实验方式，任何未布线网络、工具失败或时序退化仍拒绝验收。参考文件和所有输入在构建前后复核，不覆盖原候选。冻结的 DDR 仲裁、地址图、显示、延迟 DMA 文件逐一核对 SHA256；没有把工作区其他未提交的开发内容并入发布。

可选 `--defer-ddr-startup` 仅用于验证完整工作站 DDR 初始启动顺序：在音频 PLL 与视频 PLL 锁定后连续等待 100 ms，再释放 DDR 平台的初始复位。视频锁定标志独立于 DDR 校准，避免循环等待。门控开启后不受辅助 PLL 短暂失锁影响，原 DDR 平台的恢复逻辑继续负责正常运行；全局复位会重新执行等待。该选项不改 DDR PHY、数据路径、模型解析器或 CNN 缓存。独立真实 DDR 探针已成功，完整工作站的启动根因仍未证实；门控的硬件有效性须由完整板级测试确认。仿真命令为 `python3 tools/test_cnn_ddr_boot_gate.py`，覆盖稳定等待、短锁定脉冲、异步复位、重新启动、释放后失锁及非法参数。

可选 `--retime-cache-read` 把权重缓存的地址有效性掩码与 BSRAM 数据同拍寄存，再组合选择有效输出，维持原来一拍读取延迟和越界读零。统计用八路固定索引计数代替动态数组索引，CNN 算术和计数语义保持一致。独立测试与冻结 full85 逐周期比较 1/31/7488 字缓存、随机反压/复位/越界地址，以及 10,000 周期统计计数；CNN 三帧回归的六层哈希和谱面结果一致。构建命令可加 `--retime-cache-read`，回归命令为 `python3 tools/test_cnn_cache_read_retime.py`。

可选 `--place-option 3 --tighten-video-control` 使用另一布局搜索并把已发现的像素复位/帧统计控制路径限定到 6 ns；原始 148.5 MHz 时钟、全部保持时间及其他时序约束保留，不更改显示RTL。该选项的存在不代表所得候选已通过时序或板级验收。

每个结果目录包含 `cnn_model.bin`、模型 manifest、`workstation_inputs.json`、工具退出结果、资源审计。P&R 成功后才生成 `workstation_with_cnn.bin` 和带位流/模型 SHA256 的 `flash_bundle.json`。

可单独构建模型或打包已有位流：

```sh
python3 tools/build_cnn_flash_image.py \
  --mem rtl/music/weights/cnn_ddr_blob.mem --out /tmp/cnn_model.bin \
  --bitstream-bin <Gowin生成的Prj1.bin> --bundle /tmp/workstation_with_cnn.bin
```

仿真覆盖完整部署模型和 1/31/65536 字边界、校准等待、0 延迟与可变延迟 DDR 响应、随机阶段反压、中途复位、空白分区、头字段错误、Flash 载荷损坏、DDR 回读损坏、真实串行 UART 回退；三态适配器的独立其他主机激励检查 CLK/MOSI/CS/IO2/IO3 闲置释放与无争用，全部 SPI/DDR 测试同时穿过物理三态适配器。独立 NOR 端点检查 opcode/地址，独立 DDR 端点检查每个写入/回读地址和最终每个字，避免只比较状态机内部变量。

Flash 写入必须把模型分区和位流一起记录。原生 Arora V operation54 用于 `.fs` 位流；operation56（C Bin）用于原始模型 `.bin`/整区打包镜像，CLI 必须同时传 `--fsFile cnn_model.bin --mcuFile cnn_model.bin`：前者满足 CLI 的文件检查，后者提供原始字节；单传任一参数会导致无数据/零长度。该调用已用 operation66 与等价的文本 `.data.fs` 交叉校验实际 Flash 字节。镜像工具还输出逐字节等价的 `.data.fs` 容器，官方 `--filestransform 1` 还原结果与原始镜像一致。首次采用 raw-data 操作后须用 RTL 双 CRC 实读确认字节序/偏移；不能仅以 Programmer 的退出码代替自动搬运验收。禁止用 Bulk Erase 操作更新单个分区。实体操作需持有 debugger `2025030317` 的独占锁，写前/重加载后读回确切 UserCode。

验收时保留 UART 只读监听，先执行 SRAM Erase 仅清除易失配置，再执行 JTAG Reprogram（不提供 SRAM 位流），先等待实际目标 UserCode 与正常已配置状态（DONE bit13=1，配置错误 bits0..3 和 Auto_Boot 失败 bits4/9 必须为 0；本板正常值 `0x26020`。直接 SRAM 下载曾出现 `0x26230`，其 DONE 为 1 但自动启动失败位仍置位，不能作为 Flash 启动成功证据），再清空 UART 缓冲、持续接收两秒排空 FTDI 硬件旧包后，重新清空缓冲并读模型状态，要求来源=1 且模型状态=E，再记录多次重加载结果。物理断电/上电与耳机/显示/整曲验收需分别注明是否实际执行。

```sh
# 默认只校验工件与预览命令；实体写入显式加 --program。
python3 tools/deploy_cnn_flash_boot.py <完整结果目录>
# 正式板级验收：三次自主搬运成功后，在同一独占锁下执行实时演奏烟雾测试。
python3 tools/deploy_cnn_flash_boot.py <完整结果目录> --program --exercise-live
```

部署工具先核对原 20 ns clk50 时序、full85 原本满足频率要求的 DDR/CPU/视频各时钟是否出现新退化、板上版本、Flash ID、冻结工件与独占锁。clk50 未闭合或原本通过的时钟退化时默认拒绝实体写入；`--allow-clock-regression`（旧名 `--allow-clk50-open`）仅用于临时的启动诊断，必须恢复基线且不得据此提升 LATEST。先写模型分区并校验地址零处旧位流仍完好，再写新配置位流；三次 SRAM Erase + JTAG Reprogram 后只读监听 UART，且先等待/核对目标 UserCode 和已配置状态；不在 FPGA 配置完成前解释 DDR/UART 报文，要求模型来源=Flash 且状态=E。失败时保存原始日志，并尝试恢复原 full85 配置位流；等待其 UserCode/配置状态通过后，单独通过 UART 恢复原 full85 的易失模型并执行启动检查。回滚上传在独立证据字段里记录，不计入新功能 Flash→DDR 验收。

`--exercise-live` 的三音并发/立体声/静音/Panic 验证属于部署事务：即使三次模型 Flash 启动已通过，只要实时烟雾测试失败，也自动恢复 full85、重新上传其旧易失模型并检查启动。十项离线部署故障测试包含此失败分支，所有 Programmer/UART 操作均使用替身。实体结果仍单独记录，不能以离线测试替代。

完整工作站统一验收入口：

```sh
# 新证据目录；不触碰板卡，不提升LATEST。
python3 tools/verify_cnn_flash_workstation.py <完整结果目录>
# 先做本地资源/源文件/时序/CDC/DDR-TMDS启动/工件检查，全部通过才部署。
# Flash启动与实时烟雾测试在部署器的同一锁和回滚事务内完成。
python3 tools/verify_cnn_flash_workstation.py <完整结果目录> --program
```

该入口拒绝隔离探针、未完成构建、物理BSRAM超过260、clk50未闭合及原通过时钟退化。每次使用独立证据目录，保留前次审计。只运行本地检查时，`hardware_tested=false`；原0x95本地门槛通过而板级失败的事实继续保留，不因本地PASS改变结论。默认不更新LATEST，也不把JTAG重加载计作物理断电试验。

较长的DDR初始等待会让P10维护用的512项写FIFO装满。新`--defer-ddr-startup`构建在CPU/DDR/UI就绪后先通过片内串口发一次MIDI Panic（B0 78 00），调用原效果器的有序flush，再开始Flash模型装载；三字节期间暂停外部PC输入，其余时间直通，USB/DIN接口保持原样。该初始清理会释放启动阶段已按住的音符，现场演奏应等待启动完成。效果器、DMA、FIFO文件不改动。全局复位重新执行一次，PLL后续失锁不重复Panic。

```sh
python3 tools/test_cnn_startup_panic.py
python3 tools/test_cnn_startup_history.py
```

前者以独立位中心解码校验16周期/位和真实50MHz/115200、短就绪脉冲拒绝、最终stop位完成与串口直通。后者模拟48kHz的4800帧DDR等待，先证明FIFO溢出，再调用原有序Panic并确认状态/代际marker恢复，继续驱动45000样本，其中前43000样本与原参考逐拍比较，末2000样本为预期欠载的长停顿故障注入。故障注入末尾的长DDR停顿预期欠载，不作为正常运行成功。此前A1/A2/A3已冻结且没有该清理，不能静默改动工件；即使通过布线也仅是诊断，正式部署器拒绝其未对齐延迟历史的版本。

正式延迟启动验收读取宿主测试命令之前的`startup_panic_epoch`，至少为1；Panic缺失即使模型三次均E也回滚。相关离线测试同时检查缺少对齐的版本在硬件I/O前拒绝、启动Panic成功和Panic缺失后的完整恢复。

可选`--retime-start-delay`仅把原22位歌曲启动倒计时的零值判断寄存，按原装载/取消/重插/歌曲命令优先级计算下一拍标志，启动与重启时刻不加延迟。`python3 tools/test_cnn_start_delay_retime.py`提取full85和补丁后的实际顶层控制HDL，对30000周期、所有控制寄存器、0/1/2/装载/随机边界、同时发生的控制与复位逐拍比较，并运行未强制赋值的2500012周期完整自然歌曲启动倒计时。该选项用于修复A2/9F计数器到CNN控制的慢路径，不改CNN算术或模型。

验收UART在打开前显式置DTR/RTS为低，与实时采集工具一致；监听过程不发BPN1或模型字节。十项部署替身测试也断言这两个控制输出保持低。

可选`--retime-video-telemetry`只将UART观察用的vblank帧计数事件寄存一拍像素时钟（约6.734ns），解除原消隐判定到32位诊断计数器的使能路径。图像、扫描时序、DDR显示读取均未改动。`python3 tools/test_cnn_video_telemetry.py`比较实际旧/新诊断HDL的30000像素周期，计数/Gray输出恰好延后一拍，覆盖连续脉冲、低16位进位及异步复位，其它测频和DDR诊断寄存器同拍一致。


2026-10-09 的A5实体诊断中，Flash配置身份A5/status26020正确、DDR校准及BIST完成，但CPU停在UIBY/0x80000A5C，共享DDR访问故障位为1，模型自动装载尚未开始。100ms延迟没有解决完整工程启动；已恢复full85配置、UART模型E及实时烟雾PASS。A6视频Fmax139.745MHz未通过，未烧录。

逐路径DDR UI报告揭示另一门槛：Fmax摘要对额外受约束的CE/D路径不能代表全部建立时间闭合。full85、A5、A6的同一100MHz DDR UI路径分别出现-3.648/-5.470/-4.314ns违例，从CNN返回FIFO的可写比较穿过共享仲裁，影响各客户端。该违例是已观察事实；是否解释实体启动故障仍是待验证假设。

新可选`--register-response-credit`在原DDR16读入口预留一个返回FIFO槽，以寄存信用切断上述反馈。原DDR16单在途访问、FIFO、仲裁器、模型解析、CNN算术文件均保持原样；额外只有两个状态FF，无BSRAM。读返回提交后空出一拍，观察更新后的写指针再授予下一读信用；写请求不受信用限制。`python3 tools/test_cnn_ddr_read_credit.py`以三种随机种子覆盖每组3204个读/816个掩码写、FIFO满阻止读但允许写、异步消费暂停、1..47周期响应及在途全局复位。它证明访问安全，不能替代实体DDR或CNN音高验收。

`--replicate-resources`启用官方SUG1220所列的`set_option -replicate_resources 1`（默认0），让PNR复制高扇出资源改善物理时序；不改变原时钟和hold要求。A9使用上述信用、缓存/启动谓词/帧诊断补丁、精确full85原DDR启动，无100ms等待。A7则是原版full85除UserCode外完全一致的重构建，用作定位布局变化影响的对照。

正式部署器及统一入口增加`tools/audit_ddr_ui_timing.py`，要求显式100MHz同域setup和hold逐路径报告均存在且WNS非负；正Fmax不能绕过。旧候选缺少hold报告或实际setup为负，默认不满足该新门槛；临时诊断override仍必须保留日志和恢复基线。LATEST保留full85，完整工作站Flash模型自动启动与物理断电均未验收。


A9完成后视频180.580MHz通过，但DDR UI逐路径仍-4.368ns（信用FF到共享仲裁），clk50 -0.108ns，视频PLL_INIT10.594ns超过原10ns预算。未上板；单独的FIFO信用不足以修复整个共享仲裁反馈。A7原full85重构建的配置.bin只有偏移5283189的UserCode字节85→A7变化，其余5283211字节完全一致，关键时序数值完全一致；SDF/VO存在时间戳及等价合并节点命名差异，不声称其字节一致。

新`--pipeline-ddr-arbiter`使用`basic_pitch_ddr_arbiter_pipeline`保留原优先级/公平策略，在原生DDR入口缓存整条命令，在返回口一起寄存256位数据和tag。客户端ready表示进入片内一项命令缓存，原生命令仍按接受顺序发出；缓存排空后再接下一条，最短发起间隔2个100MHz周期。返回延后一UI周期，所有客户端配对消费同一寄存数据总线，不使用上一拍控制配当前原生数据。读tag改为32项，满后背压；BIST与显示读取使用不同tag，避免BIST完成边沿的归属改变。PHY、仲裁之外的DDR16/FIFO、CNN、图像/扫描及效果器算法不改；图像顶层仅将共用返回数据接到新的寄存边界。额外FF和物理BSRAM必须由综合/PNR再核验，不预先声称资源或时序通过。

`python3 tools/test_cnn_ddr_arbiter_pipeline.py`的独立内存模型覆盖全部8客户端，3组4/8/32项tag、各4500余命令/3100余读、masked write及读回内容、原生背压、连续返回、BIST隔离、tag满/排空、全局复位及未带tag返回的显式故障。尚未完成完整实体或显示/效果负载验收。AA使用该补丁，无初始100ms延迟；LATEST保持85。


`python3 tools/test_cnn_flash_ddr_pipeline.py`把完整52239个系数从独立NOR模型通过片内UART、原解析器、DDR16/信用、共享寄存仲裁送入独立掩码原生内存；同时有scan/writer请求及原生背压。全模型52239写+52239读回、CRC AF01A61B、source=1通过，完整模型用加速3125000波特率；31字模型单独使用真实115200波特率通过。不包括物理DDR/板卡验收，也不生成任何音频文件。


DDR流水线的提交顺序：客户端ready仅释放自身请求到片内命令缓存，不表示DDR已完成物理写。缓存一次只占一条命令，下一条（包括读取/显示请求）要等该命令被原生DDR接受后才进入；所以CPU fence之后的读取、BIST写后读、画面发布后的scan读取仍在前序写之后发出。返回tag只在原生读命令被接受时入队，与同拍返回出队可同时发生。吞吐上限由原先的每UI拍一条降为每两拍一条，即最多50M个32字节传输/秒；真实DDR阻塞/scan欠载仍必须上板测，不能由理论1.6GB/s上限或仿真PASS推断。


AA仅作临时SRAM诊断：完整CPU从UIBY走到PASS、UI自检/发布开始正常，Flash模型解析器随后运行，最终DDR读回CRC202C97F0不等于期望AF01A61B，状态F/stage3。未写Flash配置、未把临时SRAM启动计入固化验收，测试后恢复full85 Flash重加载、UART模型E及现场功能PASS。AA布线显示DDR UI -6.783ns（P10写FIFO深度512的异步读到DMA数据寄存器）；原仲裁反馈虽被分段，但信用到ready回路仍-4.628ns；video143.397MHz、clk50 setup+1.053ns但诊断异步复位复制FF的recovery -1.184ns。所有门槛失败事实保留。

后续AB把共享ready改为one-hot优先选择，宽命令数据寄存器只由本地空闲位使能，避免owner编码/再解码和selected-write反馈。所有原优先/公平条件与原生/客户端事务顺序不变，八客户端独立内存模型测试重新通过。AB未启用全局高扇出复制，保持原诊断复位链名称/结构。

可选`--sync-delay-write-fifo`只更换P10维护写FIFO实例类型（65位x512），用真正同步双口BSRAM读取和寄存输出保存替代深层异步SSRAM mux；原delay算法/DMA/读FIFO不变。预取多保存一个输出项，消费顺序和flush标记按原样传递，传输增加若干DDR周期。3组地址宽度2/4/9的双时钟独立队列测试覆盖满/空/环绕/输出背压/65位标记/全局复位后恢复。完整效果器43000样本等价性另跑`python3 tools/test_cnn_startup_history.py --sync-write-fifo`，通过前不把队列顺序测试当作效果器无变化的证明。

此FIFO明确允许物理BSRAM上限从260增加到264（设备340；不是静默放宽），只在元数据声明该新FIFO且精确实例替换/新FIFO源哈希核验通过时适用。普通候选仍上限260。完整PNR超出264即报错；综合及PNR实际占用都需报告。几何路径ROM、CNN模型分区、所有音频文件合规约束不变。


同步FIFO的完整P10仿真已通过：4800冷启动帧后以原有序Panic恢复marker，前43000样本valid/ready/L/R/clip逐拍等价；末2000样本为预期欠载故障注入。one-hot仲裁版本的完整52239权重Flash→原生内存CRC AF01A61B也重新通过。实体结果仍未通过，不能以此更新LATEST。


AB综合实测218BSRAM（原216），其中新维护FIFO2BSRAM；SSRAM单元1049（AA1593），LUT56817（AA57814），FF41654。PNR计量单独核验，不能把综合218误报为完整物理占用。同步FIFO仅要求正常启动的全局复位清空；DDR单域复位恢复并未另行验收，不据此扩展复位功能承诺。


B0可选`--predecode-dashboard --predecode-text-coordinates`在一个enable级内并行计算文字锚点减法、字模索引和卡片命中。渲染器有效/末尾标记增加同样一拍；所有停顿均保持，frame_start动画逻辑保留原时刻。完整1920×1080含分析页和随机元数据/停顿/复位的2,137,105次像素对照通过，独立DDR停顿下的1,036,800双像素渲染器beat内容/地址/valid/last通过。

`--parallel-delay-pointer`只改变DMA读指针+4的组合表达式，32位回绕、非对齐输入和各级进位逐位等价；`--power-two-tf-ring`只对2幂TF环形容量使用掩码，非2幂容量保持原加/比较/减。两项分别通过1,001,024和1,100,022组输入，TF16组合及P10完整效果回归通过；测试输出记录与候选HDL匹配的哈希。CNN算术、CPU固件和DDR PHY仍被冻结。双同步P10 FIFO明确物理上限268/340，任何候选超过即报错；仿真不保存PCM或音频文件。

`--locate-reference-pll-helper`是可选的物理区域约束：采用官方SUG935的GROUP/GRP_LOC，使参考PLL的官方初始化辅助逻辑位于底部左侧R[100:108]C[24:44]。它不更改官方helper/PLL参数、50MHz输入、源哈希或独立10ns全传播验收。区域只作为实际长连线的修正候选，准备验证通过不等于最终布线达标；本选项未加入B0。


当前B2增加两个等价组合修正：`--parallel-dashboard-cards`并行算四个固定动画目标，再按原顺序和缺席回退规则选择，卡片文字几何用carry-save组合减少串行进位；`--lut-tmds-popcount`把8位population count改为两个4位完整真值表并行查找。7,340,032组动画/坐标穷举、完整像素/双渲染器和100,000周期TMDS全部通过。B1与B2的PLL源和物理区域相同。可选`--predecode-background-coordinates`进一步把纯背景坐标条件在前一级捕获，已经完整像素/渲染器对照通过，未加入B2。所有证据均绑定生成HDL的SHA256，实际是否发布取决于完整路由门禁和实体Flash/live测试。


B2完成但时序发布拒绝：clk50 feature-cache地址-2.226ns、DDR UI校准→模型客户使能-1.800ns；没有实体写入。B3增加`--retime-model-memory-ready`同内存域本地calibration寄存，启动level延后1cycle（CPU/BIST/UI完成后才启动模型），全局memory_reset异步清零；该选项不承诺独立PHY复位新行为。`--predecode-wave-heights`把波形shift/clamp放入已有预解码级，`--predecode-background-coordinates`保留一个像素enable延迟；完整像素及renderer对照通过。`--register-arbiter-tag-flags`同拍预测计数full/empty，6组全部8客户端独立内存/背压/回绕/复位测试及52239系数写读CRC通过。`--tighten-feature-read-route`只是更严格19ns物理预算，原20ns、CNN算术/源/固件/PHY保持；不能用预算声明替代真实闭合。

特征缓存读地址备选优化：`--narrow-feature-read-slot` 必须配合 `--retime-cache-read`。保留原完整有符号边界检查，只在合法0..4/0..6/0..2窗口内把乘常数的相对slot限制到3位；无新增周期、BSRAM或CNN算术改动。`tools/test_cnn_feature_read_address.py` 对实际原/新解码HDL的149位输入进行SAT等价证明，FRAME_LIMIT=1/172/512全部成立，并证明三个最大合法地址10559/19711/8447可达。未应用到B3；B4已开始构建，实际源码绑定SAT通过，统一发布门禁在任何硬件操作前重复该绑定检查，均尚未写板。证据为`reports/CNN_FLASH_BOOT_FEATURE_READ_ADDRESS_TESTS.json`。

`--register-pixel-ready` 在原renderer与原ddr_frame_writer之间加入两拍64-bit寄存缓冲，同DDR UI时钟，无BSRAM。输入ready是精确下一占用寄存，完成事件要等全部已接收像素送至writer；原writer仍执行最后DDR数据与元数据握手后发布帧。新增接口的背压/复位/完成测试和完整1920x1080、129601个原生DDR命令逐项比较已通过。发布门禁对实际冻结缓冲/renderer/dashboard/writer源码再次运行协议和完整帧测试；通过不替代真实路由时序。

TF可选 `--parallel-tf-byte-counters` 需要现有 `--power-two-tf-ring` 组合，三个业务计数器只改为逐字节并行进位。全部32-bit数值和6-bit增量的模32-bit结果经SAT证明（含0..63、所有进位及溢出），控制/容量错误/播放字节序保持。`--complete-background-coordinates` 需要背景预解码，把剩余纯坐标/菱形/箭头条件搬到已经增加的同一拍，无进一步像素延迟；完整RGB565和DDR命令比较通过。两个功能都为显式选项，尚未板级验证。

已补强完整renderer测试的实际分析页参数：ENABLE_ANALYSIS=1、SHARED_EXPORT=1、SHARED_RENDER=1、SHARED_WAVE_ZERO_BITS=15，并包含原output_audio_analysis/capture/FFT-ROM源码；全帧RGB565/地址/meta在独立停顿下相同。统一发布脚本使用该参数组合。可选 `--predecode-dynamic-background-ink` 需要完整背景坐标预解码，把原A输入的波形/频谱/峰值判定在原A边界注册；只替换B组合使用，元数据/样本对应及周期保持，完整动态随机像素和实际分析页完整帧测试通过，尚未应用B6。

`--retime-bist-expected-pattern` 只在原BIST READ_REQUEST等待拍捕获当前地址/反码模式，READ_RESPONSE仍原拍比较和统计，没有减少测试地址/轮次，也不改变timeout或完成行为。BURSTS=1/31/257、正常/最终bit故障/所有通道故障/读超时/写超时共15组，含3复位epochs、最早响应/随机等待逐周期等价。统一发布门禁绑定冻结BIST源码重新执行该回归。DDR PHY/原厂IP保持冻结。


可选 `--retime-tf-read-total` 要求 `--parallel-tf-byte-counters`，在接受读请求时保存响应后的精确字节计数，零周期响应仍取本拍计算值。最终不足32-byte的EOF读直接使用committed write_total，其他情况精确加32，包含32-bit回绕。实际变换表达式65-bit输入SAT及36组直接/缓冲/背压/同周期响应协议测试通过。`--parallel-renderer-spectrum-address` 要求 `--predecode-dashboard`，并行计算当前/下一列后由advance选择；新增0周期/0 BSRAM，WIDTH=2/64/1920/2048全部SAT等价且实际分析页完整帧相同。发布门禁分别绑定实际构建源码重跑这些检查。
