# 25K USB2 独立诊断

记录时间：2026-10-28，UTC+08:00；本页保留当天实验，23:36为DB的后续采样。2026-10-29先用C12528DC原生RXCMD／SE0／NXT统计探针通过电脑端HS及MIDI回环，00:43已恢复完整键盘观察版C12528DA，00:50通过电脑端PL握手、252块整屏传输及MIDI接收；当前身份及新证据见 [10月29日诊断](USB2_RXCMD_DIAGNOSTIC_20261029.md)。25K JTAG与板上USB2均接电脑，尚未接回138K。

用户已授权自主编写、综合及SRAM迭代。本轮仅下载25K SRAM，Flash C1251032与138K Flash C11028E5未操作。23:29曾加载USB-only MIDI回送与事件探针C12528DB，下载校验与独立身份读回通过；它不是完整键盘，后由DC替代。18:22的完整MIDI_KEYBOARD观察版C12528DA保留为直接回退位流，定位结束后须回到完整业务验证。

## 实板结果

| 候选 | 实验配置 | 实际结果 |
| --- | --- | --- |
| C12528D1 | 原 USB3300_HS RTL；仅适配 Linux、输出目录与 UserCode | SRAM 校验通过；独立 50 MHz 观察正常，60 MHz 计数 0 |
| C12528D2 | 失钟时保持 STP 高并释放 DATA | SRAM 校验通过；两次采样仍计数 0，无新鲜 PHY 快照 |
| C12528D3 | DATA 始终高阻；独立 50 MHz 域每 335.54432 ms 切换 STP | SRAM 校验通过；三次捕获均有原生时钟计数与 CLK 引脚跳变，比例约 60 MHz；DIR/NXT 也有历史跳变 |
| C12528D4 | 回到原独立 CDC RTL，不保留 D2/D3 逻辑 | SRAM 校验通过；USB3300 ID、Scratch、配置读回及初始化通过 |
| C12528D5 | 初始化完成后保持 protocol reset 约 280 ms，再释放链路状态机 | SRAM 校验通过；初始化通过，等待电脑复位，尚未枚举；未证实电脑识别到 detach/attach |

D5 的独立 GAO 采样结果：

- USB3300 VID/PID 为 `0x0424 / 0x0004`。Scratch 55/AA、FC41、IF00、OTG00 均完成写入与读回。
- `boot_stage=0x12 / boot_done=1 / boot_error=0`；10 ms 时钟计数为 600048。
- `hs_state=1`（WAIT_RST）、`utmi_linestate=1`、`device_address=0 / configured=0 / hs_active=0`。
- 电脑仍无 FB9A:FB9B，且未出现新 USB 接入日志。已请求只拔插 USB2 数据线，保留 JTAG，再获取枚举日志与同期 GAO。

D1/D2 当时的时钟计数为 0，但 D3 及后续捕获已证明当前时钟和寄存器通路可运行，不能再据此前两轮断言 CLKOUT 断线或 PHY 没供电。没有 D3 前后的用户确认电源循环对照，尚不能把恢复唯一归因为某个 STP 边沿。

## 构建与验证

复用 `projects/25k/example/USB3300_HS/`，九项历史硬件输入与 PACKAGED_FROM.json 哈希一致，原工程、vendor、历史 manifest 未改。实验只在独立 staging 适配，experiment.json 保存输入哈希、精确替换锚点、执行构建脚本哈希。临时探针不成为生产入口；后续必要修复回到现有 MIDI_KEYBOARD 源码及 builder。

已下载的 D1–D5 routed setup/hold violated endpoints 均为 0。GAO 使用独立 50 MHz 域、64 bit 状态、128 samples、GAO_ID=D2B0；每次编程及采样前后核对 ID 与 UserCode。D3 有 Icarus 定向用例，通过停钟／运行计数、独立 STP、引脚电平与跳变计数、DATA 释放检查。D3 原始 GAO 窗口末尾两点有环形回绕，频率比例取回绕前连续样本，不以首末差估算。

D5 首次构建因 `/tmp` 用户配额耗尽产生空位流，被 GAO 身份门禁拒绝，未下载；随后复制也因配额拒绝。切换 home cache scratch 后重新完整 SYN/PNR 成功。下载首次只读预检因临时目录问题退出 -7，未进入编程，保留 failed_preflight_tmp_quota.json；设置 TMPDIR 后重新核对 D4 身份，再下载 D5。未绕过空位流、GAO、时序或身份检查。失败 staging 已完整移至 cache 的 tmp/failed-gw25k-build-hn045jkv，未清理历史工作目录。

## 完整 MIDI 观察配置的实现迭代

观察配置接入现有 MIDI_KEYBOARD builder 的 `--usb2-debug`，默认关闭，与 USB1 配置互斥。保留完整业务与描述符；源策略、跨域和采样说明见 `../docs/USB2_DEBUG.md`。下列失败候选均未下载，不能当成板上身份。

| 候选 | 结果 | 后续处理 |
| --- | --- | --- |
| C12528D6 | 综合入口不支持 `-verilog_define` | 改为经过空头文件身份校验的 staging 配置头；不改默认宏 |
| C12528D7 | 综合通过，PnR 资源检查为 58 BSRAM，超过 56 | 缩窄可选 GAO 总线；REG 试验也超过逻辑资源，未采用 |
| C12528D8 | 综合通过，第二份 SDC 覆盖原 SDC，PnR 缺失时钟 | 在 staging 组合原板级和调试 SDC，保留原时钟和 I/O 约束 |
| C12528D9 | 综合通过，PnR 最终 332 nets 未布通 | 仅精简可选观察字段和寄存器，不削减业务或放宽工作时钟 |
| C12528DA | 布线完成，所有 slack 为正；旧发布门禁因额外 GAO JTAG 时钟误拒绝 | 修复时钟集合判定，独立复核未改变的冻结产物；18:22 SRAM 下载及 18:23 GAO 通过 |

D9 普通实现报告为 22228/23040 logic、11425/11520 CLS，已接近资源上限；该报告的 BSRAM 项不作为包含 GAO 的最终总量。D7–D9 各候选原始输入、source_snapshot、构建日志与失败 manifest 均保留在 `~/.cache/fpga-usb2-hdmi/25k-midi-debug-c12528d{7,8,9}-*/`。D7 staging 内 GAO 存储类型试验日志另外保存，不用于证明原始候选来源。

D9 版本离线回归通过 40 个 RTL bench 和 37 个 Python 用例，包括默认／调试顶层展开；18 项 USB vendor／BLE 受保护来源与原始输入一致。精简后的 C12528DA 已通过观察器 25 项定向检查、18 次一致快照提交、12 个解码／身份工具用例及调试顶层展开；17:58 完整 40 个 RTL bench 和 37 个 Python 用例也全部通过，输入无漂移。证据为 `~/.cache/fpga-usb2-hdmi/25k-midi-debug-checks-da-20261028_175345/validation.json`。时序门禁修复后另通过全部 46 个 Python 用例，其中新增 9 个门禁用例覆盖缺失／额外／重复时钟、三个时钟降频或 Fmax 不足、四类负 slack 和 endpoint violation。

17:54 对仍在运行的 D5 重新只读采样：精确身份仍为 C12528D5，PHY 初始化通过、设备地址 0、configured=0，电脑没有新的 USB 接入日志。原始捕获位于 D5 目录的 `capture_20261028_175440_382172/`。当前物理动作是拔插 USB2 数据线并保留 JTAG，以取得一次新的真实接入过程。

## C12528DA 当前实现、部署与采样

综合开始于 17:53:32，PnR 完成于 18:14:17；PnR 用时 17m49s，其中 routing phase 3 为 15m54s。此轮没有重启或重复综合正在运行的进程。普通资源表为 logic 21946/23040、CLS 11396/11520、BSRAM 54/56；GAO 表另外列 BSRAM 2，总物理 BSRAM 为 56。SYN 的 T_Bsram=40 不等同于物理块数。

STA 的 setup/hold violated endpoints 均为 0；最差 setup `+0.452 ns`、hold `+0.190 ns`、recovery `+0.729 ns`、removal `+0.758 ns`。50 MHz、60.002 MHz、GAO TCK 20 MHz 的 Fmax 分别为 51.157、66.093、75.456 MHz。

原 builder 的门禁只接受两个板级时钟，误拒绝新增的 `tck_pad_i`。现在默认配置仍严格要求两个原时钟；仅 `--usb2-debug` 要求精确的三个时钟，并逐个检查约束频率和 Fmax，不接受任意额外时钟，不放宽时钟或负 slack。

此修复只改变 Python 检查逻辑，没有改变 DA 的 HDL、约束或位流，也没有重新运行 SYN/PnR。原始失败 manifest 保持原样；独立 acceptance 记录绑定其 SHA256、冻结 source_snapshot 全部输入、原回归、逐字节核验的 staging 转换、STA／资源／PnR 命令与 GAO 身份、修正后的校验器及 46 用例日志。独立复核脚本及其哈希随记录保存于 cache；后续新构建直接使用已修复的版本化门禁，不依赖该一次性复核入口。

```text
~/.cache/fpga-usb2-hdmi/25k-midi-debug-c12528da-20261028_175332/
  last_failure.json                       # 原始失败证据，未改
  source_snapshot/                        # 实际综合来源，未改
  acceptance_20261028_182213/
    build.json                            # 独立冻结产物复核，不冒充重新编译
    gate_tests.log
    ao_0.fs
    deployment.json
    capture_20261028_182306/
      capture.json
      decoded.json
```

位流 SHA256：`61af877c9a7883e28e36fd28bb3fb038d978ee4f7d9b5b01629300388da4778b`。18:22 operation 4 SRAM 校验及 operation 0 独立读回：`ID=0x0001281B / UserCode=0xC12528DA / Status=0x70022020`。采样前后身份一致；GAO D2B8 使用 50 MHz、32 bit、128 samples，解出三轮完整且一致的页快照。

18:23 实测字段为 `boot_stage=0x12 / boot_done=1 / boot_error=0 / protocol_reset=0`，原生分频时钟计数 234（量化频率 59.904 MHz），`phy_state=1 / line_state=1 / device_address=0 / online=0 / hs_active=0`，MIDI TX/RX 应用受理计数均为 0。该值证明当前完整 MIDI 位流能初始化 PHY 并保持原生时钟，但正在等待主机复位，尚未枚举。

18:24 再查 `lsusb` 仍无 FB9A:FB9B，18:08 之后没有 USB 内核接入事件。下一步需要用户实际拔插一次 USB2 数据线，JTAG 保持在 25K；之后读取同一 DA 观察器，验证地址、online 与实际 MIDI／PL 收发，再转接到 138K 验证两板握手。

## 18:08 原始 MIDI 重载

时钟恢复之后，为区分原业务位流与临时 CDC 探针，再次下载原始 C1251032 到 SRAM，未写 Flash。位流 SHA256 与原始记录严格一致，operation 4 下载校验及 operation 0 独立读回均通过：`ID=0x0001281B / UserCode=0xC1251032 / Status=0x70022020`。操作记录为 `~/.cache/fpga-usb2-hdmi/25k-original-midi-retry-20261028_180806/deployment.json`。

18:08:30 电脑仍无 FB9A:FB9B，重载后没有新的 USB 内核事件。因此还需要一次用户实际拔插 USB2，JTAG 保持连接，才能观察新的主机枚举过程；不把当前无事件归因于两板业务协议。完整调试候选 C12528DA 的编译不影响当前这个已读回的 SRAM 身份。

## D5 身份与原始证据

```text
~/.cache/fpga-usb2-hdmi/25k-usb-probe-c12528d5-20261028_163527/
  experiment.json
  reports/last_build.json
  deployment.json
  builds/20261028_163527_626141/impl/pnr/ao_0.fs
  capture_20261028_163704_857281/
```

- 位流 SHA256：`4825b0b6d30877f541e35c581f058c9350247cc9b987a30647defc45f2d37f91`。
- 执行构建脚本 SHA256：`91fe7d153fe092acf99c5b67bd6d876c911e26242c6c2376aff95d1a7e686a28`。
- 下载为 operation 4（SRAM Program and Verify），之后 operation 0 独立读回 `ID=0x0001281B / UserCode=0xC12528D5 / Status=0x70022020`。
- D3 证据：`~/.cache/fpga-usb2-hdmi/25k-usb-probe-c12528d3-20261028_162246/`。
- D4 证据：`~/.cache/fpga-usb2-hdmi/25k-usb-probe-c12528d4-20261028_163047/`。

各候选保存实际执行的构建脚本，不依赖后来修改过的 cache 入口证明来源。生成位流、数据库与捕获均留在 cache，不加入源码。

## 后续与回退

### 23:08 用户确认重插后的新证据

本次并非“电脑没有检测到插入”：23:08:10 的 `usb 3-5` 是0403:6010下载器，23:08:11–13 的 `usb 3-6` 则是25K USB2。电脑检测到 full-speed 接入，随后四次尝试均出现 `device descriptor read/64, error -71` 或 `Device not responding to setup address`，最终 `unable to enumerate USB device`；失败设备不会留在正常 `lsusb` 列表中。19:11:40–42也有相同失败过程。这些日志否定了18点阶段“尚无新接入过程”的旧阻塞条件。

23:09 独立JTAG身份仍为 `ID=0x0001281B / UserCode=0xC12528DA / Status=0x70022020`，并非已退回Flash旧固件。匹配DA manifest的新捕获位于 `acceptance_20261028_182213/capture_20261028_230920/`：boot_stage=0x12、boot_done=1、boot_error=0、约60 MHz时钟；当前PHY状态1、地址0、online=0，TX/RX MIDI受理计数均0。静态末态不能判定枚举过程是否曾进入chirp或收到包，因此增加显式USB-only事件探针配置，记录原生历史并实际命令PHY先断开再连接。该probe不替代完整键盘，也不用于宣称两板业务完成。

### 23:29 C12528DB 快速探针

复用 MIDI_KEYBOARD 现有入口的显式 `--usb2-probe`，没有复制工程或修改历史／vendor输入。SYN+PnR 从23:23:27到23:23:51，共24秒；原50 MHz、60.002 MHz、GAO TCK20 MHz约束全部保留，setup/hold违例0，最差setup+0.521 ns、hold+0.181 ns、recovery+5.270 ns、removal+1.097 ns。业务模块范围及退出条件见 `../docs/USB2_DEBUG.md`，此处不冒充完整键盘构建。

完整离线回归为42个RTL bench与48个Python用例，默认／完整观察／临时probe顶层展开通过，输入无漂移，BLE ROM拒绝与参考哈希门禁保留。新增事件bench覆盖boot排除、turnaround排除、粘滞状态、RXCMD与饱和计数；attach bench直接检查ULPI写出detached Function Control、延迟期间writer不停和随后attached Function Control，不能仅凭该仿真断言电脑已识别到物理断开。

```text
~/.cache/fpga-usb2-hdmi/25k-midi-probe-c12528db-20261028_232327/
  build.json
  source_snapshot/
  impl/pnr/ao_0.fs
  deployment.json
  capture_20261028_232903/
~/.cache/fpga-usb2-hdmi/25k-midi-probe-checks-db-20261028_232431/validation.json
~/.cache/fpga-usb2-hdmi/25k-usb-replug-kernel-20261028_2308.log
```

位流SHA256为 `55984169690f64cd50d4f26ef1f16b9b6e6807294ea41fec7f091303d745d99a`，GAO D2BC。下载前读回DA，operation4 SRAM校验后及采样前后均读回 `ID=0x0001281B / UserCode=0xC12528DB / Status=0x70022020`。Flash未写。

23:29采样：boot完成、约60 MHz时钟；当前state1／地址0／online0，历史states_seen={0,1}、有效RXCMD lines_seen={0,1}、rxactive曾出现、UTMI接收字节0、txvalid从未出现，最后RXCMD=0x4d。该历史从本次加载开始，不包含23:08的主机尝试；初始SE0记录也不能代替主机reset持续时间证据。

加载后内核没有新的USB事件，因此软件延迟尚未证明电脑识别到detach/attach，也不归因于某个确定硬件故障。下一次物理动作是只将25K USB2数据线的电脑端换到另一个USB口，保持JTAG与25K电源，不再拔下载器；随后同步读取新端口日志和DB事件历史。若板上身份因断电变化，先重新读回，不能用DB配置采旧Flash。

### 23:33 再次重连与 DB 事件历史

23:33:48–50，USB2 仍在 `usb 3-6`，电脑再次尝试地址22–25，均因描述符读取／SET_ADDRESS 阶段的 `error -71` 失败，最终 `unable to enumerate USB device`。因此正常 `lsusb` 无25K条目，不表示电脑完全没有检测到接入。下载器从 `usb 3-5` 移至新Hub的 `usb 3-1.2`，WINUSB只读扫描得到新location786；没有继续使用旧location53。

23:36使用DB manifest和D2BC配置只读捕获，采样前后身份均为 `ID=0x0001281B / UserCode=0xC12528DB / Status=0x70022020`，证据为上述DB候选目录的 `capture_20261028_233626/`，含 `kernel_usb.log`。初始化完成、时钟约60 MHz，地址0、online0；历史PHY状态仍只有{0,1}，没有进入chirp／FS／HS运行状态，UTMI有效接收字节0、txvalid未出现。原生RXCMD线态曾见{0,1}，末值0x4d；该位图没有持续时间信息，不能把短暂SE0解释为已收到完整主机reset，也不能仅凭这次捕获确定模拟线或RTL哪一个有问题。本次没有重新下载或写Flash。

下一次只移动25K USB2数据线的电脑端至另一个端口，保持现有JTAG与板卡供电；当前日志显示下载器已换口，但USB2仍在原 `3-6` 端口。继续用当前DB manifest／D2BC读取历史；不要用DA或D5配置读取DB。待物理接入与复位收发定位后，恢复完整DA或带明确新身份的修复候选，验证真实MIDI／PL，再接回138K验证板间握手和MIDI。原始两侧协议的离线闭环结果见138K的 USB2_25K_PROTOCOL_AUDIT_20261028.md，不替代这些实板步骤。

回退可重载未改动 Flash C1251032，或向 SRAM 下载原位流：

```text
projects/25k/example/MIDI_KEYBOARD/results/slider_fix_20261023/build/impl/pnr/midi_keyboard.fs
SHA256 303e1403f67503285e07469bb6c13dd8aa698db77d42054ad102ead622a2e671
```
