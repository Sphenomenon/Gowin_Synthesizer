# M19／W17 全量综合与实际 VG 检查点

2026-11-01。[来源锁与prepare](DUAL138K_M19_W17_PREPARE_20261101.md)之后，两份候选均完成全量综合、strict整机网表检查、实际VG原生协议及边界负控。各自default全量P&R已启动，完整物理门和实板声画仍未接受。

| 实际综合测量 | M19 | W17 |
|---|---|---|
| 候选身份后缀 | `3b42d2cc55cc70d5` | `518b142532fd5352` |
| 综合时长／退出码 | 178.443秒／0 | 219.956秒／0 |
| FF／LUT／ALU | 46932／53910／12550 | 45220／57394／13802 |
| 综合BSRAM equivalent | 195 | 257 |
| actual VG原生回归 | 58项：53通过、5不适用 | 58项：44通过、14不适用 |
| 原生负控 | 68项全拒 | 59项全拒 |
| actual VG边界回归／负控 | 7项通过／69项全拒 | 7项通过／69项全拒 |
| default物理输入身份 | `D2110120` | `D2110122` |

综合数从各自`custom_138k_integration_syn_rsc.xml`顶层读取；不能与旧候选物理BSRAM、CLS或DSP混算。综合运行前后M的590项、W的648项输入hash一致。完整VG SHA256及物理prepare manifest、冻结来源／工具和命令在[机器记录](DUAL138K_M19_W17_SYNTHESIS_20261101.json)中绑定。

主线程独立复验7039个路径：重读来源锁检查点、M综合阶段seal、两份综合元数据／日志、实际VG和资源XML、strict与各项回归原始日志／负控、物理8项输入及原SDC。M的compact unittest日志按冻结TestLoader的实际58项顺序和源码skip guard核对5个不适用项；W逐一核对14个完整测试名及理由，其中10项因W明确退出TF，4项因该VG不含对应routed／source-slice映射。没有因缺环境、网表或vendor而跳过实际检查。

W实际返回邮箱v3专项4项测试、19项负控全过，确认296个实际payload源、301个generation资格端点以及9928对真实源／消费者均有10.000ns与匹配hold-only覆盖；未新增setup falsepath。冻结原SDC直接经strict审计，不依赖未安装overlay。该证明仍以已命名的native-response可达性条件为前提，未完成完整映射归纳证明，`whole_source_CDC_accepted`与`physical_CDC_accepted`保持false。新VO和实际routed约束／时序仍须重验，不转授完整CDC接受。

W封存wrapper最初只匹配一种TF skip描述，主线程wrapper最初假定M有verbose skip行；两次均只使外围封存断言失败。原始失败记录及脚本保留，新记录分别核对完整W测试名和M紧凑日志的实际测试顺序；冻结工具、测试、生产RTL和原结果未改，也未靠重复回归掩盖失败。

两份default物理输入各8项已封存，Place2／Route0／replicate=false，VG分别来自本次综合，原SDC逐字节保持，无DDR适配。P&R运行和之后六组actual VO／PLL／完整STA审计另成阶段；不从综合退出0推断routed闭合或可上板。

主线程复核：`/Users/sphenicidition/.cache/gw138k-dual-20261031/m19-w17-root-synthesis-review-v2.json`，SHA256 `21214aa2a3bbcd01e4503554abac1a65fc814bc7ba62eb154b3ce4a4f174241a`。M综合seal为`m19-synthesis-stage-v1/seal.json`，W网表seal为`w17-vg-gates-seal-v2.json`；冻结工具仍为各1403项。

M基础无CNN；W录音对象仍为16384帧／64KiB，约0.341秒。真实HDMI／I2S／DAC、Push／25K、手机A2DP／D实时处理及BLE下载／共存尚未验收，模拟器不替代无线证据。T2-D1／D2保持未完成。本阶段未操作板、未下载SRAM或写Flash，原板和Flash回退保持。
