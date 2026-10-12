/* POSIX process checkpoints for LuaTeX. */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/mman.h>
#include <time.h>
#include <stdint.h>
typedef struct lua_State lua_State;
typedef long long lua_Integer;
extern lua_Integer luaL_checkinteger(lua_State*,int);
extern int luaL_error(lua_State*,const char*,...);
extern void lua_pushinteger(lua_State*,lua_Integer);
extern void lua_pushcclosure(lua_State*,int (*)(lua_State*),int);
extern void lua_createtable(lua_State*,int,int);
extern void lua_setfield(lua_State*,int,const char*);
extern const char *luaL_checklstring(lua_State*,int,size_t*);
extern void lua_pushlstring(lua_State*,const char*,size_t);
extern int lua_getglobal(lua_State*,const char*);
extern int lua_gettop(lua_State*);
extern void lua_settop(lua_State*,int);
extern const char *lua_tolstring(lua_State*,int,size_t*);
extern int lua_pcallk(lua_State*,int,int,int,intptr_t,int (*)(lua_State*,int,intptr_t));
/* Exported by the pinned Linux LuaHBTeX 1.14 backend. No private struct layout
 * is used. The page-stream adapter checks the engine before loading this code. */
extern void *static_pdf;
extern void pdf_flush(void*);
extern void bako_source_enable(int) __attribute__((weak));
extern void bako_source_register(const char*,int) __attribute__((weak));
extern int bako_source_length(int) __attribute__((weak));
extern void bako_sources_refresh(void) __attribute__((weak));
extern void bako_set_boundary(void (*)(void)) __attribute__((weak));
extern int bako_write_font_bundle(FILE*,const int*,int) __attribute__((weak));
static lua_State *boundary_lua;
static void engine_boundary(void) {
  int top=lua_gettop(boundary_lua);
  lua_getglobal(boundary_lua,"bako_boundary");
  if(lua_pcallk(boundary_lua,0,0,0,0,NULL)) {
    dprintf(2,"Engine checkpoint callback failed: %s\n",lua_tolstring(boundary_lua,-1,NULL));
    _exit(7);
  }
  lua_settop(boundary_lua,top);
}
static int enable_boundaries(lua_State *L) {
  if(!bako_set_boundary)return luaL_error(L,"Engine checkpoint API unavailable");
  boundary_lua=L;bako_set_boundary(engine_boundary);return 0;
}
static int disable_boundaries(lua_State *L) {
  (void)L;if(bako_set_boundary)bako_set_boundary(NULL);return 0;
}
static int refresh_sources(lua_State *L) {
  if(!bako_sources_refresh)return luaL_error(L,"Source refresh API unavailable");
  bako_sources_refresh();return 0;
}
static int source_enable(lua_State *L) {
  if(!bako_source_enable)return luaL_error(L,"Token origins require the bundled patched LuaHBTeX engine");
  bako_source_enable((int)luaL_checkinteger(L,1));return 0;
}
static int source_register(lua_State *L) {
  if(!bako_source_register)return luaL_error(L,"Token origin API unavailable");
  bako_source_register(luaL_checklstring(L,1,NULL),(int)luaL_checkinteger(L,2));return 0;
}
static int source_length(lua_State *L) {
  lua_pushinteger(L,bako_source_length?bako_source_length((int)luaL_checkinteger(L,1)):0);return 1;
}

struct saved_fd { int fd,flags; off_t pos; char path[4096]; };
static int limit=100;
static int live=0;
static off_t capture_offset=0;
static int memory_pdf=-1;
static long long request_us=0,fork_start_us=0,fork_us=0,restore_us=0;
static long long clock_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (long long)t.tv_sec*1000000+t.tv_nsec/1000;}
static int timings(lua_State *L){
  lua_pushinteger(L,request_us);lua_pushinteger(L,fork_us);lua_pushinteger(L,restore_us);lua_pushinteger(L,fork_start_us);return 4;
}
static int now(lua_State *L){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);lua_pushinteger(L,(lua_Integer)t.tv_sec*1000000+t.tv_nsec/1000);return 1;}
static int is_live(lua_State *L){lua_pushinteger(L,live);return 1;}
static int park(lua_State *L){(void)L;return 0;}
static int stats(lua_State *L){
  char buffer[512];
  snprintf(buffer,sizeof(buffer),"{\"mode\":\"fork\",\"pid\":%d}",getpid());
  lua_pushlstring(L,buffer,strlen(buffer));return 1;
}

static int page_bytes(lua_State *L) {
  pdf_flush(static_pdf);fflush(NULL);
  int memory=memory_pdf;
  int fd=memory>=0?dup(memory):open("main.pdf",O_RDONLY);struct stat st;
  if(fd<0||fstat(fd,&st))return luaL_error(L,"Cannot read page command buffer");
  off_t size=st.st_size-capture_offset;
  if(size<0||size>64*1024*1024){close(fd);return luaL_error(L,"Invalid page buffer size");}
  char *data=malloc(size?size:1);if(!data){close(fd);return luaL_error(L,"Page buffer allocation failed");}
  off_t done=0;
  while(done<size){ssize_t n=pread(fd,data+done,size-done,capture_offset+done);if(n<=0){free(data);close(fd);return luaL_error(L,"Page buffer read failed");}done+=n;}
  close(fd);capture_offset=st.st_size;lua_pushlstring(L,data,size);free(data);return 1;
}
static int copy_prefix(int from,int to,off_t size) {
  char data[65536];off_t offset=0;
  while(offset<size){size_t amount=size-offset<(off_t)sizeof(data)?size-offset:sizeof(data);
    ssize_t n=pread(from,data,amount,offset);if(n<=0)return -1;
    ssize_t done=0;while(done<n){ssize_t w=pwrite(to,data+done,n-done,offset+done);if(w<=0)return -1;done+=w;}offset+=n;
  }return 0;
}
static int export_pdf(lua_State *L) {
  int memory=memory_pdf;
  if(memory<0)return 0;
  fflush(NULL);struct stat st;if(fstat(memory,&st))return luaL_error(L,"Missing in-memory PDF output");
  int out=open("main.pdf.tmp",O_WRONLY|O_CREAT|O_TRUNC,0600);
  if(out<0||copy_prefix(memory,out,st.st_size)){if(out>=0)close(out);return luaL_error(L,"PDF resource export failed");}
  close(out);if(rename("main.pdf.tmp","main.pdf"))return luaL_error(L,"PDF resource export rename failed");return 0;
}
static int send_all(int fd,const char *data,size_t size) {
  while(size){ssize_t n=send(fd,data,size,MSG_NOSIGNAL);if(n<0&&errno==EINTR)continue;if(n<=0)return -1;data+=n;size-=n;}return 0;
}
static void font_bundle(int channel,const int *fonts,int count) {
  int fd=memfd_create("bako-font-bundle",MFD_CLOEXEC),status=0;
  if(fd<0){send_all(channel,"0\n",2);return;}
  fflush(NULL);
  pid_t child=fork();
  if(child==0) {
    alarm(10);
    /* Font loading may write log/recorder data. Do not advance the parent's
     * shared descriptors or change its unfinished PDF. */
    int sink=open("/dev/null",O_WRONLY);
    if(sink<0)_exit(1);
    for(int n=0;n<256;n++) {
      if(n==fd||n==sink||n==channel)continue;
      int flags=fcntl(n,F_GETFL);struct stat st;
      if(flags>=0&&(flags&O_ACCMODE)!=O_RDONLY&&!fstat(n,&st)&&
         (n==1||n==2||S_ISREG(st.st_mode)))dup2(sink,n);
    }
    if(sink>=0)close(sink);
    FILE *out=fdopen(fd,"wb");
    _exit(out&&bako_write_font_bundle&&bako_write_font_bundle(out,fonts,count)?0:1);
  }
  pid_t reaped=-1;
  if(child>0)do {reaped=waitpid(child,&status,0);} while(reaped<0&&errno==EINTR);
  struct stat st;
  if(child<0||reaped!=child||!WIFEXITED(status)||WEXITSTATUS(status)||fstat(fd,&st)||st.st_size<=0||st.st_size>32*1024*1024) {
    send_all(channel,"0\n",2);close(fd);return;
  }
  char header[64],data[65536];int n=snprintf(header,sizeof(header),"%lld\n",(long long)st.st_size);
  if(!send_all(channel,header,n))for(off_t pos=0;pos<st.st_size;) {
    ssize_t got=pread(fd,data,sizeof(data),pos);
    if(got<=0||send_all(channel,data,got))break;
    pos+=got;
  }
  close(fd);
}
static int publish(lua_State *L) {
  size_t metadata_size,data_size;
  const char *metadata=luaL_checklstring(L,1,&metadata_size),*data=luaL_checklstring(L,2,&data_size);
  int fd=socket(AF_UNIX,SOCK_STREAM,0);struct sockaddr_un a={.sun_family=AF_UNIX};strcpy(a.sun_path,"pages.sock");
  if(fd<0||connect(fd,(struct sockaddr*)&a,sizeof(a))){if(fd>=0)close(fd);return luaL_error(L,"Page transport unavailable");}
  char header[80];int n=snprintf(header,sizeof(header),"%zu %zu\n",metadata_size,data_size);
  int failed=send_all(fd,header,n)||send_all(fd,metadata,metadata_size)||send_all(fd,data,data_size);
  if(failed){close(fd);return luaL_error(L,"Page transport failed");}
  /* Retain the unfinished output. A resource miss can continue to PDF export;
   * the next edit instead restores the preceding compiler checkpoint. */
  if(getenv("BAKO_FONT_STREAM")) {
    /* Demand-driven replies share this publisher's channel, so resources
     * cannot accidentally come from a different checkpoint or revision. */
    while(1) {
      raise(SIGSTOP);
      char command[4096];size_t used=0;
      while(used+1<sizeof(command)) {
        ssize_t got=recv(fd,command+used,1,0);
        if(got<=0)break;
        if(command[used++]=='\n')break;
      }
      command[used]=0;
      if(strncmp(command,"fonts ",6))break;
      int fonts[256],count=0;char *p=command+6,*end;
      while(*p&&*p!='\n'&&count<256) {
        long value=strtol(p,&end,10);if(end==p||value<=0||value>1000000){count=0;break;}
        fonts[count++]=(int)value;p=end;while(*p==' ')++p;
      }
      if(count)font_bundle(fd,fonts,count);else send_all(fd,"0\n",2);
    }
  } else {close(fd);fd=-1;raise(SIGSTOP);}
  if(fd>=0)close(fd);return 0;
}

static int checkpoint(lua_State *L) {
  int index=(int)luaL_checkinteger(L,1);
  if(index>limit && !getenv("BAKO_LIVE_DOCUMENT")) {lua_pushinteger(L,limit);return 1;}
  fflush(NULL);
  char session_path[4096];if(!getcwd(session_path,sizeof(session_path)))return luaL_error(L,"Cannot resolve checkpoint session directory");
  struct saved_fd saved[256]; int count=0;
  for(int fd=3;fd<256;fd++) {
    if(fd==memory_pdf)continue;
    struct stat st;
    if(fstat(fd,&st)||!S_ISREG(st.st_mode))continue;
    off_t pos=lseek(fd,0,SEEK_CUR); if(pos<0)continue;
    char link[64];snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);
    struct saved_fd *s=&saved[count];
    ssize_t n=readlink(link,s->path,sizeof(s->path)-1);
    if(n<0)continue;s->path[n]=0;s->fd=fd;s->pos=pos;s->flags=fcntl(fd,F_GETFL);
    if((s->flags&O_ACCMODE)!=O_RDONLY && strncmp(s->path,"/memfd:bako-page-output",23) && (strncmp(s->path,session_path,strlen(session_path)) || s->path[strlen(session_path)]!='/'))
      return luaL_error(L,"Checkpoint cannot restore a writable file outside its generated session: %s",s->path);
    count++;
  }
  char sockpath[100],pidpath[100];
  snprintf(sockpath,sizeof(sockpath),"cp-%03d.sock",index);
  snprintf(pidpath,sizeof(pidpath),"cp-%03d.pid",index);
  int server=socket(AF_UNIX,SOCK_STREAM,0);
  if(server<0)return luaL_error(L,"checkpoint socket: %s",strerror(errno));
  struct sockaddr_un address={.sun_family=AF_UNIX};
  strcpy(address.sun_path,sockpath);unlink(sockpath);
  if(bind(server,(struct sockaddr*)&address,sizeof(address))||listen(server,4))
    return luaL_error(L,"checkpoint bind: %s",strerror(errno));
  FILE *pidfile=fopen(pidpath,"w");if(pidfile){fprintf(pidfile,"%d",getpid());fclose(pidfile);}
  pid_t child=-1;int first=1;
  for(;;) {
    pid_t retired=-1;
    if(!first) {
      int client=accept(server,NULL,NULL);
      if(client<0){if(errno==EINTR)continue;_exit(2);}
      char buffer[64]={0};int n=read(client,buffer,sizeof(buffer)-1);
      if(n<=0){close(client);continue;}
      int requested=atoi(buffer);
      if(requested<1||requested>10000){close(client);continue;}
      limit=requested;
      request_us=clock_us();
      live=1;
      /* A discarded child must never run against the restored output files.
       * SIGKILL also terminates a SIGSTOPped publisher. Reap after forking so
       * freeing its page tables overlaps the next typesetting operation. */
      if(child>0){kill(child,SIGKILL);retired=child;}
      close(client);
    }
    first=0;
    fork_start_us=clock_us();
    child=fork();
    if(child<0)_exit(3);
    if(child==0) {
      fork_us=clock_us();
      close(server);
      if(memory_pdf>=0){close(memory_pdf);memory_pdf=-1;}
      /* Reopen file descriptions so sibling checkpoints do not share offsets.
       * All writable regular descriptors here are generated session artifacts.
       * Reset the underlying offset to match each copied C/Lua input buffer.
       */
      for(int i=0;i<count;i++) {
        struct saved_fd *s=&saved[i];
        int mode=s->flags&O_ACCMODE;
        size_t path_length=strlen(s->path);
        int use_memory=live&&getenv("BAKO_PAGE_STREAM")&&mode!=O_RDONLY&&
          ((path_length>=9&&!strcmp(s->path+path_length-9,"/main.pdf"))||!strncmp(s->path,"/memfd:bako-page-output",23));
        int fresh=use_memory?memfd_create("bako-page-output",MFD_CLOEXEC):open(s->path,mode);
        if(use_memory){
          char link[64];snprintf(link,sizeof(link),"/proc/self/fd/%d",s->fd);
          int original=open(link,O_RDONLY);
          if(fresh<0||original<0||copy_prefix(original,fresh,s->pos)){dprintf(2,"In-memory checkpoint restore failed: %s\n",strerror(errno));_exit(4);}
          close(original);
          memory_pdf=dup(fresh);if(memory_pdf<0)_exit(4);
        }
        /* TeX deletes a partial PDF on fatal errors. The checkpoint still has
         * its inode open: recover the prefix before resuming that TeX state. */
        if(fresh<0&&errno==ENOENT&&mode!=O_RDONLY) {
          fresh=open(s->path,mode|O_CREAT|O_EXCL,0600);
          if(fresh<0)_exit(4);
          char link[64],buffer[65536];
          snprintf(link,sizeof(link),"/proc/self/fd/%d",s->fd);
          int original=open(link,O_RDONLY);if(original<0)_exit(4);
          off_t offset=0;
          while(offset<s->pos) {
            size_t size=s->pos-offset<(off_t)sizeof(buffer)?(size_t)(s->pos-offset):sizeof(buffer);
            ssize_t n=pread(original,buffer,size,offset);if(n<=0)_exit(4);
            ssize_t written=0;
            while(written<n){ssize_t w=pwrite(fresh,buffer+written,n-written,offset+written);if(w<=0)_exit(4);written+=w;}
            offset+=n;
          }
          close(original);
        }
        if(fresh<0)_exit(4);
        if(mode!=O_RDONLY&&ftruncate(fresh,s->pos))_exit(5);
        if(lseek(fresh,s->pos,SEEK_SET)<0||dup2(fresh,s->fd)<0)_exit(6);
        if(fresh!=s->fd)close(fresh);
      }
      FILE *active=fopen("active.pid.tmp","w");if(active){fprintf(active,"%d",getpid());fclose(active);rename("active.pid.tmp","active.pid");}
      restore_us=clock_us();
      lua_pushinteger(L,limit);return 1;
    }
    if(retired>0)while(waitpid(retired,NULL,0)<0&&errno==EINTR){}
  }
}

int luaopen_bako_snapshot(lua_State *L) {
  /* The same small bridge is used by provenance and checkpoint control. */
  lua_createtable(L,0,5);lua_pushcclosure(L,checkpoint,0);lua_setfield(L,-2,"checkpoint");lua_pushcclosure(L,now,0);lua_setfield(L,-2,"now");
  lua_pushcclosure(L,is_live,0);lua_setfield(L,-2,"is_live");lua_pushcclosure(L,page_bytes,0);lua_setfield(L,-2,"page_bytes");lua_pushcclosure(L,publish,0);lua_setfield(L,-2,"publish");
  lua_pushcclosure(L,export_pdf,0);lua_setfield(L,-2,"export_pdf");
  lua_pushcclosure(L,timings,0);lua_setfield(L,-2,"timings");
  lua_pushcclosure(L,park,0);lua_setfield(L,-2,"park");
  lua_pushcclosure(L,stats,0);lua_setfield(L,-2,"stats");
  lua_pushcclosure(L,source_enable,0);lua_setfield(L,-2,"source_enable");
  lua_pushcclosure(L,source_register,0);lua_setfield(L,-2,"source_register");
  lua_pushcclosure(L,source_length,0);lua_setfield(L,-2,"source_length");
  lua_pushcclosure(L,enable_boundaries,0);lua_setfield(L,-2,"enable_boundaries");
  lua_pushcclosure(L,disable_boundaries,0);lua_setfield(L,-2,"disable_boundaries");
  lua_pushcclosure(L,refresh_sources,0);lua_setfield(L,-2,"refresh_sources");return 1;
}
