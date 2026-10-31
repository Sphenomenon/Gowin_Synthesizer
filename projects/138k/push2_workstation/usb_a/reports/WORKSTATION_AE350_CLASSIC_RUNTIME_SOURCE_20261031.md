# AE350 Classic 实际 CPU runtime 源阶段 — 2026-10-31

本阶段把真实 security／Classic／SBC／原生 HCI C adapter／PCM C adapter 接到版本化
`ui_main.c` 背景服务根。仅通过显式 `--runtime-owner` 选择；GeneralBonding 因缺少持久
bond backend 保持 `enabled=0`，当前 PCM capability bit3／4 均为零。没有手机播放、
原生整机候选选择、CPU 周期、综合／P&R、板卡或 Flash 验收。

源码基点为隔离 clone 的 `f8882c5` 加已封存安全源 `45ef475` 的 cherry-pick `1cd8071`。
本次只交付该基点之后的版本化源码／测试／报告，不修改 frozen baseline、历史证据或 task.md。
完整来源与输出 seal 位于外部证据根
`/Users/sphenicidition/.cache/gw138k-task-20261030/b04-cpu-runtime-v1/`；最终 delivery commit
和全 tracked-source inventory 由该根 `delivery.json`／`seal.json` 记录。

## 实际边界

- `hci_transport.[ch]` 只适配 PL 原生 F8050200 ABI，独立 CPU TX／RX 缓冲各 280 bytes。
  staging COMMIT 不算接受；实际 ACCEPTED、transport_done 和 owner2 exact raw CC／CS
  分别观察。transport token 单独严格递增，不能与两个 C service 各自从 1 开始的 token 混用。
  最终 ACK 必须在 C 收到 exact response 后；RX exact epoch／ticket 才释放，held copy 每轮
  刷新退休状态。不接管 UART／H5／HCI credits／Reset 或物理 host-credit return。
- `classic_runtime.[ch]` 组合真实 C owners，先独立 PL monotonic tick、再 TX 接受、再 RX。
  Connection Request 使用实际 BR capacity bit；RX BUSY 与 PCM REJECTED 各限 100 ms。
  uncertain commit、descriptor／epoch 漂移、超时和 owner failure 关闭 Classic，exact-epoch
  fence 不清共享 BLE／BR 账本。版本化 UI 每次背景调用四个固定 transport pass，总共最多
  一次 SBC decode，再调用原 BLE business pump。固定工作量不构成物理服务间隔保证。
- `pcm_media.[ch]` 使用完整五字段 key 和 F803 实际 clock ticket，先看 capability bit3 再允许
  ARM／切率／source 副作用。每次最多写 16 stereo PCM16 words；mono 复制为双声道。
  只有完整 block、exact new command ID 才返回 ACCEPTED，partial／full 返回 REJECTED，
  不确定写不可盲目重试。当前 armed failure 终止 observer；旧 owner sticky failed 不阻挡
  重建 observer 向 PL 提交 fresh ARM，PL 继续拒绝 same／older stream。旧 key 不能 cancel
  新 owner。队列 ready、SELECT 接受、首实际 sample 的 applied source 是独立事实。
- 实际固件只安装 bounded unavailable bond callbacks，全部返回 ERROR，并明确禁用
  GeneralBonding；不存在 RAM persistence 替身或 Flash 写。`ui_runtime.c` 的 freestanding
  `memcmp` 仅在显式 runtime 宏内编译。安全默认和既有源选择没有因实验自动启用。

## 通过的离线验证

| 验证 | 最终证据 | 结果／范围 |
| --- | --- | --- |
| 实际 C runtime／真实 SBC 参考 | `verification-v4/verification.json` | 11 cases，native／ASan+UBSan 各 3223 checks，最大误差 5 LSB；15 runtime／transport mutants 全拒绝 |
| 实际 C PCM adapter | 同上 | native／san 各 4548 checks，含保留 clock API 836 checks；9 mutants 全拒绝；capability／物理事实为测试注入 |
| 实际 C + 冻结原生 HCI RTL | `native-cosim-v3/verification.json` | 3316 checks、1712 clocks、最大 APB wait 3；外层为同步 H5 RAM fixture，非本测试的实际 UART／H5 或板卡 |
| 完整实际 RV32 root | `link-v10/verification.json` | xPack GCC 15.2.0；无 GC／LTO／text overlay；callback audit true |
| ELF 完整 callback／栈链 | `link-v10/runtime_callgraph_verification.json` | 实际可达 171 处 JALR 全闭合，保守栈上界 1904 bytes；missing-site／unknown-target／source-drift／stack-overflow 均拒绝 |
| 实际 UI source／APB replay | `ui-regression-v1/verification.json` | native／san 各 34867 checks；12 mutants；实际 UI APB RTL 回放通过，最终输入哈希重核一致 |
| 默认维护固件 | `stage-firmware-regression-v1.log` | 10 tests PASS |
| ILM／DLM loader + clone identity | `local-memory-regression-v2.log` | 13 tests PASS；mixed GCC clone exact title 唯一匹配及歧义拒绝 |
| 原 budget ROM128／CPU model | `rom-split-regression-v2.log` | 12 tests PASS；未认证 AVDTP 拒绝后才在模型中显式注入 grant；Delay／SBC 实际 RV32 指令模型通过 |
| accepted input boundary | `current-sources-regression-v2.log` | 17 tests PASS |

原生 HCI 联跑实际检查 CC-before-H5done 和 done-before-CC、raw response transport token、
私有字节拷贝、BR Accept→ConnectionComplete generation、held CPU ACL copy 不占物理 host
credit、Disconnect 使 held copy retired、exact CPU fence 不改变共享 credits／host budget。
runner 先把外部实际 RTL 全部快照并哈希再编译；对方冻结 native transport SHA256 为
`01c72a3b365e711e2425d552dec2eaaa5863292ca38295a27bb35a0c666f6d8e`。

实际 RV32 footprint：BIN 94752 bytes，payload 84752；upper cold code 29216／剩余 36320；
lower hot-load bank 55536／剩余 10000；ILM 54928／usable remaining 10604；DLM 静态 7616、
保留 stack 16384、未分配 41280。栈最长保守链为 services_main → firmware pump → runtime
pass → security_classic_acl → classic_acl → dispatch → SDP search／sequence。
tail call 仍保守按嵌套计；完整 stack bound 不代表实板 watermark、CPU cycles 或 DDR wait。

| 最终文件 | SHA256 |
| --- | --- |
| `verification-v4/verification.json` | `b03b1def6433c5a9e778a1c5560b4999757058ac8c1aa41e02f6732c9468c15e` |
| `native-cosim-v3/verification.json` | `baa9a2d617698b63f7d24267427f7652468dcf46ae79f6ad17185af7b594350a` |
| `link-v10/verification.json` | `e4a646561eae21ef6e14946bc1ab0218e134ff872718fb8f62dc9b1a2e6469b4` |
| `link-v10/runtime_callgraph_verification.json` | `b3ee02bad3a45eba54a5dea87ea4871ea5e5405a07908a821db55ce9d6add741` |
| `link-v10/firmware.elf` | `92eca5d392a472cdc2f570c039cc36f8c84001f7c0f6670568f5ee7aaf0fed11` |
| `link-v10/firmware.bin` | `43e87f191099597e5357fa156f5f41b2deffcc1ccb1f851a84752b38a10478e0` |
| `link-v10/boot.mem` | `535f56aa0efe6dd9862ebfaf1c6881448d01e7dc3070f5ef8164b954734af65e` |

## 保留的失败与剩余验收

外部证据保留全部迭代：link-v2 真正 ILM／lower-ROM overflow，随后显式把 security cold
code 放 upper ROM；link-v4／v5／v6 分别揭露未审 clock callbacks、不可达 wrapper review
和 mixed GCC clone label，均未放宽 audit。verification-v1 的 wrong-token mutant 初始
测试不足，强化为响应绝不消费断言后重跑通过。native-cosim-v1 失败来自 C++ fixture
同 tick 提前推进 event 写索引，v2 修正 fixture，v3 对冻结实际 RTL 再验证。旧 budget
regression-v1 因未注入安全 grant 正确收到拒绝；v2 先断言拒绝，再重建模型显式 grant。
所有失败输出保持原样，不改标 PASS。

完整 CPU↔PCM RTL↔原 DSP／最终音量／I2S 联跑、真实 CPU/DDR 周期与队列预算、物理
栈水位、sustained／drift capability 验收、总延迟测量、持久 bond backend 或单独显式
session-only 策略、手机认证／加密／重连／音乐、综合／P&R／实板均属后续阶段。
本阶段未生成或复用 accepted bitstream identity，没有硬件部署。回滚可停止选择显式
`--runtime-owner` 并恢复本次 source commit；原 accepted／pinned ROM 和板上状态不变。
