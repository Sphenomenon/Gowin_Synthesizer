# D5 HDMI＋USB2 热插拔诊断与电脑监视器

这个小配置将已验证的 `C11028D5` HDMI 显示与原生 USB2 热插拔诊断并列组合，用来快速检查同一个 USB-A 口上交替插入的 25K／Push。顶层 `workstation_usb2_hdmi_top.sv` 只负责接口组合，不接入声音合成或各种演奏业务。默认 HDMI 保留 D5 确定性动态测试界面，USB 检测结果显示在电脑监视器中；显式增加 `--usb2-hdmi-status` 时，在右下方加入实时 USB 信息与声部占用栏，产生新的显示输入身份。

它复用已有 `build.py --prepare-usb2-soc --usb2-component workstation-hotplug` 入口，通过显式的 `--usb2-hdmi-baseline` 选项启用；不替换已有完整工作站或独立 HDMI 配置。单独的 USB 诊断仍见 [USB2_HOTPLUG_DIAGNOSTIC.md](USB2_HOTPLUG_DIAGNOSTIC.md)。

## 来源与实现

准备阶段先核对已接受 D5 的清单、位流及全部暂存输入，再重新生成 HDMI 子配置，并逐字节比较每个实际 RTL 来源及原始显示约束。USB 子配置仍选择原生产固件、USB3300／ULPI、HS／FS Host、输入 owner、事件 FIFO 和反馈通道。两个子清单原样保留，根清单绑定全部实际输入、GAO 探针布局、ROM 及回退位流。

两侧同名模块仅在整个来源文件字节一致时去重；其它冲突直接报错。SDC 只给内部对象加组合层级，外部时钟／端口不改名，不降低频率或扩大 false path。审计在实际综合／路由网表上检查 PLL、原生 USB CDC、FIFO、复位链、D5 DDR 配置及视频 PLL／串行器，并保留全局 setup／hold／recovery／removal 报告。PLL 参考及 HDMI 串行时钟没有普通寄存器 Fmax 行，另由完整实现时钟表和原视频 PLL／串行器审计验证。

从仓库根目录准备新候选；修改输入时须分配新的八位十六进制 UserCode：

```sh
FPGA=projects/138k/push2_workstation/usb_a
OUT="$HOME/.cache/fpga-usb2-hdmi/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT-tmp"
export TMPDIR="$OUT-tmp"
python3 "$FPGA/build.py" \
  --prepare-usb2-soc --usb2-component workstation-hotplug \
  --usb2-firmware-profile workstation \
  --usb2-hdmi-baseline "$FPGA/out/hdmi_isolation_20261028_d5" \
  --netlist-dir "$HOME/Documents/fpga补充文档" \
  --usb2-soc-output "$OUT" --user-code "${USER_CODE:?set a new candidate UserCode}"
PYTHONPATH="$FPGA" python3 -m tools.workstation_usb2_hdmi "$OUT"
PYTHONPATH="$FPGA" python3 -m tools.workstation_usb2_hdmi_audit "$OUT"
```

`build_result.json` 是工具执行与输出证据；`integration_audit.json` 分别记录结构检查及实际时序结果。审计退出成功表示结构检查通过，不能代替读取 `timing_closed` 和详细负路径。2026-10-28 的组合候选与实际耗时见 [C11028E4 报告](../../reports/USB2_HDMI_DIAGNOSTIC_20261028.md)。

## HDMI 右侧 USB 与声部信息

在上述 prepare 命令中增加 `--usb2-hdmi-status`。USB 状态读取原输入 owner 的 MMIO 0x00 同源投影与既有链路快照，区分断开、枚举中、已连接、错误和状态过期；识别 `PUSH 2`、`25K KEYBOARD`、`USB MIDI`，连接后显示实际 HS／FS。断开、错误或过期时清除设备名称。该名称是已支持的设备分类，不读取任意 USB 产品字符串。

同一区域显示 `VOICES  nn / 32` 与 512 像素进度条，每声部对应 16 像素，满载转为黄色。数量取渲染快照 `shared_render_meta[159:128]` 的活动声部掩码，按置位数计算，和现有画面的声部状态同源；不是 Note On 计数或 held 键数。**本组合诊断没有 DSP，该掩码来自 D5 的确定性演示输入；因此这里的声部条是显示验证，不是实际发声音源的整机验收。** 后续整机接入须继续使用实际输出快照，不能改用 USB 事件数冒充声部占用。

实现位于 `rtl/display_data/workstation_usb_status_panel.sv`：USB 状态整体经 mailbox 跨到 DDR UI 时钟域，源停止更新100,000,000个UI时钟后标记过期；每帧开始固定 USB 状态与声部数量，帧中变化延至下一帧。另在CPU域监测上游ULPI mailbox的新快照，48,000,000个CPU时钟没有更新就置链路错误，避免CPU继续运行时不断发布旧链路状态。源复位通过UI域本地同步释放链限定freshness状态。信息栏只修饰原有 renderer 的双像素流，再由原 writer 写入既有 DDR 背缓冲，沿用原帧发布和 HDMI 扫描；无新 DDR 区域、客户端或音频背压。

prepare 首先完整验证 D5，再把三份仅接线的适配源写到新候选的 `status/`，原 `hdmi/`、`usb/` 子清单与内容保留。第三份只为内部USB子模块启用状态输出，独立hotplug顶层保留原引脚集合。另有第四份 `feedback_renderer.v` 适配，仅将四行wire声明移到使用点前，以兼容Icarus 13的严格声明顺序；全部表达式逐行保留，不改绘制算法。根清单记录适配前后哈希、适配类型、实际编译列表及 `hdmi_implementation_byte_identical=false`。接线与声明顺序适配使用唯一锚点且漂移即失败；退出条件是将锁定 D5 显示边界迁为版本化原生装配，绘制与状态行为不进入文本生成器。新增约束覆盖mailbox与本地复位释放链，不放宽既有时序／CDC／PLL与资源门禁；新增端点的实际网表和物理审计仍待完成。原PR变更验证见 [2026-11-02 记录](../../reports/HDMI_USB_VOICES_20261102.md)，合入后的修复须使用新来源身份。

定位 PHY 未就绪时，在准备命令中增加 `--usb2-observer-profile phy`。这个独立 v2 布局保留 v1 owner 探针，并追加原有 ULPI 心跳、50 MHz 参考域时钟监控、Host 使能／复位、初始化／端口状态、快照请求／确认及原始 ULPI 电平。没有改动 USB 业务 RTL；这些跨域调试读数不是新增运行时 CDC 接口。解码器对整个窗口计数心跳沿和快照确认翻转；没有观察到快照更新时显示“状态快照未更新”，不再把全零快照直接称作 PHY 正在初始化。旧 E4 v1 布局仍可读。

短暂失败可能只持续几微秒，而软件重试间隔为 100 ms。实验选项 `--usb2-observer-trigger clock-failure` 将同一 PHY 布局的触发接到原时钟故障位 0；这个选择须与 `phy` 配置一起准备，使用新的 UserCode。它不覆盖故障码 2 的“运行后丢钟”，也不延长运行时超时或更改重试策略。当前 E6 两次读回均未包含触发故障位，不能当作故障瞬间证据；解码器现会拒绝这种窗口。该实验尚未取得有效故障触发记录，不替代已恢复的 E5 连续监视配置。默认仍为复位释放后立即采样。

当参考／CPU 域已释放、两组不受 Host 使能门控的 ULPI 复位释放链却在整个窗口保持 0，且没有 ULPI／参考心跳变化时，窗口显示“未观察到 ULPI 时钟，PHY 尚不能工作”。这项判断来自时钟域自身的释放链，不依赖尚未送达的 PHY 快照。

## 保留HS连接的恢复与端口历史

原生Host在启用后只等待FS J接入时，无法主动恢复仍由USB1独立供电、保留HS状态的设备。端口在允许HS且连续200 ms观察为SE0时，每次Host启用最多补做一次原有50 ms根端口复位；随后仍走原有chirp资格检查、PHY配置读回和恢复时间。没有设备响应时回到等待接入，不报告connected，也不开放业务流量；FS-only策略及正常FS接入去抖不变。这个物理恢复行为属于 `rtl/usb2/workstation_usb2_host_port.sv`，不改变MIDI或PL线协议。

显式选择 `--usb2-observer-profile port` 使用独立v3 GAO布局，保留原owner与phy探针，并加入跨软件重试保存的端口状态历史、失败码历史、最后失败前状态／FunctionControl、PHY就绪次数和接收／发送／SOF峰值。峰值是自全局复位以来的单次尝试最大值，不是跨尝试累加。寄存器以原生ULPI时钟更新，由CPU时钟的GAO作调试观察，不作为运行时CDC或设备分类依据。

记录器通过独立诊断顶层显式启用 `PORT_OBSERVER`；原生MMIO默认不启用，完整工作站冻结来源不随之切换。v1、v2布局和旧E5读回保持兼容。软件关闭Host不会清除本轮历史，全局复位才清除；因此不必反复依靠短窗口碰到失败瞬间。定向复现、候选及上板结果见 [2026-10-29恢复排查](../../reports/USB2_HOST_RECOVERY_20261029.md)。

## 电脑窗口

桌面需要 Python 3 和 Tkinter。`--candidate` 指向准备／实现后的组合候选目录，不能指向 D5 或独立 USB 候选。脚本核对 FPGA UserCode 与 GAO 布局后才读回；不提供下载、Flash 写入或复位功能。

```sh
FPGA=projects/138k/push2_workstation/usb_a
PYTHONPATH="$FPGA" python3 -m tools.workstation_usb2_monitor \
  --candidate "$OUT" --output "$HOME/.cache/fpga-usb2-monitor"
```

窗口显示设备类型、枚举／识别阶段、实际 HS／FS 状态、SOF、输入／事件／生命周期／取消计数、Push 完整帧／命令、USB IN／OUT 错误、断连及 CPU 故障。插入 25K 显示“25K 键盘”，插入 Push 显示“Push 垫”；其它 MIDI 设备单列，不能误当作 25K。握手判断取原固件完成配置后写入的 owner connected 和原有设备分类，不把 PHY ready 当作枚举成功。`transaction_ready` 对应原 MAC 事务复位释放，不是最早的物理插入检测。

每次读取都保存独立目录中的原始 CSV、前后 UserCode、工具日志、解码结果及哈希。默认每次读取完成后等待三秒再采样；一次 GAO 窗口为 CPU 48 MHz 域的 1024 拍，约 21.3 µs，不是连续录像。计数是自复位累计值；短暂瞬态可能落在窗口间隔内。读回失败或超过 20 秒没有新数据时，设备状态变灰并显示未知，不继续保持绿色成功标记。

不接板即可演示窗口，界面明确标记为模拟数据：

```sh
PYTHONPATH="$FPGA" python3 -m tools.workstation_usb2_monitor --demo
```

单次 JSON 读回可供终端或自动化脚本使用，输出目录必须是新目录：

```sh
PYTHONPATH="$FPGA" python3 -m tools.workstation_usb2_monitor \
  --candidate "$OUT" --once --output "$HOME/.cache/fpga-usb2-capture/$(date +%Y%m%d-%H%M%S)"
```

独立于 CPU／DDR／HDMI 的时钟与 PHY 定位入口见 [ULPI 自测](ULPI_SELFTEST.md)。

## 上板顺序与回退

本轮用户已明确授权“下载进sram就不用问我了，你自己下载”：诊断候选可直接下载 138K SRAM，下载后独立核对 UserCode；Flash 未授权。本监视器本身不负责下载。用户当前保持 25K 插入，先保留该状态定位 PHY／枚举，再记录键盘／面板操作；需要交替验证 Push 时另行记录实际插拔。两种设备交替使用，不假定同时连接。用新的采样目录保留每一步证据。

回退位流为 D5 的 `impl/pnr/ao_0.fs`，SHA256：

```text
82a2f3aa1cc6a6b4660cc94bb837a56234397f8c6e859e8d06e30962e5c2e8aa
```

ULPI 旁路电气沿用同一 pinout，待实测项仍是 USB3300 ULPI IO 是否确由 3V3 供电。这里没有增加整机音频路径，也不把离线回归、窗口演示或旧 D5 验证记为新组合候选的硬件验证。
