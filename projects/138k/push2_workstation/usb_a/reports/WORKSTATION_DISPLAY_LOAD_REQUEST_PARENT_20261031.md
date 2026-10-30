# 显示 load-request 父级合入（2026-10-31）

owning `workstation_display_runtime.sv` 已合入主线，新增请求寄存和 export-live 取消 token。请求多一个内存时钟周期；current-image 的上下文失效保持立即生效，reader 完成必须满足 loading／enabled／live／current 与完整 rate/epoch 验证。最坏允许接受边界多做一个不能发布的旧 private-cache read（365 个 BL8、原有单 outstanding），不增加音频背压或公共参数副本。接口、时钟、约束、baseline 不变。

父级在独立封存源码 clone 重跑完整 runtime＋三个官方 GW5A HDMI elaboration，通过 6 次 publication／9 commit／128,702 atomic tuples，无 owning 警告。真实 writer／reader 竞争回归通过 12 场景／47 checks／10 loads／3,286 reads／四行为负控；覆盖上下文失效同拍、disable／迟到完成／重新使能、raster arbitration 和无 loading token 的 completion。主仓库导入 RTL、测试与文档逐字等于交付，四 profile 只替换 owning RTL SHA，保留先前八项 CDC helper 锁。

四份主仓库 fresh prepare 各 12 项来源检查通过；579／580／592／599 staged 的唯一变化是 owning display RTL，260／260／267／269 enabled 的唯一变化是该项 source/sha 记录，GPRJ 字节与编译顺序不变。profile 21 项（历史可选一项跳过）、accepted 17 项通过。首次验证器错误地要求含哈希的 enabled_inputs 整对象不变；第二次又误当其 value 为纯 SHA。v3 按实际 provenance-record 结构逐字段验证预期两个 hash，所有其余 key／value 精确相同；原脚本／失败日志保留，没有修改 prepare 字节或重跑构建来覆盖它们。新 no-panel prepare 为 `222fb761448fb6c0`，不是物理接受身份。

完整 hash／捕获源码／四 prepare 与执行范围见[机器记录](workstation_task_20261030/display_load_request_parent.json)。固定 18ed/C2103101 已在本次合入前独立复制冻结，仍使用旧显示源码；物理包 4,278 份输入在 root 修改后 hash-only 重验仍通过。本源码修复未综合，不宣称时序改善，后续须另建候选、实际网表／完整 CDC／routed STA／硬件验证。没有将此源码烧入 SRAM 或 Flash。
