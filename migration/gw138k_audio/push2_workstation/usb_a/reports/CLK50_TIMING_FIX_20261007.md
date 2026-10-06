# 50MHz 低 BSRAM 时序修复（2026-10-07，进行中）

本轮目标是修复当前 full84 的 50MHz 域，保留 CNN 分级缓存和示波器/TF 集成，
P&R BSRAM 预算不高于 260。板上仍是 0x00000084；候选 0x00000085 尚未烧录。
全设计音频/USB/DDR 的其他时序问题与 50MHz 域闭合分别记录。

## 基线与定位

- 当前基线：`results/workstation_scope83_20261006_230626_011557/`，提交 `ffd007d` 的
  权威状态记录板上 full84，P&R BSRAM=260。
- 原报告 clk50 Fmax=41.813MHz，Setup TNS=-669.020ns / 356 端点，Hold TNS=0。
- 原报告默认最差 50 条主要被跨时钟路径占满，没有显式 clk50->clk50 setup/hold
  报告。不能依据总 TNS 确定全部内部瓶颈，更不能把构建成功标记为闭合。
- 保留所有原始 RTL/时钟/时序例外，在复制的完整 full84 树加专项报告，独立增量
  P&R 定位：`results/clk50_fix_20261007/baseline_clk50/`。基线原树不修改。

## 第一项 RTL 改动

`rtl/music/basic_pitch_viterbi.sv` 将候选循环拆分为 READ / SUM / SELECT，最后一项
比较完成后另拍 COMMIT。原来一拍串联 RAM/mux、转移代价、32bit 加法、比较、选择与
最终分数加法，现在用 3 个 32bit 标量寄存器隔开。score、prev_score、emission 与
历史 RAM 原样保留；未加数组、未复制 CNN 特征缓存，卷积 MAC 节拍未改。

`p_cnt` 在 READ/SUM/SELECT 期间保持，索引与数据一致；严格 `>` 保留首次获胜的
平分规则；最后候选先更新 best，再提交分数/回溯指针，避免 NBA 最后一项漏比较。
理论额外周期为 171×89×(2×89+1)=2,724,201，即 50MHz 下约 54.48ms/172 帧窗；
板上窗耗时影响仍须实测，不能把理论值当实测。

## 已完成验证

- Icarus 四态 172×89 数学递推 oracle PASS：全部分数/回溯指针、静音/平分、DDR
  延迟/背压、并行 delay 写流、28 项出谱。旧地址负对照仍在 frame=1/state=0 捕获碰撞。
  证据 `results/clk50_fix_20261007/dp_oracle/`。
- 新 full85 完整 staging 的 scope 8 项、菜单/playlist/guidance 7 项已 PASS；
  TF 16 项、delay 等价与完整回归仍运行中。
- 12 帧 CNN 双配置六层哈希与出谱等价性运行中。

## 构建与检查工具

- `tools/build_full_song_85_clk50_timing.py` 从完整 full84 树构建，仅显式覆盖允许文件，
  UserCode=00000085，保留原 SDC 并新增 clk50 专项报告。构建前后检查输入与冻结 SHA256，
  P&R BSRAM >260 即失败；不操作板子，不修改部署状态。
- `tools/audit_clk50_timing.py` 必须看到显式 clk50 setup/hold 报告，检查 WNS、端点
  TNS 和 Fmax。缺报告返回未闭合；不会把默认报告遗漏的路径当通过。
- 第一候选：`results/song_guide_full85_clk50_20261007_002805_594995/`，完整构建进行中。
- 五项冻结文件全部 SHA256 未变，BP 回溯地址继续保持 0x30400000。

尚未宣告时序闭合或候选板级验收。最终结果将在取得 P&R 路径、资源和回归后补充。
