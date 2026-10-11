/* Source origins for LuaHBTeX 1.14. Included at the end of textoken.c.
 * The scanner owns token boundaries and catcodes. No TeX source is rewritten.
 * Fork checkpoints retain this metadata together with the engine state.
 */
int bako_origin = 0;
int bako_attribute = -1;
int bako_after_origin = 0;
int *bako_token_origins = NULL;
void (*bako_boundary_hook)(void) = NULL;
void bako_set_boundary(void (*hook)(void)) { bako_boundary_hook = hook; }
static unsigned bako_token_capacity = 0;
typedef struct {
    char *path;
    int slot, size, lines;
    int *scalar, *line_start, *ends;
} bako_file;
static bako_file bako_files[2147];
static int bako_file_count = 0;
static bako_file *bako_scanning = NULL;
static int bako_start = 0;
static const char *bako_last_path = NULL;
static bako_file *bako_last_file = NULL;

void bako_token_store(unsigned p) {
    if (bako_attribute < 0) return;
    if (p >= bako_token_capacity) {
        unsigned old = bako_token_capacity;
        bako_token_capacity = fix_mem_max + 1;
        bako_token_origins = realloc(bako_token_origins, bako_token_capacity * sizeof(int));
        if (!bako_token_origins) abort();
        memset(bako_token_origins + old, 0, (bako_token_capacity-old)*sizeof(int));
    }
    bako_token_origins[p] = bako_origin;
}
int bako_token_origin(unsigned p) {
    return p < bako_token_capacity ? bako_token_origins[p] : 0;
}
void bako_origin_copy(unsigned to, unsigned from) {
    if (bako_attribute >= 0) {
        bako_token_store(to);
        bako_token_origins[to] = bako_token_origin(from);
    }
}
void bako_source_enable(int attribute) { bako_attribute = attribute; }
void bako_source_register(const char *path, int slot) {
    if (slot < 1 || slot > 2146) abort();
    for (int i=0;i<bako_file_count;++i) {
        if (!strcmp(path,bako_files[i].path)) {
            if (bako_files[i].slot!=slot) abort();
            return;
        }
    }
    if (bako_file_count >= 2147) abort();
    bako_file *f = &bako_files[bako_file_count++];
    f->path = xstrdup(path); f->slot = slot;
}
static bako_file *bako_file_for(const char *path) {
    if (!path) return NULL;
    while (path[0]=='.' && path[1]=='/') path+=2;
    for (int i=0; i<bako_file_count; ++i)
        if (!strcmp(path,bako_files[i].path)) return &bako_files[i];
    return NULL;
}
static void bako_source_load(const char *path, int preserve) {
    bako_last_path = NULL;
    bako_file *f = bako_file_for(path);
    if (!f) return;
    FILE *in=fopen(path,"rb");
    if (!in) return;
    fseek(in,0,SEEK_END); long size=ftell(in); rewind(in);
    if (size<0 || size>16000000) { fclose(in); return; }
    unsigned char *data=malloc(size+1);
    if (!data || fread(data,1,size,in)!=(size_t)size) abort();
    fclose(in);
    int old_size = f->size, *old_ends = f->ends;
    free(f->scalar); free(f->line_start);
    f->size=(int)size;
    f->scalar=calloc(size+1,sizeof(int));
    f->line_start=calloc(size+2,sizeof(int));
    f->ends=calloc(size+1,sizeof(int));
    if (!f->scalar || !f->line_start || !f->ends) abort();
    /* Already-built nodes in a checkpoint still reference prefix tokens.
     * Their lengths survive refresh; rescanned suffix tokens replace theirs. */
    if (preserve && old_ends)
        memcpy(f->ends, old_ends, ((old_size < size ? old_size : size)+1)*sizeof(int));
    free(old_ends);
    int scalar=0;
    f->lines=1;
    for (int i=0; i<size; ++i) {
        f->scalar[i]=scalar;
        if ((data[i]&0xc0)!=0x80) ++scalar;
        if (data[i]=='\n') f->line_start[f->lines++]=i+1;
    }
    f->scalar[size]=scalar;
    /* Continuation bytes belong to the same Unicode scalar. */
    for (int i=1;i<size;++i) if ((data[i]&0xc0)==0x80) f->scalar[i]=f->scalar[i-1];
    free(data);
}
void bako_source_open(const char *path) { bako_source_load(path, 0); }
void bako_sources_refresh(void) {
    /* Closed files reopen through bako_source_open. Only the active input
     * stack can retain old line tables after a checkpoint is resumed. */
    for (int i=1; i<=in_open; ++i) {
        bako_file *f = bako_file_for(full_source_filename_stack[i]);
        if (f) bako_source_load(f->path, 1);
    }
}
void bako_scan_begin(void) {
    bako_scanning = NULL;
    bako_origin = 0;
    if (bako_attribute < 0 || iname <= 21 || iindex > in_open) return;
    const char *path=full_source_filename_stack[iindex];
    if (path!=bako_last_path) {
        bako_last_path=path;bako_last_file=bako_file_for(path);
    }
    bako_file *f=bako_last_file;
    if (!f || !f->scalar || line<1 || line>f->lines) return;
    int start=f->line_start[line-1]+iloc-istart;
    if (start<0 || start>=f->size) return;
    bako_scanning=f; bako_start=start;
}
void bako_scan_end(void) {
    bako_file *f=bako_scanning;
    if (!f) return;
    int end=f->line_start[line-1]+iloc-istart;
    if (end>f->size) end=f->size;
    int start=f->scalar[bako_start];
    if (end<=bako_start || start>=1000000) return;
    bako_origin=f->slot*1000000+start;
    f->ends[start]=f->scalar[end]-start;
}
int bako_source_length(int origin) {
    int slot=origin/1000000, offset=origin%1000000;
    for (int i=0;i<bako_file_count;++i) {
        bako_file *f=&bako_files[i];
        if (f->slot==slot && f->ends && offset<=f->size) return f->ends[offset];
    }
    return 0;
}
