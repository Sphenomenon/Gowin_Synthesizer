# W14 默认完整物理实现

W14 `D211010E` 已完成全量 P&R 和六组物理子审计，整机时序仍失败。setup 7,270 个违例端点、最差 −5.434 ns；hold 1 个端点、最差 −3.538 ns。物理 BSRAM 293／340、DSP 66.5／298、CLS 53,327／69,120；FF 45,092、LUT 57,144、ALU 14,384、SSRAM 298，与综合 equivalent BSRAM 257 分列。不得作为已通过的 D 声画镜像部署。

候选 `custom138k-workstation-w-demo-v1-df8c9ba4d32507f1`，physical manifest SHA256 `6cbe62ec231263753da2d8e28933cbdda06ff4857def0be2a4aff12660305478`；VG `36576c86a2c2c6d42830bb2c75af5441143ca288ca93397b17923de03fee2141`；完整 SDC `fa6bfc049f6a1f4910d8c4391f04457534ef67deeb5eccb5d4f38aaaef704f65`；FS `18ffab6fa64a7e3468bdf8d211a06758e58cff0069d34d08687e4783c0cb6b66`。[机器报告](dual138k_w14_default_physical_20261101.json)绑定配置、全部执行命令、来源及输出身份。

Gowin V1.9.12、place2／route0，关闭资源复制，保留自动 hold 修复和原 DDR 3.500 ns。P&R 437.721 秒，退出 0，布线和位流生成完成。recovery +2.618 ns、removal +0.278 ns。唯一 DDR hold 位于 R87C146 邻近两位置，arrival 1.892、required 5.430、skew 0.486 ns。保持同 VG／完整 SDC、仅追加两条 DDR 远区域 CST 的 `D211010F` 已启动独立 P&R，不预记其收益。

最差实际同步路径为录音 arbiter read_pointer0→raw store memory_failure[2/3] CE，10 ns 关系、约 15.26 ns 数据延迟；随后是 completion_generation CE。即时 owner8／transport fault 否决和原错误优先级保持，后续针对实际 raw 故障与完成发布链修复，不以延后故障、丢信用或减少显示／D 效果通过。此前 fetch-address cache 提案不是当前最差端点，尚未采用。四条实际 clk50 专项报告为 setup −4.967／hold +0.180 ns，全来源 setup −4.967／hold −3.538 ns；100 条上限不冒充完整专项端点统计。

原 W14 v1 strict／boundary 失败记录保持。外部 v2 审计快照只加入已证明的 DMA next-Q helper，完整 strict 和 physical prepare 对同一已封存 VG 通过；v3 只更新增加强负控的测试。全部 1374 冻结审计输入均从旧快照派生并核对精确两文件差异，没有引入后续 TF 维护源或改变 staged／候选来源／原 SDC metadata。

实际 VO native 54 项（40 通过／14 跳过）及 35 破坏负控、boundary 7 项及 69 破坏负控、官方六 PLL／三 shared tuple／7 负控全部通过。全部任务退出后，主线程重验 30 个完整物理文件及 3246 项证据，包含 1374 冻结审计输入、645 staged、951 prepare 来源和 PLL 依赖。完整 seal `w14-audits-v3/default-complete-seal-v1.json` SHA256 `d0e67a2abdce32b20b7ab691324e659dc3c5cb9af487ed89c965b187c8b5a833`。

无板卡操作、SRAM 或 Flash。D A2DP／25K 调参、完整 HDMI／实际 DAC、唯一对象录音下载及并发声画仍需同一合格位流实板验收；当前录音仍约 0.341 秒，不是长录音。手机仅模拟器，真机无线验收稍后，单板分时不代表双板并发。
