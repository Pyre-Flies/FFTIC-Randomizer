// Exact-build, transactional startup patches for tables absent from FFTIC's loader.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <stdexcept>
#include <algorithm>
#pragma comment(lib,"bcrypt.lib")

static HMODULE module_handle;
static FILE* log_file;
static void log(const std::string& text) {
    const std::string line="[fftivc.randomizer.native] "+text+"\n";
    if(log_file) { fputs(line.c_str(),log_file); fflush(log_file); }
    OutputDebugStringA(line.c_str());
}
static std::wstring module_path(HMODULE module) {
    std::vector<wchar_t> buffer(32768);
    auto n=GetModuleFileNameW(module,buffer.data(),static_cast<DWORD>(buffer.size()));
    if(!n || n>=buffer.size()) throw std::runtime_error("Cannot resolve module path");
    return std::wstring(buffer.data(),n);
}
static std::vector<uint8_t> read_file(const std::wstring& path) {
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,
                           nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot open patch input");
    LARGE_INTEGER size{};
    if(!GetFileSizeEx(file,&size) || size.QuadPart<=0 || size.QuadPart>128*1024*1024) {
        CloseHandle(file); throw std::runtime_error("Invalid patch input size");
    }
    std::vector<uint8_t> result(static_cast<size_t>(size.QuadPart)); DWORD got=0;
    bool ok=ReadFile(file,result.data(),static_cast<DWORD>(result.size()),&got,nullptr)!=FALSE;
    CloseHandle(file);
    if(!ok || got!=result.size()) throw std::runtime_error("Incomplete patch input read");
    return result;
}
static std::vector<uint8_t> sha256(const std::vector<uint8_t>& data) {
    BCRYPT_ALG_HANDLE algorithm=nullptr; BCRYPT_HASH_HANDLE hash=nullptr;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)
        throw std::runtime_error("Cannot initialize build hash");
    std::vector<uint8_t> result(32);
    NTSTATUS status=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0);
    if(status>=0) status=BCryptHashData(hash,const_cast<PUCHAR>(data.data()),static_cast<ULONG>(data.size()),0);
    if(status>=0) status=BCryptFinishHash(hash,result.data(),32,0);
    if(hash) BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm,0);
    if(status<0) throw std::runtime_error("Cannot verify build hash");
    return result;
}
struct Reader {
    const std::vector<uint8_t>& data; size_t offset=0;
    const uint8_t* take(size_t n) {
        if(offset>data.size() || n>data.size()-offset) throw std::runtime_error("Truncated patch payload");
        const auto* p=data.data()+offset; offset+=n; return p;
    }
    uint32_t number() { uint32_t v; memcpy(&v,take(4),4); return v; }
};
struct Patch { uint32_t rva,size; std::string name; const uint8_t* expected; const uint8_t* changed; };
struct Page { uint8_t* address; SIZE_T size; DWORD protection; bool writable=false; };
static void apply() {
    auto own=module_path(module_handle); auto slash=own.find_last_of(L"\\/");
    const auto directory=own.substr(0,slash+1);
    _wfopen_s(&log_file,(directory+L"runtime-patches.log").c_str(),L"wb");
    log("Starting process "+std::to_string(GetCurrentProcessId()));
    const auto bytes=read_file(directory+L"runtime-patches.bin"); Reader input{bytes};
    if(memcmp(input.take(8),"FFTICRCC",8)!=0 || input.number()!=1)
        throw std::runtime_error("Unsupported patch payload");
    const auto count=input.number();
    if(count>4096) throw std::runtime_error("Too many patch records");
    const auto* digest=input.take(32);
    const auto timestamp=input.number(), image_size=input.number();
    HMODULE main=GetModuleHandleW(nullptr); auto* base=reinterpret_cast<uint8_t*>(main);
    const auto executable=module_path(main);
    if(_wcsicmp(executable.substr(executable.find_last_of(L"\\/")+1).c_str(),L"FFT_enhanced.exe")!=0)
        throw std::runtime_error("Unsupported executable");
    auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    auto* pe=reinterpret_cast<IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE || pe->Signature!=IMAGE_NT_SIGNATURE ||
       pe->FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64 ||
       pe->FileHeader.TimeDateStamp!=timestamp || pe->OptionalHeader.SizeOfImage!=image_size)
        throw std::runtime_error("Game image identity differs");
    if(memcmp(sha256(read_file(executable)).data(),digest,32)!=0)
        throw std::runtime_error("Game executable hash differs");
    std::vector<Patch> patches;
    for(uint32_t i=0;i<count;i++) {
        Patch p{}; p.rva=input.number(); p.size=input.number(); const auto length=input.number();
        if(!p.size || p.size>4*1024*1024 || length>256 || p.rva>=image_size || p.size>image_size-p.rva)
            throw std::runtime_error("Patch range is outside the game image");
        p.name=std::string(reinterpret_cast<const char*>(input.take(length)),length);
        p.expected=input.take(p.size); p.changed=input.take(p.size);
        for(const auto& previous:patches)
            if(p.rva<previous.rva+previous.size && previous.rva<p.rva+p.size)
                throw std::runtime_error("Overlapping patch records");
        patches.push_back(p);
    }
    if(input.offset!=bytes.size()) throw std::runtime_error("Unexpected trailing patch bytes");
    for(const auto& p:patches) {
        std::vector<uint8_t> current(p.size); SIZE_T got=0;
        if(!ReadProcessMemory(GetCurrentProcess(),base+p.rva,current.data(),p.size,&got) || got!=p.size ||
           memcmp(current.data(),p.expected,p.size)!=0)
            throw std::runtime_error("Original bytes differ for "+p.name);
    }
    SYSTEM_INFO info{}; GetSystemInfo(&info);
    if(!info.dwPageSize) throw std::runtime_error("Cannot resolve memory page size");
    std::vector<Page> pages;
    for(const auto& p:patches) {
        const auto first=reinterpret_cast<uintptr_t>(base+p.rva);
        const auto last=first+p.size;
        for(auto at=first-first%info.dwPageSize;at<last;at+=info.dwPageSize) {
            auto* address=reinterpret_cast<uint8_t*>(at);
            if(std::any_of(pages.begin(),pages.end(),[address](const Page& page){return page.address==address;})) continue;
            MEMORY_BASIC_INFORMATION region{};
            if(VirtualQuery(address,&region,sizeof(region))!=sizeof(region) || region.State!=MEM_COMMIT)
                throw std::runtime_error("Patch page is unavailable");
            pages.push_back({address,info.dwPageSize,region.Protect,false});
        }
    }
    auto restore_pages=[&pages]() {
        bool success=true;
        for(auto i=pages.rbegin();i!=pages.rend();++i) {
            if(!i->writable) continue;
            DWORD ignored=0;
            if(VirtualProtect(i->address,i->size,i->protection,&ignored)) i->writable=false;
            else success=false;
        }
        return success;
    };
    for(auto& page:pages) {
        DWORD previous=0;
        if(!VirtualProtect(page.address,page.size,PAGE_EXECUTE_READWRITE,&previous)) {
            const bool restored=restore_pages();
            throw std::runtime_error(restored ? "Cannot protect patch pages; no bytes changed" :
                                     "Cannot protect/restore pages; no bytes changed, restart required");
        }
        page.protection=previous; page.writable=true;
    }
    auto rollback=[&]() {
        bool writable=true;
        for(auto& page:pages) {
            DWORD ignored=0;
            if(VirtualProtect(page.address,page.size,PAGE_EXECUTE_READWRITE,&ignored)) page.writable=true;
            else writable=false;
        }
        bool flushed=true;
        if(writable) {
            for(const auto& p:patches) memcpy(base+p.rva,p.expected,p.size);
            for(const auto& p:patches)
                if(!FlushInstructionCache(GetCurrentProcess(),base+p.rva,p.size)) flushed=false;
        }
        const bool restored=restore_pages();
        return writable && flushed && restored;
    };
    bool flushed=true;
    for(const auto& p:patches) {
        memcpy(base+p.rva,p.changed,p.size);
        if(!FlushInstructionCache(GetCurrentProcess(),base+p.rva,p.size)) flushed=false;
        log("Applied "+p.name+" ("+std::to_string(p.size)+" bytes, RVA "+std::to_string(p.rva)+")");
    }
    const bool restored=restore_pages();
    if(!flushed || !restored) {
        const bool reverted=rollback();
        throw std::runtime_error(reverted ? "Cache/protection check failed; original bytes and protections restored" :
                                 "Cache/protection check failed; changes may remain, restart required");
    }
    log("PASS: "+std::to_string(patches.size())+" guarded patch ranges applied");
}
extern "C" __declspec(dllexport) void Init() {
    try { apply(); }
    catch(const std::exception& error) { log(std::string("FAILED: ")+error.what()); }
    if(log_file) { fclose(log_file); log_file=nullptr; }
}
extern "C" __declspec(dllexport) bool ReloadedCanUnload() { return false; }
extern "C" __declspec(dllexport) bool ReloadedCanSuspend() { return false; }
BOOL APIENTRY DllMain(HMODULE module,DWORD reason,LPVOID) {
    // /MT needs CRT thread attach/detach notifications.
    if(reason==DLL_PROCESS_ATTACH) module_handle=module;
    return TRUE;
}
