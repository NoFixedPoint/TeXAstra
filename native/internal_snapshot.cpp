// In-process, differential checkpoints for the pinned single-threaded Linux
// LuaHBTeX compiler. Control memory and stack live outside the rollback domain.
// No libc calls are allowed on the control stack: libc itself is snapshotted.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <cstdint>
#include <cstddef>
#include <fcntl.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <unistd.h>
#include <time.h>
#include <dlfcn.h>
#include <emmintrin.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error Internal snapshots currently require Linux x86-64
#endif

namespace {
using U = unsigned long;
constexpr U PAGE = 4096, MAX_PAGES = 524288, HASH_SIZE = 1048576;
constexpr U ARENA_SIZE = 12UL << 30, SHADOW_OFFSET = 1UL << 30, JOURNAL_OFFSET = 3UL << 30;
constexpr int MAX_STATES = 102, MAX_FDS = 64;
struct alignas(16) Context {
    U rbx, rbp, r12, r13, r14, r15, rsp, rip;
    unsigned char fp[512];
};
extern "C" int bako_save(Context *) __attribute__((returns_twice));
extern "C" void bako_jump(Context *) __attribute__((noreturn));
extern "C" void bako_control(void *, void (*)());
asm(R"(
.text
.hidden bako_save
.global bako_save
bako_save:
 mov %rbx,0(%rdi)
 mov %rbp,8(%rdi)
 mov %r12,16(%rdi)
 mov %r13,24(%rdi)
 mov %r14,32(%rdi)
 mov %r15,40(%rdi)
 lea 8(%rsp),%rax
 mov %rax,48(%rdi)
 mov (%rsp),%rax
 mov %rax,56(%rdi)
 fxsave64 64(%rdi)
 xor %eax,%eax
 ret
.hidden bako_jump
.global bako_jump
bako_jump:
 fxrstor64 64(%rdi)
 mov 0(%rdi),%rbx
 mov 8(%rdi),%rbp
 mov 16(%rdi),%r12
 mov 24(%rdi),%r13
 mov 32(%rdi),%r14
 mov 40(%rdi),%r15
 mov 48(%rdi),%rsp
 mov $1,%eax
 jmp *56(%rdi)
.hidden bako_control
.global bako_control
bako_control:
 push %rbp
 mov %rsp,%rbp
 mov %rdi,%rsp
 and $-16,%rsp
 call *%rsi
 mov %rbp,%rsp
 pop %rbp
 ret
)");

inline long call(long n, long a = 0, long b = 0, long c = 0, long d = 0, long e = 0, long f = 0) {
    register long r10 asm("r10") = d, r8 asm("r8") = e, r9 asm("r9") = f;
    long result;
    asm volatile("syscall"
                 : "=a"(result)
                 : "a"(n), "D"(a), "S"(b), "d"(c), "r"(r10), "r"(r8), "r"(r9)
                 : "rcx", "r11", "memory");
    return result;
}
void copy(void *to, const void *from, U n) {
    asm volatile("rep movsb" : "+D"(to), "+S"(from), "+c"(n) : : "memory");
}
bool equal(const void *a, const void *b, U n) {
    auto *x = static_cast<const unsigned char *>(a), *y = static_cast<const unsigned char *>(b);
    for (U i = 0; i < n; ++i) {
        if (x[i] != y[i]) {
            return false;
        }
    }
    return true;
}
bool equal16(U a, U b) {
    return _mm_movemask_epi8(_mm_cmpeq_epi8(_mm_loadu_si128((const __m128i *)a),
                                            _mm_loadu_si128((const __m128i *)b))) == 65535;
}
U length(const char *s) {
    U n = 0;
    while (s[n]) {
        ++n;
    }
    return n;
}
bool contains(const char *s, const char *v) {
    for (; *s; ++s) {
        if (equal(s, v, length(v))) {
            return true;
        }
    }
    return false;
}
void print(int fd, const char *s) {
    call(SYS_write, fd, (long)s, length(s));
}
[[noreturn]] void die(const char *s) {
    print(2, "Internal snapshot: ");
    print(2, s);
    print(2, "\n");
    call(SYS_exit_group, 91);
    __builtin_unreachable();
}
long now() {
    timespec t{};
    call(SYS_clock_gettime, CLOCK_MONOTONIC, (long)&t);
    return t.tv_sec * 1000000 + t.tv_nsec / 1000;
}
void number(char *out, U n) {
    char tmp[32];
    int k = 0;
    do {
        tmp[k++] = char('0' + n % 10);
        n /= 10;
    } while (n);
    int i = 0;
    while (k) {
        out[i++] = tmp[--k];
    }
    out[i] = 0;
}
void path_number(char *out, const char *prefix, U n, const char *suffix) {
    U p = length(prefix);
    copy(out, prefix, p);
    number(out + p, n);
    p += length(out + p);
    copy(out + p, suffix, length(suffix) + 1);
}
int open_file(const char *p, int flags, int mode = 0600) {
    return call(SYS_openat, AT_FDCWD, (long)p, flags, mode);
}
void file_text(const char *p, const char *s) {
    int fd = open_file(p, O_WRONLY | O_CREAT | O_TRUNC);
    if (fd < 0) {
        die("cannot write control file");
    }
    print(fd, s);
    call(SYS_close, fd);
}
struct Page {
    U address, generation, seen[4];
};
struct Undo {
    U previous, address, size, page;
};
struct Descriptor {
    int fd, flags, fd_flags, backup;
    long position;
    bool pdf;
    char path[4096];
};
struct State {
    Context context;
    U journal, pages, brk;
    int index, count;
    Descriptor descriptors[MAX_FDS];
};
struct Runtime {
    U base, used, page_count, journal, generation, hash[HASH_SIZE], scan_flags[65536];
    Page pages[MAX_PAGES];
    State states[MAX_STATES];
    int count, input, limit, server, pagemap, clear_refs, pdf, mode;
    bool armed;
    long request_us, restored_us, restore_pages, restore_bytes, scan_us, undo_us, files_us,
        capture_us;
    char maps[262144], io[65536], stack[1024 * 1024];
};
Runtime *R;
U shadow(U i) {
    return R->base + SHADOW_OFFSET + i * PAGE;
}
U hash(U address) {
    return ((address >> 12) * 11400714819323198485UL) >> (64 - 20);
}
U lookup(U address, bool add, bool present = true) {
    U slot = hash(address);
    while (R->hash[slot] && R->pages[R->hash[slot] - 1].address != address) {
        slot = (slot + 1) & (HASH_SIZE - 1);
    }
    if (!R->hash[slot] && add) {
        if (R->page_count == MAX_PAGES) {
            die("compiler memory exceeds snapshot budget");
        }
        U i = R->page_count++;
        R->pages[i].address = address;
        R->hash[slot] = i + 1;
        if (present) {
            copy((void *)shadow(i), (void *)address, PAGE);
        }
    }
    return R->hash[slot] ? R->hash[slot] - 1 : MAX_PAGES;
}
U hex(const char *&p) {
    U n = 0;
    while ((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f')) {
        n = n * 16 + (*p <= '9' ? *p - '0' : *p - 'a' + 10);
        ++p;
    }
    return n;
}
void record(U index) {
    U address = R->pages[index].address, old = shadow(index);
    U changed = 0;
    for (U offset = 0; offset < PAGE; offset += 16) {
        if (!equal16(address + offset, old + offset)) {
            changed += 16;
        }
    }
    if (changed >= 1024) {
        U location = R->used;
        if (location + sizeof(Undo) + PAGE > ARENA_SIZE) {
            die("undo journal exceeds snapshot budget");
        }
        auto *u = (Undo *)(R->base + location);
        u->previous = R->journal;
        u->address = address;
        u->size = PAGE;
        u->page = index;
        copy(u + 1, (void *)old, PAGE);
        copy((void *)old, (void *)address, PAGE);
        R->journal = location;
        R->used += sizeof(Undo) + PAGE;
        return;
    }
    // Store runs of changed 16-byte blocks; unchanged engine memory is shared
    // across all snapshots through one shadow image.
    for (U begin = 0; begin < PAGE;) {
        if (equal16(address + begin, old + begin)) {
            begin += 16;
            continue;
        }
        U end = begin + 16;
        while (end < PAGE && !equal16(address + end, old + end)) {
            end += 16;
        }
        U size = end - begin, location = R->used;
        if (location + sizeof(Undo) + size > ARENA_SIZE) {
            die("undo journal exceeds snapshot budget");
        }
        auto *u = (Undo *)(R->base + location);
        u->previous = R->journal;
        u->address = address + begin;
        u->size = size;
        u->page = index;
        copy(u + 1, (void *)(old + begin), size);
        copy((void *)(old + begin), (void *)(address + begin), size);
        R->journal = location;
        R->used += sizeof(Undo) + size;
        begin = end;
    }
}
void scan(bool restoring) {
    int fd = open_file("/proc/self/maps", O_RDONLY);
    if (fd < 0) {
        die("maps unavailable");
    }
    long used = 0, n;
    while ((n = call(SYS_read, fd, (long)R->maps + used, sizeof(R->maps) - 1 - used)) > 0) {
        used += n;
        if (used >= long(sizeof(R->maps) - 1)) {
            die("too many mappings");
        }
    }
    call(SYS_close, fd);
    R->maps[used] = 0;
    char *line = R->maps;
    while (*line) {
        char *end = line;
        while (*end && *end != '\n') {
            ++end;
        }
        char saved = *end;
        *end = 0;
        const char *p = line;
        U lo = hex(p);
        if (*p++ != '-') {
            die("invalid maps");
        }
        U hi = hex(p);
        while (*p == ' ') {
            ++p;
        }
        if (p[0] == 'r' && p[1] == 'w' && p[3] == 's') {
            die("shared writable mappings are outside the checkpoint contract");
        }
        if (p[0] == 'r' && p[1] == 'w' && p[3] == 'p' &&
            !(lo >= R->base && lo < R->base + ARENA_SIZE) && !contains(line, "bako_internal.so")) {
            for (U chunk = lo; chunk < hi;) {
                U count = (hi - chunk) / PAGE;
                if (count > 65536) {
                    count = 65536;
                }
                if (call(SYS_pread64, R->pagemap, (long)R->scan_flags, count * 8,
                         (chunk / PAGE) * 8) != long(count * 8)) {
                    die("pagemap unavailable");
                }
                for (U j = 0; j < count; ++j) {
                    if (restoring && !(R->scan_flags[j] & (1UL << 55))) {
                        continue;
                    }
                    U address = chunk + j * PAGE, index = lookup(address, false);
                    if (index == MAX_PAGES) {
                        // Only never-populated anonymous heap pages are known
                        // zero. Swapped pages and file-backed .data must be read.
                        if (!restoring) {
                            lookup(address, true,
                                   !contains(line, "[heap]") || (R->scan_flags[j] & (3UL << 62)));
                        }
                        continue;
                    }
                    if (R->scan_flags[j] & (1UL << 55)) {
                        if (restoring) {
                            copy((void *)address, (void *)shadow(index), PAGE);
                            ++R->restore_pages;
                        } else {
                            record(index);
                        }
                    }
                }
                chunk += count * PAGE;
            }
        }
        if (!saved) {
            break;
        }
        line = end + 1;
    }
}
void clear_dirty() {
    if (call(SYS_write, R->clear_refs, (long)"4", 1) != 1) {
        die("soft-dirty reset unavailable");
    }
}
void close_state(State &s) {
    for (int i = 0; i < s.count; ++i) {
        if (s.descriptors[i].backup >= 0) {
            call(SYS_close, s.descriptors[i].backup);
        }
    }
    s.count = 0;
}
void save_files(State &s) {
    s.count = 0;
    for (int fd = 3; fd < 1024; ++fd) {
        struct stat st{};
        if (call(SYS_fstat, fd, (long)&st) < 0) {
            continue;
        }
        if (!S_ISREG(st.st_mode)) {
            die("unsupported compiler descriptor at checkpoint");
        }
        if (s.count == MAX_FDS) {
            die("too many compiler files");
        }
        auto &d = s.descriptors[s.count++];
        d.fd = fd;
        d.position = call(SYS_lseek, fd, 0, SEEK_CUR);
        d.flags = call(SYS_fcntl, fd, F_GETFL);
        d.fd_flags = call(SYS_fcntl, fd, F_GETFD);
        d.backup = -1;
        char link[64];
        path_number(link, "/proc/self/fd/", fd, "");
        long n = call(SYS_readlink, (long)link, (long)d.path, sizeof(d.path) - 1);
        if (n < 0 || d.position < 0) {
            die("cannot save compiler descriptor");
        }
        d.path[n] = 0;
        U path_size = length(d.path);
        bool memory_output = equal(d.path, "/memfd:bako-page-output", 23);
        d.pdf = (path_size >= 9 && equal(d.path + path_size - 9, "/main.pdf", 9)) || memory_output;
        if ((d.flags & O_ACCMODE) != O_RDONLY) {
            char cwd[4096];
            if (call(SYS_getcwd, (long)cwd, sizeof(cwd)) < 0) {
                die("cannot resolve session");
            }
            U len = length(cwd);
            if (!memory_output && (!equal(d.path, cwd, len) || d.path[len] != '/')) {
                die("writable file outside session");
            }
            int original = open_file(link, O_RDONLY);
            if (original < 0) {
                die("cannot retain output inode");
            }
            d.backup = call(SYS_fcntl, original, F_DUPFD_CLOEXEC, 1024);
            call(SYS_close, original);
            if (d.backup < 0) {
                die("cannot retain output inode");
            }
        }
    }
}
void restore_files(State &s) {
    // Close transient compiler descriptors. Runtime descriptors use >=1024.
    for (int fd = 3; fd < 1024; ++fd) {
        call(SYS_close, fd);
    }
    if (R->pdf >= 0) {
        call(SYS_close, R->pdf);
        R->pdf = -1;
    }
    for (int i = 0; i < s.count; ++i) {
        auto &d = s.descriptors[i];
        int mode = d.flags & O_ACCMODE;
        int fd = d.pdf ? call(SYS_memfd_create, (long)"bako-page-output", MFD_CLOEXEC)
                       : open_file(d.path, mode);
        bool copy_output = d.pdf;
        if (fd < 0 && mode != O_RDONLY) {
            fd = open_file(d.path, mode | O_CREAT | O_EXCL);
            copy_output = true;
        }
        if (fd < 0) {
            die("cannot reopen compiler file");
        }
        if (copy_output) {
            for (long pos = 0; pos < d.position;) {
                long size = d.position - pos;
                if (size > long(sizeof(R->io))) {
                    size = sizeof(R->io);
                }
                long n = call(SYS_pread64, d.backup, (long)R->io, size, pos);
                if (n <= 0) {
                    die("cannot restore output prefix");
                }
                long written = 0;
                while (written < n) {
                    long w =
                        call(SYS_pwrite64, fd, (long)R->io + written, n - written, pos + written);
                    if (w <= 0) {
                        die("cannot restore output bytes");
                    }
                    written += w;
                }
                pos += n;
            }
        }
        if (mode != O_RDONLY && call(SYS_ftruncate, fd, d.position) < 0) {
            die("cannot truncate output");
        }
        if (call(SYS_lseek, fd, d.position, SEEK_SET) < 0 || call(SYS_dup2, fd, d.fd) < 0) {
            die("cannot restore file position");
        }
        if (call(SYS_fcntl, d.fd, F_SETFL, d.flags) < 0 ||
            call(SYS_fcntl, d.fd, F_SETFD, d.fd_flags) < 0) {
            die("cannot restore file flags");
        }
        if (fd != d.fd) {
            call(SYS_close, fd);
        }
        if (d.pdf) {
            R->pdf = call(SYS_fcntl, d.fd, F_DUPFD_CLOEXEC, 1024);
        }
    }
}
void restore(int target, int limit) {
    R->request_us = now();
    R->restore_pages = 0;
    R->restore_bytes = 0;
    int position = -1;
    for (int i = 0; i < R->count; ++i) {
        if (R->states[i].index == target) {
            position = i;
        }
    }
    if (position < 0) {
        die("requested checkpoint is unavailable");
    }
    auto &s = R->states[position];
    scan(true);
    R->scan_us = now() - R->request_us;
    U end = R->used, begin = s.journal
                                 ? s.journal + sizeof(Undo) + ((Undo *)(R->base + s.journal))->size
                                 : JOURNAL_OFFSET;
    ++R->generation;
    // Earliest undo bytes after the target are the target's bytes. Apply each
    // 16-byte block once, even when fifty later pages changed it repeatedly.
    // Then install each affected compiler page once. This avoids replaying
    // hundreds of MB of intermediate states during a jump to an early page.
    for (U cursor = begin; cursor < end;) {
        auto *u = (Undo *)(R->base + cursor);
        cursor += sizeof(Undo) + u->size;
        if (u->page >= s.pages) {
            continue;
        }
        auto &page = R->pages[u->page];
        if (page.generation != R->generation) {
            page.generation = R->generation;
            for (auto &bits : page.seen) {
                bits = 0;
            }
        }
        if ((page.seen[0] & page.seen[1] & page.seen[2] & page.seen[3]) == ~0UL) {
            continue;
        }
        if (u->size == PAGE && !(page.seen[0] | page.seen[1] | page.seen[2] | page.seen[3])) {
            copy((void *)shadow(u->page), u + 1, PAGE);
            for (auto &bits : page.seen) {
                bits = ~0UL;
            }
            R->restore_bytes += PAGE;
            continue;
        }
        U offset = u->address & (PAGE - 1), block = offset / 16, last = block + u->size / 16;
        while (block < last) {
            if (page.seen[block / 64] & (1UL << (block % 64))) {
                ++block;
                continue;
            }
            U first = block;
            do {
                page.seen[block / 64] |= 1UL << (block % 64);
                ++block;
            } while (block < last && !(page.seen[block / 64] & (1UL << (block % 64))));
            U size = (block - first) * 16;
            copy((void *)(shadow(u->page) + first * 16), (char *)(u + 1) + first * 16 - offset,
                 size);
            R->restore_bytes += size;
        }
    }
    for (U i = 0; i < s.pages; ++i) {
        if (R->pages[i].generation == R->generation) {
            copy((void *)R->pages[i].address, (void *)shadow(i), PAGE);
        }
    }
    R->used = begin;
    R->journal = s.journal;
    U release = (begin + PAGE - 1) & ~(PAGE - 1);
    if (end > release) {
        call(SYS_madvise, R->base + release, end - release, MADV_DONTNEED);
    }
    R->undo_us = now() - R->request_us - R->scan_us;
    // The malloc arena has been restored; restore its kernel program break too.
    if (call(SYS_brk, s.brk) != long(s.brk)) {
        die("cannot restore compiler heap extent");
    }
    if (R->page_count > s.pages) {
        call(SYS_madvise, shadow(s.pages), (R->page_count - s.pages) * PAGE, MADV_DONTNEED);
        R->page_count = s.pages;
        for (U i = 0; i < HASH_SIZE; ++i) {
            R->hash[i] = 0;
        }
        for (U i = 0; i < R->page_count; ++i) {
            U slot = hash(R->pages[i].address);
            while (R->hash[slot]) {
                slot = (slot + 1) & (HASH_SIZE - 1);
            }
            R->hash[slot] = i + 1;
        }
    }
    for (int i = position + 1; i < R->count; ++i) {
        char p[64];
        path_number(p, "cp-", R->states[i].index, ".snap");
        call(SYS_unlink, (long)p);
        close_state(R->states[i]);
    }
    R->count = position + 1;
    long before_files = now();
    restore_files(s);
    R->files_us = now() - before_files;
    R->limit = limit;
    R->mode = 1;
    clear_dirty();
    R->restored_us = now();
    bako_jump(&s.context);
}
void receive() {
    for (;;) {
        int fd = call(SYS_accept, R->server, 0, 0);
        if (fd < 0) {
            continue;
        }
        char buffer[64]{};
        long n = call(SYS_read, fd, (long)buffer, sizeof(buffer) - 1);
        call(SYS_close, fd);
        if (n <= 0) {
            continue;
        }
        int target = 0, limit = 0;
        char *p = buffer;
        while (*p >= '0' && *p <= '9') {
            target = target * 10 + (*p++ - '0');
        }
        if (*p++ != ' ') {
            continue;
        }
        while (*p >= '0' && *p <= '9') {
            limit = limit * 10 + (*p++ - '0');
        }
        if (target > 0 && limit > 0 && limit <= 10000) {
            restore(target, limit);
        }
    }
}
void checkpoint_control() {
    long started = now();
    if (R->count == MAX_STATES) {
        die("too many internal checkpoints");
    }
    scan(false);
    auto &s = R->states[R->count];
    s.index = R->input;
    s.journal = R->journal;
    s.pages = R->page_count;
    s.brk = call(SYS_brk, 0);
    save_files(s);
    char path[64], value[32];
    path_number(path, "cp-", s.index, ".snap");
    number(value, call(SYS_getpid));
    file_text(path, value);
    ++R->count;
    clear_dirty();
    R->capture_us = now() - started;
}
int high(int fd) {
    if (fd < 0) {
        die("cannot open snapshot control descriptor");
    }
    int out = call(SYS_fcntl, fd, F_DUPFD_CLOEXEC, 1024);
    call(SYS_close, fd);
    if (out < 0) {
        die("cannot reserve snapshot descriptor");
    }
    return out;
}
void initialize() {
    U base = call(SYS_mmap, 0, ARENA_SIZE, PROT_READ | PROT_WRITE,
                  MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (base > U(-4096)) {
        die("cannot reserve snapshot memory");
    }
    R = (Runtime *)base;
    R->base = base;
    R->used = JOURNAL_OFFSET;
    R->limit = 100;
    R->pdf = -1;
    static_assert(sizeof(Runtime) < SHADOW_OFFSET, "snapshot metadata overlaps shadow");
    int tasks = open_file("/proc/self/task", O_RDONLY | O_DIRECTORY), threads = 0;
    if (tasks < 0) {
        die("cannot inspect compiler threads");
    }
    long n;
    while ((n = call(SYS_getdents64, tasks, (long)R->io, sizeof(R->io))) > 0) {
        for (long at = 0; at < n;) {
            unsigned short size = *(unsigned short *)(R->io + at + 16);
            if (size < 20 || at + size > n) {
                die("invalid task listing");
            }
            if (R->io[at + 19] != '.') {
                ++threads;
            }
            at += size;
        }
    }
    call(SYS_close, tasks);
    if (threads != 1) {
        die("internal snapshots require a single compiler thread");
    }
    R->pagemap = high(open_file("/proc/self/pagemap", O_RDONLY));
    R->clear_refs = high(open_file("/proc/self/clear_refs", O_WRONLY));
    R->server = high(call(SYS_socket, AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0));
    sockaddr_un a{};
    a.sun_family = AF_UNIX;
    copy(a.sun_path, "internal.sock", 14);
    call(SYS_unlink, (long)a.sun_path);
    if (call(SYS_bind, R->server, (long)&a, sizeof(a)) < 0 || call(SYS_listen, R->server, 4) < 0) {
        die("cannot bind internal control socket");
    }
    char pid[32];
    number(pid, call(SYS_getpid));
    file_text("active.pid", pid);
    R->armed = true;
}
void *stack() {
    return R->stack + sizeof(R->stack) - 64;
}
} // namespace

extern "C" int bako_internal_checkpoint(int index) {
    if (!R) {
        initialize();
    }
    if (index > R->limit) {
        return R->limit;
    }
    if (R->count == MAX_STATES) {
        die("too many internal checkpoints");
    }
    R->input = index;
    // The context and controller memory survive all restores. This point is
    // before Lua returns from the checkpoint callback, at a fixed C boundary.
    if (bako_save(&R->states[R->count].context)) {
        return R->limit;
    }
    bako_control(stack(), checkpoint_control);
    return R->limit;
}
extern "C" void bako_internal_park() {
    if (R && R->armed) {
        bako_control(stack(), receive);
    }
}
extern "C" int bako_internal_pending() {
    // A page publisher was SIGSTOPped. SIGCONT means either export continuation
    // or an already-queued rollback command; poll distinguishes the two.
    if (!R) {
        return 0;
    }
    struct {
        int fd;
        short events, revents;
    } p{R->server, 1, 0};
    if (call(SYS_poll, (long)&p, 1, 0) > 0) {
        bako_internal_park();
    }
    return 0;
}
extern "C" int bako_internal_live() {
    return R ? R->mode : 0;
}
extern "C" int bako_internal_pdf() {
    return R ? R->pdf : -1;
}
extern "C" long bako_internal_request() {
    return R ? R->request_us : 0;
}
extern "C" long bako_internal_restored() {
    return R ? R->restored_us : 0;
}
extern "C" long bako_internal_stat(int key) {
    if (!R) {
        return 0;
    }
    switch (key) {
    case 0:
        return R->count;
    case 1:
        return R->used - JOURNAL_OFFSET;
    case 2:
        return R->page_count * PAGE;
    case 3:
        return R->restore_pages;
    case 4:
        return R->restore_bytes;
    case 5:
        return R->scan_us;
    case 6:
        return R->undo_us;
    case 7:
        return R->files_us;
    case 8:
        return R->capture_us;
    default:
        return 0;
    }
}
extern "C" __attribute__((noreturn)) void exit(int status) {
    if (R && R->armed) {
        file_text("failed.json", "{\"failed\":true}");
        bako_internal_park();
    }
    auto real_exit = (void (*)(int))dlsym(RTLD_NEXT, "exit");
    if (real_exit) {
        real_exit(status);
    }
    call(SYS_exit_group, status);
    __builtin_unreachable();
}
