# 新板 USB2：真实工作站输入 owner／FIFO 集成

日期：2026-10-22。继 `e896526` 推送检查点继续本地开发；没有再次提交／推送，也未操作板卡、SRAM 或 Flash。本阶段把实际业务 CPU 从外部服务模型接到原工作站控制 owner、事件 FIFO 和音频域读端，不把组件通过当作新板整机完成。

## 1. 实现与来源

- 显式选择 `build.py --prepare-usb2-soc --usb2-component workstation-input --usb2-firmware-profile workstation`；输出必须是新目录。默认 SoC、accepted full83、pinned timing85 和资源整机候选不改用本组件。
- 新组合 `rtl/workstation/workstation_usb2_input.sv` 复用原生 VexRiscv／USB2 SoC、原 `push2_usb_a_control`、原 18 bit 事件 FIFO／读缓存和反馈 CDC，不复制公共参数、音频或应用实现。
- `tools/workstation_usb2_input.py` 显式选择 11 项当前 owner／交互／显示及新装配源，并从 `resource_rework_route0` 的版本化锁定基线还原四项支持源。加上 SoC 的 14 项，共 29 项 RTL；四项分别为事件 FIFO、反馈 CDC、Push MIDI 解码和字体。
- 缺少支持源、前后输入 bundle 漂移、已复制 owner／支持源漂移均失败，不回退 probe 或私有暂存。四时钟及其频率写入生成 SDC 和 metadata，保留 48／50／60／76.8 MHz，不新增 false path。

接口、域归属、MMIO 白名单与完整失败语义见 [输入组件说明](../rtl/workstation/USB2_INPUT.md)。CPU 域的显示／服务／score／playlist 端口不能当成已经跨域的公共总线；外部组合根仍需实现必要 CDC。

## 2. 断线与背压

服务适配器只捕获一笔服务请求；请求保持时至多提交一次，原 owner 接受的同拍反馈 ACK。CPU 撤销后立即撤销 owner 选择，禁止等待超时后的迟到副作用。非法、未对齐和部分写仍报总线错误，不放宽 CPU sticky fault 门禁。

传输会话失效时直接根据原 owner 的 connected 状态优先提交断开，触发原 FIFO 清空、读缓存排空及音频域取消生命周期，不等待业务固件完成下一轮轮询。旧会话的 MIDI／connect 请求以取消完成、不提交 owner，避免正常断线被误作永久 CPU 总线故障。`canceled_requests_o` 记录 CPU 撤销／旧会话取消的饱和计数；ACK 不代表参数应用成功。

正常 FIFO 满仍背压 CPU，不停音频时钟。默认 10 ms 服务超时仍保留并记录真实 sticky fault；尚不证明任意长下游停顿后的自动恢复。18 bit 布局及 kind 15 接入／断开／PANIC／屏障语义未改变。

## 3. 真实链路验证范围

新增 `tb_workstation_usb2_input_25k.sv` 执行未改业务 `firmware.c`，以实际 CPU／原生 USB2／原 owner／真实异步 FIFO／读缓存，连接实际 25K MIDI USB 核和 PL endpoint。此处**没有工作站服务 ACK 模型**。

HS 和显式 Host FS 各自检查：

1. 枚举、实际速度、地址／配置和接入默认标志；首个生命周期屏障后再交付演奏事件。
2. 阻塞音频消费端直到真实 FIFO 满，使 `54` MMIO 至少等待 200 个 CPU 拍，再恢复并逐项核对首批 128 个音频域 NoteOn／Off 的顺序与内容。
3. 再阻塞音频端，实际接收并入队 20 个旧会话音符；物理模型断线后，不超过八个 CPU 拍检查原 owner 已离线，取消生命周期优先于排队音符。
4. 原 25K 经真实 USB 总线复位丢弃旧地址／配置；保持断线 12 ms 后重接，再经真实业务固件枚举，检查八个新事件，不补播 20 个旧音符。
5. 总计接收 136 个音频事件、两次接入／屏障、一次断开、至少四块 PL TILE；PL 坐标／尺寸、协议、速度、PHY、CPU fault 门禁同时检查。

只把 attach 去抖缩为 100 µs；根复位、recovery、SOF 与四个实际时钟不加速。第一轮及完成来源／内存交叉审计后的最终 HS／FS 均通过；最终输入组件 8 项检查无 skip，耗时 496.398 s，证据保存在 `/tmp/workstation-usb2-input-evidence-20261022-final-v2/hs_{1,0}`。

**仍是模型的部分：** USB3300 是物理协议仿真模型；音频下游只是有背压的事件检查器，没有 `workstation_session`／参数提交／DSP；performance／服务反馈为静态输入；LCD 仍为 tile 完成模型。不能据此声称默认参数实际应用、真实发声、LCD 总线或物理 25K／Push 已验收。

## 4. 实际组件综合与门禁

最终离线组件目录：`/tmp/workstation-usb2-input-synthesis-20261022-final-v2`。GowinSynthesis V1.9.12.03，`GW5AST-LV138PG484AC2/I1`，顶层 `workstation_usb2_input`，实际 29 项输入。

- 38 个 SDPB **另加原事件 FIFO 的 1 个 SDPX9B**，Gowin 综合等效 BSRAM 合计 39，另有 82 SSRAM、3,861 个寄存器；重建网表初始化的全部 16,384 个 ROM word，逐字匹配。此处不是 P&R 物理 BSRAM 数。
- 原 SoC 的寄存器门禁仍为 `<2304`、38 SDPB／零 SDPX9B；只有新增 owner 组件采用独立 `<4096` 门禁。SDPB 的 38 项实例集合、FIFO 的唯一 `storage_storage_0_0_s` SDPX9B 和 XML 的 BSRAM／SSRAM／寄存器总数均严格交叉检查，不放宽默认组件预算。
- 综合 manifest SHA-256：`da10912d4678655a9a936874aa6c6ce24420ed23f44d656e3a653de2aacd60d0`。
- 网表 SHA-256：`b6264a6c3214aa1c8de55892d5aeaaaf550ae7edacc0df57226ca1e237a9660f`。
- 允许 HS 的 ROM SHA-256：`31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457`；不创建新业务固件分叉。

Gowin 保留 32 条警告：EX1998 1、EX3791 24、CV0020 6、NL0002 1。六条 CV0020 对应原 owner 不消费的 performance／display 端口位，未删除接口或屏蔽警告。Verilator `-Wall` 保留原 owner／vendor 的 268 条警告；新装配／适配器零警告，原 SoC 仅允许已有 `cpu_reset_n` 的混合同步／异步警告，三项既有复位警告不是整板 CDC 通过。新装配实例重命名为 `input_owner`，消除与内部 control 的新增遮蔽，而非屏蔽 VARHIDDEN。

综合审计增加 source policy／实际网表 top／29 源集合、四项锁定支持源身份、ROM 单 bit 篡改、寄存器恰到门限及源漂移负例。最初资源负例使用数组实例，未进入按标量实例计数的审计表达式；现改为补齐至门限的独立 DFF 实例，不放宽生产门禁。最终 XML 复核又发现只统计 SDPB 会漏掉 FIFO 的 SDPX9B：现增加缺失／多出 FIFO RAM、错误 top 和错误 XML 总数的负例，并重新综合与执行完整八项，不能把 38 SDPB 写成整个组件只有 38 BSRAM。

## 5. 回归与复现

| 最终执行 | 独立 Python 测试数 | 结果 |
|---|---:|---|
| 新输入组件：实际 CPU／owner／FIFO／CDC、HS／FS 重连、来源／ROM／资源负例及 lint | 8 | 全通过，496.398 s |
| 既有应用 4＋准备 15＋CPU 3＋MMIO 7，含实际 25K、C ASan／UBSan 与默认组件综合 | 29 | 全通过，547.060 s |
| accepted 来源 10＋固件 staging 6＋引脚 25＋clean baseline 23 | 64 | 全通过，6.677 s |

共 **101 个独立 Python 测试，无 skip**；速度／时钟子场景、重复执行及单测内部 C 程序不重复计数。初次保护回归命令误用了不存在的 pinout 测试模块，已改正名称并完整重跑，未跳过任何用例。加强 SDPX9B／XML 交叉审计后，默认组件的实际综合单测另复跑通过，25.014 s，不另加独立测试数；默认 SoC 的 38 SDPB／零 SDPX9B、原寄存器门禁及 ROM 逐字审计继续通过。

```sh
GW138K_USB2_INPUT_EVIDENCE=/tmp/usb2_input_evidence_new \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_input.py -v
GW138K_USB2_APPLICATION_EVIDENCE=/tmp/usb2_application_evidence_new \
  PYTHONPATH=projects/138k/push2_workstation/usb_a/sim python3 -m unittest \
  test_workstation_usb2_application test_workstation_usb2_preparation \
  test_workstation_usb2_soc test_workstation_usb2_mmio -v
GW138K_VERIFY_CLEAN_PREPARE=1 PYTHONPATH=projects/138k/push2_workstation/usb_a/sim \
  python3 -m unittest test_current_workstation_sources test_stage_usb_firmware \
  test_workstation_pinout test_workstation_baselines -v
```

证据目录必须不存在；准备、编译、实际执行日志及复制输入单独保留。机器记录在 `custom_board_usb2_input_20261022/verification.json`，旧应用／CPU 报告的输入哈希和证据不改写为本轮状态。

## 6. 新板交付尚未完成

重新读取三份实际网表并成功完成 101 端口的 pinout-only 准备；电气状态仍为 blocked，未解除 USB3300 与转换器电平不匹配。功放网表的 U1 仍只有 LQFP-48／`{Value}`，不能据此决定 serializer、MCLK、PDN 或滤波配置。蓝牙剩余球位与反序排线、DAC 型号／接线、电源及真实新板组合根仍待完成。

下一步将事件边界接入 `gw138k_usb_controlled_audio.sv` 现有 `usb_event_*`、`usb_lifecycle/cancel`，复用其 session／公共参数和实际音频执行；保留现有反馈／服务／显示 CDC，而非把音频域 performance 总线直接接到本组件 50 MHz 输入。随后补齐板级时钟／复位、HDMI 串行极性、TF、BLE 与功放驱动的可观察诊断，再做 P&R、时序／CDC／PLL／资源门禁与明确授权的硬件验收。不得跳过电气门禁或把本组件直接下载到板上。

回退是继续既有显式 accepted／资源配置；本阶段没有修改冻结基线、vendor、latest 或部署索引，没有新位流，故无 SRAM／Flash 回滚动作。
