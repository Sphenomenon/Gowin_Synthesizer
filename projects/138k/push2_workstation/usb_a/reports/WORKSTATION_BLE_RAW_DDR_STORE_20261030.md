# BLE 短录音 raw DDR store 组件

日期：2026-10-30。此阶段交付独立存储组件及离线回归，不改变任何生产 profile、DDR 地址权威、原始 25K BLE 业务文件、vendor、冻结来源或板上内容。R00 的整机与硬件验收仍须分别完成。

## 实现与归属

新增 `rtl/memory/workstation_ble_raw_ddr_store.sv`，负责 50 MHz 控制域的连续 PCM32 采集、有界异步 FIFO、memory clock 域的 256-bit DDR 命令及原始 PCM 读缓存。原 BLE endpoint 继续拥有录音 ID、对象状态、任务、CRC、编码、重放和可靠传输；组件不新增另一套业务对象，也不反压实时音频。

`BASE_APP` 为八个 native 32-bit words 对齐的参数；本组件没有硬编码绝对分配。集成者须在唯一 `ddr_address_map.vh` 中分配与 CPU R00 独立的 64 KiB。最多 16,384 个 PCM32 帧，FIFO 默认 256×65 bit。帧与有序 close marker 共用 `{kind,index32,pcm32}`，start/clear/fetch 走独立不可变 descriptor 邮箱。

真实 native acceptance 才推进 committed；local slot readiness 不算提交。已发布命令在接受前保持所有字段。clear 即时隔离捕获与旧缓存，但保留已发布命令和未返回读的所有权，消费 immutable FIFO event target 后才能完成。超时／transport／协议错误会隔离 channel，迟到完成仅退役，不恢复 admission；共同 reset 必须同时复位并隔离外围 mux／ledger／controller 的旧物理响应。对象局部 clear 不能替代这个条件。

accepted 位于控制域，committed／drained／fault 通过不可变状态快照返回。start/clear 都递增 32-bit generation，达到上限即隔离、不回绕。FIFO 计数只用有界 FIFO 的 modulo pointer 宽度，不靠逐位多位同步形成一致快照。

fetch 只读取成功、closed/drained 的 committed prefix，长度 1..8112 bytes、范围加法不回绕；最多搬运 8160 bytes 的完整首尾 DDR beats。256-bit 响应邮箱在控制端写完八个缓存词后才 ACK。缓存为四个 16×1024 SDP，组合成 8 KiB，保留全部 PCM32；`sample_addr_i` 沿用绝对帧地址，一个控制时钟后返回，窗口外或未发布缓存返回零。

完整边界见 [组件契约](../rtl/memory/WORKSTATION_BLE_RAW_DDR_STORE.md)。默认命令／读超时分别 10,000 memory cycles；它们与 BLE seal 等待预算是不同边界，集成必须显式协调。

## 复现与结果

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_ble_raw_ddr_store.py \
  --output <不存在的新目录>
```

机器证据：[ble_raw_ddr_store_v1.json](workstation_task_20261030/ble_raw_ddr_store_v1.json)。完整本机日志目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/ble-raw-ddr-store-v1-sealed/`；输出身份及日志哈希包含于机器证据，不提交生成的 vvp／网表／波形。

| 场景 | 结果 |
|---|---|
| FIFO depth256、控制周期20 ns／memory周期14 ns | 94,609 checks 通过 |
| FIFO depth8、控制周期20 ns／memory周期10 ns | 93,114 checks 通过 |
| 四个行为 mutation | 全部在指定断言拒绝 |
| Verilator 5.052 lint | 仅精确匹配四个已审 warning，无新增诊断 |
| 验证前后七项来源 SHA | 一致 |

回归覆盖全部 1..15 帧 partial／burst 边界、完整 16,384 帧与 capacity overrun、字节掩码和 PCM 位精度、8112-byte 非对齐最大 fetch、两个缓存 depth banks、窗口外零值、单周期绝对地址读取、held request 只接受一次、local/native 提交区分、clear 等待真实写与读退役、旧 fetch 取消／迟到返回、FIFO 溢出／index gap 的 accepted prefix drain、descriptor 越界、command/read timeout、transport／无主响应／无主 native accept、generation 耗尽及暂停 memory clock 的共同 reset。

相位测试先确定复现了 START 错误：控制端已接收 start 后暂停的 memory clock 恢复，使新 FIFO 与 START 同时可见，旧 `!fifo_read_valid` 条件错误拒绝合法新帧。现改为验证旧 epoch 已消费至 descriptor event target 且 native quiescent，新帧可立即开始；对应 mutation 被 `real transport drain` 断言拒绝。

native read accept 与 response 同拍时以 still-published generation/word 接收并直接退役，后拍返回继续使用保存的 read owner；无读 owner 的响应仍为协议错误。同拍正向测试通过，回退该行为的 mutation 被拒绝。另外两个 mutation 分别把 local slot 当提交、清零 partial mask，也均触发指定断言。

四个 lint warning 精确限于共享 FIFO 的 `RAM_STYLE` 属性和大深度分支未使用 `full`，以及两组 reset release vectors 的同步移位／异步 reset 使用。runner 不宽泛屏蔽 warning；这些审阅不替代物理 reset/CDC 验证。

## 来源与后续门禁

七项来源集合 SHA-256：`1803f046faab7e052ac11c8bcf7c10c96d239a8a8869dbc7c2dec51cdcdc6e85`。raw store：`2c6ebca8e1766c2cd891c690c2717393064e289bfdb45a521e3baea51737cb9e`。其余逐项身份见机器证据。

本组件未进行综合、RAM 原语映射审计、P&R、物理 CDC／时序验收或板测；四块 cache SDP 与 FIFO 的实际物理 BSRAM／CLS 净收益须由集成后的真实网表证明。生产 source selection、owner8 两客户端 mux／共同 reset fence、BLE 五层适配、真实音频／下载以及 SRAM 实测分别归后续阶段，不能用组件仿真勾选整机任务。回退方式是不选择此新增组件；旧 profile 和原业务 bytes 本阶段未变。
