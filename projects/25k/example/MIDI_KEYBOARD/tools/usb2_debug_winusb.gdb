set pagination off
set confirm off
set print thread-events off
set debuginfod enabled off
break *0x47d3b0
commands
silent
call ((void* (*)(void*,const char*))0x4ba900)((void*)$rdx,"Gowin USB Cable(WINUSB)")
continue
end
start
continue
