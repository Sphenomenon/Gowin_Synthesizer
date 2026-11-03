# Custom 138K board netlist inputs

The user supplied these original netlists on 2026-11-03 for versioned build
preparation. Their bytes match the existing `../pinout.json` source identities;
the pinout and electrical evidence are unchanged.

| Input | SHA256 |
| --- | --- |
| `Netlist_my_138k_2026-10-21.tel` | `deff91f6c48be8d66241e32107b88f7eea47ad2bf6c5b607b139c4b85c33a121` |
| `功放.tel` | `b0ae6b2be4b59a60244a98ea870fc701bb4e8186123b7cb54cf79e22ea628b75` |
| `蓝牙.tel` | `832e1eae56a744f8535899f57caea097f51419e2eb210186a492c182e5091eb2` |

Pass this directory explicitly as `--netlist-dir`. Verification still rejects
missing or changed inputs. These files describe connectivity, not hardware or
electrical acceptance; they do not authorize programming a board.
