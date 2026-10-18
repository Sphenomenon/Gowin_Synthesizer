# USB1 GAO 观察与采集

本例 GAO 使用**综合后 Standard GAO 插入**：先独立综合 USB 逻辑，再由新的 PnR 进程读取 `.vg` 并插入 `.gao`。普通顶层和 PLL 源文件保持独立；准备脚本生成带观察器的顶层副本，没有新增板级引脚。构建和采集均使用 `debug/usb1_status.gao`，GAO ID 为 `1010101001010011`（`AA53`）。

原实板成功镜像为 `builds/20261016_011545_836351/impl/pnr/ao_0.fs`，可移植清单为 `reports/verified_build.json`。2026-10-16 补上拉后，该镜像已通过 SRAM Program+Verify、12 Mbps CDC 枚举和真实回环。整理目录本身没有新增实板下载；历史证据保留在 `reports/hardware_20261016/`。

## 采样布局

单核捕获 `status_50mhz[63:0]`，宽 64 位、深 128 点、一个窗口。采样时钟直接使用 E2 的 50 MHz 输入，PLL 不锁或 60 MHz 时钟停止时仍可采样。触发表达式 `M0|!M0` 恒真，启动即获取当前快照。

| 位 | 含义 |
|---|---|
| 63:48 | 50 MHz 域观察到的线态变化次数，16 位饱和 |
| 47:32 | 当前连续 SE0 的 50 MHz 周期数，其他线态清零，16 位饱和 |
| 31:16 | 当前连续 FS-J 的 50 MHz 周期数，其他线态清零，16 位饱和 |
| 15 | 两级同步后的 PLL LOCK |
| 14 | 两级同步后的 60 MHz 域 `reset_n` |
| 13 | 两级同步后的 USB bus-reset released，不表示配置成功 |
| 12 | 两级同步后的 attach intent，没有接到外部上拉控制引脚 |
| 11:10 | 两级同步的 `{D+,D−}`：00=SE0、10=FS-J、01=FS-K、11=SE1 |
| 9 / 8 | overflow / received sticky，源端 USB bus reset 会清除 |
| 7 / 6 | 50 MHz 心跳 bit25 / 同步后的 60 MHz 心跳 bit25 |
| 5 | 观察器就绪后曾观察到线态变化 |
| 4 / 3 | 曾连续 SE0 / SE1 至少 150 个 50 MHz 周期，约 3 µs |
| 2 | 观察器已等待 7 个 50 MHz 周期，两级同步初值不再直接参与计数 |
| 1 | 曾连续 FS-J 至少 150 个 50 MHz 周期，约 3 µs |
| 0 | 50 MHz 本地心跳 bit0，逐点交替；解码名 `heartbeat50_fast` |

三个多位计数均在 50 MHz 域本地产生，没有跨域采样 60 MHz 字节计数。连续周期计数约 1.31 ms 后饱和，128 点覆盖 2.56 µs。两根数据线独立同步，跳变附近可能出现暂态组合；该短数字快照用于看静态状态和标志，不能代替 USB 包解码、信号质量测量或完整枚举记录。

普通 `rtl/usb1_device_top.v` 中的 `status` 高位包含字节计数，**本 GAO 没有捕获那些字段**。判断枚举和准确字节数应使用主机报告，不能把 GAO 的线态变化计数解释成收包或回环字节数。

## 本地构建

从本例目录执行：

```sh
sh build.sh
```

`prepare_gao_top.py` 从 `usb1_status.rao` 模板生成 `.gao`，并生成包含 50 MHz 观察器的顶层。该分进程 PnR 流程只加入后综合 `.gao`，不能把输入换成 RTL 插入的 `.rao`。XML 中 `<Mode>Standard</Mode>` 表示分析仪类型，实际插入阶段由构建输入和 PnR 参数决定。

准备脚本依赖 `usb1_device_top`、`clk_50mhz`、`usb1_dp/usb1_dm`，以及普通顶层 `status` 中 15=LOCK、14=reset60n、13=bus-reset released、12=attach intent、9=overflow、6=received、5=60 MHz 心跳。顶层结构或布局更改时应同步复核准备脚本，不能只沿用信号名。

观察器输出经 50 MHz 时钟写入顶层 64 位 `status_50mhz` 寄存器，并使用 `syn_preserve`、`syn_keep`。原成功综合网表实际保留全部 64 个对应 DFFRE 及同步器；只给无扇出的 wire 加属性曾导致整个观察器被综合删除，因此每次以综合网表、PnR 找到的信号及最终产物为准。

Gowin 只启用一个 SDC，本例将 `clock/usb1_clock.sdc` 与 `debug/usb1_gao.sdc` 合并为 `generated/usb1_gao.sdc`。50 MHz 输入和相关 60 MHz PLL 时钟保留，工具在后综合插入后为 `tck_pad_i` 自动建立 20 MHz 约束；实际下载/采集仍使用适配 FT2232HL 的频率。原成功报告的 50/60 MHz/TCK setup 与 hold 违规端点均为 0。

时序仅对稳定 flags 到观察器首级同步器设置窄范围 false-path，保留同步器级间、观察逻辑和 GAO 内部路径检查。PLL 复位同步器的异步入口采用原时钟约束中的窄范围豁免，没有整组时钟或全部 USB 引脚豁免。

安全构建入口在全新 ASCII 临时目录串行执行独立综合和 PnR，并使用全局锁；成功前核对实际 `-gao` / `-gao_crc`、生成的 GAO 网表和位流 `//GAOCRC:`，拒绝误用 `-rtl_gao`。下载仍需以成功清单核对 SHA256 和时序，不能依据旧构建路径推定新产物有效。

## 采集与解码

先通过本例 `program_sram.py` 加载匹配镜像，保留 USB1 供电与下载器连接，再运行：

```sh
python3 debug/capture_status.py --manifest reports/verified_build.json
python3 debug/decode_status.py <生成的_core0_window0.csv> --output reports/status_decoded.json
```

新构建则将 manifest 换成 `reports/last_build.json`。采集默认 FT2CH channel 0、30 秒超时；需要指定位置时，先实际扫描下载器，再添加 `--location <位置>`。下载和采集不要并行占用 JTAG。

采集前校验本地 `.gao` ID 和 manifest 中的位流 SHA256，但这些只能证明本地文件兼容，不能证明板上当前镜像身份。断电、重插供电线或下载其他镜像后，应先确认实际 UserCode 和下载记录；原实测期间，USB1 拔插造成掉电后回到了 Flash 中的 MIDI 镜像，该时点全零 GAO 不能作为 USB1 故障证据。

输出默认使用唯一时间戳，JSON、日志、CSV 写入 `reports/`，拒绝复用已有前缀。解码器按 `status_50mhz[63:0]` 读十六进制，拒绝缺列、越界或未知值。CSV 时间列原样保留；真实采样周期由 50 MHz 决定，不应直接把工具导出的递增时间标签当作 USB 位宽。

## 实板结果解读

补上拉后成功回环的 128 点全部为 FS-J。PLL LOCK、reset60n、bus-reset released、attach intent、received sticky 为 1，overflow 与 SE1 long sticky 为 0，当前连续 SE0 为 0。SE0 long sticky=1 记录之前发生的主机总线复位，不能据此判定当前持续 SE0。详细记录见 [回环后解码](../reports/hardware_20261016/usb1_postchange_pass_status_20261016_2138_decoded.json)。

硬件更改前的历史快照曾持续 SE0、bus-reset released=0，当时尚未枚举。这与更改后的记录应分别保留；本例结论使用补上拉后主机真实枚举、1848 字节逐字节回环及匹配镜像的 GAO 证据。
