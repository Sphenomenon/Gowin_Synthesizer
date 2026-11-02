"""Exact new-policy LCD/F808 composition, independent of accepted profiles.

Role adapters run first. The inverse removes common wiring before the strict
role inverses. No maintained top or historical constraint bytes are rewritten.
"""
from pathlib import Path
import hashlib
import re

POLICY='task3_lcd_reqack_crc_session_budget_gated_v1'
CONFIG_POLICY='task3_f808_nonzero_nonce_v1'
LCD_BEHAVIOR='task3_lcd_fixed_direction_reqack_high_z_until_probe_v1'
TOP='rtl/workstation/gw138k_push_workstation_top.v'
BOARD='rtl/workstation/workstation_task3_paired_link_board.svh'
PINPLAN='boards/custom_138k/task3_lcd_probe_pinplan.json'
CST='boards/custom_138k/task3_lcd_probe.cst'
SOURCES=('rtl/workstation/workstation_task3_paired_link.sv',
 'rtl/workstation/workstation_task3_lcd_phy.sv','rtl/workstation/workstation_task3_lcd_pins.sv',
 'rtl/workstation/workstation_task3_lcd_transport.sv','rtl/services/workstation_task3_pair_config_service.sv')
DEPENDENCIES=('tools/workstation_task3_paired_board.py',BOARD,PINPLAN,CST,
 'rtl/workstation/TASK3_LCD_TRANSPORT.md','rtl/workstation/WORKSTATION_TASK3_PAIRED.md','rtl/services/TASK3_PAIR_CONFIG_CONTRACT.md',
 'boards/custom_138k/ae350.cst','boards/custom_138k/clocks.json',
 'boards/custom_138k/usb2_cdc.json','boards/custom_138k/input_cdc.json')
# New synchronizers must receive a routed CDC/endpoint review before a physical
# candidate can be accepted. This marker adds no false path or relaxed budget.
SDC='\n# TASK3 paired LCD/F808 CDC physical endpoint review REQUIRED; no blanket exception.\n'

def digest(value):
 return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()

def role_helper(role):
 if role=='M':
  from tools import workstation_task3_m_paired_profile as helper
 elif role=='W':
  from tools import workstation_task3_w_paired_profile as helper
 else:raise ValueError('unknown paired role')
 return helper

def edits():
 ports='    output wire [4:0] lcd_r,\n    output wire [5:0] lcd_g,\n    output wire [4:0] lcd_b,\n    output wire lcd_pclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl,\n'
 paired=ports.replace('output wire','inout wire')+'    inout wire lcd_ctp_rst,lcd_ctp_sda,lcd_ctp_scl,lcd_ctp_int,\n'
 decl='    wire [3:0] pstrb;\n'
 low="    assign lcd_r=5'd0,lcd_g=6'd0,lcd_b=5'd0;\n    assign lcd_pclk=1'b0,lcd_hsync=1'b0,lcd_vsync=1'b0,lcd_de=1'b0,lcd_bl=1'b0;\n"
 apb='`ifdef WORKSTATION_TASK3_W_MEDIA\n        .APB_PRDATA('
 mux='''        .APB_PRDATA(task3_pair_config_select?task3_pair_config_data:pcm_select?pcm_bus_data:business_select?business_bus_data:recording_select?recording_bus_data:clock_service_select?clock_service_data:service_select?service_data:ui_select?ui_read_data:32'h41313338),
        .APB_PREADY(task3_pair_config_select?task3_pair_config_ready:pcm_select?pcm_bus_ready:business_select?business_bus_ready:recording_select?recording_bus_ready:clock_service_select?clock_service_ready:service_select?service_ready:ui_select?ui_ready:1'b1),
        .APB_PSLVERR(task3_pair_config_select?task3_pair_config_error:pcm_select?pcm_bus_error:business_select?business_bus_error:recording_select?recording_bus_error:clock_service_select?clock_service_error:service_select?service_error:ui_select?ui_error:!valid_word),.APB_PADDR(paddr),
'''
 # M lacks business/recording pages. These constant aliases are board-level
 # selection only; there is no second recording backend on M.
 m_alias='''`ifdef WORKSTATION_TASK3_M_PAIRED
    wire recording_select=1'b0,recording_bus_ready=1'b1,recording_bus_error=1'b1;
    wire [31:0] recording_bus_data=0;
`endif
'''
 return ((ports,paired),(decl,decl+'`include "'+BOARD+'"\n'+m_alias),
 (low,'    // Paired LCD pads belong exclusively to u_task3_pair_link.\n'),
 (apb,'`ifdef WORKSTATION_TASK3_M_PAIRED\n'+mux+'`elsif WORKSTATION_TASK3_W_PAIRED\n'+mux+'`elsif WORKSTATION_TASK3_W_MEDIA\n        .APB_PRDATA('))

def apply_top(root,text,role):
 helper=role_helper(role)
 parent=helper.inverse_top(root,text)
 if helper.apply_top(root,parent)!=text:raise ValueError('paired common input must match exact selected role top')
 for old,new in edits():
  if text.count(old)!=1:raise ValueError('paired common unique anchor drift')
  text=text.replace(old,new,1)
 return text

def inverse_top(root,text,role):
 selected=text
 for old,new in reversed(edits()):
  if text.count(new)!=1:raise ValueError('paired common inverse anchor drift')
  text=text.replace(new,old,1)
 role_helper(role).inverse_top(root,text)
 if apply_top(root,text,role)!=selected:raise ValueError('paired common inverse roundtrip drift')
 return text

def prepare_top(root,stage,role):
 target=Path(stage)/TOP
 parent=target.read_text()
 selected=apply_top(root,parent,role)
 target.write_text(selected)
 return dict(policy=POLICY,config_policy=CONFIG_POLICY,role=role,
  parent_top_sha256=digest(parent),selected_top_sha256=digest(selected),
  sources_sha256={p:digest((Path(stage)/p).read_bytes()) for p in (*SOURCES,BOARD)},
  pinplan_sha256=digest((Path(root)/PINPLAN).read_bytes()),
  compile_experiment_enabled=True,compile_business_enabled=True,
  runtime_probe_default=False,runtime_budget_default=False,runtime_business_default=False,
  nonce_source='explicit_CPU_writes_nonzero_unique_per_root_and_peer_session',
  lcd_behavior=LCD_BEHAVIOR,physical_cdc_verified=False,hardware_accepted=False)

def verify_selection(root,stage,metadata,role):
 target=Path(stage)/TOP
 selected=target.read_text()
 parent=inverse_top(root,selected,role)
 expected=dict(policy=POLICY,config_policy=CONFIG_POLICY,role=role,
  parent_top_sha256=digest(parent),selected_top_sha256=digest(selected),
  sources_sha256={p:digest((Path(stage)/p).read_bytes()) for p in (*SOURCES,BOARD)},
  pinplan_sha256=digest((Path(root)/PINPLAN).read_bytes()),
  compile_experiment_enabled=True,compile_business_enabled=True,
  runtime_probe_default=False,runtime_budget_default=False,runtime_business_default=False,
  nonce_source='explicit_CPU_writes_nonzero_unique_per_root_and_peer_session',
  lcd_behavior=LCD_BEHAVIOR,physical_cdc_verified=False,hardware_accepted=False)
 if metadata!=expected:raise ValueError('paired common evidence drift')
 for path in (*SOURCES,BOARD):
  if (Path(stage)/path).read_bytes()!=(Path(root)/path).read_bytes():raise ValueError('paired common staged source drift: '+path)
 return expected

def adapt_constraints(root,sdc):
 if SDC.strip() in sdc:raise ValueError('paired SDC already selected')
 return sdc+SDC,dict(policy=POLICY,parent_sha256=digest(sdc),selected_sha256=digest(sdc+SDC),
  physical_cdc_verified=False,added_exceptions=0)

def restore_constraints(root,sdc):
 if sdc.count(SDC)!=1 or not sdc.endswith(SDC):raise ValueError('paired SDC marker drift')
 return sdc[:-len(SDC)]

def adapt_cst(root,cst):
 fragment=(Path(root)/CST).read_text()
 rows=[line for line in fragment.splitlines(keepends=True) if line.startswith(('IO_LOC ','IO_PORT '))]
 old=[];added=[]
 for row in rows:
  port=re.search(r'"([^"]+)"',row).group(1)
  pattern=r'^'+row.split(' ',1)[0]+r' "'+re.escape(port)+r'"[^\n]*\n'
  found=re.findall(pattern,cst,re.M)
  if port.startswith('lcd_ctp_'):
   if found:raise ValueError('paired CTP port already constrained')
   added.append(row)
  elif found!=[row]:raise ValueError('paired LCD existing constraint identity drift: '+port)
  else:old.append(row)
 if len(old)!=42 or len(added)!=8:raise ValueError('paired pin inventory drift')
 balls=re.findall(r'^IO_LOC "[^"]+" (\w+);',cst,re.M)
 for row in added:
  if row.startswith('IO_LOC ') and row.split()[-1][:-1] in balls:raise ValueError('paired CTP ball conflict')
 selected=cst+'\n// TASK3 paired reserved CTP ports\n'+''.join(added)
 return selected,dict(policy=POLICY,parent_sha256=digest(cst),selected_sha256=digest(selected),
  fragment_sha256=digest(fragment),unchanged_existing_signal_ports=21,added_reserved_ports=4)

def verify_constraints(root,stage,metadata):
 """Recompute both exact adapters, independently of self-reported hashes."""
 from tools.workstation_ae350_clock_placement import CONSTRAINT
 cst=(Path(stage)/'constraints/custom_138k.cst').read_text()
 suffix=CONSTRAINT+'\n'
 if not cst.endswith(suffix):raise ValueError('paired CST dedicated PLL suffix missing')
 selected=cst[:-len(suffix)]
 marker='\n// TASK3 paired reserved CTP ports\n'
 if selected.count(marker)!=1:raise ValueError('paired CST reserved port marker drift')
 original=selected.split(marker)[0]
 rebuilt,evidence=adapt_cst(root,original)
 if rebuilt!=selected or evidence!=metadata.get('task3_paired_cst'):raise ValueError('paired CST exact reconstruction drift')
 assignments=re.findall(r'^IO_LOC "([^"]+)" (\w+);',cst,re.M)
 ports=[p for p,b in assignments];balls=[b for p,b in assignments]
 if len(ports)!=len(set(ports)) or len(balls)!=len(set(balls)):raise ValueError('paired CST duplicate port/ball')
 selected_sdc=(Path(stage)/'constraints/custom_138k.sdc').read_text()
 original_sdc=restore_constraints(root,selected_sdc)
 rebuilt_sdc,sdc_evidence=adapt_constraints(root,original_sdc)
 if rebuilt_sdc!=selected_sdc or sdc_evidence!=metadata.get('task3_paired_sdc'):raise ValueError('paired SDC evidence drift')
 return dict(cst=evidence,sdc=sdc_evidence)
