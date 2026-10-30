# Native audio component Gowin 综合

2026-10-30，源提交 `a93aba8` 的独立音频组合综合成功。此前
`runtime-audio-component-synth-29d0083e` 的 `EX3638`／`EX1998` 在新快照
中均消失；旧无驱动网表保留，不能继承这次结论。

新实验身份 `runtime-audio-component-synthesis-108192b1-v2`，输入来自已通过
父级完整音频回归的精确闭包：47 RTL、13 memory、2 preset/include，
只排除仿真 TB 与 prim_sim，综合使用原生 DCS。器件为
GW5AST-LV138PG484AC2/I1 C，sysv2017；50／76.8／100 MHz 和
12.288／16.9344 MHz 五路时钟保持真实值，无 false path／放宽时钟／删功能。

- manifest SHA256：`e1bf193033443c158930f4577cff8fd721470b8299bd2e76e54934b4109be891`
- synthesis log：`d154f5f4ac14ea9cdfeb8095913c1743719298fc4e4ef81932cc81718e05f412`
- VG：`69815f20b97deafbf7940bc6f7e1c8bc621726450756cab3729db8b58cd5b96e`

工具持共享独占锁，仅执行 `run syn`，07:48:40—07:49:56 退出 0，全部输入
前后哈希相同。没有生成 FS，未进行 P&R 或板卡操作。新 VG 中仍有四个 FDN
与 early RAM 实例；其门级控制已优化重命名，不能只凭实例存在证明清历史功能。
独立 Reverb gate-level 对照另行验证，不将 warning 消失冒充完整网表等价。

综合报告总量为 Register 12,735、LUT 47,705、Syn BSRAM 53、SSRAM 1,112，
MULTALU27X18 51、MULT27X36 45、MULT12X12 1。它们只是此组件的综合口径，
不是整机占用或物理 BSRAM 数量，也没有形成时序／资源接受。保留的五条 warning
为 ROM 文本宽度、两处截断、综合忽略 fatal 和初始只读 ROM；精确位置在机器证据。

修后另以完整默认启动参数（1028 startup／4 PDN frames，生产时钟资格窗口）
复跑，57 ms 仿真中 211 物理帧、211 good、127 非零、无 error，完成首次
44.1 kHz 切换。其输入 source-set 与本实验同为
`108192b1849b1f81a9b412658e2d027ddd37257375122d2c45d85d887d802eb0`。

[机器证据](workstation_task_20261030/runtime_audio_component_synthesis.json) 包含
完整输入／工具／preset／ROM 路径哈希、配置、执行与产物身份。缓存实验仅为
可综合性诊断，不是生产来源；后续显式完整 profile 才能选择并重新物理验证。
后来新增的非零 epoch 配置不属于这次 VG，不能沿用本身份。回退为继续保留
原有 top/profile 与部署，这个未选中的组件没有改变 SRAM 或 Flash。
