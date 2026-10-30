# C06 最终说明文档来源锁修正

`cb4e8ac` 在 prepare／verify 通过后补写了 `WORKSTATION_PROFILE.md`，遗漏更新五份 profile 中该文档的 SHA256；最终提交因此会被下一次来源检查拒绝。此修正只更新这个锁，不改代码、固件、容量、约束或冻结输入；原先候选与父级证据保留原身份。

在独立的 `cb4e8ac` checkout 中补锁，五个 profile 均加载通过，`ProfileSources` 六项通过，并重新实际 prepare／verify：`custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1-ef580f60160b1e27`。600 项 staged 中 599 项与原 C06 完全相同，唯一差异是 `native_usb_firmware/build.log` 的源码根目录诊断路径；路径替换后的日志完全一致，所有编译输入及 ROM 字节保持。

机器记录：[ae350_boot64_doc_lock.json](workstation_task_20261030/ae350_boot64_doc_lock.json)。独立源码、日志及候选位于缓存 `c06-doc-lock-fix-v1`／`c06-doc-lock-fix-prepare-v1`；没有综合、物理或板卡操作。回退到原配置或用新身份重建，不能复用旧来源身份。
