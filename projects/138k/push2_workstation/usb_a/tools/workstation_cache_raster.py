"""M preboard raster pacing by the existing validated-cache owner.

The old local snapshot remains the default. This selection retires only its
unused duplicate capture/alignment cone and the two orphan ACK constraints.
The native runtime's current-image admission and P5 cache lease stay intact.
"""
from pathlib import Path
import hashlib,json

KEY='display_raster_policy'
POLICY='task3_M_validated_cache_raster_admission_v1'
SOURCE='rtl/display_data/feedback_renderer.v'
DEFAULT='parameter integer SHARED_CACHE_ONLY = 0'
SELECTED='parameter integer SHARED_CACHE_ONLY = 1'
MANIFEST='rtl/display_data/workstation_cache_raster_v1.provenance.json'
TOOL='tools/workstation_cache_raster.py'
RETIRED_LINES=(
 'set_false_path -to [get_pins {u_video/u_renderer/u_capture/ack_meta_s*/D}]',
 'set_max_delay 2.000 -from [get_pins {u_video/u_renderer/u_capture/ack_meta_s*/Q}] -to [get_pins {u_video/u_renderer/u_capture/ack_sync_s*/D}]',
)

def require(ok,message):
    if not ok:raise ValueError('M cache raster: '+message)


def digest(payload):return hashlib.sha256(payload).hexdigest()


def configured(configuration):
    policy=configuration.get(KEY)
    require(policy in (None,POLICY),'unknown policy')
    if policy:
        require(configuration.get('demo_role')=='M' and
                configuration.get('display_metadata_minor')==1 and
                configuration.get('display_reader_validated_policy')==
                'task3_M_validated_display_metadata_storage_v1','requires native M validated minor1 cache')
    return bool(policy)


def unselect(text):
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected parameter missing or duplicated')
    text=text.replace(SELECTED,DEFAULT,1)
    manifest=json.loads((Path(__file__).resolve().parents[1]/MANIFEST).read_text())
    require(digest(text.encode())==manifest['sources'][SOURCE]['native_sha256'],'native parameter inverse drift')
    return text


def select(stage,configuration):
    if not configured(configuration):return None
    path=Path(stage)/SOURCE;text=path.read_text()
    require(text.count(DEFAULT)==1 and SELECTED not in text,'native default missing or duplicated')
    chosen=text.replace(DEFAULT,SELECTED,1)
    require(unselect(chosen)==text,'native selection does not invert')
    path.write_text(chosen)
    return evidence(stage,configuration)


def evidence(stage,configuration):
    if not configured(configuration):return None
    stage=Path(stage);manifest=json.loads((stage/MANIFEST).read_text())
    require(manifest['policy']==POLICY,'source provenance policy drift')
    hashes={}
    for source,row in manifest['sources'].items():
        payload=(stage/source).read_bytes();require(digest(payload)==row['selected_sha256'],'selected source drift: '+source)
        text=unselect(payload.decode())
        for edit in reversed(row['edits']):
            require(text.count(edit['after'])==1,'reverse source anchor drift')
            text=text.replace(edit['after'],edit['before'],1)
        require(digest(text.encode())==row['parent_sha256'],'parent source drift')
        for edit in row['edits']:
            require(text.count(edit['before'])==1,'forward source anchor drift')
            text=text.replace(edit['before'],edit['after'],1)
        require(text.replace(DEFAULT,SELECTED,1).encode()==payload,'source roundtrip drift');hashes[source]=digest(payload)
    return dict(policy=POLICY,source=SOURCE,source_sha256=hashes,
        manifest_sha256=digest((stage/MANIFEST).read_bytes()),
        removed_constraints=list(RETIRED_LINES),
        frame_start_owner='native_raster_allowed && shared_initialized && !write_req',
        cache_lease='native_raster_lease through final P5 write ACK',
        pixel_pipeline_changed=False,legacy_default_changed=False,
        physical_gates_passed=False,hardware_tested=False)


def constraints(stage,sdc,configuration):
    result=evidence(stage,configuration)
    if result is None:return sdc,None
    lines=sdc.splitlines()
    for line in RETIRED_LINES:
        require(lines.count(line)==1,'retired ACK constraint absent or duplicated')
        lines.remove(line)
    require(not any('u_video/u_renderer/u_capture/' in line for line in lines),
            'unexpected live legacy capture constraint')
    return '\n'.join(lines)+'\n',result


def verify(stage,configuration,metadata):
    expected=evidence(stage,configuration)
    require(expected==metadata,'selection metadata drift')
    if expected:
        sdc=(Path(stage)/'constraints/custom_138k.sdc').read_text()
        require('u_video/u_renderer/u_capture/' not in sdc,'retired owner still constrained')
    return expected


def audit(netlist,configuration):
    require(configured(configuration),'mapped check without explicit selection')
    for prefix in ('u_video/u_renderer/u_capture','u_video/u_renderer/u_align'):
        require(not any(p.startswith(prefix+'/')for p in netlist.cells),'duplicate local snapshot remains')
    counts={}
    for prefix in ('u_video/u_renderer/u_even','u_video/u_renderer/u_odd',
                   'u_video/u_runtime_display/producer/waveform',
                   'u_video/u_runtime_display/producer/analysis',
                   'u_video/u_runtime_display/reader'):
        counts[prefix]=sum(p.startswith(prefix+'/')for p in netlist.cells)
        require(counts[prefix]>0,'required shared display owner absent: '+prefix)
    return dict(policy=POLICY,duplicate_capture_and_alignment_absent=True,retained_cell_counts=counts,
        scope='actual synthesis owner inventory; functional admission and pixel proof remains separate',
        routed_timing_verified=False,hardware_tested=False)
