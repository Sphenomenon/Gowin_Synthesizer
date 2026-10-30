# R00 owner8 组件主线复验（2026-10-30）

主线从 `28706a8` 白名单导入独立组件提交 `d3ddb5142197a8ee1e8dd88841aeee7ca34a9867`，未合并隔离分支的其它历史。机制、三次接受边界、取消和 sticky transport fault 契约见[组件报告](WORKSTATION_RECORDING_DDR_OWNER8_20261030.md)。本阶段仍未选入生产 owner8、最终 PCM CDC 或录音对象业务，R00/R01/R02 不勾选。

父级在实际主目录分别重新执行原生路径 **44 项（33 正向、11 负控）**与后端 **41 项（28 正向、13 负控）**，全部符合预期。两组来源运行期间保持，事后逐文件哈希复核匹配隔离封存身份；严格 lint 均零 warning。原 timing/music 依赖字节不改。用例包含默认/空闲 legacy 逐拍 miter、owner8 与合法 music/NN 客户端并发、真实 native 写接受、mask/返回账本、cancel 排空及 bridge 故障同拍阻断；并发客户端不代表完整 CNN 算法实例。

新真实 prepare 位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-owner8-unselected-v1`：

```text
candidate: custom138k-workstation-v1-7ffad19cde578d67
candidate_input_sha256: 7ffad19cde578d673e54ca3a9b492f249eef91910fe5512437d4dd77e704d87a
configuration_sha256: e1f13c6662772b1855368041e60f7493af2299978f6483f4f3aa8a7bd3f0d84b
prepare_artifact_sha256: 6f73af99fcaabd53e61d9614300ddaa0d5a6fdbef9adfa3ada2b2eb4def128a3
```

来源为 **313 锁 / 738 snapshot / 570 staged / 259 enabled**。相对 `bd40620bb1b139bb`，snapshot 新增三个 memory 组件、更新未选择 backend；全部 570 staged 和 259 enabled 映射完全相同，实际 staged 字节也逐项重验。新组件只是进入源码快照，没有因目录枚举而成为编译输入。

profile **19/19**、实际来源 **12/12**、accepted sources **10/10** 全部通过，无 skip；预处理为 256 HDL units / 288 modules / 2 packages。profile 首次调用误填了不存在的 legacy fixture 路径，随后使用既有 `native-default-after-media-v1` 完整重跑 19 项通过，非产品失败。完整父级用例结果、来源哈希、日志和比较见[机器证据](workstation_task_20261030/recording_ddr_owner8_main_integration.json)。

没有本阶段组件综合、P&R 或硬件操作，也不移用 f1be 的综合/局部 CDC 或 F8/F9 的物理结果。下一步仍需显式来源策略接入生产 DDR owner、最终 PCM 与对象生命周期，并完成共享 DDR 期限、完整 CDC/reset/PLL、routed timing 和实板录音验证。回滚应同时撤回组件/契约/fixture/runner、backend 可选 transport 接口及本阶段证据，保留前阶段 DDR 地址分配和历史报告；当前板卡无部署变化。
