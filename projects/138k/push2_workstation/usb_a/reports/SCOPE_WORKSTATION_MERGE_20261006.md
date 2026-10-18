# 2026-10-06：将矢量/TF 示波器入口接回完整 0x83 workstation

本次是离线集成，基线为用户已验收的 `cnn83-accepted-20261006`。完整工作站保留 CNN staged caches、TF 热插拔/目录/整曲练习指引、P10 delay DDR、USB Push、HDMI/display-data、AE350 和原实时合成器，并接回现场几何 voice 与 TF 示波器播放入口。代码提交 `a8376bd`；机器可读验证绑定见同名 `.json`。

## Git 状态与选用基线

2026-10-06 执行 fetch 和 `git pull --ff-only`，返回 `Already up to date.`。起点为本地 main `d0c92a0`，origin/main `e966c01`；本地已有 13 个后续提交。以下优化与修复已经在本地历史中，不能退回早期 scope 候选重新构建：

| 提交 | 当前集成必须保留的内容 |
|---|---|
| `1a41c0a` | TF/song guidance、热插拔、整曲窗口及前期 scope 源码 |
| `7437dda` | P10 delay 迁往 DDR，仲裁 owner 6 |
| `dcd86f6` / `97e68f6` / `e966c01` | 0x80 PNR/听感验收记录 |
| `2402e37` | 0x82 特征/权重/平面缓存，避免每个 MAC 单独取 DDR |
| `e1f50f7` | Viterbi score pipeline，保持原算术语义 |
| `8bc80e9` | CNN traceback 地址迁到 0x30400000，避开 delay ring |
| `af2ff9a` / `d0c92a0` | 资源口径修正、0x83 Model E/吞吐量与用户验收 |

实际基线为 `results/song_guide_full83_20261006_203125_607466/Prj1`，按其 `workstation_inputs.json` 全量检查 SHA256 后复制到新目录。之前的 scope 源码虽然已经进入 Git，但 0x83 staged top 没有 TF scope transport、最终 DAC 选择器和最终引脚显示采样接线。因此此次提交集成这些接口，保留已经验收的 CNN/DDR/固件实现。

对 baseline 的 73 个 `rtl/music` 文件逐一校验并保留；未被工作站实例化的 standalone `basic_pitch_tf_board_top.sv` 有一处后续 `pcm_end_i(0)` tie-off，stage 仍保留验收版本。另对 DDR arbiter、HDMI、DDR 地址表、delay DMA 和 delay effect 五个冻结文件核对固定 SHA256。

## BSRAM：228、216、260 的统计含义

| 工程/阶段 | 占用 | 含义 |
|---|---:|---|
| 2026-10-01 完整工作站 SYN | 228/340 | 含 TF WAV/FAT/SPI、几何 voice、USB/HDMI/AE350/P10；当时未实例化 Basic Pitch |
| 0x80/0x81 完整工作站 PNR | 215/340 | delay DDR 迁移后、CNN 缓存修复前 |
| 已验收 0x82/0x83 完整工作站 PNR | 260/340 | 保留 CNN 吞吐缓存，余 80 个物理块 |
| 已验收 0x83 完整工作站 SYN | 216/340 | Gowin SYN 的 block-equivalent 口径 |
| 本次完整 scope 合并 SYN | 216/340 | 已展开 TF、CNN、8 vector voice、P10 DDR delay 和完整界面 |

0x82/0x83 相对 0x81 的 PNR 净增 45：feature cache 32、weight cache 8、plane cache 2、pipeline buffers 3；Viterbi 两版都是 6，不能重复列入增量。SYN 与 PNR 使用不同计数口径，本次 SYN 216 不能解释成从 PNR 260 节省了 44。新候选尚无 PNR 资源数及闭合时序结论。

`LATEST_WORKSTATION.json` 顶层继续保存已上板、已验收的 0x83；新验证结果仅加入 `offline_candidate`。本次不改变 `LATEST_BUILD.txt` 的已验收指向。

## 当前合并行为

现场几何 voice 继续由 HDL 逐样本生成，路径 ROM、包络、音高表达、morph/旋转/校准及控制事件场景沿用现有实现。新构建覆盖现行音频 core，包含 PANIC 后清除遗留 inflight 的修复；不改变原合成器内部结构。P10 默认精确干声，delay/chorus/reverb 可按原控制开启。

TF 示波器模式在共享 reader/DDR bridge 上独立启动播放：

- 进入 TF 模式时取消尚未完成的 CNN 分析窗口，保留模型；播放捕获不依赖模型 ready 或 NN PCM ready。TF 模式不向 CNN 送 `pcm_valid/pcm_end`。
- 保留原 TF capture gate，TF run 为真时允许 SD reader 前进；暂停冻结 decoder/FIFO 读位置，同时 serializer 持续发零。恢复继续当前位置，重播明确 restart。
- `scope_tf_transport.sv` 在 50 MHz 处理菜单选曲、相对切曲、当前曲重播、目录边界和插卡后的同曲恢复。相对切曲始终基于实际菜单选中的曲目，重播不会退回音频域旧的绝对索引。
- 超出实际目录数量、目录重扫后缺少该曲目，或 held-state CDC 合并多个相对操作时，显式置 `error_o` 并停播。有效绝对选曲、菜单确认或重播可重新启动；不会把越界曲目静默截断。
- 退出 TF 模式会清除曲目 pending/started 状态和旧 CNN 分析上下文；原歌曲菜单下次选曲重新启动分析，不需要重复上传模型。

最终物理引脚由 `scope_dac_select` 在帧边界切换，期间使用功放 shutdown 和完整帧 settle。现场几何模式具有输出优先权；现场静音/PANIC 不会让 TF 自动夺回 DAC。

显示继续使用现有 display-data/DDR 通路。`pt8211_observer` 从最终 `hp_bck/hp_ws/hp_din` 还原真实 L/R；切源期间清零观察器。PCM、参考标记、voice mask、健康计数经同一 128-bit acknowledged CDC 发布，避免引用旧显示批次的 metadata。TF 的参考标记和 voice mask 为零；原合成器的参考与 voice 信息保留。分析器启用 direct X-Y：L→X、R→Y，不建立新的显示架构。

## Push 操作与菜单优先级

| 操作 | 当前完整工程行为 |
|---|---|
| Session（物理 CC51 → 引擎 CC104=64） | 切入/退出 TF 示波器模式；进入前须无活动 voice |
| Play（CC85） | 保留原 TF 歌曲菜单打开/关闭 |
| 菜单内 Left/Right、Select | 浏览目录、确认曲目；TF 模式下无需模型直接播放，其他模式保留识别/练习入口 |
| 菜单外 Left/Right（CC44/45 → CC108） | 切实际正在播放曲目的前一首/后一首 |
| New（CC87 → CC105=64） | 暂停/继续 |
| Duplicate（CC88 → CC105=127） | 重播当前实际选中曲目 |
| 菜单外 Select（CC48 → CC90=64） | 切现场几何模式 |
| Mute/PANIC、pad、力度、旋钮、弯音 | 保留现场几何实时演奏映射 |

外部 TF 预录示波器音乐使用独立播放入口，不能作为参赛实时合成吞吐量。此前已准备的 MIT 衍生素材及卡外复制工具见 `tools/tf_scope_media/README.md`；此次 Git 合并没有增加实体读卡器复制或板测结果。

## 离线验证及证据

最终构建：`results/workstation_scope83_20261006_223538_716443`。

综合结果：Gowin exit 0、597 个输入 hash 不变、完整 SYN BSRAM **216/340**。`workstation_memory.json` 检查完整工作站层级；另外确认保留 `u_scope_output`、`u_final_output_observer`、`u_final_output_cdc`、`u_tf_control_cdc`、`u_tf_scope_transport`、`u_delay_ddr_dma`。原有 CNN 的未驱动 LUT 端口告警数量与验收基线相同，未借本次接线修改其冻结算术。

`current_regression_20261006_223547_564765/verification.json` 的 **18/18 门禁通过**：8 个 scope TB、7 个原 Push/menu/playlist/hotplug/guidance TB、TF 16-case suite、delay DDR equivalence、BP DDR isolation。关键量化结果：

| 检查 | 本次结果 |
|---|---|
| scope transport | 21 项断言；10 次有效 restart；含菜单曲目/相对边界/暂停/热插拔/合并命令错误 |
| 真实 DAC/显示配对 | 722 个 L/R 发布；暂停区间 77 个零配对；同帧参考/voice/health 校验 |
| 切源 | 4231 synth pair、152 TF pair；最短 BCK 脉冲 12 audio 周期，无 mux 短脉冲 |
| 工作站调度 | 最长 1067/1600 audio 周期，coexist deadline miss=0 |
| X-Y | 四象限 direct L/R 与 legacy 投影分别断言 |
| 原 TF suite | 16/16 PASS，涵盖 WAV/MP3/FLAC 和 SD/FAT/DDR 边界；完整工作站本次仍只展开 WAV |
| delay DDR | 45,000 样本逐位等价；故意施加长 DDR stall 的 underrun 分支已覆盖 |
| CNN traceback / delay 并发 | 172 帧×89 states 数学 oracle、28 notes PASS；旧 0x30000000 地址负对照在第 1 帧失败，验证测试能检出碰撞 |

原几何引擎的包络、morph、扫描精度和防混叠频谱证据仍见 `rtl/audio/scope_vec/VERIFICATION.md`。本次重跑集成与地址隔离，不把未重跑的整条 CNN 12-frame A/B 或原频谱测量标记成本次新测量。

五种非法 current-build 配置在 staging 前明确拒绝；`build.py --current-workstation --prepare-only` 与最终 SYN staging 的 597 个输入 SHA256 全部相同。新回归不写样本流/PCM/波形 dump；TF 既有压缩 fixture 解包到仓库外临时目录，运行后清理，仅保留日志、指标与输入 hash。delay 仿真输出也放在新 results，避免修改已跟踪的旧 `.vvp`。

## 复现与未验证范围

从 `usb_a`：

```sh
python3 build.py --current-workstation --prepare-only
python3 build.py --current-workstation --synthesis-only
python3 sim/scope_vec/run_current.py results/<新 workstation_scope83 目录>
```

也可直接使用 `tools/build_current_workstation.py`。此入口要求本机已有上述验收 baseline 及其清单，缺失/漂移失败；仅允许 WAV 的 prepare/SYN，不分配 UserCode，也不运行 P&R 或 programmer。原不带 `--current-workstation` 的 `build.py` 保留历史构建用途，不能代替此次完整 0x83 基线。

新候选未 P&R、未下载、未进行耳机/Push/HDMI/插卡板测，没有 routed 时序证据。SYN 估计 audio 为 43.635 MHz（目标 76.8），USB 为 38.330 MHz（目标 48），不能宣称时序闭合；已验收 0x83 本身的静态时序也仍未闭合。构建的 `build_metadata.json.git_commit` 保存构建开始时 HEAD `d0c92a0`；本次代码包含未提交修改，最终 `.json` 的 `source_commit` 与输入 SHA256 才是合并代码绑定。所有本地 results 仍按项目约定不进入 Git；提交的是代码、可复现入口及量化记录。
