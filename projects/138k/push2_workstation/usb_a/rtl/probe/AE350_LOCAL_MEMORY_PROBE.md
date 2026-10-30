# AE350 ILM/DLM 与 64 KiB 冷启动存储独立探针

这是 prepare-only 数字实验入口，不是工作站 profile。它保留锁定
`resource_rework_route0` 的 AE350 配置、加密硬核、包装器和 CPU PLL，
以原有 50 MHz 板时钟生成 100 MHz core／50 MHz bus；使用维护中的
64 KiB 原生 boot memory，以及**未改字节**的正式 ILM/DLM loader。
不依赖 DDR readiness，也不装配 DDR、USB、BLE、音频或显示业务。
它不能代替完整工作站的资源、时序、CDC、功能或硬件验收。

AE350 的 CORE_CLK 必须来自 `PLL_R[0].clkout1`，并显式约束 PLL_ADV
位置（MUG1031 v1.3.1 第 7.3 节，PDF 第 56 页／印刷第 48 页）。本入口
生成 `INS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];`，prepare 审计拒绝遗漏、
错误及重复约束；P&R 后另用 `audit_cpu_pll_placement(.tr文本)` 检查实际位置，
仍须独立核查完整 STA。C7／C8 的实际位置为 `PLL_B[2]`，即使可见 PL
路径 STA 为正，也未满足硬核物理要求，不能视作完整物理接受。

C9 仅修正 PLL 位置，固件及 100／50 MHz 配置不变，便于单变量板测。
当前 RTC_CLK 仍继承 50 MHz 接线，偏离手册规定的 32.768 kHz，留待后续
独立修正；不能从探针的离线通过推导硬核启动或缓存可用。

## 准备与身份

在 `usb_a` 目录执行；必须提供一个未使用的 UserCode 和新输出目录：

```sh
python3 build.py --ae350-local-memory-probe --prepare-only \
  --ae350-probe-output /absolute/new/probe-output \
  --netlist-dir /absolute/locked-netlists --user-code C21031C6 \
  --riscv-prefix /absolute/toolchain/bin/riscv-none-elf
```

准备只生成输入、固件和 `run.tcl`，不会启动 EDA 或访问板卡。
`inputs.json` 记录全部准备字节的哈希、7 个编译源、硬核基线、时钟、
引脚、编译命令／版本、ELF／BIN／ROM 和 payload 身份；
`tools.workstation_ae350_local_probe.audit_prepare(output)` 可重新检查。
输出目录不可重用，来源变化必须建立新的候选和固定清单。
后续综合、P&R、实际 PLL／CDC／引脚／资源审计、SRAM 操作与配置读回
由主流程分别记录，不从 prepare 成功推导。

## 固件行为

正式 loader 先完成 cache-off、64 KiB ILM/DLM 几何／启用读回、局部 RAM
读写和边界检查、ROM→ILM／DLM 复制读回、BSS 清零、栈填充、fence 与
ILM 入口检查。探针仅在进入 `services_main` 后安装自己的 stackless trap。

32 KiB payload 的每个非零、互异 word 为
`xorshift32(index XOR 0xa1386401)`，移位顺序 13／17／5；包含整个 payload
的冷启动镜像超过旧 16 KiB 容量。实际 ILM C 服务从 volatile 指针读遍
8192 words，计算与 host 独立生成结果比较的 LE CRC32 及首尾值。
另将地址 XOR `0x9e3779b9` 写入安全空闲 ILM／DLM 区，两个区域均完成
写入后再读回，避免只测单地址。它保留 linker 标记的代码／常量／数据／
BSS 和 16 KiB 栈，并在 DLM 栈前保留 256 bytes。

CSR 探针只读 cache、MMSC、MISA、local base、counter 配置和 PMA；
仅在 MMSC 的 PPMA 位存在时读 PMACFG。mcycle／minstret 使用最多四次
high-low-high 快照，记录 4096 次固定循环前后数值及差值。
不写 counter enable／inhibit，不开启 I/D cache，不将 RTC_CLK 接入的
50 MHz 解释为标准 timer。可选 CSR 仅在精确标记的 CSRR 指令发生
illegal-instruction 时恢复；其他陷阱记录 PC／cause 后停机。
栈 pattern 的实际占用只是一轮观测，静态调用闭包另存于固件构建元数据。

## 板级固定输出

时钟 V22、UART TX U15 取自锁定主板网表。DAC 六脚复用 B7 独立音频探针
已审计的映射及 3.3 V／DRIVE=4 约束：SMUTE=A15 固定高，PDN=C13 固定低，
MCLK=B13、BICK=A13、LRCK=B15、SDATA=A14 固定低。
不使用 pinout-only 的同序排线候选，也不依赖上个镜像的静音状态。
这些是数字电平策略；SMUTE 的数字软静音不证明模拟无声或无爆音。

## UART 与 GAO

UART 以独立 50 MHz 参考时钟、除数 434（约 115207 baud）、8N1 输出，
约每 100 ms 发一帧。APB 域一次寄存全部 64 words，再经双级 request／ack
与稳定等待传给参考域。超时保留上次完整 bank，明确置平台 bit4；
未完成请求保持 outstanding，不因下一帧翻转而误认旧 ack。

每帧 280 bytes，所有整数为 little endian：

| 字节 | 内容 |
|---|---|
| 0–7 | ASCII `A138LM01` |
| 8–11 | UserCode |
| 12–15 | frame sequence，从 0 开始 |
| 16–19 | word count，固定 64 |
| 20–275 | 下表 64 diagnostic words |
| 276–279 | 前 276 bytes 的 reflected CRC32/ISO-HDLC，终异或 |

GAO 采样为 `clk_50m`，`status_50mhz[511:0]` 的低 word 到高 word 为
diagnostic `[1,6,7,8,9,11,12,14,16,17,18,19,20,32,34,35]`。
它是同一次参考域 bank 的摘要；完整 counter／trap 结果由 UART 提供。

从 C21031C8 起，GAO 增加 `[543:512]` 平台观察 word，不改变 UART
280-byte 格式或原低 512 bit。该 word 的 bit31–16 是 reference 域
power-on 计数器，bit15–11 为 lock qualification 计数器低五位，bit10／9
为 ROM 任意访问／高地址访问 sticky 的 reference 域两级同步值，
bit8 为 lock qualified，bit7 为 system reset 释放，bit6–4 为 UART
状态机（0等待、1等快照、2稳定、3发布、4发送、5排空），bit3–0 为
已同步的 APB reset／core reset／PLL资格／PLL锁定。
平台观察不依赖 C 软件写 diagnostic，不能用非零平台值代替软件 PASS。

| Word | 含义 |
|---|---|
| 0 | 服务签名 PRB1 |
| 1–4 | 正式 loader PASS/FAIL、阶段、cause、PC |
| 5–10 | 版本 1、服务 PASS/FAIL、错误位、阶段、payload 进度、心跳 |
| 11–15 | PC、SP、stack top、CSR 可读 mask、可选 CSR trap 数 |
| 16–24 | MICM、MDCM、MMSC、MILMB、MDLMB、MCACHE、MISA、mcountinhibit、mcounteren |
| 25–28 | PMACFG0–3；是否读取由 mask 及 MMSC 判定 |
| 29–31 | 最近 probe trap cause、PC、probe trap vector |
| 32–36 | payload CRC、预期 CRC、首 word、末 word、8192 words |
| 37–43 | DLM／ILM 测试 word 数、首错地址／预期／实际、错误数、观测栈占用 |
| 44–49 | mcycle 起点／终点／差值，各两 words，低 word 在前 |
| 50–55 | minstret 起点／终点／差值，同上 |
| 56–57 | counter 可读 flags：cycle前/后为 bit0/1，inst前/后 bit2/3；循环数4096 |
| 58–59 | RTL：观察过 0x80004000 以上 ROM 访问；外部数据总线未映射访问 sticky |
| 60 | 保留 |
| 61 | UART 平台 flags：PLL锁定／资格／core reset释放／APB reset释放 bit0–3；快照超时bit4 |
| 62–63 | 保留 |

服务阶段为 1入口、2CSR、3payload CRC、4写 pattern、5检查 pattern、
6counter、7结束。错误位 bit0 为 payload，bit1 为 pattern；
意外 trap 阶段为 `0x80000080`。CSR mask 的 bit0 对应 word16，依次类推。

仅解码已保存的原始二进制捕获：

```sh
python3 tools/decode_ae350_local_probe.py --input /absolute/capture.bin \
  --manifest /absolute/probe-output/inputs.json --output /absolute/new/result.json
```

解码器重同步帧头、检查 CRC／word count，并以**最后完整帧**判定当前状态；
旧 PASS 后的新 reset／timeout 不能沿用旧成功。local-memory 和 counter
观察分别报告，CSR 不可读不伪装成运行中的计数器。
还须单独绑定实际 JTAG／SRAM 身份、工具结果、路由时序和捕获时间。

## 验证、回退与退役

`sim/test_ae350_local_probe.py` 运行实际编译的 loader 与 C 服务字节；
检查 payload／pattern、16 KiB ROM 回卷／ILM 地址别名、可选 CSR trap
恢复、最后帧判定、CRC 损坏、实际串行 UART 与持续变化 APB bank 的
一致性／连续超时，以及保留冻结 wrapper 端口声明的实际顶层安全输出。
模型中的 counter 是合成值，只验证读取和差值路径，不是性能实测。

EDA 与板测失败时保留全部候选和证据，由主流程选择哈希已核对的既有
SRAM 候选回退；准备和解码工具均不写 Flash。cache 的 PMA/device 属性与
硬核 cache 操作证据未闭合前保持关闭。完整工作站 ILM/DLM 路径及正式
硬件门禁通过后退役此实验输入，保留报告和可复用回归；不得将它变为
另一个长期生产 builder 或默认 source profile。
