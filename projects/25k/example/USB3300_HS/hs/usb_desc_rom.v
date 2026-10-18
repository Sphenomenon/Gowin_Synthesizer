//-----------------------------------------------------------------
//                       USB CDC Device
//                            V0.1
//                     Ultra-Embedded.com
//                     Copyright 2014-2019
//
//                 Email: admin@ultra-embedded.com
//
//                         License: LGPL
//-----------------------------------------------------------------
//
// This source file may be used and distributed without         
// restriction provided that this copyright statement is not    
// removed from the file and that any derivative work contains  
// the original copyright notice and the associated disclaimer. 
//
// This source file is free software; you can redistribute it   
// and/or modify it under the terms of the GNU Lesser General   
// Public License as published by the Free Software Foundation; 
// either version 2.1 of the License, or (at your option) any   
// later version.
//
// This source is distributed in the hope that it will be       
// useful, but WITHOUT ANY WARRANTY; without even the implied   
// warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR      
// PURPOSE.  See the GNU Lesser General Public License for more 
// details.
//
// You should have received a copy of the GNU Lesser General    
// Public License along with this source; if not, write to the 
// Free Software Foundation, Inc., 59 Temple Place, Suite 330, 
// Boston, MA  02111-1307  USA
//-----------------------------------------------------------------

//-----------------------------------------------------------------
//                          Generated File
//-----------------------------------------------------------------
// GW25K derived descriptor ROM. Offsets match usb_cdc_core.v.
// VID/PID FB9A:FB9B are retained only for local bring-up identification.
module usb_desc_rom
(
    input        hs_i,
    input        configured_i,
    input  [7:0] addr_i,
    output reg [7:0] data_o
);
always @ *
begin
    case (addr_i)
        8'd0: data_o = 8'h12;
        8'd1: data_o = 8'h01;
        8'd2: data_o = 8'h00;
        8'd3: data_o = 8'h02;
        8'd4: data_o = 8'h02;
        8'd5: data_o = 8'h00;
        8'd6: data_o = 8'h00;
        8'd7: data_o = hs_i ? 8'h40 : 8'h08;
        8'd8: data_o = 8'h9a;
        8'd9: data_o = 8'hfb;
        8'd10: data_o = 8'h9b;
        8'd11: data_o = 8'hfb;
        8'd12: data_o = 8'h00;
        8'd13: data_o = 8'h01;
        8'd14: data_o = 8'h01;
        8'd15: data_o = 8'h02;
        8'd16: data_o = 8'h03;
        8'd17: data_o = 8'h01;
        8'd18: data_o = 8'h09;
        8'd19: data_o = 8'h02;
        8'd20: data_o = 8'h43;
        8'd21: data_o = 8'h00;
        8'd22: data_o = 8'h02;
        8'd23: data_o = 8'h01;
        8'd24: data_o = 8'h00;
        8'd25: data_o = 8'h80;
        8'd26: data_o = 8'h32;
        8'd27: data_o = 8'h09;
        8'd28: data_o = 8'h04;
        8'd29: data_o = 8'h00;
        8'd30: data_o = 8'h00;
        8'd31: data_o = 8'h01;
        8'd32: data_o = 8'h02;
        8'd33: data_o = 8'h02;
        8'd34: data_o = 8'h01;
        8'd35: data_o = 8'h00;
        8'd36: data_o = 8'h05;
        8'd37: data_o = 8'h24;
        8'd38: data_o = 8'h00;
        8'd39: data_o = 8'h10;
        8'd40: data_o = 8'h01;
        8'd41: data_o = 8'h05;
        8'd42: data_o = 8'h24;
        8'd43: data_o = 8'h01;
        8'd44: data_o = 8'h03;
        8'd45: data_o = 8'h01;
        8'd46: data_o = 8'h04;
        8'd47: data_o = 8'h24;
        8'd48: data_o = 8'h02;
        8'd49: data_o = 8'h06;
        8'd50: data_o = 8'h05;
        8'd51: data_o = 8'h24;
        8'd52: data_o = 8'h06;
        8'd53: data_o = 8'h00;
        8'd54: data_o = 8'h01;
        8'd55: data_o = 8'h07;
        8'd56: data_o = 8'h05;
        8'd57: data_o = 8'h83;
        8'd58: data_o = 8'h03;
        8'd59: data_o = 8'h40;
        8'd60: data_o = 8'h00;
        8'd61: data_o = 8'h02;
        8'd62: data_o = 8'h09;
        8'd63: data_o = 8'h04;
        8'd64: data_o = 8'h01;
        8'd65: data_o = 8'h00;
        8'd66: data_o = 8'h02;
        8'd67: data_o = 8'h0a;
        8'd68: data_o = 8'h00;
        8'd69: data_o = 8'h00;
        8'd70: data_o = 8'h00;
        8'd71: data_o = 8'h07;
        8'd72: data_o = 8'h05;
        8'd73: data_o = 8'h01;
        8'd74: data_o = 8'h02;
        8'd75: data_o = hs_i ? 8'h00 : 8'h40;
        8'd76: data_o = hs_i ? 8'h02 : 8'h00;
        8'd77: data_o = 8'h00;
        8'd78: data_o = 8'h07;
        8'd79: data_o = 8'h05;
        8'd80: data_o = 8'h82;
        8'd81: data_o = 8'h02;
        8'd82: data_o = hs_i ? 8'h00 : 8'h40;
        8'd83: data_o = hs_i ? 8'h02 : 8'h00;
        8'd84: data_o = 8'h00;
        8'd85: data_o = 8'h04;
        8'd86: data_o = 8'h03;
        8'd87: data_o = 8'h09;
        8'd88: data_o = 8'h04;
        8'd89: data_o = 8'h0c;
        8'd90: data_o = 8'h03;
        8'd91: data_o = 8'h47;
        8'd92: data_o = 8'h00;
        8'd93: data_o = 8'h57;
        8'd94: data_o = 8'h00;
        8'd95: data_o = 8'h32;
        8'd96: data_o = 8'h00;
        8'd97: data_o = 8'h35;
        8'd98: data_o = 8'h00;
        8'd99: data_o = 8'h4b;
        8'd100: data_o = 8'h00;
        8'd101: data_o = 8'h1a;
        8'd102: data_o = 8'h03;
        8'd103: data_o = 8'h47;
        8'd104: data_o = 8'h00;
        8'd105: data_o = 8'h57;
        8'd106: data_o = 8'h00;
        8'd107: data_o = 8'h32;
        8'd108: data_o = 8'h00;
        8'd109: data_o = 8'h35;
        8'd110: data_o = 8'h00;
        8'd111: data_o = 8'h4b;
        8'd112: data_o = 8'h00;
        8'd113: data_o = 8'h2d;
        8'd114: data_o = 8'h00;
        8'd115: data_o = 8'h55;
        8'd116: data_o = 8'h00;
        8'd117: data_o = 8'h53;
        8'd118: data_o = 8'h00;
        8'd119: data_o = 8'h42;
        8'd120: data_o = 8'h00;
        8'd121: data_o = 8'h2d;
        8'd122: data_o = 8'h00;
        8'd123: data_o = 8'h48;
        8'd124: data_o = 8'h00;
        8'd125: data_o = 8'h53;
        8'd126: data_o = 8'h00;
        8'd127: data_o = 8'h14;
        8'd128: data_o = 8'h03;
        8'd129: data_o = 8'h47;
        8'd130: data_o = 8'h00;
        8'd131: data_o = 8'h57;
        8'd132: data_o = 8'h00;
        8'd133: data_o = 8'h32;
        8'd134: data_o = 8'h00;
        8'd135: data_o = 8'h35;
        8'd136: data_o = 8'h00;
        8'd137: data_o = 8'h4b;
        8'd138: data_o = 8'h00;
        8'd139: data_o = 8'h48;
        8'd140: data_o = 8'h00;
        8'd141: data_o = 8'h53;
        8'd142: data_o = 8'h00;
        8'd143: data_o = 8'h30;
        8'd144: data_o = 8'h00;
        8'd145: data_o = 8'h31;
        8'd146: data_o = 8'h00;
        8'd147: data_o = 8'h00;
        8'd148: data_o = 8'hc2;
        8'd149: data_o = 8'h01;
        8'd150: data_o = 8'h00;
        8'd151: data_o = 8'h00;
        8'd152: data_o = 8'h00;
        8'd153: data_o = 8'h08;
        8'd154: data_o = 8'h0a;
        8'd155: data_o = 8'h06;
        8'd156: data_o = 8'h00;
        8'd157: data_o = 8'h02;
        8'd158: data_o = 8'h02;
        8'd159: data_o = 8'h00;
        8'd160: data_o = 8'h00;
        8'd161: data_o = hs_i ? 8'h08 : 8'h40;
        8'd162: data_o = 8'h01;
        8'd163: data_o = 8'h00;
        8'd164: data_o = 8'h09;
        8'd165: data_o = 8'h07;
        8'd166: data_o = 8'h43;
        8'd167: data_o = 8'h00;
        8'd168: data_o = 8'h02;
        8'd169: data_o = 8'h01;
        8'd170: data_o = 8'h00;
        8'd171: data_o = 8'h80;
        8'd172: data_o = 8'h32;
        8'd173: data_o = 8'h09;
        8'd174: data_o = 8'h04;
        8'd175: data_o = 8'h00;
        8'd176: data_o = 8'h00;
        8'd177: data_o = 8'h01;
        8'd178: data_o = 8'h02;
        8'd179: data_o = 8'h02;
        8'd180: data_o = 8'h01;
        8'd181: data_o = 8'h00;
        8'd182: data_o = 8'h05;
        8'd183: data_o = 8'h24;
        8'd184: data_o = 8'h00;
        8'd185: data_o = 8'h10;
        8'd186: data_o = 8'h01;
        8'd187: data_o = 8'h05;
        8'd188: data_o = 8'h24;
        8'd189: data_o = 8'h01;
        8'd190: data_o = 8'h03;
        8'd191: data_o = 8'h01;
        8'd192: data_o = 8'h04;
        8'd193: data_o = 8'h24;
        8'd194: data_o = 8'h02;
        8'd195: data_o = 8'h06;
        8'd196: data_o = 8'h05;
        8'd197: data_o = 8'h24;
        8'd198: data_o = 8'h06;
        8'd199: data_o = 8'h00;
        8'd200: data_o = 8'h01;
        8'd201: data_o = 8'h07;
        8'd202: data_o = 8'h05;
        8'd203: data_o = 8'h83;
        8'd204: data_o = 8'h03;
        8'd205: data_o = 8'h40;
        8'd206: data_o = 8'h00;
        8'd207: data_o = 8'h02;
        8'd208: data_o = 8'h09;
        8'd209: data_o = 8'h04;
        8'd210: data_o = 8'h01;
        8'd211: data_o = 8'h00;
        8'd212: data_o = 8'h02;
        8'd213: data_o = 8'h0a;
        8'd214: data_o = 8'h00;
        8'd215: data_o = 8'h00;
        8'd216: data_o = 8'h00;
        8'd217: data_o = 8'h07;
        8'd218: data_o = 8'h05;
        8'd219: data_o = 8'h01;
        8'd220: data_o = 8'h02;
        8'd221: data_o = hs_i ? 8'h40 : 8'h00;
        8'd222: data_o = hs_i ? 8'h00 : 8'h02;
        8'd223: data_o = 8'h00;
        8'd224: data_o = 8'h07;
        8'd225: data_o = 8'h05;
        8'd226: data_o = 8'h82;
        8'd227: data_o = 8'h02;
        8'd228: data_o = hs_i ? 8'h40 : 8'h00;
        8'd229: data_o = hs_i ? 8'h00 : 8'h02;
        8'd230: data_o = 8'h00;
        8'd231: data_o = 8'h00;
        8'd232: data_o = 8'h00;
        8'd233: data_o = {7'b0, configured_i};
        8'd234: data_o = 8'h00;
        default: data_o = 8'h00;
    endcase
end
endmodule
