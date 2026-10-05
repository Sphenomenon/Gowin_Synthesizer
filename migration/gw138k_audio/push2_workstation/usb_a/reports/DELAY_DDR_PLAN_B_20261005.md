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

## 实现记录（2026-10-05，0x80 构建中）

设计三点确认后已实现并验证：

**新文件**
- `rtl/audio/delay_ddr/serial_delay_effect_ddr.sv`：音频域 wrapper。5 状态 FSM
  算术逐位保留；state1 从读 FIFO 出数（FWFT，时序位置与原 BRAM 同步读一致），
  state4 推写 FIFO。clear_i 通过写 FIFO 带 flush 标记（65 位宽的第 65 位）。
- `rtl/audio/delay_ddr/delay_ddr_dma.sv`：内存域 DMA（owner 6）。环
  128KiB @ BULK_POOL 字节 0x3000_0000（app 字地址 0x0C00_0000，4 样本/256bit 块）；
  单 outstanding 读 + 满 4 样本才发写（mask=0 全块写）；预取水位
  `wptr-rptr >= ECHO_SAMPLES-448`（读 FIFO 永不满、写路径不停、启动零突发）。

**流对齐协议（等价性的核心）**
- 读 FIFO 条目 #m 服务音频样本 m+9600，与原 `pointer-9600` 严格对应。
- clear→写 FIFO flush 标记→DMA 丢弃在途读响应→复位环指针→向读 FIFO 推
  代际标记；音频侧丢弃标记前旧代条目（1/周期），标记后按 1 样本/次消费。
  复位即隐含代际边界（FIFO 双侧同清为空），marker_seen 复位值为 1。
- 欠载（DDR 停顿 >448 样本≈9.3ms）wet=0 + 粘滞标志（流会偏移一个样本，
  病态场景才可达）；写 FIFO 满丢新样本 + 粘滞标志（不反压合成器）。

**验证**
- 逐位等价 TB（`sim/audio/run_delay_ddr_equivalence.py`，iverilog）：冻结
  `serial_delay_effect` 作参考，45000 样本（覆盖 clear@12000、60µs DDR 停顿
  @20000、中途复位@30000）valid/ready/left/right/clip 全等；长停顿场景
  underrun/overflow 粘滞标志正确、无挂起。
- 仲裁器 TB 扩 owner 6：满块写受理、优先级（高于 CPU/写者，低于
  scanout/TF 音频/music turn）、标签响应路由。过程中修了测试自身的两个错
  （标签队列未排空顶满 DEPTH=8、delay_valid 持续有效却期望 CPU 获服务）。
- **教训（行为级 DDR 模型陷阱）**：模型停顿期间曾让 ready 继续翻转但不受理
  ——仲裁协议里 ready=1 必须意味着受理，否则主设备以为完成而丢请求。第一轮
  综合前的等价 TB 由此抓出 ~107 次丢写。真实仲裁器 `delay_ready=app_en&&owner==6`
  只在真受理时脉冲，RTL 无此问题。
- 0x80 构建：`tools/build_full_song_80.py`（基线 full79；冻结文件哈希断言后
  补丁：stereo_effects 端口 + delay_stage 实例换名接线；穿线链
  event_workstation→controlled_adapter→usb_controlled_audio→push_top；
  gprj 新文件插在 music_async_fifo 之后保证包/FIFO 先编译）。
  第一轮综合暴露 stereo_effects 端口名带 delay_ 前缀与实例裸名不一致——已改
  为裸名 + 隐式同名连接。
- 注意：live 树的 `hdmi_display.v` 曾落后于 staged 血统（缺 music 端口），
  已同步后再加 delay 端口；`gw138k_event_workstation.sv` live 与 staged 双向
  分叉（live 多 scope 控制与 PANIC 修复），构建只对 staged 打补丁，live 仅
  镜像端口，禁止整文件拷贝。
- 烧板前需与吞吐优化窗口同步（UserCode 0x80 归属本窗口）。

## 0x80 构建结果（2026-10-05 05:41，results/song_guide_full80_20261005_045703）

- **构建成功**（gw_sh 全流程 exit 0，位流 `impl/pnr/Prj1.fs` 已生成，未烧板）。
- **BSRAM：279 → 215（-64，SDPB 218→154）**，与设计预估一致——delay_stage 的
  64 块全数迁出，SDPX9B/pROM/pROMX9 不动；两条 512×65 异步 FIFO 走分布式
  RAM（BSRAM 计数零增长）。
- 时序：audio_76m8 TNS -2123→-2419ns，但 0x80 榜首路径全部是 FIFO Gray 指针
  →同步器的**跨时钟 CDC 路径**（audio_76m8↔ddr_ui100），与 0x79 榜上既有的
  format_sync/ddr_rsp_cdc 同类——STA 按单周期悲观分析，Gray+2FF 同步本就为此
  设计，基线实板数周无碍。真正的域内读出 mux 路径（read_binary→FIFO 存储读出）
  不在违例榜。可选后续：在 SDC 给两组 FIFO 的 Gray 总线加 set_false_path/
  set_max_delay 清报告（与现有 CDC 路径同处理）。
- git：commit 7437dda（RTL+TB+构建脚本+报告），已推送 origin/main。
- 下一步：与吞吐优化窗口同步后烧板（UserCode 0x80），P10 开延迟听感比对 +
  长时间运行 telemetry；BSRAM 审计应显示 u_audio 122→58。

## 板测验收（2026-10-05，用户执行）

0x80 板上实测通过：P10 延迟开启弹奏，尾音与 0x79 听感一致（逐位等价在
sim 已证），无爆音/无 wet 丢失。方案 B 验收标准全部达成：
- 片上等价：45000 样本逐位相等（clear/停顿/复位四场景）
- 板上听感：用户验收通过
- BSRAM：279 → 215（-64）
遗留可选项：SDC 为两组 FIFO 的 Gray 总线加 set_false_path/set_max_delay
清时序报告（与既有 CDC 路径同处理，纯报告整洁性，无功能影响）。
