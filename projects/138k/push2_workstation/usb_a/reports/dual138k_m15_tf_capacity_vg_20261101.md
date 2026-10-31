# M15 TF capacity：实际 VG 分组与准入锥证明

日期：2026-11-01。仅为实际综合网表的结构／组合函数证据；未据此宣称资源收益、布线时序闭合、板测或部署。

候选 `custom138k-workstation-m-demo-v1-cf9d6319a310d6fe` 的实际 VG SHA256 为 `4707d235626cd446faf4ab00174f51c363c32db7926199cb2aa2449f51eb6a06`。实际被消费与冻结的 DMA 均为 `5ac87cbacd1ddc35f897fdf7c3427f80bcf7b151e44370baae6fb3305a596d3b`；588 staged 与1365冻结工具／源码逐SHA核验通过，prepare snapshot清单875项。

五个模块级标量均通过实际 primitive 函数与精确独立 FF support 检查：

| 标量 | available FF support | LUT数 | 组合深度 |
|---|---|---:|---:|
| ring_upper_equal_0 | 11:6 | 2 | 2 |
| ring_upper_equal_1 | 18:12 | 3 | 2 |
| ring_upper_equal_2 | 25:19 | 2 | 2 |
| ring_upper_equal_3 | 31:26 | 2 | 2 |
| ring_upper_equal | 31:6 | 10（含四组） | 3 |

四组全部出现在实际最终 equality 节点中；五个标量又全部出现在真实容量反相谓词 `u_tf_audio/audio_ddr_write_3` 和最终 `audio_ddr_write` 准入锥中。该容量谓词为33个组合单元、深度9，按真实 LUT INIT／GW5A ALU 函数，对所有32个 available及6个pending FF Q任意二态赋值，与原32bit modulo容量式的反相等价（UNSAT），不加可达状态假设。最终实际 LUT4 `16'h1000` 的真实输入绑定及门控后容量函数也通过UNSAT检查。

7项实际网表破坏负控均拒绝：依次保留五个原始节点、只断开其实际consumer输入；翻转最终equality LUT INIT；把真实最终write consumer的capacity输入绕过。前五项中保留旁路节点仍存在，但live锥和函数检查失败，并均给出SAT反例。

证书使用的实际 `Graph.expr` ALU模型通过AST直接抽取，与安装的原GW5A ALU模块进行9模式×16二态输入×2输出共288项Icarus对照检查。source的四态语义由维护源occupancy/threshold/runtime-stop阶段另证；该VG证书不是四态证明或形式化SV elaboration。

先前M14 function-local keep的partial失败仍原样保留：full分组通过，但capacity仅group0有独立实际节点。M15的新实际VG证据仅覆盖这次模块级标量方案，不改写历史M14结果。首个v1生成器在全部语义检查后遇到JSON自引用封存错误，已保留；v2以深拷贝修正记录序列化后重跑并封存，未改任何候选／生产输入。

完整证书：`/Users/sphenicidition/.cache/gw138k-dual-20261031/m15-tf-capacity-vg-certificate-v2/certificate.json`，SHA256 `254f4fcec799388b7ee12335219acaccb2dd03872a7d50706bd57fe92791fabd`。

独立封存：`/Users/sphenicidition/.cache/gw138k-dual-20261031/m15-tf-capacity-vg-certificate-v2/independent-report-seal.json`，SHA256 `fa5212e1283e8802fa9d05605cc481d425db382923278049ffc34f9afe8acce7`。

独立 proof seal：`cc755ef96e5829cd971bac4eb2e1d51a65ee3f8221d4e866d2c0d89808692360`。
