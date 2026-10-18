puts "PROBE_START"
puts [info commands *project*]
puts [info commands *option*]
puts [info commands *device*]
foreach cmd {{create_project -help} {set_device -help} {set_option -help} {run -help}} {
 catch {eval $cmd} result
 puts "$cmd -> $result"
}
puts "PROBE_END"
exit
