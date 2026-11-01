# M TF private read-buffer preload

M17 far measured the actual `available_bytes` → 256-bit `read_buf` CE path at −1.766 ns. Maintained DMA now preloads private `read_buf` while `read_buf_valid` is zero in the original active-stream branch; valid data stays fixed while the FIFO consumes it. Unknown validity takes the original procedural response branch. Unchanged response publication/index/count/pointer timing adds no cycle.

Maintained SHA256 `5fc0fd0930fcaedf9a5b2e43f8f0b04a8fd085ba7261f68feefe80539ad5ef3f`; immutable before fixture `1baa71464c9180f13fa03a281c81d9cd7d8cb3ace0c538b674e610604d6f25e7`. Exact whole-source inverse and all non-read_buf NBA targets/RHS/order are checked. Previous available/accepted arithmetic stays unchanged. No occupancy equality or app_rvalid-only-when-pending assumption is added.

Six source-pinned hand-lifted binary transition checks are UNSAT: reset establishes pending/valid exclusion; all priorities preserve it; response cannot coexist with a valid buffer; newly published data match; still-valid data remain stable; valid FIFO data match. Three faulty equations yield SAT counterexamples. This is not formal SV elaboration or universal four-state proof.

Actual complete before/current modules at both capacities each pass 737,280 bounded four-state edges; four actual-source negative controls are rejected. All nonprivate state/control remains equal; private buffer is compared when valid and FIFO payload when write-enable is exactly one. The old occupancy oracle now expresses these effective-data boundaries and adds pending/valid exclusion; all other assertions remain.

Maintained regressions passed: new source/invariant/four-state entry; available four runs/three negatives including 2,097,152 four-state vectors; accepted-response seven runs/six negatives; occupancy 14 runs/eight negatives including four actual ring runs; threshold eight runs/six negatives; original complete TF service/clear/stop. Original cofactor source pins and NBA assertions remain through strict reversible 5fc→1baa adaptation; actual simulation uses maintained 5fc. Root independently reread ten owned sources, 54 test inputs, 288 maintained artifacts and 3,696 cache proposal artifacts. The adjacent JSON records all source/result identities.

Three early stop-wrapper fixture failures remain preserved. The successful original wrapper restores missing historical support into a cache-only repository layout after checking frozen descriptor hashes, including line-ending/base64 policy. Original runners, locked descriptors, vendor bytes and gates remain unchanged; cache fixtures are never production inputs.

Evidence root: `/Users/sphenicidition/.cache/gw138k-dual-20261031/m18-tf-private-preload-maintained-v1`; seal `98468c40e201684de91ea54eabfb41452d31b84fc3cc8f976449c380fa0392b1`, verification `9b9690a3c0efb9eeb041f9d7f27d6e41fb99070af003468d5224b40e28c23420`. Cache proposal seal `28cd63f88d4c38dea8bfa08985d3351841e58878a478cccca874cb5c5e718759` retains old M17 prepared/routed/tool identities.

This is maintained-source/offline acceptance. M18/W16 prepare and synthesis consume new bytes as a separately recorded stage. No resource/routed timing benefit, SRAM/Flash write, physical EOS/sound/video or two-board acceptance follows; M base still omits CNN.
