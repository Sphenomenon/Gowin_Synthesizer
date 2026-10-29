# DDR 扫描窗口的后台写 admission

`workstation_ddr_scan_window.sv` 是同一 DDR UI 时钟域的组合请求门控，不持有命令、地址、payload、参数或新 owner。它应放在稳定客户端请求槽 **之前**，不能放在已入槽请求、native command 或返回通道之后。

`ENABLE=0` 默认逐位透传 writer／CPU 的 valid 和 ready。显式启用时，`scan_fetch_busy_i` 来自实际 `video_ddr_scanout.fetch_busy=active || request_pending`；取行窗口内暂停 merged raster/shared writer 以及 CPU 写的新 admission，正向 valid 与反向 ready 同时置 0。CPU 读仍可接受。宽数据、地址、active-low byte mask 沿原连线保持，生产者在 valid 未被接受时继续持有它们。

TF、delay、CNN、display reader 和 BIST 不经过这两个后台写门。已接受的 writer／CPU 槽、registered grant 与 native command buffer 不因窗口开始而取消，仍按原仲裁顺序排空；不清队列，不伪造完成，也不丢弃迟到响应。共享请求槽与一个 command buffer 最多留下每 owner 两笔尚未 native-issued 的写；registered grant 引用槽而不另存命令。这个上限不包含 DDR IP 已接收的内部事务，不能替代控制器规格中的尾部／返回保证。

原生组合位于 `rtl/workstation/workstation_hdmi_display.sv`，保留 module `hdmi_display` 及原公有端口。`SCAN_WINDOW_ENABLE` 默认 0；编译宏 `WORKSTATION_DDR_SCAN_WINDOW_ENABLE` 将默认值明确置 1，实例参数仍可覆盖。新 profile 必须同时显式选择此组合及 gate，不能把原活动／冻结 `hdmi_display.v` 改写成同名新输入。迁移来源、父 prepared 哈希和七个精确变更区域保存在同目录的 `workstation_hdmi_display.provenance.json`；反向恢复后应逐字节等于父输入。

此模块复用独立 D5 的 admission 原则，并扩大到 CPU 后台写；没有实现 D01 的水位／deadline／公平调度。窗口结束后后台写恢复，但若取行因控制器长期停顿而迟迟不结束，门本身不给 CPU／writer 一个额外超时或强制份额；不得据此宣称所有客户端 ≤1 ms。原 scan 无活动 watchdog 也不等于行期限。保留 TF／delay／CNN 的服务能避免直接取消实时流，但它们的读写切换同样可能使行迟到，需要在同一并发预算中解决。

针对性诊断使用实际 prepared 的 scanout、SDP、queues/core，并记录来源与控制器模型。默认关闭与旧分支比较像素及 native 命令计数；开启后检查禁止假 ACK、CPU 读透传、既有尾部的地址／数据／mask／顺序与精确排空、返回账本及队列峰值。其他客户端以明确速率的有界请求模型施压，不能替代真实 TF／delay／CNN DMA、物理 DDR 或两种音频模式验收。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_scan_window.py \
  --project /absolute/prepared/workstation/Prj1 \
  --output /absolute/new/diagnostic-output
```

报告必须保留不通过的控制器模型：100 UI 拍人工读写切换代价下，只有后台 writer 的 D5 场景可通过，但 TF／delay／CNN 等混合请求可能继续造成黑行。退出条件是 D01 有界服务和 D04 同候选整机期限／物理／实板验证；本模块源码与仿真不关闭这些任务。
