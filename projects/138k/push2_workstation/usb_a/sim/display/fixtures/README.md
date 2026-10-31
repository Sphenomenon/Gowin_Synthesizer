# Display analysis reference

`display_data_analysis_source_pre_m8.sv` preserves the exact maintained producer at commit `ec223df`, before the M8 equality/sequence timing change. Its SHA256 is `a8f1a948370a464d6ed609d275075e2ff936a01e62bc915074914a1193d9736c`.

`../run_display_analysis_equivalence.py` requires those bytes, preserves the existing prepared support hashes, and renames only the reference module identifier in its output directory. The fixture is a test oracle, never a production build input. Update production RTL independently; do not alter this reference to make equivalence pass.
