#ifndef GW138K_UI_RENDER_H
#define GW138K_UI_RENDER_H
#include <stdint.h>
#include "ui_model.h"
enum { UI_FRAME_ROWS=1080, UI_FRAME_WORDS_PER_ROW=960 };
void ui_render(volatile uint32_t *frame,const ui_model *model,unsigned touch_attached);
void ui_patch(volatile uint32_t *frame,const ui_model *old,const ui_model *next,unsigned old_touch,unsigned next_touch);
/* Physical row slices. Clamp to the page, do nothing for an empty range.
 * The service owner holds an immutable model and an exclusively owned back
 * page across all slices; publish only after the final slice and a fence. */
void ui_render_rows(volatile uint32_t *frame,const ui_model *model,unsigned touch_attached,unsigned first_row,unsigned row_count);
void ui_patch_rows(volatile uint32_t *frame,const ui_model *old,const ui_model *next,unsigned old_touch,unsigned next_touch,unsigned first_row,unsigned row_count);
#endif
