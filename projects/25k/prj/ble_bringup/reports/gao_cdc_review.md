# GAO CDC 核查，2026-10-16

检查对象为 Gowin V1.9.12.03 于 2026-10-16 00:10:44 生成的 `impl/pnr/ble_bringup_gao.tr`。本检查只读已有输出，没有综合、重布局、下载或修改约束。

## 已确认的证据

- 时钟表（`.tr:75` 附近）将 `clk_50mhz` 和 `gao_jtag_tck` 分别列为 20.000 ns / 33.333 ns 的独立 Base clock，源为 `clk_50mhz` 和 `tck_pad_i`。外部系统晶振与下载器 TCK 没有已知相位关系。
- 可见网表 `impl/gwsynthesis/ble_bringup_gao.vg:229975` 开始的 `tck_ibuf` 将 `tck_pad_i` 接入 `GW_JTAG.tck_pad_i`，该原语的 `tck_o` 通过 `control0[0]` 进入 `u_la0_top`；GAO 同时另接 `clk_50mhz_d`。
- 违例详细路径（`.tr:1579` 起）：`u_ao_mem_ctrl/capture_mem_wr_s1` 的时钟为 `clk_50mhz`；其 Q 通过 `n2695_s1` LUT 到 `capture_end_tck_0_s0/D`；接收寄存器时钟从 `tck_pad_i` 经 IBUF、GW_JTAG.tck_o 到达。hold slack 为 -0.606 ns。
- Recovery 报告（`.tr:2701`、2750、2796 附近）还明确列出 `capture_end_tck_1_s0`、`capture_end_tck_2_s0` 和 `capture_end_tck_0_s0`，三者由 JTAG 时钟触发并接收 `rst_ao` 清零。这证明有三个同名编号寄存器，不能单独证明它们串联。
- 核心时钟 Fmax=54.156 MHz；报告汇总 setup 违例为 0、hold 违例为 1。同域 50 MHz 核心 setup/hold TNS 均为 0。

## 无法核实的部分与决定

GAO 官方 `gw_ao_top.v`、`gw_ao_mem_ctrl.v`，以及综合 `.vg` 内的 GAO 模块、布局 `.p/.pr`，均含 `pragma protect` 加密内容。当前普通文本报告没有列出 `capture_end_tck_0_s0/Q` 到后继 D 的数据连接、首级扇出或同步寄存器属性，不能确认首级只驱动后续同步链，也不能确认防亚稳态结构完整。

因此本次**不添加 false-path、clock-group 或 hold-only 例外**，`constraints/ble_bringup_gao.sdc` 保持不变。若未来通过 Gowin 官方网表/时序查询证明具体同步链正确，可将候选例外严格限制在已核实的发送寄存器到第一级 D，保留第一级到后级及其它核心路径的时序检查。当前证据不足以把候选约束写入工程。

当前镜像的原型观测由根任务单独决定；GAO 采集需要结合多次快照与实际 BLE 广播/连接结果。单次 GAO 读值不能替代 CDC 签核，也不能据采集异常认定 BLE 核心失败。
