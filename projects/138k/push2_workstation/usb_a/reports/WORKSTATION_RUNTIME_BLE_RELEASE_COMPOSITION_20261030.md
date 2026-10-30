# revision5：BLE release 约束回到维护入口（2026-10-30）

维护入口已修复 [F7 的空 BLE release 查询](WORKSTATION_RUNTIME_F7_QUERY_F8_PREPARE_20261030.md)。runtime 专用适配要求原 BLE SDC 的完整 SHA256 和唯一完整 reset 行，只删除该行；held payload、req/ack 首级及 UART 的其余六行原样保留。replacement 从既有 `BLE_RELEASE_ALIASES` 权威生成，必须在 runtime CDC bundle 中恰好存在一次。默认 native 分支继续使用原 BLE 常量，accepted/pinned 的来源策略保持原检查。

`profile.verify()` 会重新计算适配策略，并检查实际 staged SDC：旧查询缺席、六条保留约束及真实别名 replacement 各一次。元数据不能自行抹掉 replacement 或宣称新路径已经接受。没有扩大 shared filter 或用宽 false path 规避错误；冻结基线、vendor、原网表及旧证据未改。

新 prepare 结果：

```text
candidate: custom138k-workstation-v1-bd40620bb1b139bb
candidate_input_sha256: bd40620bb1b139bb72c8d8a58aa4eb687a2947dfb3b9ef4ce708cd4439c3bb2e
configuration_sha256: e1f13c6662772b1855368041e60f7493af2299978f6483f4f3aa8a7bd3f0d84b
SDC SHA256: 6134703a9f00a8009a1b20280a2cab0e9e361e2c3c626dd82745f8c216bb46b2
```

来源仍为 313 锁／735 snapshot／570 staged／259 enabled。相比 `60f1c843ad79aa6e`，570 项 staged 中只有完整 SDC 改变，其余 569 项逐字节相同；新 SDC 为 270 行，活动约束与 F8 完全相同（F8 另有一条适配说明注释）。没有移用 F8 的实验身份或后续物理结果。

父级在真实新 prepare 上完成 profile **19/19**、来源 **12/12**、accepted sources **10/10**、CDC policy **4/4**，均无 skip。policy 含五种输入／锚点漂移负控；另复制真实新 prepare，分别篡改 replacement 元数据、恢复旧 reset 行、移除真实 held payload delay，三个负控均在实际 `profile.verify()` 调用路径被拒绝，复原后通过。默认旧 prepare 也验证了 BLE bundle 和原 ROM 来源未变。预处理仍为 256 HDL units／288 modules／2 packages。

完整身份、输入锁、日志、负控和独立提案检查见[机器证据](workstation_task_20261030/runtime_ble_release_composition.json)。真实 prepare 位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-ble-alias-v1`。本阶段未对新候选综合、P&R 或板测；旧 25/77 CDC、f1be 综合和 F8 物理试验继续绑定各自原输入，不能因活动约束相同转移接受。

该修复关闭了 cache 适配成为唯一生产输入的问题。后续仍需完成 PCM bridge/context 等剩余 CDC、完整复位／PLL、双模式 routed timing 和真实功能验收；部署门禁保持 false。没有 SRAM/Flash 操作。回滚须同步撤回 runtime 专用适配、composition 调用、profile 重算检查、fixture 和三项来源锁，不能单独恢复旧空查询后继续沿用新身份。
