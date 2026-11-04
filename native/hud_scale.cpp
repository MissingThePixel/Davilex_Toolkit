// Build-specific A2IV probe. No external calls/data relocations in the injected code.
struct HudRect { long left,top,right,bottom; };
typedef long (__stdcall *SurfaceBlt)(void*,HudRect*,void*,HudRect*,unsigned long,void*);
#ifdef HUD_RECORD
#include <intrin.h>
#pragma intrinsic(_ReturnAddress)
#endif
#ifdef HUD_TEST
static int testWidth=1280,testHeight=720,testHud=1;
#define WIDTH testWidth
#define HEIGHT testHeight
#define HUD_INDEX testHud
#elif defined(HUD_CUSTOM)
#define WIDTH (*reinterpret_cast<volatile int*>(HUD_WIDTH_ADDRESS))
#define HEIGHT (*reinterpret_cast<volatile int*>(HUD_HEIGHT_ADDRESS))
#define HUD_INDEX 1
#else
#define WIDTH (*reinterpret_cast<volatile int*>(0x5b3798))
#define HEIGHT (*reinterpret_cast<volatile int*>(0x5b379c))
#define HUD_INDEX (*reinterpret_cast<volatile int*>(0x6fb890))
#endif

extern "C" long __stdcall HudBlt(void* surface,HudRect* rectangle,void* source,
                                HudRect* sourceRectangle,unsigned long flags,void* effects) {
    HudRect scaled;
#ifdef HUD_RECORD
    const HudRect* input=rectangle;
#endif
    const int width=WIDTH,height=HEIGHT;
    bool enabled=true;
#ifdef HUD_ACTIVE_ADDRESS
    enabled=(*reinterpret_cast<volatile int*>(HUD_ACTIVE_ADDRESS)!=0);
#endif
    if (enabled && rectangle && HUD_INDEX==1 && width>=320 && width<=8192 && height>=200 && height<=8192) {
        // Preserve the 640x480 artwork's proportions inside a centred safe area.
        const bool wide=width*480>=height*640;
        const int numerator=wide?height:width,denominator=wide?480:640;
        int x=(width-640*numerator/denominator)/2;
#ifdef HUD_EDGE_RIGHT
        // These adapters are enabled only inside draw_dashboard. The right
        // instrument panel starts beyond x=400 in the 640-wide design.
        // Central game prompts keep their safe-area position.
        if (rectangle->left>=400) x*=2;
#endif
        const int y=(height-480*numerator/denominator)/2;
        scaled.left=x+rectangle->left*numerator/denominator;
        scaled.right=x+rectangle->right*numerator/denominator;
        scaled.top=y+rectangle->top*numerator/denominator;
        scaled.bottom=y+rectangle->bottom*numerator/denominator;
        rectangle=&scaled;
    }
#ifdef HUD_RECORD
    volatile unsigned long* records=reinterpret_cast<volatile unsigned long*>(0x752400);
    unsigned long slot=records[0]++ & 31;
    volatile unsigned long* row=records+1+slot*10;
    row[0]=reinterpret_cast<unsigned long>(_ReturnAddress());
    row[1]=input?input->right-input->left:0;
    row[2]=input?input->bottom-input->top:0;
    row[3]=sourceRectangle?sourceRectangle->right-sourceRectangle->left:0;
    row[4]=sourceRectangle?sourceRectangle->bottom-sourceRectangle->top:0;
    row[5]=rectangle?rectangle->right-rectangle->left:0;
    row[6]=rectangle?rectangle->bottom-rectangle->top:0;
    row[7]=reinterpret_cast<unsigned long>(surface);
    row[8]=input?input->left:0;
    row[9]=input?input->top:0;
#endif
    SurfaceBlt original=reinterpret_cast<SurfaceBlt>((*reinterpret_cast<void***>(surface))[5]);
    return original(surface,rectangle,source,sourceRectangle,flags,effects);
}
