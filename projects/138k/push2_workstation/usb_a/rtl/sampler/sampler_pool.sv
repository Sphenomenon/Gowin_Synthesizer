`timescale 1ns/1ps
`include "ddr_address_map.vh"
// Reserve -> write -> commit. Sequential first-fit avoids a large combinational
// GRANULES x GRANULES search network. Committed sounds survive restart.
module sampler_pool #(
  parameter logic [31:0] BASE=`PRJ1_DDR_GROWTH_POOL_BYTE_BASE,
  parameter integer GRANULE=`PRJ1_DDR_ALLOC_GRANULE_BYTES,
  parameter integer GRANULES=104
)(
  input logic clk,rst_n,restart,
  input logic reserve, input logic [5:0] slot,
  input logic [7:0] owner, input logic [31:0] bytes,
  input logic commit,abort_slot,free_slot,
  input logic [31:0] frames,gain_q16,crc32,
  input logic [63:0] referenced,
  output logic done, output logic [7:0] error,
  input logic [5:0] query_slot,
  output sampler_pkg::descriptor_t descriptor,
  output logic [31:0] reserved_base,reserved_capacity,
  output logic [7:0] epoch
);
  import sampler_pkg::*;
  localparam integer IDX=$clog2(GRANULES+1);
  descriptor_t table_d[64];logic [GRANULES-1:0] used;
  logic [63:0] reserved;
  logic [IDX-1:0] first[64],count[64],cursor,pos,run_length,needed,start_at;
  logic [IDX:0] examined;
  logic searching;logic [5:0] target_slot;logic [7:0] target_owner;
  logic [31:0] need;logic [IDX:0] run_next;logic [IDX-1:0] run_start;
  initial begin
    if(BASE[4:0] || GRANULE%32 || (GRANULE&(GRANULE-1))!=0 || GRANULES<1 ||
       {1'b0,BASE}+GRANULE*GRANULES > {1'b0,`PRJ1_DDR_GROWTH_POOL_BYTE_LAST}+1 ||
       BASE<`PRJ1_DDR_GROWTH_POOL_BYTE_BASE) $fatal(1,"sampler pool overlaps address map");
  end
  assign descriptor=table_d[query_slot];
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin
      used<='0;reserved<=0;cursor<=0;epoch<=0;done<=0;error<=0;
      reserved_base<=0;reserved_capacity<=0;searching<=0;pos<=0;run_length<=0;needed<=0;
      start_at<=0;examined<=0;target_slot<=0;target_owner<=0;
      for(int i=0;i<64;i++) begin table_d[i]<='0;first[i]<=0;count[i]<=0;end
    end else begin
      done<=0;
      if(restart) begin
        epoch<=epoch+1'b1;searching<=0;
        if(|reserved) begin
          for(int j=0;j<GRANULES;j++) if(j>=first[target_slot] && j<int'(first[target_slot])+int'(count[target_slot])) used[j]<=0;
          reserved<=0;table_d[target_slot].valid<=0;
        end
      end else if(searching) begin
        // Do not wrap a single allocation across the physical pool boundary.
        run_next=used[pos] ? 0 : (pos==0 ? 1 : run_length+1'b1);
        run_start=(run_length==0 || pos==0) ? pos : start_at;
        start_at<=run_start;run_length<=IDX'(run_next);
        if(run_next>=needed) begin
          for(int j=0;j<GRANULES;j++) if(j>=run_start && j<int'(run_start)+int'(needed)) used[j]<=1;
          first[target_slot]<=run_start;count[target_slot]<=needed;reserved[target_slot]<=1;
          table_d[target_slot]<='0;
          table_d[target_slot].base_bytes<=BASE+int'(run_start)*GRANULE;
          table_d[target_slot].capacity_bytes<=int'(needed)*GRANULE;
          table_d[target_slot].owner<=target_owner;table_d[target_slot].epoch<=epoch;
          reserved_base<=BASE+int'(run_start)*GRANULE;reserved_capacity<=int'(needed)*GRANULE;
          cursor<=int'(run_start)+int'(needed)==GRANULES ? 0 : run_start+needed;
          done<=1;error<=OK;searching<=0;
        end else if(examined+1>=GRANULES+int'(needed)-1) begin done<=1;error<=E_CAPACITY;searching<=0;end
        else begin pos<=pos==GRANULES-1 ? 0 : pos+1'b1;examined<=examined+1'b1;end
      end else if(reserve) begin
        error<=OK;
        need=(bytes/GRANULE)+((bytes%GRANULE)!=0);
        if(referenced[slot] || (|reserved) || table_d[slot].valid) begin done<=1;error<=E_BUSY;end
        else if(bytes==0 || need>GRANULES) begin done<=1;error<=E_CAPACITY;end
        else begin
          target_slot<=slot;target_owner<=owner;needed<=IDX'(need);
          pos<=cursor;run_length<=0;start_at<=cursor;examined<=0;searching<=1;
        end
      end else if(commit) begin
        done<=1;error<=OK;
        if(!reserved[slot] || table_d[slot].owner!=owner) error<=E_TAG;
        else if(frames==0 || frames>table_d[slot].capacity_bytes/2) error<=E_BOUNDS;
        else begin
          table_d[slot].frames<=frames;table_d[slot].gain_q16<=gain_q16;
          table_d[slot].crc32<=crc32;table_d[slot].valid<=1;reserved[slot]<=0;
        end
      end else if(abort_slot || free_slot) begin
        done<=1;error<=OK;
        if(referenced[slot]) error<=E_BUSY;
        else if(table_d[slot].owner!=owner) error<=E_TAG;
        else begin
          for(int j=0;j<GRANULES;j++) if(j>=first[slot] && j<first[slot]+count[slot]) used[j]<=0;
          table_d[slot]<='0;reserved[slot]<=0;count[slot]<=0;
        end
      end
    end
  end
endmodule
