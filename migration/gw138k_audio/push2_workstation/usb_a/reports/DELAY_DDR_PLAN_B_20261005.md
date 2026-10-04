# 方案 B 设计稿：delay_stage 延迟线 DDR 化（2026-10-05）

## 目标与收益

`u_workstation/effects/delay_stage`（P10 延迟效果）现占 **64 块 BSRAM**
（双通道 16384×32bit 环形缓冲）。迁移到 DDR 后片上仅剩两条异步 FIFO，
**预计 64 → 约 5 块，总量 279 → 约 220**。音频行为位精确不变（验收标准：与原实现逐位一致）。

## 关键事实（设计依据，全部已核实）

1. **读指针恒定落后写指针 9600 样本**（`read_address = pointer - ECHO_SAMPLES`，
   编译期常数，无运行时变调）→ 纯顺序流，**无需随机访问**，是理想的 DDR 环形流。
2. DDR 带宽需求：延迟效果被调度时每样本 8 字节 ×2（读写）= **最坏 768 KB/s 顺序流**，
   相对音频环（128 MiB、现有 TF 流 240 KB/s）是零头。
3. 地址图**早有预留**：`PRJ1_DDR_BULK_POOL`（0x3000_0000，256 MiB）注释明示
   "BSRAM migration, delay/reverb histories"。延迟环取首 1 MiB granule，
   环长 16384 立体声样本 = 128 KiB（与现 DEPTH 一致，语义不变）。
4. **仲裁器 owner 3（writer）在顶层无消费者，但它是只写口（无读响应路由）**；
   延迟 DMA 需要读 → **在 `gw138k_ddr_arbiter.sv` 增加 owner 6（读写）**，
   优先级插在 music(5) 之后、cpu(2) 之前（384 KB/s 的实时流，不能饿但也不许干扰
   TF/CNN 的既有延迟保障）。仲裁器是我们自有文件，改动局限在 owner 译码/ready/
   response tag 三处，用现有 `tb_workstation_ddr_audio_arbiter` 扩展验证。
5. 冻结文件处理：`stereo_effects.sv` 的延迟实例化处仅换模块名
   （`serial_delay_effect` → `serial_delay_effect_ddr`，接口逐位相同），
   与顶层补丁同模式（构建脚本字符串替换，冻结源哈希不动）。
   调度语义天然保留：delay 仅在 `state==SEND && work_id==0` 时收样本——
   效果被 mask 掉时零流量、指针冻结，与原实现一致。

## 架构

```
音频域 76.8MHz                          memory 域 100MHz
┌───────────────────────────┐   异步FIFO   ┌──────────────────────────┐
│ serial_delay_effect_ddr    │ write(65b)  │ delay_ddr_dma (owner 6)   │
│  5状态FSM/增益slew/饱和    │ ←────────── │  wptr/rptr 各 16384 样本  │
│  同端口：valid_i/left_i…   │   4KB       │  环 @0x3000_0000,128KiB   │
│  wet 门=frames>=9600 不变  │   异步FIFO   │  256bit 突发,读领先预取   │
│  （state1 改从 FIFO 出数） │  read(65b)  │  水位: 高停读/低续读       │
└───────────────────────────┘  ─────────→  └──────────────────────────┘
```

- 音频侧 5 状态 FSM 的算术（增益 slew、50% 反馈、饱和、clip）逐位保留；
  唯一改动：state1 的 `read_l/r` 改从读 FIFO 出（原为 BRAM 同步读，时序等价），
  state4 的写改为推入写 FIFO。
- 欠载行为：读 FIFO 空 → wet 按 0 处理（与现有 `frames>=ECHO_SAMPLES` 启动门语义
  一致，不爆音）；DMA 侧读领先预取 + 高水位暂停，正常情况下欠载不可达
  （DDR 服务延迟 µs 级 vs FIFO 缓冲 ~10ms）。
- 溢出行为：写 FIFO 满 → DMA 必然已落后 >10ms——带宽余量 100 倍，可达性≈0；
  仍设计为"DMA 最高优先消化写 FIFO"，不阻塞音频采样路径（与原实现"永不反压
  合成器"一致）。

## 片上 BRAM 账

| 项 | 块数 |
|---|---:|
| 写 FIFO（4KB，65b） | ~2 |
| 读 FIFO（4KB，65b） | ~2 |
| （DMA 无需额外 ping-pong，FIFO 即缓冲） | 0 |
| **替代前** | **64** |
| **净省** | **~59 → 总量 279→约 220** |

## 验证计划

1. **等价性 TB**（核心）：同一伪随机样本序列分别灌原 `serial_delay_effect` 与 DDR 版
   （配行为级 DDR 模型），越过 9600 样本预卷后**输出逐位断言相等**，覆盖环回绕、
   mask 掉调度、中途 enable/disable、rst 重启四种场景。
2. `tb_workstation_ddr_audio_arbiter` 扩展 owner 6 用例（与 TF/CNN 并发不饿死）。
3. 全套回归（16 项 TF + guidance 套件）+ 0x80 构建（BSRAM 审计应显示 delay_stage
   64→~5）。
4. 板测：P10 延迟开启听感比对 + 长时间运行（telemetry 无新异常）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| DDR 读抖动致欠载爆音 | 读 FIFO 水位 + 领先预取；欠载退化为 wet=0（原语义），加欠载粘性标志 |
| owner 6 改动影响 TF/CNN 延迟 | 优先级插最低档；既有仲裁 TB 扩展并发用例 |
| 与吞吐优化窗口冲突 | 构建基线统一 full79 暂存树；烧板前跨窗口同步（简报已约定） |
| 冻结文件补丁漂移 | 仅一行实例名替换，脚本 assert count==1 |

## 工作量

RTL（wrapper+DMA+arbiter owner 6）+ TB 约一天；构建 + 板测一轮（约 1.5 小时）。
改动文件：`rtl/audio/delay_ddr/`（新）、`gw138k_ddr_arbiter.sv`、
`ddr_address_map.vh`（记录 granule）、构建脚本 0x80（含冻结文件补丁）。
