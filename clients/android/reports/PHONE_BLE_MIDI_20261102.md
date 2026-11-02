# Android 实体手机连接 25K：故障定位与 MIDI 实测

时间：2026-11-02，UTC+08:00。范围：实体手机 App → BLE → 25K → 电脑 USB MIDI。

## 结论与边界

- 本轮实体手机实际扫描到了 `GWK-MIDI`；复现的失败不是“没有广播”或“没有附近设备权限”，而是在恢复旧配对的加密阶段断开。
- 手机蓝牙栈明确记录 `HCI_ERR_KEY_MISSING`，随后自动移除了该设备的旧绑定。再次从 App 连接成功，实际按键的 Note On／Off 经 25K 从电脑 USB MIDI 接口读回。
- 这是实体手机测试，不是模拟器连接实板。此前电脑主机 BLE 测试、模拟器 UI 测试也不能替代本报告的手机证据。
- 本轮未重装／修改 App，未修改 RTL，未加载 SRAM、写 Flash 或重载 FPGA；没有验证手机经 25K 到 138K 的实际发声，也没有完成长期稳定性验收。
- 已恢复本次连接，但没有永久修复板端配对密钥的生命周期；以后 FPGA 复位或重新配置仍可能再次触发。

## 测试身份

| 对象 | 本轮身份与依据 |
|---|---|
| 手机 | Xiaomi Civi 5 Pro（25067PYE3C），Android 16／API 36；ADB 已授权，蓝牙开启，`BLUETOOTH_SCAN`／`BLUETOOTH_CONNECT` 已授予 |
| 实装 App | `cn.gowin.control`，`0.3.1-demo-d3`，versionCode 16；从手机拉取的 APK 与本地原始 APK SHA256 完全一致 |
| APK SHA256 | `01181733c3c2c61920a9a997b3b4274f9482a05b841c7e2277e7d1d130af7899` |
| App 来源 | `origin/codex/dual-138k-workstation`；来源提交 `4349cc8404de17eca368223fd485130370d46d2d`；最近 Android 提交 `bb0319780f0c4c4bf12c45bec8f56afbbee67073`；Android tree `d359e6d505645d65537c1355513bdd23932b36c7` |
| 25K 运行身份 | 本轮只读 JTAG：ID `0x0001281B`，UserCode `0xC125C204`，Status `0x70022020` |
| BLE 目标 | `GWK-MIDI`，`34:20:03:3D:8B:10`；MIDI service `03b80e5a-ede8-4b33-a751-6ce34ec4c700`，characteristic `7772e5db-3868-4112-a1a9-f2669d106bf3` |
| USB 接收端 | 电脑上的实体 25K MIDI 节点 `/dev/snd/midiC1D0`；只读捕获，不从 USB 注入音符 |

APK 来源见[原始构建清单](../artifacts/gowin-control-0.3.1-demo-d3-build.json)。该清单是构建时记录，本报告补充此后的手机验证；不改写其历史字段，也不将此 App 身份混同于主线 `0.2.10`。

板上 C204 的既有部署证据见[独立部署记录](../../../projects/25k/example/MIDI_KEYBOARD/reports/E2_EFFECT_CYCLE_20261102.md)。本轮没有执行其中的烧录操作。

## 复现与恢复时间线

| 时间 | 观察 |
|---|---|
| 01:48:42 | 手机曾为该设备建立绑定；此为系统保留的历史记录 |
| 02:03—02:07 | 既有部署记录包含板端重新配置／重载；晚于上述手机绑定，本轮未重复这些操作 |
| 02:43:18 起 | 实体手机 App 扫描，页面实际列出 `GWK-MIDI · 34:20:03:3D:8B:10` |
| 02:45:06.795 | App GATT 回调 `status=0 connected=true` |
| 02:45:06.808 | 服务发现 `onSearchComplete status=0` |
| 02:45:06.809 | 系统记录 `SEC Encryption failed … status:HCI_ERR_KEY_MISSING`，随即因 Encryption Failure 发起断开 |
| 02:45:06.810 | App 记录启用 MIDI characteristic 通知；不能仅凭此调用认定 CCCD 订阅已成功 |
| 02:45:06.846 | 系统记录该设备 `BOND Device removed`，随后绑定状态为 0 |
| 02:45:06.851 | App 回调 `status=5 connected=false`；页面最终显示 `MIDI 连接失败：GATT subscribe 失败 (133)` |
| 02:49:32.050 | 从同一 App 再次点击设备后，GATT `status=0 connected=true` |
| 02:49:32.477 起 | 服务发现成功并启用通知；页面显示 `MIDI 已连接 · GWK-MIDI`，出现“断开MIDI”按钮；电脑 USB 收到连接初始化 PANIC |
| 02:51:38—02:51:40 | 在实体手机 App 按下／释放音符 48、50，电脑 USB 实际读回对应 Note On／Off |

没有手动删除手机全部配对、重置手机蓝牙或清除 App 数据。此次由 Android 自动删除失效绑定后，再试一次即成功。

## 原因：手机旧绑定与板端易失密钥不一致

系统直接观察到的故障是加密恢复时缺少密钥，并非扫描失败。结合板端源码和重新配置时间线，原因是手机保留了旧绑定，而板端运行期密钥已丢失：

1. [`midi_ble_smp.v`](../../../projects/25k/example/MIDI_KEYBOARD/rtl/ble_board/midi_ble_smp.v) 的 `!resetn || !enable` 分支（146、160 行）清空 `bond_valid`、`bond_ltk`、`bond_rand`、`bond_ediv`。
2. 253 行仅在 `bond_valid` 且 EDIV／RAND 匹配时恢复旧 LTK；否则进入缺失密钥路径。
3. 335—336 行对该路径发送 `16'h201b`（LE LTK Negative Reply）。这与手机日志中的 `HCI_ERR_KEY_MISSING` 一致。

该 SMP 文件 SHA256 为 `ceb9d562adcf50cb03d7f7a0bed3c81ac1bcc45acb1103676ea075f5f039ef6e`，已核对与 C204 构建 `results/build_20261102_014925_745486/build.json` 中的对应输入哈希一致。未为定位故障改变该文件。

App 当前只显示通用订阅错误 133，没有向用户呈现底层密钥失效原因，因此容易被理解为“未发现／无法连接实板”。本轮没有实现 App 错误分类或板端密钥持久化，也没有改变既有安全策略。

## 实体手机按键闭环

USB 捕获始于 `02:48:52.102807`，持续 180 秒，共 150 字节。其中最先收到 32 条初始化 PANIC：16 个通道各一条 CC120 和 CC123；随后包含下列本轮操作对应的原始 MIDI：

| 捕获相对时间（秒） | MIDI 字节 | 含义 |
|---|---|---|
| 166.8398 | `90 30 64` | 通道 1，Note 48 On，力度 100 |
| 167.3497 | `80 30 00` | Note 48 Off |
| 167.7397 | `90 32 64` | 通道 1，Note 50 On，力度 100 |
| 168.2497 | `80 32 00` | Note 50 Off |

其余字节包含同一会话内的其他手机按键，不将全部操作归于自动化。已按原始字节核验初始化 32 条消息、上述四条音符消息和总字节数，不仅依据 App 的发送计数。

## 使用入口与后续处理

- 本次成功入口是 **音乐 → 手机→25K MIDI控制 → 扫描25K MIDI → GWK-MIDI**。
- 首页“查找工作站”面向另一套业务 GATT 服务，不能据此判断当前 MIDI 固件是否在线，也不能替代 MIDI 页的扫描。
- 板端重新配置后，若再次出现密钥缺失且系统未自动恢复，可在手机蓝牙设置中仅取消 `GWK-MIDI` 的旧配对，再从 MIDI 页重新连接；不需要清空其他设备的绑定。
- 永久方案仍需另行处理配对密钥生命周期及 App 错误提示／恢复流程，不能把这次重连成功当作永久修复。不会未经授权写 Flash、修改安全策略或静默删除系统绑定。
- 25K USB 当前连接电脑；手机→25K→138K→物理音频的验收另做，不能由本次 USB 捕获推导。

## 证据位置与完整性

原始日志、App 页面 XML／截图、手机原始 APK 和 USB 捕获保留在本机 `~/.cache/fpga-android/20261102_phone25k/`，不纳入源码。以下只列本次目标相关证据，不将手机其他设备的日志写入仓库：

| 文件 | SHA256 |
|---|---|
| `midi-scan.xml` | `1784a7b06dbf01da4fa147b7599d8fe414323d453329ab3864c585ef899d57ec` |
| `connect-error-bottom.xml` | `8ba836a5f3fc8084055e52f584993e8f30e9436260fe0a9cdf3d3d3baba3619e` |
| `target-bond-and-security-events.txt` | `28556ce013432b20a513af71abf7ae5095fd37448c5f148abf95677f17beb1b3` |
| `app-after-retry.log` | `c33d3592c38aa90d3d8a119c0bfb2a7f8656ed4be489994851f95972583faa9e` |
| `midi-retry.xml` | `4d2a7f4ae1ac8b97d017ea7480771a52ec6d0fb9b3c9dad20c7789ea96350148` |
| `phone-usb-midi.json` | `8c6312843f5ecf2fb112765efc092f5b0582fd0bd91898984edcbd9f0657db3b` |

原始证据位于本机缓存，不宣称离开此机器后仍可仅凭仓库复核全部手机日志；本报告保存必要的目标事件、身份和消息摘录。
