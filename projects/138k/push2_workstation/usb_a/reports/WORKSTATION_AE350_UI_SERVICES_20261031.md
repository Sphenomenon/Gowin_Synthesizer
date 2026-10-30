# C02：AE350 实际主循环分步服务

日期：2026-10-31。基底 `2d0ba73`。本阶段修改维护 `firmware/ae350/ui_main.c`，
同步四份显式 profile 的该文件 owning SHA，并增加实际 C 入口与 APB 回放 fixture。
不修改 stage、启动、链接、冻结基线或硬件；不为原 accepted 候选复用身份。

## 实际行为

- `services_main` 运行期只调用同一个 `ui_service_step`。一次迭代推进各自有界的
  控制、采集和绘制 job，输入采样撕裂不会跳过这些工作。
- 绘制固定 model／touch／revision，独占 back page，每步只写两行。
  最后一行完成及 fence 后只提交一次。pending 时每次只读一个状态，实际
  base／visibility／commit+1 一致后才交换软件 front。新的已提交状态保留给后续 job。
- 未发布绘制取消会作废 back cache，下次完整分步重画；已接受发布只能等真实
  ACK，不能假装撤销或提前重用页面。该次 ACK 不提升 cancelled revision。
- PCM 快照保留原 MMIO 与结果格式，每步最多取一个实际 FIFO record，原数据
  排空／采后排空各受 1024 帧预算限制，等待受 10000 步限制。只保留前四帧用于
  原结果；超时、空结果或排空预算失败均报告错误。当前 token 固定，后续保留最新 token。
- 模式请求先发原 CC123，每轮最多一次实际 voice snapshot，等待真实零声部或
  48000 帧期限；32-bit frame wrap 保持正确。等待中的新请求按显式字段合并，
  不用旧硬件反馈覆盖排队模式。主循环先观察 PANIC，再撤销排队 gate 并提交控制。
  没有增加 18-bit 事件元数据或另一份 committed 参数权威。
- 自检后的首次两页绘制、控制释放和四次发布等待，在每个 slice／poll 运行
  `idle_audio` 与可选 BLE business pump。原 `ddr_checks`／`audio_checks` 启动
  自检循环未转换。`A138_BLE_BUSINESS` 默认关闭；这里只提供约定的 init／pump 调用点。

## 验证与可复现入口

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_ui_service.py --output <新目录>
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_ui_slices.py --output <新目录>
python3 projects/138k/push2_workstation/usb_a/sim/test_stage_ae350_firmware.py
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

服务 fixture 编译实际 `ui_main.c`／`ui_render.c` 临时副本，仅将 `audio_services.h`
低层读写／fence 和诊断终止接到 host。模型、绘制、快照、record-try-read 和生产
主循环逻辑保持源字节。独立像素 oracle 来自固定历史提交
`94fd199757e1da92367c6ac15555993d0e1d4ff5`，原 renderer SHA256 为
`5188d9777768e6ec6951982f3d2776fb49d20a8d0384aa31b0d742c1653c4c91`。

原生与 ASan／UBSan 各通过 **33664 checks／2887 steps／5 publications**；
观测运行迭代最大 **33 MMIO**（不是全部输入的形式化最大值）。未发布 front 每步
字节不变，写入不越过该两行，最终整页与历史 oracle 一致。30 次 pending 轮询
不退休；模拟慢 CPU 后由真实 frame commit 退休。10 个编译成功的行为突变均拒绝：
提前发布、丢冻结 model、提前交换 front、伪取消已接受发布、丢后续状态、忽略排空
预算、跳过真实声部释放、PANIC 后补排队 Note On、PANIC 前提交、单步完整 patch。

两个构建的 UI 总线转录分别在实际锁定 `gw138k_ui_services` RTL（对象
`60dae3b5e3be5888511639ea033a5e9fd71c1e16009bcaf3aa73a289873b906d.sv`）
回放，各通过 **7230 reads／15 writes／5 commits／3 resets**，包含活动 DDR
地址图头文件。此回放核对真实 APB 寄存器语义，不代表扫描读出、CPU 或 DDR 时序。

原行像素回归原生／sanitizer 各 78 次比较；固件测试 10 项、accepted 来源测试
17 项通过。四 profile 单元测试分别 21／7／7／6 项，其中 15／2／2／4 项因
没有真实 prepare 环境而按原条件跳过；未把这些 skip 当作 prepare 通过。

## 实际容量与失败保留

使用 `/opt/homebrew/bin/riscv64-elf`、既有 `-O2` 选项，真实产物结果：

| 配置 | 结果 | 静态 RAM／剩余栈容量 |
|---|---|---|
| 默认 pl16k_8k | 14476／16384 bytes | 60／7620 bytes |
| pl16k_8k ＋真实 recording API | 16252／16384 bytes | 60／7620 bytes |
| ilm64k_dlm64k ＋ recording API，实际旧 16K cold | **拒绝：ROM 超出 384 bytes** | 无成功 ELF，不申报通过 |

`services_main` 编译器单帧为 1008 bytes。当前默认构建未证明完整调用链或实板
栈水位，不能从剩余容量推导已验收。ILM/DLM 后续必须消费 C06 明确扩大冷存储的
新配置再验证；本阶段没有放宽 16K 限制、删除 API 或通过代码修饰掩盖失败。

证据目录：
`/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-ui-step-services-v1/`，
最终服务证据为 `evidence/host-final-v2/verification.json`，最终固件为
`evidence/default-final`／`recording-final`，失败为 `ilm16-rejected-final`。
外部只读 `verify_delivery.py`／`verify_seal.py` 检查来源和结果身份。

本阶段没有综合、P&R、位流、SRAM、Flash 或板卡操作；没有验证总线最长等待、
实际 CPU 服务间隔、BLE pump 时限或完整可见显示路径。C02／C04 整项保持未验收。
回退为还原本提交；冻结基线和原接受 profile 的来源策略没有变更。
