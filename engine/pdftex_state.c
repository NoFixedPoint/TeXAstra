/* POSIX process snapshots of actual pdfTeX, including its PDF/zlib/font state.
 * Only generated session outputs are writable. Each snapshot owns immutable
 * copies of output prefixes; file descriptions are reopened in the resumed
 * process, and TeX input buffering is discarded at its saved logical offset.
 */
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/mman.h>
#include <signal.h>
#include <fcntl.h>
#include <dirent.h>
#include <poll.h>
#include <errno.h>
static int ta_state_enabled, ta_serial, ta_last_page=-1, ta_last_line=-1, ta_last_slot=-1;
static pid_t ta_owner;
static char ta_session[PATH_MAX], ta_main[PATH_MAX];
static int ta_frontier[2147];

static int ta_fd_path(int fd,char *path) {
#ifdef __APPLE__
    return fcntl(fd,F_GETPATH,path);
#else
    char link[64];snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);
    ssize_t n=readlink(link,path,PATH_MAX-1);if(n<0)return -1;
    path[n]=0;return 0;
#endif
}
static int ta_prefix_fd(void) {
#ifdef __APPLE__
    /* An unlinked session-local file has the same fork lifetime as a memfd. */
    char name[]="pdftex-prefix-XXXXXX";
    int fd=mkstemp(name);
    if(fd>=0){unlink(name);fcntl(fd,F_SETFD,FD_CLOEXEC);}
    return fd;
#else
    return memfd_create("texastra-pdftex-prefix",MFD_CLOEXEC);
#endif
}

static uint64_t ta_hash(const unsigned char *p,size_t n) {
    uint64_t h=UINT64_C(14695981039346656037);
    while(n--){h^=*p++;h*=UINT64_C(1099511628211);}return h;
}
static void ta_json_string(FILE *f,const char *s) {
    fputc('"',f);for(;*s;++s){unsigned char c=*s;
        if(c=='"'||c=='\\')fprintf(f,"\\%c",c);
        else if(c<32)fprintf(f,"\\u%04x",c);else fputc(c,f);
    }fputc('"',f);
}
static void ta_done(void) {
    if(!ta_state_enabled)return;
    FILE *f=fopen("pdftex-done.new","w");if(!f)return;
    fprintf(f,"{\"pid\":%d,\"ok\":%s}\n",getpid(),history<2?"true":"false");
    fclose(f);rename("pdftex-done.new","pdftex-done.json");
}
static void ta_state_init(void) {
    const char *owner=getenv("TEXASTRA_PDFTEX_OWNER"),*main=getenv("TEXASTRA_PDFTEX_MAIN");
    if(!owner||!main||!getcwd(ta_session,sizeof(ta_session)))return;
    ta_owner=atoi(owner);if(ta_owner<=1||!realpath(main,ta_main))return;
    ta_state_enabled=1;atexit(ta_done);
}
static void ta_read_frontiers(void) {
    for(int level=1;level<=inopen;++level){
        strnumber name=fullsourcefilenamestack[level];if(!name)continue;
        char *p=gettexstring(name),*path=realpath(p,NULL);free(p);if(!path)continue;
        for(int i=0;i<ta_count;++i)if(!strcmp(path,ta_files[i].path)){
            off_t pos=ftello(inputfile[level]);
            if(pos>=0&&pos<=ta_files[i].size&&pos>ta_frontier[i])ta_frontier[i]=(int)pos;
            break;
        }free(path);
    }
}
static void ta_read_register(int n) {
    if(!ta_state_enabled||n<0||n>=16||readopen[n]==2)return;
    char path[PATH_MAX];if(ta_fd_path(fileno(readfile[n]),path))return;
    /* \read streams have a separate input path. Conservatively invalidate on
     * any change to that file instead of pretending a scanner frontier exists. */
    for(int i=0;i<ta_count;++i)if(!strcmp(path,ta_files[i].path))ta_frontier[i]=ta_files[i].size;
}
struct ta_fd {int fd,flags,copy;off_t pos,size;char path[PATH_MAX];};
static int ta_copy(int from,int to,off_t size) {
    char bytes[65536];off_t pos=0;
    while(pos<size){ssize_t n=pread(from,bytes,size-pos<(off_t)sizeof(bytes)?size-pos:sizeof(bytes),pos);
        if(n<=0)return -1;
        for(ssize_t done=0;done<n;){ssize_t w=pwrite(to,bytes+done,n-done,pos+done);if(w<=0)return -1;done+=w;}
        pos+=n;
    }return 0;
}
static void ta_close_copies(struct ta_fd *fds,int n) {
    for(int i=0;i<n;++i)if(fds[i].copy>=0)close(fds[i].copy);
}
static void ta_checkpoint(void) {
    if(!ta_state_enabled||!ta_scanning||scannerstatus!=0)return;
    if(ta_serial>=256)return;
    unsigned char next=ta_scanning->bytes[ta_start];
    if(next=='%'||next==' '||next=='\t'||next=='\r'||next=='\n')return;
    if(totalpages==ta_last_page&&(totalpages>0||(line==ta_last_line&&ta_last_slot==ta_scanning->slot)))return;
    ta_last_page=totalpages;ta_last_line=line;ta_last_slot=ta_scanning->slot;
    /* Whole-process snapshots are valid even inside an expansion. Full line
     * read frontiers, rather than visible page positions, govern reuse. */
    ta_read_frontiers();for(int i=0;i<16;++i)ta_read_register(i);fflush(NULL);
    struct ta_fd fds[256];int n=0,unsupported=0;
    off_t positions[1024];
    if(inopen>=1024)return;
    for(int i=1;i<=inopen;++i)positions[i]=fullsourcefilenamestack[i]&&inputfile[i]?ftello(inputfile[i]):-1;
#ifdef __APPLE__
    /* Include high-numbered descriptors; never silently omit compiler files. */
    int limit=getdtablesize();
    for(int fd=3;fd<limit;++fd){
        struct stat st;
        if(fstat(fd,&st)||!S_ISREG(st.st_mode))continue;
#else
    DIR *dir=opendir("/proc/self/fd");if(!dir)return;
    struct dirent *entry;
    while((entry=readdir(dir))){
        int fd=atoi(entry->d_name);struct stat st;
        if(fd<3||fd==dirfd(dir)||fstat(fd,&st)||!S_ISREG(st.st_mode))continue;
#endif
        /* Prefix memfds belong to this capture, not the engine. */
        int own=0;for(int i=0;i<n;++i)if(fds[i].copy==fd)own=1;if(own)continue;
        if(n==256){unsupported=1;break;}
        struct ta_fd *f=&fds[n];memset(f,0,sizeof(*f));f->copy=-1;
        if(ta_fd_path(fd,f->path)){unsupported=1;break;}
        f->fd=fd;f->flags=fcntl(fd,F_GETFL);f->pos=lseek(fd,0,SEEK_CUR);f->size=st.st_size;
        if(f->pos<0||f->flags<0){unsupported=1;break;}
        if((f->flags&O_ACCMODE)!=O_RDONLY){
            if(strncmp(f->path,ta_session,strlen(ta_session))||f->path[strlen(ta_session)]!='/'){unsupported=1;break;}
            f->copy=ta_prefix_fd();
            int readable=open(f->path,O_RDONLY);
            struct stat reopened;
            if(readable>=0&&(fstat(readable,&reopened)||reopened.st_dev!=st.st_dev||reopened.st_ino!=st.st_ino)){
                close(readable);readable=-1;
            }
            if(f->copy<0||readable<0||ta_copy(readable,f->copy,f->size))unsupported=1;
            if(readable>=0)close(readable);
        }
        ++n;if(unsupported)break;
    }
#ifndef __APPLE__
    closedir(dir);
#endif
    /* An output can have been closed before the checkpoint and overwritten
     * later (including an include-file .aux). Its checkpoint bytes also belong
     * to the retained state, even though it has no live descriptor. */
    char *job=gettexstring(jobname),recorder[PATH_MAX];
    snprintf(recorder,sizeof(recorder),"%s.fls",job);free(job);
    FILE *records=fopen(recorder,"r");
    if(records){
        char row[PATH_MAX+16];
        while(!unsupported&&fgets(row,sizeof(row),records))if(!strncmp(row,"OUTPUT ",7)){
            char path[PATH_MAX];row[strcspn(row,"\r\n")]=0;
            if(!realpath(row+7,path))continue;
            int saved=0;for(int i=0;i<n;++i)if(!strcmp(fds[i].path,path)&&(fds[i].flags&O_ACCMODE)!=O_RDONLY)saved=1;
            if(saved)continue;
            if(n==256||strncmp(path,ta_session,strlen(ta_session))||path[strlen(ta_session)]!='/'){unsupported=1;break;}
            struct ta_fd *f=&fds[n++];memset(f,0,sizeof(*f));f->fd=-1;f->flags=O_RDWR;strcpy(f->path,path);
            f->copy=ta_prefix_fd();
            int in=open(path,O_RDONLY);struct stat st;
            if(in<0||fstat(in,&st)||f->copy<0){unsupported=1;}
            else {f->size=st.st_size;if(ta_copy(in,f->copy,f->size))unsupported=1;}
            if(in>=0)close(in);
        }
        fclose(records);
    }
    if(unsupported){ta_close_copies(fds,n);return;}
    int serial=++ta_serial;
    char sock[96],meta[96],temporary[100];
    snprintf(sock,sizeof(sock),"pdftex-cp-%06d.sock",serial);
    snprintf(meta,sizeof(meta),"pdftex-cp-%06d.json",serial);
    snprintf(temporary,sizeof(temporary),"%s.new",meta);
    int server=socket(AF_UNIX,SOCK_STREAM,0);
    if(server>=0)fcntl(server,F_SETFD,FD_CLOEXEC);
    struct sockaddr_un addr={.sun_family=AF_UNIX};strcpy(addr.sun_path,sock);unlink(sock);
    if(server<0||bind(server,(struct sockaddr*)&addr,sizeof(addr))||listen(server,2)){
        if(server>=0)close(server);ta_close_copies(fds,n);return;
    }
    pid_t snapshot=fork();
    if(snapshot<0){close(server);unlink(sock);ta_close_copies(fds,n);return;}
    if(snapshot>0){
        FILE *f=fopen(temporary,"w");
        if(f){
            fprintf(f,"{\"pid\":%d,\"serial\":%d,\"pages\":%d,\"sources\":{",snapshot,serial,totalpages);
            for(int i=0;i<ta_count;++i){
                if(i)fputc(',',f);ta_json_string(f,ta_files[i].path);
                fprintf(f,":{\"frontier\":%d,\"hash\":\"%016llx\"}",ta_frontier[i],
                    (unsigned long long)ta_hash(ta_files[i].bytes,ta_frontier[i]));
            }
            fprintf(f,"},\"outputs\":[");int first=1;
            for(int i=0;i<n;++i)if(fds[i].copy>=0){if(!first)fputc(',',f);first=0;ta_json_string(f,fds[i].path);}
            fprintf(f,"]}\n");fclose(f);rename(temporary,meta);
        }
        close(server);ta_close_copies(fds,n);return;
    }
    /* Snapshot stays dormant; each resume forks a disposable continuation. */
    for(;;){
        while(waitpid(-1,NULL,WNOHANG)>0){}
        if(kill(ta_owner,0)&&errno==ESRCH)_exit(0);
        struct pollfd poller={server,POLLIN,0};
        if(poll(&poller,1,1000)<=0)continue;
        int client=accept(server,NULL,NULL);if(client<0)continue;
        fcntl(client,F_SETFD,FD_CLOEXEC);
        char command; if(recv(client,&command,1,0)!=1||command!='R'){close(client);continue;}
        pid_t worker=fork();
        if(worker!=0){dprintf(client,"%d\n",worker);close(client);continue;}
        close(client);close(server);
        for(int i=0;i<n;++i){
            struct ta_fd *f=&fds[i];int mode=f->flags&O_ACCMODE;
            int fresh=open(f->path,mode==O_RDONLY?O_RDONLY:O_RDWR|O_CREAT|O_TRUNC,0600);
            if(fresh<0||(f->copy>=0&&ta_copy(f->copy,fresh,f->size)))_exit(71);
            if(f->fd<0){close(fresh);continue;}
            if(lseek(fresh,f->pos,SEEK_SET)<0||dup2(fresh,f->fd)<0)_exit(71);
            if(fresh!=f->fd)close(fresh);
        }
        ta_close_copies(fds,n);
        for(int i=1;i<=inopen;++i)if(positions[i]>=0){
            int fd=fileno(inputfile[i]),found=0;
            for(int j=0;j<n;++j)if(fds[j].fd==fd){
                /* fseek may optimize a seek inside the OLD libc buffer even
                 * after dup2. freopen discards that buffer unconditionally. */
                if(!freopen(fds[j].path,"rb",inputfile[i])||fseeko(inputfile[i],positions[i],SEEK_SET))_exit(72);
                found=1;break;
            }
            if(!found)_exit(72);
        }
        for(int i=0;i<ta_count;++i)ta_load(&ta_files[i]);
        ta_last_name=-1;
        return;
    }
}
