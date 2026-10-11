/* Native Windows engine/host seam. This is linked into the engine PE module;
 * the host owns memory histories, continuations, I/O histories and transport. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <io.h>
#include "lua.h"
#include "lauxlib.h"

#define HOST __declspec(dllimport)
HOST void *bako_host_malloc(size_t);
HOST void *bako_host_realloc(void *, size_t);
HOST int bako_host_free(void *);
HOST void bako_host_open(void *, const char *, const char *);
HOST int bako_host_close(void *);
HOST int bako_host_checkpoint(int);
HOST int bako_host_live(void);
HOST void bako_host_publish(const char *,size_t,const char *,size_t);
HOST void bako_host_park(void);
HOST long long bako_host_now(void);
HOST void bako_host_stats(char *,size_t);
HOST void bako_host_timings(long long *);
HOST void bako_host_io(const void *,size_t);
extern void bako_source_enable(int);
extern void bako_source_register(const char *,int);
extern int bako_source_length(int);
extern void bako_sources_refresh(void);
extern void bako_set_boundary(void (*)(void));
extern int bako_write_font_bundle(FILE *,const int *,int);
extern void *static_pdf;
extern void pdf_flush(void *);
static lua_State *boundary_lua;
static long long capture_offset;

void *__real_malloc(size_t);
void *__real_realloc(void *,size_t);
void __real_free(void *);
FILE *__real_fopen(const char *,const char *);
int __real_fclose(FILE *);
size_t __real_fread(void *,size_t,size_t,FILE *);
size_t __real_fwrite(const void *,size_t,size_t,FILE *);
int __real__read(int,void *,unsigned);
int __real__write(int,const void *,unsigned);
int __wrap__read(int fd,void *p,unsigned size) {bako_host_io(p,size);return __real__read(fd,p,size);}
int __wrap__write(int fd,const void *p,unsigned size) {bako_host_io(p,size);return __real__write(fd,p,size);}
int __wrap_read(int fd,void *p,unsigned size) {return __wrap__read(fd,p,size);}
int __wrap_write(int fd,const void *p,unsigned size) {return __wrap__write(fd,p,size);}
size_t __wrap_fread(void *p,size_t size,size_t count,FILE *file) {
    if(size && count>SIZE_MAX/size)return 0;
    bako_host_io(p,size*count);return __real_fread(p,size,count,file);
}
size_t __wrap_fwrite(const void *p,size_t size,size_t count,FILE *file) {
    if(size && count>SIZE_MAX/size)return 0;
    bako_host_io(p,size*count);return __real_fwrite(p,size,count,file);
}

void *__wrap_malloc(size_t size) { return bako_host_malloc(size); }
void *__wrap_calloc(size_t count,size_t size) {
    if(size && count>SIZE_MAX/size)return NULL;
    void *p=bako_host_malloc(count*size);if(p)memset(p,0,count*size);return p;
}
void __wrap_free(void *p) { if(p&&!bako_host_free(p))__real_free(p); }
void *__wrap_realloc(void *p,size_t size) {
    /* Engine-owned allocations use the host heap. CRT-owned return values are
     * normalized by the string/path wrappers below. */
    return bako_host_realloc(p,size);
}
char *__wrap_strdup(const char *text) {
    size_t n=strlen(text)+1;char *p=bako_host_malloc(n);if(p)memcpy(p,text,n);return p;
}
char *__wrap__strdup(const char *text) { return __wrap_strdup(text); }
static wchar_t *wide(const char *text) {
    int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,NULL,0);
    if(!n)return NULL;
    wchar_t *p=__real_malloc((size_t)n*sizeof(wchar_t));
    if(p)MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,p,n);return p;
}
FILE *__wrap_fopen(const char *path,const char *mode) {
    wchar_t *p=wide(path),*m=wide(mode);
    FILE *file=p&&m?_wfopen(p,m):NULL;
    __real_free(p);__real_free(m);
    if(file)bako_host_open(file,path,mode);return file;
}
int __wrap_fclose(FILE *file) { return bako_host_close(file)?0:__real_fclose(file); }
char *__wrap__fullpath(char *buffer,const char *path,size_t count) {
    wchar_t *p=wide(path);
    if(!p)return NULL;
    DWORD n=GetFullPathNameW(p,0,NULL,NULL);
    wchar_t *full=__real_malloc(((size_t)n+1)*sizeof(wchar_t));
    if(!full||!GetFullPathNameW(p,n+1,full,NULL)){__real_free(p);__real_free(full);return NULL;}
    int bytes=WideCharToMultiByte(CP_UTF8,0,full,-1,NULL,0,NULL,NULL);
    if(!buffer)buffer=bako_host_malloc((size_t)bytes);
    else if(count<(size_t)bytes){__real_free(p);__real_free(full);return NULL;}
    if(buffer)WideCharToMultiByte(CP_UTF8,0,full,-1,buffer,bytes,NULL,NULL);
    __real_free(p);__real_free(full);return buffer;
}
/* MinGW's dllimport declarations call import pointers, whereas static library
 * code may call plain symbols. Intercept both spellings at link time. */
void *(*__wrap___imp_malloc)(size_t)=__wrap_malloc;
void *(*__wrap___imp_calloc)(size_t,size_t)=__wrap_calloc;
void *(*__wrap___imp_realloc)(void *,size_t)=__wrap_realloc;
void (*__wrap___imp_free)(void *)=__wrap_free;
char *(*__wrap___imp__strdup)(const char *)=__wrap__strdup;
FILE *(*__wrap___imp_fopen)(const char *,const char *)=__wrap_fopen;
int (*__wrap___imp_fclose)(FILE *)=__wrap_fclose;
char *(*__wrap___imp__fullpath)(char *,const char *,size_t)=__wrap__fullpath;
size_t (*__wrap___imp_fread)(void *,size_t,size_t,FILE *)=__wrap_fread;
size_t (*__wrap___imp_fwrite)(const void *,size_t,size_t,FILE *)=__wrap_fwrite;
int (*__wrap___imp__read)(int,void *,unsigned)=__wrap__read;
int (*__wrap___imp__write)(int,const void *,unsigned)=__wrap__write;

__declspec(dllexport) int bako_file_flush(FILE *file) {return fflush(file);}
__declspec(dllexport) long long bako_file_tell(FILE *file) {return _ftelli64(file);}
__declspec(dllexport) int bako_file_seek(FILE *file,long long offset) {clearerr(file);return _fseeki64(file,offset,SEEK_SET);}
__declspec(dllexport) int bako_file_close(FILE *file) {return __real_fclose(file);}

static void boundary(void) {
    int top=lua_gettop(boundary_lua);
    lua_getglobal(boundary_lua,"bako_boundary");
    if(lua_pcall(boundary_lua,0,0,0)) {
        fprintf(stderr,"Engine boundary failed: %s\n",lua_tostring(boundary_lua,-1));
        bako_host_park();exit(7);
    }
    lua_settop(boundary_lua,top);
}
static int enable(lua_State *L){boundary_lua=L;bako_set_boundary(boundary);return 0;}
static int disable(lua_State *L){(void)L;bako_set_boundary(NULL);return 0;}
static int refresh(lua_State *L){(void)L;bako_sources_refresh();return 0;}
static int source_enable(lua_State *L){bako_source_enable((int)luaL_checkinteger(L,1));return 0;}
static int source_register(lua_State *L){bako_source_register(luaL_checkstring(L,1),(int)luaL_checkinteger(L,2));return 0;}
static int source_length(lua_State *L){lua_pushinteger(L,bako_source_length((int)luaL_checkinteger(L,1)));return 1;}
static int checkpoint(lua_State *L){lua_pushinteger(L,bako_host_checkpoint((int)luaL_checkinteger(L,1)));return 1;}
static int now(lua_State *L){lua_pushinteger(L,bako_host_now());return 1;}
static int live(lua_State *L){lua_pushinteger(L,bako_host_live());return 1;}
static int park(lua_State *L){(void)L;bako_host_park();return 0;}
static int export_pdf(lua_State *L){(void)L;fflush(NULL);return 0;}
static int timings(lua_State *L){long long values[4];bako_host_timings(values);for(int i=0;i<4;i++)lua_pushinteger(L,values[i]);return 4;}
static int stats(lua_State *L){char data[512];bako_host_stats(data,sizeof(data));lua_pushstring(L,data);return 1;}
static int page_bytes(lua_State *L) {
    pdf_flush(static_pdf);fflush(NULL);
    FILE *file=__real_fopen("main.pdf","rb");
    if(!file)return luaL_error(L,"Cannot open native page buffer");
    _fseeki64(file,0,SEEK_END);long long end=_ftelli64(file),length=end-capture_offset;
    if(length<0||length>64*1024*1024){__real_fclose(file);return luaL_error(L,"Invalid native page buffer size");}
    _fseeki64(file,capture_offset,SEEK_SET);
    char *data=__real_malloc(length?length:1);
    if(!data){__real_fclose(file);return luaL_error(L,"Cannot allocate native page buffer");}
    size_t got=fread(data,1,(size_t)length,file);__real_fclose(file);
    if(got!=(size_t)length){__real_free(data);return luaL_error(L,"Cannot read native page buffer");}
    capture_offset=end;lua_pushlstring(L,data,got);__real_free(data);return 1;
}
static int publish(lua_State *L) {
    size_t m,n;const char *metadata=luaL_checklstring(L,1,&m),*data=luaL_checklstring(L,2,&n);
    bako_host_publish(metadata,m,data,n);return 0;
}
__declspec(dllexport) size_t bako_font_bundle(const int *fonts,int count,char **bytes) {
    wchar_t directory[MAX_PATH],path[MAX_PATH];
    *bytes=NULL;
    if(!GetTempPathW(MAX_PATH,directory)||!GetTempFileNameW(directory,L"bko",0,path))return 0;
    FILE *file=_wfopen(path,L"w+b");
    if(!file){DeleteFileW(path);return 0;}
    int ok=bako_write_font_bundle(file,fonts,count);fflush(file);
    long n=ftell(file);rewind(file);*bytes=NULL;
    if(ok&&n>0){*bytes=__real_malloc((size_t)n);if(*bytes&&fread(*bytes,1,n,file)!=(size_t)n){__real_free(*bytes);*bytes=NULL;}}
    __real_fclose(file);DeleteFileW(path);return *bytes?(size_t)n:0;
}
__declspec(dllexport) void bako_release_bundle(void *bytes){__real_free(bytes);}
__declspec(dllexport) int luaopen_bako_native(lua_State *L) {
    static const luaL_Reg functions[]={
        {"checkpoint",checkpoint},{"now",now},{"is_live",live},{"park",park},
        {"export_pdf",export_pdf},{"timings",timings},{"stats",stats},
        {"page_bytes",page_bytes},{"publish",publish},{"source_enable",source_enable},
        {"source_register",source_register},{"source_length",source_length},
        {"enable_boundaries",enable},{"disable_boundaries",disable},{"refresh_sources",refresh},{NULL,NULL}};
    luaL_newlib(L,functions);return 1;
}
