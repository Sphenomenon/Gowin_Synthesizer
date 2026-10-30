# 新板完整工作站来源 profile

`custom138k-workstation-v1` 当前为 revision 5，显式选择双采样率原生 runtime、统一最终 PCM、TF 服务和显示 metadata minor 1。它沿用 `--prepare-custom-board`，保留 maintained AE350 固件重编译和 native scan-window admission。accepted full83、pinned timing85、独立 resource 以及省略 profile 的原生准备均不选择这组 runtime 输入。revision 1／2／3／4 的来源与验收范围保留在历史提交和阶段报告中。

配置在 [workstation_profile_v1.json](workstation_profile_v1.json)，校验器在 [workstation_profile.py](../../tools/workstation_profile.py)。固定值为：1080p60、HS 协商开启、WAV、`implemented_sample_rates_hz=[48000,44100]`、`audio_policy=native_dual_rate_runtime_v1`、`reserve_zero_epoch=true`、`display_metadata_minor=1`、`media_preparation_policy=seal_record_stop_score_tf_ble_v1`、`ae350_firmware_policy=maintained_ae350_v1` 和 `scan_window_policy=native_admission_v1`。修改这些值须同步审查实现与测试，并创建下一配置 revision；未知配置和 revision 直接失败。

## 使用

从仓库根目录执行，输出目录必须不存在：

```sh
PYTHONPATH=projects/138k/push2_workstation/usb_a \
  python3 -m tools.workstation_profile check
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-custom-board --workstation-profile custom138k-workstation-v1 \
  --netlist-dir /path/to/locked-netlists --custom-board-output /tmp/workstation-profile-new
PYTHONPATH=projects/138k/push2_workstation/usb_a \
  python3 -m tools.workstation_profile verify /tmp/workstation-profile-new
GW138K_PROFILE_PREPARED=/tmp/workstation-profile-new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_profile.py
GW138K_PROFILE_PREPARED=/tmp/workstation-profile-new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_sources.py
```

准备需要完整 GNU RISC-V bare-metal 工具链及 C 头文件；可用 `GW138K_RISCV_PREFIX` 指定。三份外部网表仍按 `pinout.json` 检查原始字节。source audit 使用 Icarus 的 `-grelative-include` 预处理逐编译单元核对活动 module／package 定义和 include 依赖；它不执行综合。

## 编译边界与来源

[workstation_runtime_profile.py](../../tools/workstation_runtime_profile.py) 声明新 runtime 的源码、依赖、替换和约束组合。`workstation_profile_runtime.sv` 是唯一顶层 provider：在同一 `WORKSTATION_RUNTIME_NATIVE` 宏作用域包含原生 top 与 `workstation_profile_hdmi.sv`。HDMI wrapper 和 implementation 作为受锁定依赖保留；单独重复编译 wrapper 会失败。参数、会话、渲染、时钟服务、TF 和显示依然由各自原生子系统拥有。

被替换的父输入禁用编译并保留原字节。TF transport 的维护源与父路径相同，因此候选将它安装到 `rtl/runtime_replacements/scope_tf_transport.sv`，清单明确绑定维护源与安装路径。维护版 display writer／reader、feedback capture／analysis／renderer 各自替换对应父文件；原 output capture、wave aligner 和 analysis ROM 等共享支持继续使用锁定父输入。display layout package 与维护 `.svh` 字节完全相同：保留父工程首项 package 编译顺序，另校验并记录其版本化等价来源。

`integration_inputs.json.workstation_profile` 指向候选自己的 `workstation_profile.json`。它记录每个启用编译输入的哈希与来源、所有维护源的实际安装位置、包含依赖、受检变换、完整 staged 闭包、USB／AE350 固件工具和产物、整个准备源码快照、feature matrix，以及 A2／D5／C1 的逐文件关系。候选身份绑定配置、完整 staged 输入、完整源码快照与固件身份；更换工具或 ROM 会产生新身份。旧历史参考 UserCode 不赋予本 profile 新的验收范围。

runtime profile 显式启用 BLE 的 `relative_rom_paths`：生成的 `patch_path.vh` 只引用候选内 `native_bluetooth/rtl8723ds_patch.mem`，生成器和 vendor ROM 字节均记录哈希，复制候选时无需读取原 prepare 目录。默认入口仍生成原来的绝对候选路径，vendor ROM 本身没有改动。端口审计预处理实际选中的 provider，并严格检查原 pinout 与 runtime 唯一补充的 `clk_16m9344/J19`；这项检查不覆盖旧审计中写死的物理 CDC 层级。

- A2：USB Host RTL、生产固件和原生输入 owner 继续复用维护源码。Push／25K 在同一 USB-A 口交替使用；完整工作站热插拔、会话恢复与发声须另有 I01 证据。
- D5：共享 DDR 地址图与 scanout 保留。新 runtime 在真实最终 PCM 上生成四类 minor 1 显示块，带实际 rate／epoch，并显式处理取消、原子缓存与 raster 租用。扫描 admission 保留已接受尾部与实时客户端。D01／D04 的整机服务期限和实板争用尚未验收。
- C1：现有 BLE business transport 复用。短录音仍限定 48 kHz；44.1 kHz observation 不能伪装为 48 kHz。C1 历史录音 PCM 全零，不能作为新候选真实乐音、Android 或长录音验收。

R00 的 `workstation_pcm_ddr_backend` 是未选择的存储组件，未加入本 profile 的编译列表或现有 BLE 录音路径。地址权威登记 `0x30500000..0x305fffff`，组件当前只使用首 64 KiB；实际 owner8、native 提交通知、最终 PCM CDC 和业务对象接入仍待完成。其离线双率／竞争／命令优先级证据不提升本 profile 的录音容量或物理接受状态。新增预留宏和未选择源码会产生新的来源／prepare 身份，既有 f1be50 综合与物理试验继续绑定原输入，不移用其验收。

revision 5 显式启用 AE350 时钟命令的媒体准备：保留持音，正常封存受控REC／BLE对象、取消score、真实停止TF后才向唯一采样率核心发请求。`workstation_media_preparation`只组合各owner的实际终态和hold；CPU observer reset不撤销后台fence。TF选用token-qualified byte FIFO／DMA clear ACK，重复stop复用既有generation fence，末次inactive控制mailbox仍必须得到目的端ACK。共享BLE五层端口均默认关闭，仅native顶层启用；旧格式录音仍限48 kHz。未初始化的BLE EMPTY／已READY对象可幂等封存，不阻止基础采样率切换。接口见[媒体准备](../../rtl/services/MEDIA_PREPARATION_CONTRACT.md)、[REC／score／clock策略](../../rtl/services/MEDIA_STOP_POLICY.md)与[BLE封存](../../rtl/bluetooth/WORKSTATION_BLE_SEAL_CONTRACT.md)。

统一最终 PCM 在物理串行输出之前应用一次 master gain，并向观察消费者提供实际送出的带标签帧。连续计算时钟仍为 76.8 MHz；DCS 只选择物理音频时钟。TF 只接受当前已应用采样率匹配的 WAV，不请求自动换率或重采样；显式用户重启与文件退出分开处理，已接受 DDR 读先排空。暂停和 EOF／取消语义由 TF 服务合同定义，不能据 prepare 成功宣称完整歌曲已播放成功。

## 固件与漂移失败

只有显式 profile 调用 `stage_ae350_firmware()`，将 [firmware/ae350](../../firmware/ae350/README.md) 的 C／头文件／启动汇编／链接脚本重编译到候选 `ae350_firmware/`，安装其 `boot.mem`。安装前检查父 ROM，安装后核对新 ROM；缺源、工具失败或容量不足均直接停止，不能回退锁定 ROM。未指定 profile 及 accepted／pinned／resource 继续保留原 ROM。

固件证据绑定工具版本、ELF／binary／ROM、16 KiB ROM／8 KiB RAM 容量和至少 4 KiB 栈保留。验证同时检查独立固件证据目录与工程里安装的字节。逐函数栈值仍不能证明完整调用链、运行时栈水位、服务期限或实板执行。

配置锁检查所选维护源码与 glob 来源库存；准备和 verify 还重新计算完整源码快照，拒绝内容变化、新增输入、编译列表变化、安装位置歧义、依赖变化、staged 文件增减及固件／feature／硬件状态改写。父基线清单、还原和漂移检查继续由既有 baseline 工具执行。不得为消除失败改写冻结基线、原始网表或历史证据。

## 验证范围

本 profile 产物是 `prepare_only` 检查点。脚本只提供综合入口；默认整机实现脚本拒绝 P&R／部署。新增 CDC 的端点、payload／Gray 传播边界、reset、两个时钟模式和切换路径仍需独立综合、布线、PLL、资源及硬件审查。约束清单保留被替换层级的省略理由；不会以宽泛 false path 冒充完整 CDC。

`workstation_runtime_cdc.py` 的第二批审计使用原生 token-qualified TF FIFO 的直接 Gray 同步链，另登记媒体 request／ack／held failure、异步 hold 以及 USB drain 六级围栏。它为已审边界声明精确传播约束，保留恢复／撤销检查；其余 held payload、FIFO 存储所有权及复位边界仍须逐项关闭。新源码必须绑定新的综合网表再运行端点／负控审计，checker fixture 或旧网表不能替代本候选的完整 CDC 与物理接受。

runtime 准备只从已锁定的 USB 混合旧约束中移除 `queue_write_release_0*/D` 的 setup false path，保留同一行的 settled／panic／defaults 端点；新 write-release 首级使用显式传播上限，旧行形状漂移直接失败。异步 hold PRESET 与 drain CLEAR 的例外检查独立于 `-from` 查询：不允许额外 false path，max delay 仅允许已审的两条精确 assertion bound；这仍需实际工具解析及布线后的 recovery／removal／pulse 检查。

综合、P&R、硬件验收、SRAM 和 Flash 是独立状态，均须新候选身份、位流 SHA256、验证范围、缺口和回退证据。工具不会操作板卡或更新 accepted／latest 指针。稳定边界说明放在架构文档，具体候选和实测结果放在日期报告。
