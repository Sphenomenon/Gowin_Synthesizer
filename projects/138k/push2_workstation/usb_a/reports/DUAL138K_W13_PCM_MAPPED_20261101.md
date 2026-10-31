# W13 PCM 实际分组与 live rejected COMMIT primitive 证明

W13 实际 VG 中的 20 个 key 分组全部保持了预期函数，完整 key 等式和真实拒绝 COMMIT 作用锥通过 Boolean 等价证明。拒绝动作对 531 个真实 FF next-Q 的约束通过，其中包括全部 512 位 written bitmap；25 个实际网表破坏负控均产生预期 SAT 反例。该结论仅覆盖本报告列出的综合网表功能，不能转授为时序闭合、P&R、声画、BLE 或实板验收。

## 冻结来源

候选 `w-demo-d-v13`，VG SHA256 `3c7866321188f7b36dc601c36f6b572b04ee5c5f7786f434a10a1b0d2bb4a787`。实际消费 owner SHA256 `3eab83ad77e0ff28aac3bee416751262bb3af01241d1df596e769a871d53f5b3`，与冻结维护源／prepare snapshot 相同。验证器从 `w13-audits-v1/source-tools` 加载冻结 parser，重新逐项核对 1365 个 frozen、645 个 staged 和 951 个 prepare-source 文件，均无差异；enabled inputs 为 284。未把额外生成的 pycache 纳入冻结源码数量。完整身份、runner 和证据哈希见[机器报告](dual138k_w13_pcm_mapped_20261101.json)。

全部输入对按 source-owned staged/active 字段及其固定 bit 范围指定，没有从已观察 leaves 反推期望函数。96 个 session epoch/generation/physical publisher bit 单独检查；其中 64 个 escaped session vector bit 用原始 VG 的同父层、同一精确 `[31:0]` actual、声明方向／宽度以及 `epoch_o/generation_o` FF 的逐位 Q 连接建立别名见证。维护 parser 本身不 canonicalize 这些 escaped vector bit，故本报告保留 formal 输入函数证明和显式原始连接见证两个部分，没有修改 parser 或 VG 来制造一致。

## 实际函数与 live 消费

controller／generation／stream／rate／physical 各 4 个 8-bit 组，共 20 组。每组实际为 7 个 `ALU_MODE=3` NE ALU 加 1 个 `LUT3 INIT=8'h41`，最长 CIN 为 7，组合深度 8；每组输入恰好是预期的 8 对 FF Q，没有缺位、重位或跨组 CIN 连接。20 次独立 Boolean miter 全部 UNSAT。分组内仍使用 carry；本报告没有称其为纯 LUT tree，也不预记资源或时序收益。

实际 `key_matches` 已改名为 `n2383_19`：5 个 AND4 加 2 个 AND3，kept cut 后组合深度 3。分别以 20 个 kept 输出以及全部 160 对 source-owned staged/active 位作两个独立期望式，实际 primitive miter 均 UNSAT。完整比较锥为 140 ALU、27 LUT、组合深度 11。

`rejected_commit` 源名未保留；真实作用条件 `rejected_commit && usable && key_matches && !owned[tail_slot]` 映射为 `n16547_5`。证明展开了实际 LUT INIT、ALU_MODE、CIN、MUX2 引脚以及 descriptor 的全部 512 位 bitmap 选择。key、live／physical／usable、full-write、write admission、tail ownership、ID 饱和、sequence、COMMIT validity、opcode/address 和最终拒绝动作共 12 个实际 predicates，连同 2 个输入装配 predicates，全部为无附加假设的 UNSAT 等价证明。

Mapper 将 compute reset 的一部分前推入 APB valid 的 `n432_4`：其真实函数是 `(req_settled != acknowledge_toggle) && request_decoded && compute_release[2]`，CPU-ready release 在 write admission 中另行应用。此别名没有被误当作裸 `command_valid_i`。context 输入也从真实 `compute_context_valid/config_state/compute_fault` 展开证明。W13 enabled profile 的 `WORKSTATION_DEMO_NO_TF` 与实际顶层常量接线单独绑定，因而该候选的 tf_busy 为 0；没有把这个配置特性推广到其他 profile。

在 source 拒绝动作成立这一明确条件下，实际 FF 的 D、CE 和 CLEAR 共同构成的 next-Q miter 证明：failed=1，armed=0，owned[3:0]=0，tail_slot=0，queued=0，desired_source=0，以及 4×128 written bitmap 全部清零，共 531 个真实端点。未将本次映射中不存在的 head_slot 等源字段冒称为实际 FF 端点；完整源行为及四态证明仍见既有 PCM key/COMMIT 源报告。本报告也没有新声称 failure reason 的全部优先级或整个 owner 的 sequential 等价。

## 负控与 oracle

20 个组分别破坏一个实际 ALU 操作数，均得到 SAT 反例。另 5 个实际破坏为：组末 LUT INIT 清零、AND20 consumer 丢弃 controller 第 0 组、拒绝动作 LUT 清零、删除 full-write 拒绝项，以及同一拒绝锥断开后检查真实 failed next-Q。后者在 source 拒绝动作成立时仍能得到必须出现的反例，防止证明只停留在未使用的同名网络。

Boolean primitive 方程还用官方 GW5A `prim_sim.v` 的逐字模块／UDP 片段在 Icarus 中核对：ALU 全 9 种模式的 144 个 binary 输入组合，以及 LUT3/LUT4/MUX2 的全部 binary 组合均相符。完整官方模型 SHA256 `2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`。这只是 binary 方程交叉验证，不代替四态 primitive 或器件延迟模型。

外部证据目录为 `/Users/sphenicidition/.cache/gw138k-dual-20261031/w13-pcm-mapped-v1/`，最终证书为 `certificate-v5.json`。早期 register scope、被优化端点、escaped vector publisher 检查及缺少 MUX 依赖的失败尝试均保留。最终 source binding、证书和 primitive checker 均退出 0。封存索引为相邻的 `w13-pcm-mapped-sealed-v1.json`，绑定本报告与全部外部证据。

本阶段没有改生产 RTL、配置、锁或 task2，没有提交、push、烧录或板卡操作。P&R／硬件结果应由对应独立候选报告记录。
