// Keep the video reference PLL's two-cycle enable local to its helper.
// Merging it into the USB helper lengthened the video RESET path beyond 10 ns.
// This affects synthesis only; the official PLL_INIT source/sequence is unchanged.
INS "u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/enable_r" syn_preserve = 1;
