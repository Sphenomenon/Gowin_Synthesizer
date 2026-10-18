#ifndef GW138K_UI_RENDER_H
#define GW138K_UI_RENDER_H
#include <stdint.h>
#include "ui_model.h"
void ui_render(volatile uint32_t *frame,const ui_model *model,unsigned touch_attached);
void ui_patch(volatile uint32_t *frame,const ui_model *old,const ui_model *next,unsigned old_touch,unsigned next_touch);
#endif
