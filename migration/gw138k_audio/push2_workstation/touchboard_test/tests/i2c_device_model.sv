`timescale 1ns/1ps
module i2c_device_model #(parameter [6:0] ADDRESS=7'h0d, parameter CHECK_PROTOCOL=1)(
    inout wire scl,sda, input wire enabled
);
    reg drive=0;
    assign sda=drive ? 1'b0 : 1'bz;
    reg [7:0] mem[0:255];
    integer i;
    initial begin
      for(i=0;i<256;i=i+1) mem[i]=0;
      mem[0]=8'h11; mem[1]=8'h40; mem[2]=8'h80;
      for(i=0;i<16;i=i+1) begin
        mem[100+i*2]=(1000-i)&255; mem[101+i*2]=(1000-i)>>8;
        mem[132+i*2]=1000&255; mem[133+i*2]=1000>>8;
      end
    end
    reg active=0,selected=0,direction=0,address_phase=1,pointer_phase=0;
    reg [1:0] mode=0;
    integer bits=0;
    reg [7:0] shift=0,pointer=0,saved_pointer=0;
    time last_stop=0;
    integer stop_count=0;
    reg [6:0] slave_address=ADDRESS;
    // START and STOP are only valid while the physical SCL is high.
    always @(negedge sda) if(scl===1'b1) begin
      if(CHECK_PROTOCOL && active) $fatal(1,"QT2160 repeated START is unsupported");
      if(CHECK_PROTOCOL && last_stop!=0 && $time-last_stop < 500) $fatal(1,"STOP/START free interval too short");
      active=1; selected=0; direction=0; address_phase=1; pointer_phase=0;
      mode=0; bits=0; shift=0;
    end
    always @(posedge sda) if(scl===1'b1 && active) begin
      active=0; drive=0; pointer=saved_pointer;
      last_stop=$time; stop_count=stop_count+1;
    end
    always @(posedge scl) if(active) begin
      if(mode==0) begin
        if(bits<8) begin
          shift={shift[6:0],sda}; bits=bits+1;
          if(bits==8 && address_phase) begin selected=(shift[7:1]==slave_address && enabled); direction=shift[0]; end
        end else begin
          bits=0;
          if(address_phase) begin
            address_phase=0;
            if(selected && direction) mode=1;
            else pointer_phase=1;
          end else if(selected && pointer_phase) begin
            pointer=shift; saved_pointer=shift; pointer_phase=0;
          end else if(selected) begin
            mem[pointer]=shift;
            if(pointer==11 && shift!=0) begin
              for(i=10;i<80;i=i+1) mem[i]=0;
              mem[2][7]=1;
            end
            pointer=pointer+1'b1;
          end
          shift=0;
        end
      end else if(mode==1) begin
        bits=bits+1;
        if(bits==8) begin
          if(pointer==2) mem[2][7]=0;
          mode=2; bits=0;
        end
      end else if(mode==2) begin
        if(sda===0) begin pointer=pointer+1'b1; mode=1; bits=0; end
        else begin mode=3; end
      end
    end
    always @(negedge scl) if(active) begin
      if(mode==0) drive=(bits==8 && selected);
      else if(mode==1) drive=!mem[pointer][7-bits];
      else drive=0;
    end else drive=0;
endmodule
