# 波形 smooth CSA 维护源码落地与完整显示回归

已将独立审查通过的 smooth CSA 函数精确落到维护 `rtl/display_data/feedback_capture.v`。仅该函数体改变；完整模块其余字节、端口、参数、状态、时钟和样本周期保持原样。新增可独立重跑的维护 runner 和精确旧版完整 fixture，完整 capture 双实例及相关真实 display 回归均通过。本阶段没有综合、P&R、资源收益或板测结论。

## 来源与原算术语义

新完整源码 SHA256 为 `6b09b616d061a2d6fb8defd08d8be2889e70fca93e0d05a243b42887a3eddab9`，与批准的 cache 候选完全相同。旧源码／版本化完整 fixture 为 `62195a1777f8308f0e20687e6dcae14af932e65eac0cf6ca814b6e40d294bb56`。runner 同时固定旧／新函数 hash，并将新函数精确逆替换回旧函数后要求恢复完整旧文件字节；运行结束再次检查两份输入身份。

新函数使用低 7 位舍入进位和三层 XOR／majority carry-save 组合，再进行最终 32 位加法。原有 signed 33 位 `delta+16` 正溢出必须保留：`value=7fffffff, old=80000000` 的原结果是 `78000000`。删除溢出修正会变为 `88000000`，本次没有将原行为改为无限精度数学结果。

独立 cache review 为 `waveform-smooth-csa-independent-review-v1/review.json`，SHA256 `4e9530e9e826959cec5fef575f551628d3c72819c64136a4f8facfd0d7dba4da`；其最终 seal-v2 为 `473d1a41254dc08de385fac64bb0bd283c45b5092ebc6272fa382010ba03a156`。原 proposal 的 18 项库存中，`verify-run-v1.log` 曾在 shell 重定向未结束时取 hash；独立 review 已记录唯一差异。本次保留原 JSON、日志和旧 seal，没有覆盖历史证据。

## 独立维护回归

维护入口 `sim/display/run_feedback_smooth_csa.py` 仅依赖版本化维护源码、精确旧 fixture、公开 Python `z3-solver` 及 Icarus，不读取私有 cache 或已准备工程。`--output` 必须是新目录。

- 独立手工翻译的 64 个任意二进制输入位 SMT 为 UNSAT，无可达状态假设；保留原 33 位溢出和 signed shift。独立 IEEE 运算符 known-mask 上界对全部 X／Z 输入位置也为 UNSAT：任意未知输入使最终加法包含未知位并输出全 X，与旧算术一致。这里没有声称使用 HDL 前端的全模块 formal equivalence。
- 删除溢出修正、错误舍入常数和丢失 carry operand 三个精确破坏变换均得到 SMT SAT 反例。三个真实源码 mutant 在 `INPUT_REGISTERED=0/1` 下全部编译成功，然后因实际模块函数的 `SMOOTH_MISMATCH` 失败；没有将编译错误作为成功负控。
- 两配置各执行 1,067,717 个实际函数探针，包含极值网格、百万随机、两位四态排列、每位单独 X／Z 及全 X／Z。极端结果 `78000000` 有显式独立期望断言。
- 两配置各运行完整新旧 capture 双实例 44,000 个 source clocks。source／render 时钟周期为 10／14 ns，每次两域正沿后核对全部持久标量／向量状态（未使用的循环整数除外）、六极点及全部公开输出；每次 RAM 写入核对实际目标字，每次新发布及结束核对全部 1,024 个 RAM 字。
- 两配置均完成 43 次真实发布、39 次释放和 45,056 次全 bank 字比较。非注册／注册输入分别写入 23,152／23,149 字、读取 23,376／23,372 次，并覆盖 7,417／7,411 次忙时丢样；均含一次真实 8,192 样本超时、平滑／相位／静音触发、三个复位周期、valid 间隙、152 个 X 位及 100 个 Z 位样本。每次释放前读取完整 512 字快照。

最终维护 runner SHA256 为 `3d536c1430d58bbee838a6934a8e5858eeadf084e2222b97c0ff5ee6ca626b98`；最终 `waveform-smooth-csa-maintained-v2/verification.json` 为 `4aa3c3ca307f22ea5e5c7a9995b9d07bb9af0fdec8a9905cf5b83a6710434370`。初次 v1 已通过；补充结束时输入漂移检查后完整重跑 v2，旧成功记录保留。

## 实际 display integration／metadata

以下既有维护入口没有修改门禁或 oracle，均直接编译新维护 feedback_capture；实际 producer 与 renderer 使用 `SMOOTH_TRIGGER=1, INPUT_REGISTERED=1`。配套冻结文件仍取自显式 prepared 工程，具体每个输入 hash 在各自 verification JSON 内。

- `run_display_metadata_v11.py` 使用冻结 M15 support，退出 0，身份 `native-display-metadata-v11-offline-v1-4fa195bbae0ee701`。minor0 对照 615,641 周期及 1,098 beat 完全相符；minor1 的取消、旧上下文拒绝、完整 cache、最终 payload 负控通过。真实 48／44.1 kHz analysis 发布 3 次，输出 1,536 waveform samples、196,608 XY pixels 及 1,536 FFT columns。
- `run_workstation_display_runtime.py --native-counter --hdmi-adaptation recording_owner8_v1` 使用冻结 W13 support，退出 0，身份 `native-runtime-display-offline-v1-fb67ab642a8a5781`。真实 wave／FFT／XY→DDR/cache 完成 8 发布、13 commits、166,525 次 204 位原子 tuple 核对，输出 1,024 waveform samples、131,072 XY pixels 和 1,024 FFT columns。60 次 CDC drops、5,528,428 次 gray-drop 逐周期检查、62 次撤销、取消竞争及停止时钟 reset release 均通过。
- 同一 runtime 入口完成官方 GW5A primitive 下 default、runtime、runtime_owner8 三种完整 HDMI elaboration，确认维护 provider 未被 prepared 目录遮蔽、唯一 FFT owner、两 dashboard、runtime 双 cache bank 和 owner8 九个 request slots。这里的 elaboration 不等于真实 HDMI 像素板测。

最初以 M15 运行显式 owner8 回归，在输入库存阶段因缺少其本不消费的 owner8 recording queue 文件失败，尚未进入行为验证。错误及原命令保留在 `waveform-smooth-csa-display-runtime-v1/attempt-result.json`。随后使用确实含该业务输入的冻结 W13，既有 provenance 与 source binding 检查原样通过。没有向 M15 补文件、放宽门禁或改冻结证据。

## 复现与后续候选

在 USB-A 项目根目录执行以下命令，三个输出均应选尚不存在的目录；第一条所用 Python 环境需要安装 `z3-solver`。

```text
python3 sim/display/run_feedback_smooth_csa.py --output <new-proof-directory>
python3 sim/display/run_display_metadata_v11.py --project <frozen-M15>/workstation/Prj1 --output <new-metadata-directory>
python3 sim/display/run_workstation_display_runtime.py --project <frozen-W13>/workstation/Prj1 --native-counter --hdmi-adaptation recording_owner8_v1 --output <new-runtime-directory>
```

[机器报告](dual138k_waveform_smooth_csa_20261101.json) 记录精确源身份、全部正负控、指标、失败尝试及证据 hash。外部根目录为 `/Users/sphenicidition/.cache/gw138k-dual-20261031`；最终库存 seal 为其中的 `waveform-smooth-csa-maintained-sealed-v1.json`。seal 在所有进程退出和报告写完后生成，并逐文件重新读取核对。

冻结 M15／W13 内两处 feedback_capture 各自仍为旧 `62195a…bb56`，没有继承本次新源。主线程须以新身份冻结输入并运行 accepted-source 回归，然后检查完整实际 VG 平滑锥、真实资源、P&R／STA 和实板声画。单独函数／显示离线回归不能预记物理收益或板卡验收。

本子任务未改 profile 锁、task2、其余生产 RTL 或固件；没有 commit／push、SRAM／Flash 或其他板卡操作。阶段提交和候选更新由主线程统一处理。
