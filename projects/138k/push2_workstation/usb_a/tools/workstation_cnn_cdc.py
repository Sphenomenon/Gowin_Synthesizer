"""Bounded local diagnostic patch on the pinned CNN timing85 link only."""
import hashlib
from workstation_sources import TIMING85_OVERLAYS
from workstation_baselines import load_baseline
LINK='rtl/music/basic_pitch_workstation_link.sv'


def transform(text):
    old='''    wire [9:0] model_path_trace = {bp_mem_req,bp_mem_ready,
        ddr_cmd_valid,ddr_cmd_ready,ddr_req,ddr_ready,
        ddr_rsp_valid,ddr_rsp_fifo_valid,memory_reset_n,memory_calibrated};'''
    new='''    // UART samples levels, not event counts. Retain its bit layout while
    // sampling the seven DDR-domain diagnostics through local two-stage FFs.
    wire [6:0] ddr_trace_sync;
    gw138k_level_cdc #(.WIDTH(7)) u_trace_cdc(
        .clk(clk_50m),.reset_n(reset_n),
        .data_i({ddr_cmd_valid,ddr_cmd_ready,ddr_req,ddr_ready,ddr_rsp_valid,memory_reset_n,memory_calibrated}),
        .data_o(ddr_trace_sync));
    wire [9:0] model_path_trace = {bp_mem_req,bp_mem_ready,
        ddr_trace_sync[6:2],ddr_rsp_fifo_valid,ddr_trace_sync[1:0]};'''
    if text.count(old)!=1:raise ValueError('CNN diagnostic trace anchor changed')
    text=text.replace(old,new,1)
    old_status="model_status,memory_calibrated,1'b1};"
    if text.count(old_status)!=1:raise ValueError('CNN UART status anchor changed')
    return text.replace(old_status,"model_status,ddr_trace_sync[0],1'b1};",1)


def select(root,selected):
    if LINK not in TIMING85_OVERLAYS:raise ValueError('trace patch must stay inside the six timing files')
    payload=load_baseline(root,'timing85').read_bytes(LINK)
    before=hashlib.sha256(payload).hexdigest()
    if selected[LINK]!=before:raise ValueError('trace patch requires the exact pinned timing85 link')
    text=transform(payload.decode());after=hashlib.sha256(text.encode()).hexdigest()
    selected=selected.copy();selected[LINK]=after
    return selected,dict(file=LINK,base_sha256=before,selected_sha256=after,
        transform='seven DDR diagnostic levels, including reset and calibration status -> two 50MHz sampling stages; UART bit positions unchanged',
        flash_boot=False,cnn_arithmetic_changed=False)
