# DDR DLLSTEP / DQS HOLD 配置路径依据

复现命令（使用本机安装的 Gowin 1.9.12.03 公共原语模型）：

```powershell
python scripts/audit_ddr_configuration_paths.py --output docs/evidence/ddr_configuration_paths.json
```

脚本复用 [复位审计](ddr_reset_sequence.md) 的原始 C 版 `.vo`，检查工程加密 `.v` 与参考 `.v` 的 SHA-256 一致。仅从本地资料和工具安装目录读取文件，不复制大型原厂源码。JSON 保存所读时序模型的 SHA-256，约束依据改变时可追溯。

## DLLSTEP：冻结后的一次性采样

UG306-1.0.9 第 105 页定义 `DDRDLL.UPDNCNTL` 为低有效更新控制。公开 `IDE/simlib/gw5a/prim_sim.v` 的 `DDRDLL` 模型在 `UPDNCNTL==0` 时将 `step_reg` 传入输出 `step_reg_sig`，其余时间保持；这里没有把延时码当作每个 400 MHz 边沿都改变的有效载荷。

参考网表的 8 个 `dll_step_base` 寄存器使用 100 MHz `clk_out`，其共同 CE 真值表严格等于：

```text
!ddr_init_st_rrr && ddr_init_st_rr && dll_lock
```

这是经过初始化指示管线后的一次采样。原厂完整复位状态机中，`UPDNCNTL` 置高冻结输出后，过 31 个 50 MHz 周期（620 ns）才重新开启 `memory_clk`；随后再经过 UI 域指示管线才采样。审计同时检查首次初始化和重校准。DLLSTEP 输入配置值因此具有远大于一拍的稳定窗口。

工程仅对 `u_dll/STEP[7:0] → dll_step_base[7:0]/D` 设置 40 ns 传播预算及此稳定配置采样的 hold 例外，保留 CE、快照输出以及其余 DDR 数据路径分析。40 ns 预算远小于 620 ns；不对 DLL 时钟组整体豁免。

## HOLD：公开模型中的 PCLK 控制输入

两个独立格式的官方时序模型均明确列出：

```verilog
$setuphold (posedge PCLK, posedge HOLD, ...);
$setuphold (posedge PCLK, negedge HOLD, ...);
```

对应 `DQS_tsim_M.vp` 第 192–193 行和 `DQS_tsim_V.vp` 第 265–266 行。它们没有列出针对 FCLK 的 HOLD setup/hold；同一文件中 RESET 则明确分别列出 PCLK、FCLK 正沿和 FCLK 负沿的 recovery/removal。参考 IP 将 DQS.PCLK 接 100 MHz `clk_out`，FCLK 接 400 MHz `memory_clk`。

网表中的控制关系也与慢速配置操作一致。脚本检查全部 512 个局部历史组合，确认：

```text
trigger = WRLVL_ADJ_DQS || READ_CAL_HOLD 的一拍延迟
hold_i_next = trigger || trigger 的前 7 拍历史
HOLD[lane] = hold_i[lane] && !read_rclksel_conf[lane]
```

`hold_i` 是 UI 寄存器，单次 trigger 会展宽至至少 8 个 UI 周期。32 个 WSTEP 位在配置更新寄存器后还经过 `wstep_reg_d → wstep_Z` 两级 UI 寄存器。每个 `read_rclksel_conf` 仅在校准检查合格时由 0 置 1，直到 DDR reset 才清零，置位后该 lane 的 HOLD 保持 0。

仅凭脉冲宽度并不能忽略首边沿时序。工程采用上述公开模型的 PCLK 检查口径，只对来源为 `read_rclksel_conf` / `hold_i` 的 DQS.HOLD 配置路径设置一个 PCLK 周期的 10 ns 最大传播预算，**保留 hold 分析**。此约束不扩大到 DQS 数据、WSTEP 或其它控制信号。它的依据是公开模型的采样时钟以及已核对的控制结构；不是已经完成板上校准的声明。

## WLOADN：继续保留实际时序检查

WLOADN 的 UI→50 MHz 寄存器路径没有被上述 DLLSTEP/HOLD 证据覆盖。此前尝试的 `set_min_delay 3` 将 hold 要求额外增加 3 ns，路由器没有据此插入足够延迟，已撤销该试验。当前对该路径采用物理位置调整，并继续检查完整 setup/hold 报告；它不使用 false path 或放宽 hold 要求。
