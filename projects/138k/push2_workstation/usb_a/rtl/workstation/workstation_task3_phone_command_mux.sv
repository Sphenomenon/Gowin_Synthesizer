`timescale 1ns/1ps
// W PCM1 and clock command CDC completion arbiter. Holds one complete caller
// until its remote response completes and that caller releases valid. It does
// not acknowledge a second caller or reorder PCM-window writes/descriptors.
module workstation_task3_phone_command_mux (
    input wire clk_i,reset_ni,
    input wire [1:0] valid_i,write_i,
    input wire [23:0] address_i,
    input wire [63:0] data_i,
    input wire [7:0] strobes_i,
    output wire [1:0] ready_o,
    output wire [1:0] response_error_o,
    output wire [63:0] response_data_o,
    output wire valid_o,target_o,write_o,
    output wire [11:0] address_o,
    output wire [31:0] data_o,
    output wire [3:0] strobes_o,
    input wire ready_i,response_error_i,
    input wire [31:0] response_data_i
);
    reg held,owner,completed,prefer_clock;
    reg held_write;
    reg [11:0] held_address;
    reg [31:0] held_data;
    reg [3:0] held_strobes;
    wire selected=valid_i==2'b11 ? prefer_clock:valid_i[1];
    assign valid_o=reset_ni && held && !completed;
    assign target_o=owner;
    assign write_o=held_write;
    assign address_o=held_address;
    assign data_o=held_data;
    assign strobes_o=held_strobes;
    assign ready_o=valid_o && ready_i?(owner?2'b10:2'b01):2'b00;
    assign response_error_o={2{response_error_i}};
    assign response_data_o={2{response_data_i}};
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            held<=0;owner<=0;completed<=0;prefer_clock<=0;
            held_write<=0;held_address<=0;held_data<=0;held_strobes<=0;
        end
        else if(!held)begin
            if(|valid_i)begin
                owner<=selected;held_write<=write_i[selected];
                held_address<=selected?address_i[23:12]:address_i[11:0];
                held_data<=selected?data_i[63:32]:data_i[31:0];
                held_strobes<=selected?strobes_i[7:4]:strobes_i[3:0];
                held<=1;completed<=0;
            end
        end else begin
            if(valid_o && ready_i)completed<=1;
            if(completed && !valid_i[owner])begin held<=0;completed<=0;prefer_clock<=!owner;end
        end
    end
endmodule
