"""Exact gain-path structural lineage; sample and update edges are unchanged."""
import hashlib

SOURCE = 'rtl/audio/workstation_runtime_stereo_effects.sv'
TOOL = 'tools/workstation_effect_gain_path.py'
PARENT_SHA256 = '50d18332d820f8bc11f272726b6ed51190cd3ec4acde666c9ef4d0c511ab4e13'
SELECTED_SHA256 = '9583b6a9f4d4359018da4fdbbe08b5d8ed4eb34d9a126b1643314d5a21838036'
EDITS = [('  wire [15:0] gain_delta=applied_rate_44100_o ?\n'
  "      16'd139+{15'd0,gain_fraction_sum>=8'd147} : 16'd128;\n",
  '  // remainder is 0..146. Compare before addition to shorten the gain path.\n'
  '  wire [15:0] gain_delta=applied_rate_44100_o ?\n'
  "      16'd139+{15'd0,gain_remainder>=8'd100} : 16'd128;\n"),
 ('    logic [15:0] upper,lower;\n'
  '    begin\n'
  "      upper=value>16'hffff-delta ? 16'hffff : value+delta;\n"
  "      lower=value<delta ? 16'd0 : value-delta;\n"
  '      if(target>upper)runtime_slew=upper;\n'
  '      else if(target<lower)runtime_slew=lower;\n'
  '      else runtime_slew=target;\n'
  '    end\n',
  '    logic [15:0] distance_up,distance_down;\n'
  '    begin\n'
  '      // Distances depend only on committed gains. Delta selects a bounded\n'
  '      // movement; target ordering guarantees that movement cannot wrap.\n'
  '      distance_up=target-value;\n'
  '      distance_down=value-target;\n'
  '      if(target>=value)\n'
  '        runtime_slew=distance_up>delta ? value+delta : target;\n'
  '      else\n'
  '        runtime_slew=distance_down>delta ? value-delta : target;\n'
  '    end\n')]

def normalize(source):
    try:
        from tools.workstation_effects_reserved_config import normalize as normalize_dispatch
    except ModuleNotFoundError:
        from workstation_effects_reserved_config import normalize as normalize_dispatch
    source = normalize_dispatch(source)
    digest = lambda b: hashlib.sha256(b).hexdigest()
    if digest(source) != SELECTED_SHA256:
        return source
    text = source.decode()
    for before, after in reversed(EDITS):
        if text.count(after) != 1:
            raise ValueError('effects gain reverse anchor changed')
        text = text.replace(after, before, 1)
    restored = text.encode()
    if digest(restored) != PARENT_SHA256:
        raise ValueError('effects gain parent identity changed')
    for before, after in EDITS:
        if text.count(before) != 1:
            raise ValueError('effects gain forward anchor changed')
        text = text.replace(before, after, 1)
    if text.encode() != source:
        raise ValueError('effects gain round trip changed')
    return restored
