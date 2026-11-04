#define HUD_TEST
#include "hud_scale.cpp"
#include <stdio.h>
static HudRect received;
static unsigned long receivedFlags;
static long __stdcall blt(void*,HudRect* rectangle,void*,HudRect*,unsigned long flags,void*) {
    received=*rectangle;receivedFlags=flags;return 123;
}
#define CHECK(condition) if (!(condition)) { printf("Failed line %d\n",__LINE__); return 1; }
int main() {
    void* table[6]={};table[5]=reinterpret_cast<void*>(blt);void** surface=table;
    HudRect input={10,20,50,100};
    CHECK(HudBlt(&surface,&input,nullptr,nullptr,7,nullptr)==123);
    CHECK(received.left==175 && received.top==30 && received.right==235 && received.bottom==150);
    CHECK(input.left==10 && input.top==20 && receivedFlags==7);
#ifdef HUD_EDGE_RIGHT
    HudRect rightPanel={500,20,600,100};
    HudBlt(&surface,&rightPanel,nullptr,nullptr,9,nullptr);
    CHECK(received.left==1070 && received.right==1220 && received.top==30);
    CHECK(rightPanel.left==500 && receivedFlags==9);
#endif
    testWidth=1280;testHeight=960;
    HudBlt(&surface,&input,nullptr,nullptr,0,nullptr);
    CHECK(received.left==20 && received.top==40 && received.right==100 && received.bottom==200);
    testWidth=720;testHeight=1280;
    HudBlt(&surface,&input,nullptr,nullptr,0,nullptr);
    CHECK(received.left==11 && received.top==392 && received.right==56 && received.bottom==482);
    testHud=2;
    HudBlt(&surface,&input,nullptr,nullptr,0,nullptr);
    CHECK(received.left==input.left && received.bottom==input.bottom);
    puts("HUD scaling: wide, 4:3, portrait, original rectangle and HRESULT passed.");
    return 0;
}
