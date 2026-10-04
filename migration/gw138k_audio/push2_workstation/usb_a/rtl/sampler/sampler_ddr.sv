`timescale 1ns/1ps
`include "ddr_address_map.vh"
// Same clock as clients. A top-level CDC bridge must transfer the entire command.
// The outer DDR arbiter MUST return these tags on write completion as well as reads.
module sampler_ddr #(parameter integer CLIENTS=3, MAX_WAIT=18)(
  input logic clk,rst_n,restart,
  input logic [CLIENTS-1:0] valid,write,
  input logic [31:0] address[CLIENTS],base[CLIENTS],capacity[CLIENTS],
  input logic [255:0] data[CLIENTS],
  output logic [CLIENTS-1:0] ready,response,
  output logic [255:0] response_data,
  output logic [7:0] response_error,
  output logic req_valid,req_write,
  input logic req_ready,
  output logic [28:0] req_addr,
  output logic [255:0] req_data,
  output logic [15:0] req_tag,
  input logic rsp_valid,
  input logic [15:0] rsp_tag,
  input logic [255:0] rsp_data,
  output logic [31:0] max_latency,beats,stale_responses,
  output logic [7:0] fault
);
  import sampler_pkg::*;
  logic busy,sent,killed,timed_out,checking;
  logic [31:0] checked_address,checked_base,checked_capacity;
  logic [7:0] epoch;
  logic [5:0] serial;
  integer cursor,selected,client,age;
  logic legal;
  always_comb begin
    ready='0;selected=-1;
    if(!busy && !restart) begin
      for(int k=0;k<CLIENTS;k++) if(valid[(cursor+k)%CLIENTS] && selected<0)
        selected=(cursor+k)%CLIENTS;
      if(selected>=0) ready[selected]=1;
    end
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin
      busy<=0;sent<=0;killed<=0;timed_out<=0;epoch<=0;serial<=0;cursor<=0;client<=0;age<=0;
      checking<=0;checked_address<=0;checked_base<=0;checked_capacity<=0;req_valid<=0;req_write<=0;req_addr<=0;req_data<=0;req_tag<=0;
      response<=0;response_data<=0;response_error<=0;max_latency<=0;beats<=0;stale_responses<=0;fault<=0;
    end else begin
      response<='0;
      if(busy) begin
        age<=age+1;
        if(age>MAX_WAIT && !timed_out) begin fault<=E_TIMEOUT;timed_out<=1;end
      end
      if(restart) begin
        epoch<=epoch+1'b1;
        if(busy && sent) killed<=1;
        else if(busy && req_valid && req_ready) begin sent<=1;req_valid<=0;killed<=1;end
        else begin busy<=0;checking<=0;req_valid<=0;end
      end else if(!busy && selected>=0) begin
        client<=selected;cursor<=(selected+1)%CLIENTS;
        busy<=1;sent<=0;killed<=0;timed_out<=0;age<=0;checking<=1;
        checked_address<=address[selected];checked_base<=base[selected];checked_capacity<=capacity[selected];
        req_write<=write[selected];req_addr<=address[selected][30:2];
        req_data<=data[selected];req_tag<={2'(selected),epoch,serial};serial<=serial+1'b1;
      end else if(checking) begin
        checking<=0;
        legal=(checked_address[4:0]==0 && checked_base[4:0]==0 && checked_capacity>=32 &&
          checked_address>=checked_base &&
          {1'b0,checked_address}+33'd32<={1'b0,checked_base}+{1'b0,checked_capacity} &&
          checked_base>=`PRJ1_DDR_GROWTH_POOL_BYTE_BASE &&
          {1'b0,checked_base}+{1'b0,checked_capacity}<={1'b0,`PRJ1_DDR_GROWTH_POOL_BYTE_LAST}+1);
        if(!legal) begin response[client]<=1;response_error<=E_BOUNDS;fault<=E_BOUNDS;busy<=0;end
        else req_valid<=1;
      end else if(req_valid && req_ready) begin req_valid<=0;sent<=1;end
      if(rsp_valid) begin
        if(busy && (sent || (req_valid && req_ready)) && rsp_tag==req_tag) begin
          if(!killed && !restart) begin
            response[client]<=1;response_data<=rsp_data;response_error<=timed_out ? E_TIMEOUT : OK;
            if(age+1>max_latency) max_latency<=age+1;
          end else stale_responses<=stale_responses+1;
          busy<=0;sent<=0;req_valid<=0;beats<=beats+1;
        end else begin stale_responses<=stale_responses+1;fault<=E_TAG;end
      end
    end
  end
endmodule
