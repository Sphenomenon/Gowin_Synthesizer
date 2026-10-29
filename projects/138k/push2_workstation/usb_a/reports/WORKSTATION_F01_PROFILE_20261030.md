# F01：显式新板工作站来源检查点

日期：2026-10-30（Asia/Shanghai）。继环境阶段 `0ab4d86`，新增 `--prepare-custom-board --workstation-profile custom138k-workstation-v1`。当前 revision 1 固定已有 1080p60／HS 可协商／WAV／48 kHz 装配，目标的双采样率和其他未实现功能明确留在 feature matrix。accepted、pinned、resource 及未指定 profile 的原生入口保持原来源。

## 来源和身份

真实三网表与 xPack 15.2.0-1 编译 prepare 通过；锁定 233 项来源，230 个启用编译输入。候选 `custom138k-workstation-v1-2ed5155f12a6b585`，配置 SHA256 `2eaf2aca7eee25e3fd4e0a91883d008a2a368d1b076e296021fab4430b901ba1`；完整逐文件闭包和来源对照见 [f01_profile.json](workstation_task_20261030/f01_profile.json)，校验结果见 [f01_verification.json](workstation_task_20261030/f01_verification.json)。

候选身份同时绑定配置、实际 staged 文件和 USB 固件工具／ELF／ROM 身份。校验器检查所有实际启用输入及未编译的 ROM／include 依赖，拒绝额外 staged 文件、编译项、来源漂移和硬件验收声明篡改；不会仅按文件存在或旧 a26 identity 判定成功。

- A2：原生 USB RTL、生产固件和 owner 复用当前唯一版本化实现；12 项参考来源同字节。headless 探针顶层不作为整机顶层，热插拔与真实发声仍待 I01。
- D5：11 项参考中 10 项同字节；`build.py` 因新增显式入口发生可追溯变化。扫描模块共享，但独立 `scanout_write_window()` 适配尚未接完整装配，不能继承 D5 的显示验收。
- C1：16 项所选 BLE／业务／PCM 来源与参考同字节；保留短录音容量及历史全零 PCM 限制，不声称真实录音、手机或长录音通过。

USB 固件 binary 为 21,380 B，静态 RAM end 为 27,228／65,536 B，余下栈容量 38,308 B；这是容量，不能替代运行时栈水位证明。AE350 仍用父基线 ROM，后续维护源码接入必须增加 revision 和候选身份。

## 验证与交付边界

profile 回归 9／9 通过，无跳过项，覆盖真实 prepare、配置隔离、源／ROM／额外输入／验收字段篡改拒绝和工具链身份变化。既有新板装配回归 9 项中，8 项首次通过，包含真实 25K 设备模型的 FS／HS 输入和 Gowin 官方原语的 TMDS 综合／仿真；唯一失败是把 2026-10-24 编译器产物 SHA 写死。测试现改为检查生产入口／源哈希，以及本次 ELF binary 的精确小端 ROM 编码与实际哈希；该项定向重跑通过。历史 ROM 和证据原件未修改，没有把新编译产物冒充旧位流。

F01 的来源／配置交付完成；整机综合在独立复制的输入上执行，结果另报，不把 prepare 或源选择通过当作物理验收。当前未下载 SRAM、未写 Flash、无本候选硬件验收，回退来源仍完整保留。D5 整合、双时钟、最终 PCM、DDR 服务预算和业务迁移继续按任务依赖推进。
