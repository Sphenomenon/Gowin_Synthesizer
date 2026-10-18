# USB1 无枚举时的 GAO 观察

`build_gao.tcl` 使用**后综合 Standard GAO**：先独立综合 USB 逻辑，再在新 PnR 进程中读取 `.vg` 并插入 `.gao` 分析仪。2026-10-16 已完成构建、SRAM Program/Verify 和一次128点采集；普通 `build.tcl`、`rtl/usb1_device_top.v` 及 PLL 源文件不因此改写。可选入口生成顶层副本，追加观察模块和状态寄存器，不改变 USB1、LED 或其他引脚的输出行为。

`prepare_gao_top.py` 从 XML 模板 `usb1_status.rao` 生成供本流程使用的 `usb1_status.gao`。构建和采集均使用 **`.gao`**；不能给分进程 PnR 流程加入 RTL 模式 `.rao`，也不能在采集时换回 `.rao`。XML v3.0 中的 `<Mode>Standard</Mode>` 是分析仪类型；这里的 RTL/后综合插入阶段由构建输入类型和 PnR 参数决定。独立 GAO_ID 为 `1010101001010011`（AA53），与 BLE 的 4C64 不同。

单核采样 `status_50mhz[63:0]`，宽64位、深128点、1个窗口。采样时钟直接使用 E2 的50MHz输入 `clk_50mhz`；即使 PLL 不锁或60MHz时钟停止，观察器仍能记录PLL标志和USB线态。静态表达式 `M0|!M0` 始终为真，启动采集即可得到当时快照，不依赖枚举或PLL成功。

## 状态布局

| 位 | 含义 |
| --- | --- |
| 63:48 | 50MHz域观察到的线态变化次数，16位饱和 |
| 47:32 | 当前连续SE0的50MHz周期数，遇其他线态清零、16位饱和 |
| 31:16 | 当前连续FS-J的50MHz周期数，遇其他线态清零、16位饱和 |
| 15 | 两级同步后的PLL LOCK |
| 14 | 两级同步后的60MHz域reset_n |
| 13 | 两级同步后的USB bus-reset released；不是SET_CONFIGURATION成功 |
| 12 | 两级同步后的attach intent；当前板上未接到受控1.5k上拉，不能据此认定主机看到attach |
| 11:10 | 直接在50MHz域两级同步的 `{D+,D-}`：00 SE0、10 FS-J、01 FS-K、11 SE1 |
| 9 / 8 | 同步后的overflow / received sticky；源端USB bus reset会清除它们 |
| 7 / 6 | 50MHz心跳bit25 / 同步后的原60MHz心跳bit25，需隔足够时间重复采集才会翻转 |
| 5 | 观察器就绪后曾观察到线态变化 |
| 4 / 3 | 曾连续SE0 / SE1至少150个50MHz周期（约3µs） |
| 2 | 观察器已等待7个50MHz周期，两级同步初始值不再直接参与计数 |
| 1 | 曾连续FS-J至少150个50MHz周期（约3µs） |
| 0 | 50MHz本地心跳bit0，逐采样点交替；解码字段 `heartbeat50_fast` |

这三个多位计数都在50MHz域本地产生，没有采样60MHz多位字节计数，也不采可能漏掉的单拍recv_valid。16位连续周期计数约1.31ms后饱和。128点覆盖2.56µs，适合观察静态状态及短窗口变化，不能当作完整USB枚举记录。两根线分别经同步器采样，在跳变附近可能出现暂态组合；计数和粘滞位表示数字观察结果，不能证明USB信号质量、包CRC、主机驱动方向或协议正确。判定枚举/数据链路仍需主机的VID/PID记录和真实CDC回环。

## 观察信号在综合中的保留

`prepare_gao_top.py` 依赖普通顶层模块名 `usb1_device_top`、时钟端口 `clk_50mhz`、USB端口 `usb1_dp/usb1_dm`，以及现有 `status[63:0]` 中15=LOCK、14=reset60n、13=USB bus-reset released、12=attach intent、9=overflow sticky、6=received sticky、5=60MHz心跳。脚本检查关键结构出现次数；若顶层或status布局改变，需先复核这些连线。可选顶层写入 `generated/usb1_device_gao_top.v`，构建清单不同时加入两份top。

后综合GAO插入之前，观察逻辑必须已经存在于 `.vg`。生成顶层将观察器输出先接到 `status_50mhz_raw`，再经50MHz时钟写入顶层64位寄存器 `status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */`。GAO捕获的是这一级寄存器，较原始观察器输出晚一拍；异步flag和线态此前还经过 `meta`、`sync` 两级。bit0使用真实心跳，避免保留位变成常量。

成功构建 `20261016_011545_836351` 的实际综合网表保留了 `u_status_observer`、全部64个 `status_50mhz_*_s1` DFFRE，以及flag两级同步寄存器；PnR能找到全部64个待观察信号。先前仅给无扇出wire加 `syn_keep` 时，综合会删除整个观察器。属性是实现手段，实际 `.vg` 中的触发器及连线才是每次构建的核对边界；不能仅凭RTL名称或属性宣称观察逻辑存在。当前方案也未导出新顶层观察端口或占用额外板级引脚。

`ASYNC_REG` 标明同步器意图，不能代替器件布局或CDC签核。原60MHz计数仍在普通顶层中，本次GAO不引用它们。

## 时钟与安全构建

从工作区根目录执行：

```sh
sh prj/tools/gowin.sh prj/usb1_device/build_gao.tcl
```

Gowin只启用一个SDC文件。准备脚本把普通 `clock/usb1_clock.sdc` 与 `debug/usb1_gao.sdc` 合并成 `generated/usb1_gao.sdc`，构建仅加入合并文件，保留50MHz输入与60MHz PLL时钟。

后综合GAO在用户SDC处理之后才插入JTAG对象；本机此时用 `get_ports` 或 `get_pins` 均无法引用这些新对象，不能靠猜测名称手工创建TCK。成功报告由工具自动定义 `tck_pad_i`，对象 `tck_ibuf/I`，周期50ns（20MHz）。本机FT2CH安装工具列出的频率最高15MHz，操作保持在这一范围。每次仍须核对最终报告，不能从另一个项目推断时钟已建立。

只对60MHz稳定flags到观察器首级 `u_status_observer/flags_meta_*_s0/D` 设置窄范围false-path；`flags_meta→flags_sync`、50MHz观察逻辑以及GAO内部跨域继续接受时序检查。没有全域CDC时钟组或USB引脚时序豁免。成功构建报告列出50MHz、60MHz、20MHz三个时钟，setup/hold违例端点均为0；该结论以本次实际网表和约束为限。

[安全包装器](../../tools/README.md) 使用全新英文临时目录，串行启动独立综合/PnR进程；PnR日志必须确认跳过综合。成功发布前检查 `cmd.do` 中真正的 `-gao` 与 `-gao_crc`、生成的 `impl/gao/gao.v`，并拒绝 `-rtl_gao`；bitstream的 `//GAOCRC:` 必须与本`.gao`的ID匹配。只使用成功清单中的新路径并核对SHA256。

## 采集与解码

先按主流程向SRAM下载匹配GAO镜像并检查时序，再运行：

```sh
python3 prj/usb1_device/debug/capture_status.py
python3 prj/usb1_device/debug/decode_status.py <新生成的_core0_window0.csv> --output /private/tmp/usb1_status.json
```

capture默认检查USB项目 `reports/last_build.json`；也可用 `--manifest <本次成功build_*.json>` 指定固定记录。它在运行 `gao_sh -gao debug/usb1_status.gao` 前核对本地GAO_ID和SHA256，但本地清单不能证明板上已经加载该镜像；实际采集须与下载记录及GAO工具的ID检查配合。脚本不含编程命令，默认FT2CH通道0、30秒超时，输出前缀含唯一时间戳，日志/JSON/CSV均保存到USB项目reports；已存在的前缀拒绝复用。仅当实际扫描得到下载器位置后才加 `--location <位置>`。

CSV解码按 `status_50mhz[63:0]` 列读十六进制数据，拒绝缺列、越界或未知值。导出的时间列仅原样保留，不能据其标签推算真实USB位宽；本次工具虽标 `time unit: us`，行号逐1递增，真实采样周期由50MHz时钟决定。

读快照时分别检查三组证据：

1. **PLL与复位**：bit0交替表示50MHz观察/采集链运行；bit15/14是同步后的LOCK/reset60n。LOCK=1不能独自证明USB协议正常，LOCK=0也不会让本观察器停止。
2. **线态与接入**：查看D+/D-、SE0/J连续计数、变化次数，并与主机连接日志及实际上拉电路交叉核对。内部attach intent=1只表示逻辑意图。
3. **USB内部进展**：bit13表示bus reset已释放，bit8/9是源端sticky接收/溢出标志。它们随源端USB bus reset清除，不能当作整个上电期间的永久累计，更不能等同主机完成配置。

## 首次实测记录

2026-10-16成功镜像为 `builds/20261016_011545_836351/impl/pnr/ao_0.fs`，SHA256 `bed38e61a1c0b21c738f5ad56d43ea2dc2abe0b1a53ac236fdde674ad4cdc253`。主流程记录SRAM Program/Verify通过，UserCode `4322`、Status `70022020`。成功清单为 `reports/build_20261016_011545_836351.json`。

首份采集 `reports/usb1_status_20261016_011711_115814_core0_window0.csv` 共128点，值在 `0001FFFF0000D0B4` 与 `0001FFFF0000D0B5` 间逐点交替。PLL LOCK=1、reset60n=1，bus-reset released=0，attach intent=1，D+/D-=SE0，连续SE0计数65535，线态变化次数1，received/overflow均0。它确认50MHz观察链和GAO读回工作，并表明采样窗口内USB线维持SE0；是否有实际D+上拉、是否检测到主机连接，仍须由电路和主机侧证据确认。
