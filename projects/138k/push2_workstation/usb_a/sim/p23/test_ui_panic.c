#include <assert.h>
#include <stdio.h>
#include "ui_model.h"
int main(void) {
    ui_model model;
    ui_init(&model);
    assert(ui_touch(&model,ui_white_x(3)+10,500,1)&UI_CHANGED);
    assert(model.gate&&model.keyboard&&model.old_down);
    assert(ui_panic(&model,1)==UI_CHANGED);
    assert(!model.gate&&!model.keyboard&&model.panic_latched);
    assert(!ui_touch(&model,ui_white_x(4)+10,500,1)&&!model.gate);
    assert(!ui_touch(&model,0,0,0)&&!model.panic_latched);
    assert(ui_touch(&model,ui_white_x(4)+10,500,1)&UI_CHANGED);
    assert(model.gate&&model.keyboard);
    assert(ui_panic(&model,1)==0&&model.gate);
    assert(ui_panic(&model,2)==UI_CHANGED&&!model.gate&&!model.keyboard);
    puts("PASS PANIC UI: epoch clears local gate and blocks held touch until release");
    return 0;
}
