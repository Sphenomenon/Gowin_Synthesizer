"""Explicit native HDMI modes; frozen and accepted inputs remain unchanged."""

from pathlib import Path
import shutil
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha


MODES = ('1080p60', '720p30', '720p60')
IDENTITY_720 = 'custom138k-native-integration-20261027-video720p30-a25'
LOCKED_INPUTS = {
    'src/video/hdmi_display.v': '900914bbcc98cdb563f708eea2bf6edf989917526103d628799930acfba59794',
    'src/video/feedback_renderer.v': '70b273a40429e7af40830664990280a2dcc1d1ec79c693b8b23d8f3276064834',
    'src/video/feedback_dashboard.v': '0271e9a6897eaff4308a4b01380429672e67d669ab422e31e1190ed7a0278c6b',
    'vendor/sipeed_dvi/video_pll_1080p_gw5a.v': '0807a7d45aa095e327a6da3ba119fac727d982cdb99b6da02bdf11f6858fdad3',
}
RENDERER = 'rtl/display_data/feedback_renderer.v'
TIMING = 'rtl/display_data/workstation_video_timing_720p30.sv'
ADAPTED_PLL = 'rtl/display_data/workstation_video_pll_720p30.v'
PROFILES_720 = {
    '720p30': dict(identity=IDENTITY_720, refresh_hz=30, h_total=3300,
                   timing=TIMING, pll=ADAPTED_PLL),
    '720p60': dict(identity='custom138k-native-integration-20261027-video720p60-a25',
                   refresh_hz=60, h_total=1650,
                   timing='rtl/display_data/workstation_video_timing_720p60.sv',
                   pll='rtl/display_data/workstation_video_pll_720p60.v'),
}


def once(text, original, replacement):
    if text.count(original) != 1:
        raise ValueError('HDMI mode adaptation anchor drift: ' + original)
    return text.replace(original, replacement)


def apply(root, stage, files, mode):
    if mode not in MODES:
        raise ValueError('unsupported HDMI mode: ' + str(mode))
    if mode == '1080p60':
        return dict(mode=mode, width=1920, height=1080, refresh_hz=60,
                    pixel_hz=148500000, serial_hz=742500000, adapted={})
    profile = PROFILES_720[mode]
    timing, adapted_pll = profile['timing'], profile['pll']
    root, stage = Path(root), Path(stage)
    for relative, expected in LOCKED_INPUTS.items():
        if sha(stage / relative) != expected:
            raise ValueError('HDMI mode locked input drift: ' + relative)
    replacements = {
        'video_timing_1080p u_timing (': f'workstation_video_timing_{mode} u_timing (',
        'feedback_renderer #(.ENABLE_ANALYSIS(1),':
            'feedback_renderer #(.WIDTH(1280),.HEIGHT(720),.SCALE_THREE_HALVES(1),.ENABLE_ANALYSIS(1),',
        'video_ddr_scanout #(.EXPLICIT_BASE(1))':
            'video_ddr_scanout #(.WIDTH(1280),.HEIGHT(720),.EXPLICIT_BASE(1))',
    }
    original = (stage / 'src/video/hdmi_display.v').read_text()
    for anchor, replacement in replacements.items():
        original = once(original, anchor, replacement)
    pll = (stage / 'vendor/sipeed_dvi/video_pll_1080p_gw5a.v').read_text()
    pll = once(pll, '.OUTPUT_DIV0(1), .OUTPUT_DIV1(5),', '.OUTPUT_DIV0(2), .OUTPUT_DIV1(5),')
    dashboard = once((stage / 'src/video/feedback_dashboard.v').read_text(),
                     '1920 X 1080 / 60 HZ             ',
                     f"1280 X 720 / {profile['refresh_hz']} HZ              ")
    entries = [entry for entry in files if entry.get('path') == 'vendor/sipeed_dvi/video_pll_1080p_gw5a.v'
               and entry.get('enable') == '1']
    if len(entries) != 1:
        raise ValueError('HDMI PLL compilation selection drift')
    (stage / adapted_pll).parent.mkdir(parents=True, exist_ok=True)
    (stage / adapted_pll).write_text(pll)
    (stage / 'src/video/hdmi_display.v').write_text(original)
    (stage / 'src/video/feedback_dashboard.v').write_text(dashboard)
    shutil.copyfile(root / RENDERER, stage / 'src/video/feedback_renderer.v')
    shutil.copyfile(root / timing, stage / timing)
    entries[0].set('enable', '0')
    for relative in (adapted_pll, timing):
        if any(entry.get('path') == relative for entry in files):
            raise ValueError('HDMI mode duplicate input: ' + relative)
        ElementTree.SubElement(files, 'File', path=relative, type='file.verilog', enable='1')
    return dict(mode=mode, width=1280, height=720, refresh_hz=profile['refresh_hz'],
                pixel_hz=74250000, serial_hz=371250000, h_total=profile['h_total'], v_total=750,
                canvas_width=1920, canvas_height=1080, canvas_mapping='floor(output_coordinate*3/2)',
                source_inputs=LOCKED_INPUTS,
                source_overlays={relative: sha(root / relative) for relative in (RENDERER, timing)},
                adapted={relative: sha(stage / relative) for relative in
                         ('src/video/hdmi_display.v', 'src/video/feedback_renderer.v',
                          'src/video/feedback_dashboard.v', adapted_pll, timing)},
                exit_plan='Keep the explicit native mode; replace checked legacy HDMI/PLL adaptations when those owners move to native versioned source. Never change accepted defaults.')
