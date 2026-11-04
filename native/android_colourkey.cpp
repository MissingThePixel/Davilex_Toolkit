// Colour-key conversion for the hash-pinned DXWrapper v1.9.8700.25 only.
// Loaded for Wine/D3D9 engine processes. Other formats,
// resizing, palettes and unexpected results retain the original implementation.
#include <windows.h>
#include <d3d9.h>
#include <cstdio>
#include <cstdint>
#include <cstring>

using Convert=HRESULT(WINAPI*)(IDirect3DSurface9*,const PALETTEENTRY*,const RECT*,
    IDirect3DSurface9*,const PALETTEENTRY*,const RECT*,DWORD,D3DCOLOR);
static Convert original=nullptr;
static FILE* logFile=nullptr;
static bool enabled=false;
static volatile LONG calls=0,fastCalls=0;
static DWORD rgb565[65536];
static bool validatedBlack=false,validatedMagenta=false;
static bool lookupBlack=false,lookupMagenta=false;
struct Scratch {IDirect3DDevice9* device;IDirect3DSurface9* surface;UINT width,height;};
static Scratch scratch[96]={};
static uint64_t cachedBytes=0;
static volatile LONG ownerThread=0;
struct Signature{UINT sw,sh,dw,dh,sf,df;DWORD filter,key;};
static Signature signatures[96]={};static unsigned signatureCount=0;

static DWORD expand(unsigned value,unsigned mask){return (value*255+mask/2)/mask;}
static void tables(){
    for(unsigned v=0;v<65536;v++){
        rgb565[v]=0xff000000|(expand(v>>11,31)<<16)|(expand((v>>5)&63,63)<<8)|expand(v&31,31);
    }
}
struct SurfaceOwner{IDirect3DSurface9* value=nullptr;~SurfaceOwner(){if(value)value->Release();}};
static bool validateLookup(IDirect3DDevice9* device,DWORD key){
    SurfaceOwner source,destination;
    if(FAILED(device->CreateOffscreenPlainSurface(256,256,D3DFMT_R5G6B5,D3DPOOL_SYSTEMMEM,&source.value,nullptr))
       || FAILED(device->CreateOffscreenPlainSurface(256,256,D3DFMT_A8R8G8B8,D3DPOOL_SYSTEMMEM,&destination.value,nullptr)))return false;
    D3DLOCKED_RECT locked={};
    if(FAILED(source.value->LockRect(&locked,nullptr,0)))return false;
    for(unsigned y=0;y<256;y++){
        auto row=reinterpret_cast<WORD*>(static_cast<BYTE*>(locked.pBits)+y*locked.Pitch);
        for(unsigned x=0;x<256;x++)row[x]=static_cast<WORD>(y*256+x);
    }
    source.value->UnlockRect();
    if(FAILED(original(destination.value,nullptr,nullptr,source.value,nullptr,nullptr,1,key))
       || FAILED(destination.value->LockRect(&locked,nullptr,D3DLOCK_READONLY)))return false;
    unsigned differences=0;
    for(unsigned y=0;y<256;y++){
        auto row=reinterpret_cast<const DWORD*>(static_cast<const BYTE*>(locked.pBits)+y*locked.Pitch);
        for(unsigned x=0;x<256;x++){
            DWORD pixel=rgb565[y*256+x];
            if((pixel&0xffffff)==(key&0xffffff))pixel=0;
            if(row[x]!=pixel)differences++;
        }
    }
    destination.value->UnlockRect();
    if(logFile){std::fprintf(logFile,"exhaustive key=%08lx colours=65536 differences=%u\n",key,differences);std::fflush(logFile);}
    return differences==0;
}
static bool rectangle(const RECT* requested,const D3DSURFACE_DESC& desc,RECT& result){
    result=requested?*requested:RECT{0,0,static_cast<LONG>(desc.Width),static_cast<LONG>(desc.Height)};
    return result.left>=0 && result.top>=0 && result.right>result.left && result.bottom>result.top
        && result.right<=static_cast<LONG>(desc.Width) && result.bottom<=static_cast<LONG>(desc.Height);
}
static HRESULT WINAPI convert(IDirect3DSurface9* dst,const PALETTEENTRY* dp,const RECT* dr,
    IDirect3DSurface9* src,const PALETTEENTRY* sp,const RECT* sr,DWORD filter,D3DCOLOR key){
    LONG thread=static_cast<LONG>(GetCurrentThreadId());
    InterlockedCompareExchange(&ownerThread,thread,0);
    if(ownerThread!=thread)return original(dst,dp,dr,src,sp,sr,filter,key);
    LONG number=InterlockedIncrement(&calls);
    D3DSURFACE_DESC sd={},dd={};
    bool described=src && dst && SUCCEEDED(src->GetDesc(&sd)) && SUCCEEDED(dst->GetDesc(&dd));
    Signature signature={sd.Width,sd.Height,dd.Width,dd.Height,static_cast<UINT>(sd.Format),static_cast<UINT>(dd.Format),filter,key};
    bool newSignature=true;
    for(unsigned i=0;i<signatureCount;i++)if(!std::memcmp(&signatures[i],&signature,sizeof(signature))){newSignature=false;break;}
    if(newSignature && signatureCount<96)signatures[signatureCount++]=signature;
    if((number<=12 || (newSignature && signatureCount<96)) && logFile){
        std::fprintf(logFile,"call=%ld src=%ux%u format=%u pool=%u dst=%ux%u format=%u pool=%u filter=%lx key=%08lx palettes=%d,%d enabled=%d\n",
            number,sd.Width,sd.Height,sd.Format,sd.Pool,dd.Width,dd.Height,dd.Format,dd.Pool,filter,key,sp!=nullptr,dp!=nullptr,enabled);
        std::fflush(logFile);
    }
    const DWORD* table=sd.Format==D3DFMT_R5G6B5?rgb565:nullptr;
    RECT s={},d={};
    if(!enabled || !described || !table || dp || sp || (filter&0xffff)!=1 || (filter&0xffff0000)
       || dd.Format!=D3DFMT_A8R8G8B8 || !rectangle(sr,sd,s) || !rectangle(dr,dd,d)
       || s.right-s.left!=d.right-d.left || s.bottom-s.top!=d.bottom-d.top)
        return original(dst,dp,dr,src,sp,sr,filter,key);
    // Initially cover only the actually observed format/key pairs. Compare each
    // pair against the original implementation before allowing accelerated use.
    if(sd.Format!=D3DFMT_R5G6B5 || (key!=0xff000000 && key!=0xffff00ff))
        return original(dst,dp,dr,src,sp,sr,filter,key);
    IDirect3DDevice9* device=nullptr;
    if(FAILED(dst->GetDevice(&device)))return original(dst,dp,dr,src,sp,sr,filter,key);
    bool* checked=key==0xff000000?&lookupBlack:&lookupMagenta;
    if(!*checked){
        *checked=validateLookup(device,key);
        if(!*checked){enabled=false;device->Release();return original(dst,dp,dr,src,sp,sr,filter,key);}
    }
    UINT width=s.right-s.left,height=s.bottom-s.top;
    IDirect3DSurface9* staging=nullptr;
    for(auto& entry:scratch){
        if(entry.surface && entry.device==device && entry.width==width && entry.height==height){staging=entry.surface;break;}
    }
    const uint64_t bytes=static_cast<uint64_t>(width)*height*4;
    if(!staging && cachedBytes+bytes<=16*1024*1024)for(auto& entry:scratch){
        if(!entry.surface){
            if(SUCCEEDED(device->CreateOffscreenPlainSurface(width,height,D3DFMT_A8R8G8B8,D3DPOOL_SYSTEMMEM,&entry.surface,nullptr))){
                entry.device=device;entry.width=width;entry.height=height;staging=entry.surface;cachedBytes+=bytes;
            }
            break;
        }
    }
    // Each cached surface retains its device. The process-scoped cache is bounded
    // to 16 MiB and ends with this engine process; no pointers cross race launches.
    device->Release();
    if(!staging)return original(dst,dp,dr,src,sp,sr,filter,key);
    bool* verified=key==0xff000000?&validatedBlack:&validatedMagenta;
    bool validation=!*verified;
    HRESULT reference=S_OK;
    if(validation){reference=original(staging,nullptr,nullptr,src,sp,&s,filter,key);if(FAILED(reference))return original(dst,dp,dr,src,sp,sr,filter,key);}
    D3DLOCKED_RECT sl={},dl={};
    HRESULT sourceLock=src->LockRect(&sl,&s,D3DLOCK_READONLY);
    if(FAILED(sourceLock)){
        if(number<=12 && logFile){std::fprintf(logFile,"source_lock_failed=%08lx\n",sourceLock);std::fflush(logFile);}
        return original(dst,dp,dr,src,sp,sr,filter,key);
    }
    HRESULT destinationLock=staging->LockRect(&dl,nullptr,validation?D3DLOCK_READONLY:0);
    if(FAILED(destinationLock)){
        if(number<=12 && logFile){std::fprintf(logFile,"destination_lock_failed=%08lx\n",destinationLock);std::fflush(logFile);}
        src->UnlockRect();return original(dst,dp,dr,src,sp,sr,filter,key);
    }
    unsigned differences=0;DWORD firstActual=0,firstExpected=0;
    for(LONG y=0;y<s.bottom-s.top;y++){
        auto input=reinterpret_cast<const WORD*>(static_cast<const BYTE*>(sl.pBits)+static_cast<ptrdiff_t>(y)*sl.Pitch);
        auto output=reinterpret_cast<DWORD*>(static_cast<BYTE*>(dl.pBits)+static_cast<ptrdiff_t>(y)*dl.Pitch);
        for(LONG x=0;x<s.right-s.left;x++){
            DWORD pixel=table[input[x]];
            if(key && (pixel&0xffffff)==(key&0xffffff))pixel=0;
            if(validation){if(output[x]!=pixel){if(!differences){firstActual=output[x];firstExpected=pixel;}differences++;}}
            else output[x]=pixel;
        }
    }
    HRESULT result=staging->UnlockRect();src->UnlockRect();
    if(validation){
        *verified=differences==0;
        if(differences)enabled=false;
        if(logFile){std::fprintf(logFile,"validation key=%08lx pixels=%ld differences=%u actual=%08lx expected=%08lx enabled=%d\n",key,(s.right-s.left)*(s.bottom-s.top),differences,firstActual,firstExpected,enabled);std::fflush(logFile);}
        if(differences)return original(dst,dp,dr,src,sp,sr,filter,key);
    }
    POINT position={d.left,d.top};
    result=device->UpdateSurface(staging,nullptr,dst,&position);
    if(FAILED(result))return original(dst,dp,dr,src,sp,sr,filter,key);
    InterlockedIncrement(&fastCalls);
    if(number<=12 && logFile){std::fprintf(logFile,"fast=%ld result=%08lx\n",fastCalls,result);std::fflush(logFile);}
    return result;
}
static DWORD WINAPI install(void*){
    wchar_t flag[8]={};GetEnvironmentVariableW(L"DAVILEX_COLOURKEY_DIAGNOSTIC",flag,8);
    if(flag[0]==L'1')logFile=std::fopen("davilex-colourkey.log","w");
    flag[0]=0;GetEnvironmentVariableW(L"DAVILEX_FAST_COLOURKEY",flag,8);enabled=flag[0]!=L'0';
    if(!enabled){if(logFile){std::fputs("disabled; original conversion unmodified\n",logFile);std::fflush(logFile);}return 0;}
    HMODULE pinned=nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&convert),&pinned);
    tables();
    for(unsigned i=0;i<10000;i++){
        HMODULE module=GetModuleHandleW(L"dxwrapper.dll");
        if(module){
            auto base=reinterpret_cast<BYTE*>(module);
            auto dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);
            auto nt=reinterpret_cast<IMAGE_NT_HEADERS*>(base+dos->e_lfanew);
            if(dos->e_magic!=IMAGE_DOS_SIGNATURE || nt->Signature!=IMAGE_NT_SIGNATURE
               || nt->FileHeader.TimeDateStamp!=0x6acc2be1 || nt->OptionalHeader.SizeOfImage!=0x7e9000
               || base[0x17135e]!=0xff || base[0x17135f]!=0xd0){
                if(logFile){std::fputs("Unsupported wrapper; no hook installed.\n",logFile);std::fflush(logFile);}return 1;
            }
            auto slot=reinterpret_cast<PVOID volatile*>(base+0x771964);
            PVOID value=InterlockedCompareExchangePointer(slot,nullptr,nullptr);
            if(value){
                original=reinterpret_cast<Convert>(value);
                InterlockedCompareExchangePointer(slot,reinterpret_cast<PVOID>(convert),value);
                if(logFile){std::fprintf(logFile,"installed enabled=%d original=%p\n",enabled,value);std::fflush(logFile);}
                return 0;
            }
        }
        Sleep(1);
    }
    if(logFile){std::fputs("D3DX entry did not initialize; no hook installed.\n",logFile);std::fflush(logFile);}
    return 2;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID){
    if(reason==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(instance);HANDLE worker=CreateThread(nullptr,0,install,nullptr,0,nullptr);if(worker)CloseHandle(worker);}
    return TRUE;
}
