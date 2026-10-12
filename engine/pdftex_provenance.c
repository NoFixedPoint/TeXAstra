/* Included after pdftexd.h. No changes to pdfTeX's memoryword or format ABI. */
#include <stdint.h>
#include <limits.h>
#include <unistd.h>
typedef struct { int id, length; } ta_span;
typedef struct {
    char *path;
    int slot, size, lines;
    unsigned char *bytes;
    int *scalar, *starts;
} ta_file;
static int ta_enabled=-1, ta_count=0;
static ta_file ta_files[2147], *ta_scanning;
static int ta_start;
static strnumber ta_last_name=-1;
static ta_file *ta_last_file;
static ta_span ta_origin, ta_drawing, *ta_nodes, *ta_call;
static size_t ta_capacity;
static void ta_state_init(void);
static void ta_checkpoint(void);

static void ta_load(ta_file *f) {
    FILE *in=fopen(f->path,"rb"); if(!in)return;
    fseek(in,0,SEEK_END);long n=ftell(in);rewind(in);
    if(n<0||n>16000000){fclose(in);return;}
    free(f->bytes);free(f->scalar);free(f->starts);
    f->size=(int)n;f->bytes=calloc(n+1,1);
    f->scalar=calloc(n+1,sizeof(int));f->starts=calloc(n+2,sizeof(int));
    if(!f->bytes||!f->scalar||!f->starts)abort();
    if(fread(f->bytes,1,n,in)!=(size_t)n)abort();fclose(in);
    int offset=0;f->lines=1;
    for(int i=0;i<n;++i){
        f->scalar[i]=offset;
        if((f->bytes[i]&0xc0)!=0x80)++offset;
        else if(i)f->scalar[i]=f->scalar[i-1];
        if(f->bytes[i]=='\n')f->starts[f->lines++]=i+1;
    }
    f->scalar[n]=offset;
}
static void ta_init(void) {
    if(ta_enabled>=0)return;
    ta_enabled=0;
    const char *manifest=getenv("TEXASTRA_PDFTEX_SOURCES");
    if(!manifest||!*manifest)return;
    FILE *in=fopen(manifest,"rb");if(!in)return;
    char row[8192];
    while(fgets(row,sizeof(row),in)){
        char *tab=strchr(row,'\t');if(!tab)continue;*tab++=0;
        tab[strcspn(tab,"\r\n")]=0;
        int slot=atoi(row);if(slot<1||slot>2146||ta_count>=2146)abort();
        ta_file *f=&ta_files[ta_count++];f->slot=slot;
        f->path=realpath(tab,NULL);if(!f->path)f->path=strdup(tab);
        ta_load(f);
    }
    fclose(in);
    ta_call=calloc(stacksize+1,sizeof(ta_span));if(!ta_call)abort();
    ta_enabled=1;
    ta_state_init();
}
static ta_span ta_get(int p) {
    ta_span empty={0,0};return p>=0&&(size_t)p<ta_capacity?ta_nodes[p]:empty;
}
static void ta_store(int p,ta_span span) {
    ta_init();if(!ta_enabled||p<0||p>memmax)return;
    if((size_t)p>=ta_capacity){
        size_t old=ta_capacity;ta_capacity=(size_t)memmax+1;
        if((size_t)p>=ta_capacity)abort();
        ta_nodes=realloc(ta_nodes,ta_capacity*sizeof(ta_span));if(!ta_nodes)abort();
        memset(ta_nodes+old,0,(ta_capacity-old)*sizeof(ta_span));
    }
    ta_nodes[p]=span;
}
static void ta_scan_begin(void) {
    ta_init();ta_scanning=NULL;ta_origin=(ta_span){0,0};
    if(!ta_enabled||curinput.namefield<=17||curinput.indexfield>inopen)return;
    strnumber name=fullsourcefilenamestack[curinput.indexfield];if(!name)return;
    if(name!=ta_last_name){
        ta_last_name=name;ta_last_file=NULL;
        char *path=gettexstring(name),*canonical=realpath(path,NULL);free(path);
        if(canonical){
            for(int i=0;i<ta_count;++i)if(!strcmp(canonical,ta_files[i].path)){ta_last_file=&ta_files[i];break;}
            free(canonical);
        }
    }
    ta_file *f=ta_last_file;
    if(f){
        if(f->bytes&&line>=1&&line<=f->lines){
            int start=f->starts[line-1]+curinput.locfield-curinput.startfield;
            if(start>=0&&start<f->size){ta_scanning=f;ta_start=start;}
        }
    }
    if(ta_scanning)ta_checkpoint();
}
static void ta_scan_end(void) {
    ta_file *f=ta_scanning;if(!f)return;
    int end=f->starts[line-1]+curinput.locfield-curinput.startfield;
    if(end>f->size)end=f->size;
    if(f->bytes[ta_start]=='\\')while(end>ta_start+1&&f->bytes[end-1]==' ')--end;
    int start=f->scalar[ta_start];
    if(end>ta_start&&start<1000000)
        ta_origin=(ta_span){f->slot*1000000+start,f->scalar[end]-start};
}
static ta_span ta_ligature(int q) {
    ta_span span=ta_get(q);
    for(int p=q;p!=-268435455L;p=zmem[p].hh.v.RH){
        ta_span next=ta_get(p);
        if(!span.id)span=next;
        if(next.id>=span.id&&next.id<=span.id+span.length&&next.id/1000000==span.id/1000000)
            span.length=next.id+next.length-span.id;
    }
    return span;
}
static void ta_pdf_raw(const char *s) {
    while(*s){if(pdfptr>=pdfbufsize)pdfflush();pdfbuf[pdfptr++]=(unsigned char)*s++;}
}
static void ta_glyph_begin(void) {
    if(!ta_enabled||!pdfdoingstring)return;
    char scope[160];
    snprintf(scope,sizeof(scope),
        ")]TJ\n/BakoSource << /V 1 /ID %d /N 1 /Kind /Glyph /Length %d >> BDC\n[(",
        ta_drawing.id,ta_drawing.length);
    ta_pdf_raw(scope);
}
static void ta_glyph_end(void) {
    if(ta_enabled&&pdfdoingstring)ta_pdf_raw(")]TJ\nEMC\n[(");
}
static void ta_rule_begin(void) {
    if(!ta_enabled)return;
    char scope[160];
    snprintf(scope,sizeof(scope),"/BakoSource << /V 1 /ID %d /N 0 /Kind /Rule /Length %d >> BDC\n",ta_drawing.id,ta_drawing.length);
    ta_pdf_raw(scope);
}
#include "pdftex_state.c"
