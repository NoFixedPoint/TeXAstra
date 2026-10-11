#pragma once
#include "renderer.hpp"
#include "cache.hpp"
#include "build_tools.hpp"
#include <functional>
extern char **environ;

namespace bako {
struct RebuildRequired : std::runtime_error { using std::runtime_error::runtime_error; };
struct ProjectOptions {
    std::string main = "main.tex", mode = "auto", compiler = "lualatex";
};
class Engine {
    fs::path project, assets, runtime, mirror, main_parent;
    ProjectOptions options;
    bool full = false;
    bool full_ready = false;
    bool live = false;
    bool live_edit_failed = false;
    std::unique_ptr<BuildCache> cache;
    std::set<fs::path> known_inputs;
    Fd listener, directory_fd;
    Fd resource_channel;
    pid_t process = -1;
    std::map<int, PageBuffer> buffers;
    std::map<int, std::vector<int>> page_ids;
    std::set<int> available;
    std::string seed_pdf;
    unsigned revision = 0;
    bool converged = false;
    bool build_limited = false;
    std::unique_ptr<BuildTools> build_tools;
    int log_fd = -1;
    static std::string extension(const fs::path &file) {
        auto value = file.extension().string();
        std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return std::tolower(c); });
        return value;
    }
    static void kill_pid(pid_t pid) {
        if (pid > 0) {
            kill(pid, SIGTERM);
            kill(pid, SIGCONT);
        }
    }
    pid_t active() const {
        try {
            return std::stoi(read(directory / "active.pid"));
        } catch (...) {
            return -1;
        }
    }
    static char state(pid_t pid) {
        try {
            auto s = read(fs::path("/proc") / std::to_string(pid) / "stat");
            return s.at(s.rfind(") ") + 2);
        } catch (...) {
            return 'Z';
        }
    }
    void cleanup_after(int index) {
        kill_pid(active());
        for (const auto &entry : fs::directory_iterator(directory)) {
            auto name = entry.path().filename().string();
            if (starts(name, "cp-") && entry.path().extension() == ".pid") {
                int n = std::stoi(name.substr(3));
                if (n > index) {
                    kill_pid(std::stoi(read(entry.path())));
                    fs::remove(entry.path());
                    fs::remove(directory / page_name(n, "cp-", ".sock"));
                }
            }
        }
    }
    void stop_process() {
        if (process > 0) {
            kill(-process, SIGKILL);
            while (waitpid(process, nullptr, 0) < 0 && errno == EINTR) {
            }
            process = -1;
        }
    }
    pid_t spawn(bool prime) {
        posix_spawn_file_actions_t actions;
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addchdir_np(&actions, directory.c_str());
        posix_spawn_file_actions_adddup2(&actions, log_fd, 1);
        posix_spawn_file_actions_adddup2(&actions, log_fd, 2);
        // The integrated renderer can hold PDF descriptors whose original
        // inode was unlinked by a failed TeX run. They are not TeX inputs and
        // must never enter a compiler checkpoint's descriptor snapshot.
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0);
        posix_spawn_file_actions_addclosefrom_np(&actions, 3);
        posix_spawnattr_t attr;
        posix_spawnattr_init(&attr);
        posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETSID);
        std::vector<std::string> env;
        for (char **e = environ; *e; ++e) {
            if (full && starts(*e, "openout_any=")) continue;
            if (!starts(*e, "BAKO_PAGE_STREAM=") && !starts(*e, "BAKO_FONT_STREAM=") && !starts(*e, "BAKO_SOURCE_MARKERS=") && !starts(*e, "BAKO_SNAPSHOT_DISABLE=") && !starts(*e, "BAKO_LIVE_DOCUMENT=")) {
                env.emplace_back(*e);
            }
        }
        env.emplace_back("BAKO_PAGE_STREAM=1");
        env.emplace_back("BAKO_FONT_STREAM=1");
        env.emplace_back("BAKO_SOURCE_MARKERS=1");
        // A relocatable engine must find the installed distro's TeX trees.
        if (!getenv("TEXMFCNF")) env.emplace_back("TEXMFCNF=/etc/texmf/web2c:/usr/local/share/texmf/web2c:/usr/share/texlive/texmf-dist/web2c");
        if (live) env.emplace_back("BAKO_LIVE_DOCUMENT=1");
        if (full) env.emplace_back("openout_any=p");
        if (prime) {
            env.emplace_back("BAKO_SNAPSHOT_DISABLE=1");
        }
        std::vector<char *> envp;
        for (auto &s : env) {
            envp.push_back(s.data());
        }
        envp.push_back(nullptr);
        std::vector<std::string> arguments = full
            ? std::vector<std::string>{options.compiler, "-no-shell-escape", "-interaction=nonstopmode",
                                       "-halt-on-error", "-file-line-error", "-recorder", "./" + fs::path(options.main).filename().string()}
            : std::vector<std::string>{(runtime / "bakoma-luahbtex").string(), "--fmt=lualatex", "--progname=lualatex", "--shell-escape", "-interaction=nonstopmode",
                                       "-halt-on-error", "-recorder", "--jobname=main", live ? "bako-driver.tex" : "main.tex"};
        std::vector<char *> argv;
        for (auto &argument : arguments) argv.push_back(argument.data());
        argv.push_back(nullptr);
        pid_t pid = -1;
        int error = posix_spawnp(&pid, arguments[0].c_str(), &actions, &attr, argv.data(),
                                 envp.data());
        posix_spawn_file_actions_destroy(&actions);
        posix_spawnattr_destroy(&attr);
        if (error) {
            throw std::runtime_error("Cannot start " + arguments[0] + ": " + strerror(error));
        }
        return pid;
    }
    std::vector<int> ids(int page) {
        sources.ranges(directory / page_name(page+1,"origins-",".txt"));
        std::vector<int> out;
        std::ifstream in(directory / page_name(page + 1, "geometry-", ".jsonl"));
        int n;
        while (in >> n) {
            out.push_back(n);
        }
        // Rules have origins but no glyph entry in the legacy sidecar.
        // Include their IDs in the page index used by forward navigation.
        std::ifstream origins(directory / page_name(page+1,"origins-",".txt"));
        int length;
        while (origins >> n >> length) out.push_back(n);
        return out;
    }
    static std::string commands(const std::string &raw) {
        size_t position = 0;
        std::string result;
        bool found = false;
        while ((position = raw.find("stream\n", position)) != std::string::npos) {
            size_t body = position + 7, object = raw.rfind(" 0 obj", position);
            position = body;
            if (object == std::string::npos || body - object > 4096) {
                continue;
            }
            auto header = raw.substr(object, body - object);
            if (header.find("endobj") != std::string::npos ||
                header.find("/Filter") != std::string::npos) {
                continue;
            }
            std::smatch match;
            static const std::regex length(R"(/Length\s+(\d+)\s*(>>|/))");
            if (!std::regex_search(header, match, length)) {
                continue;
            }
            size_t count = std::stoull(match[1]);
            if (count > raw.size() - body) {
                throw std::runtime_error("Incomplete page stream");
            }
            size_t tail = body + count;
            while (tail < raw.size() && std::isspace(static_cast<unsigned char>(raw[tail]))) {
                ++tail;
            }
            if (raw.compare(tail, 9, "endstream") != 0) {
                throw std::runtime_error("Invalid page stream length");
            }
            result = raw.substr(body, count);
            found = true;
            position = tail + 9;
        }
        if (!found) {
            throw std::runtime_error("No drawing stream in page buffer");
        }
        return result;
    }
    Json receive() {
        Fd client(accept4(listener.value, nullptr, nullptr, SOCK_CLOEXEC));
        if (client.value < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                return nullptr;
            }
            throw std::runtime_error("Page socket accept failed");
        }
        timeval timeout = {10, 0};
        setsockopt(client.value, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        std::string header;
        while (header.size() < 100) {
            auto c = receive_exact(client.value, 1);
            if (c == "\n") {
                break;
            }
            header += c;
        }
        size_t meta_size = 0, byte_size = 0;
        std::istringstream lengths(header);
        lengths >> meta_size >> byte_size;
        if (!meta_size || meta_size >= 8000000 || !byte_size || byte_size >= 64000000) {
            throw std::runtime_error("Invalid page message size");
        }
        auto metadata = Json::parse(receive_exact(client.value, meta_size));
        auto raw = receive_exact(client.value, byte_size);
        size_t offset = 0;
        for (auto page : metadata.at("pages")) {
            size_t size = page.at("byteLength");
            if (size > raw.size() - offset) {
                throw std::runtime_error("Invalid page lengths");
            }
            int n = page.at("page");
            buffers[n] = {page, commands(raw.substr(offset, size)), ids(n)};
            offset += size;
        }
        if (offset != raw.size()) {
            throw std::runtime_error("Page lengths disagree");
        }
        auto pid = active();
        auto deadline = Clock::now();
        while (state(pid) != 'T') {
            if (elapsed(deadline) > 1000) {
                throw std::runtime_error("Page publisher did not suspend");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        resource_channel = std::move(client);
        return {{"streamed", true},
                {"snapshot", metadata.value("snapshot", Json::object())},
                {"compilerStagesMs", metadata.value("compilerStagesMs", Json::object())}};
    }
    Json wait_done(bool stream) {
        auto start = Clock::now();
        while (elapsed(start) < 90000) {
            if (cancel && cancel->load()) {
                throw std::runtime_error("Build cancelled");
            }
            if (fs::exists(directory / "failed.json")) {
                throw std::runtime_error("TeX compilation failed: " + error_log());
            }
            auto value = receive();
            if (!value.is_null()) {
                if (stream) return value;
                // Resource refresh can ship more pages before final export.
                // Drain and resume each publisher instead of waiting on a
                // compiler suspended at its next paragraph boundary.
                resource_channel = Fd();
                kill(active(), SIGCONT);
            }
            if (fs::exists(directory / "completed.json")) {
                try {
                    auto pdf = read(directory / "main.pdf");
                    if (pdf.size() > 100 &&
                        pdf.find("%%EOF", pdf.size() - 100) != std::string::npos) {
                        return Json::parse(read(directory / "completed.json"));
                    }
                } catch (const std::exception &) {
                }
            }
            if (elapsed(start) > 250) {
                if (process > 0 && state(process) == 'Z') {
                    throw std::runtime_error("Compiler process exited: " + error_log());
                }
                auto pid = active();
                if (pid > 0 && state(pid) == 'Z') {
                    throw std::runtime_error("TeX compilation failed: " + error_log());
                }
            }
            pollfd fd = {listener.value, POLLIN, 0};
            poll(&fd, 1, 2);
        }
        throw std::runtime_error("TeX timeout: " + error_log());
    }
    std::string error_log() const {
        auto log = read(directory / "engine-output.log");
        return log.substr(log.size() > 3000 ? log.size() - 3000 : 0);
    }
    void seed(const Json &result) {
        seed_pdf = read(directory / "main.pdf");
        std::set<std::string> coverage;
        int count = result.value("compiledPages", 10000);
        for (const auto &entry : fs::directory_iterator(directory)) {
            auto name = entry.path().filename().string();
            if (starts(name, "resources-") && entry.path().extension() == ".json" &&
                std::stoi(name.substr(10)) <= count) {
                auto record = Json::parse(read(entry.path()));
                for (const auto &value : record.at("coverage")) {
                    coverage.insert(value.get<std::string>());
                }
            }
        }
        renderer.seed(directory / "main.pdf", std::move(coverage));
        available.clear();
        buffers.clear();
        page_ids.clear();
        for (int page = 0; page < renderer.pages(); ++page) {
            page_ids[page] = ids(page);
            available.insert(page);
        }
    }
    Json finish(int page, Json result) {
        auto started = Clock::now();
        auto seed_result = wait_done(false);
        seed(seed_result);
        result["resourceRefreshMs"] = elapsed(started);
        auto frame = renderer.render(page, sources, page_ids[page]);
        frame.update(result);
        frame["outputMode"] = "resource-seed";
        return frame;
    }
    Json display(int page, Json result) {
        auto buffer = buffers.find(page);
        if (result.value("streamed", false) && buffer != buffers.end()) {
            try {
                try { renderer.update(buffer->second); }
                catch (const FontResourceMiss &) {
                    auto started = Clock::now();
                    const auto bytes = request_fonts(buffer->second);
                    renderer.import_fonts(buffer->second, bytes);
                    renderer.update(buffer->second);
                    result["fontRefreshMs"] = elapsed(started);
                    result["fontResourceBytes"] = bytes.size();
                }
            } catch (const ResourceMiss &e) {
                resource_channel = Fd();
                kill(active(), SIGCONT);
                result["resourceRefresh"] = e.what();
                return finish(page, std::move(result));
            }
            page_ids[page] = buffer->second.ids;
            for (const auto &item : buffers) {
                available.insert(item.first);
            }
            auto frame = renderer.render(page, sources, buffer->second.ids);
            frame.update(result);
            frame["outputMode"] = "page-stream";
            frame["pageBytes"] = buffer->second.commands.size();
            return frame;
        }
        if (result.value("streamed", false)) {
            throw std::runtime_error("Requested physical page was not produced");
        }
        seed(result);
        auto frame = renderer.render(page, sources, page_ids[page]);
        frame.update(result);
        frame["outputMode"] = "resource-seed";
        return frame;
    }
    std::string request_fonts(const PageBuffer &buffer) {
        if (resource_channel.value < 0) throw ResourceMiss("Font resource channel unavailable");
        std::string command = "fonts";
        std::set<int> requested;
        static const std::regex font_id(R"(^F([1-9]\d*)[^\s/]*$)");
        for (const auto &name : Renderer::font_names(buffer)) {
            std::smatch match;
            if (!std::regex_match(name, match, font_id)) throw ResourceMiss("Unsupported font resource name");
            requested.insert(std::stoi(match[1]));
        }
        if (requested.empty() || requested.size() > 256) throw ResourceMiss("Unsupported font resource count");
        for (int id : requested) command += " " + std::to_string(id);
        command += "\n";
        std::string bytes;
        try {
            // The exporter child has a ten-second deadline; allow its parent
            // time to report failure and park before resuming the fallback.
            timeval timeout = {15, 0};
            setsockopt(resource_channel.value, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
            send_all(resource_channel.value, command);
            kill(active(), SIGCONT);
            std::string header;
            while (header.size() < 32) {
                auto c = receive_exact(resource_channel.value, 1);
                if (c == "\n") break;
                header += c;
            }
            size_t size = std::stoull(header);
            if (size > 32 * 1024 * 1024) throw ResourceMiss("Invalid font resource size");
            bytes = receive_exact(resource_channel.value, size);
            auto started = Clock::now();
            while (state(active()) != 'T') {
                if (elapsed(started) > 1000) throw ResourceMiss("Font publisher did not suspend");
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        } catch (const std::exception &e) { throw ResourceMiss(std::string("Font export failed: ") + e.what()); }
        if (bytes.empty()) throw ResourceMiss("Font export is unsupported for this page");
        return bytes;
    }
    Json resume(int input, int page) {
        auto started = Clock::now();
        if (live) remember_inputs();
        int index = 0;
        for (const auto &entry : fs::directory_iterator(directory)) {
            auto name = entry.path().filename().string();
            if (starts(name, "cp-") && entry.path().extension() == ".pid") {
                int n = std::stoi(name.substr(3));
                if (n <= input) {
                    index = std::max(index, n);
                }
            }
        }
        if (!index) {
            throw std::runtime_error("No compiler checkpoint before edit");
        }
        cleanup_after(index);
        for (auto it = buffers.lower_bound(index - 1); it != buffers.end();) {
            it = buffers.erase(it);
        }
        fs::remove(directory / "completed.json");
        fs::remove(directory / "failed.json");
        Fd fd(socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0));
        sockaddr_un address = {};
        address.sun_family = AF_UNIX;
        auto path =
            (fs::path("/proc/self/fd") / std::to_string(directory_fd.value) / page_name(index, "cp-", ".sock")).string();
        if (path.size() >= sizeof(address.sun_path)) {
            throw std::runtime_error("Checkpoint socket path too long");
        }
        strcpy(address.sun_path, path.c_str());
        if (connect(fd.value, reinterpret_cast<sockaddr *>(&address), sizeof(address))) {
            throw std::runtime_error("Cannot connect to checkpoint");
        }
        send_all(fd.value,
                 std::to_string(page + 1));
        auto resumed = Clock::now();
        auto result = wait_done(true);
        result["compileMs"] = elapsed(resumed);
        result["prepareMs"] = std::chrono::duration<double, std::milli>(resumed - started).count();
        result["resumedFrom"] = index;
        return display(page, std::move(result));
    }
    void remember_inputs() {
        std::ifstream journal(directory / "bako-inputs.jsonl");
        if (!journal) throw RebuildRequired("Input dependency journal unavailable");
        std::string line;
        while (std::getline(journal, line)) {
            auto event = Json::parse(line, nullptr, false);
            if (!event.is_array() || event.size() != 2 || !event[0].is_number_integer() || !event[1].is_string())
                throw RebuildRequired("Input dependency journal incomplete");
            auto path = fs::weakly_canonical(directory / event[1].get<std::string>());
            known_inputs.insert(path);
        }
    }
    int checkpoint_before(const std::string &file, size_t changed) {
        const auto target = fs::weakly_canonical(inside(mirror, file));
        remember_inputs();
        if (!known_inputs.count(target)) throw RebuildRequired("Included file has no recorded body dependency");
        int checkpoint = 0;
        for (const auto &entry : fs::directory_iterator(directory)) {
            auto name = entry.path().filename().string();
            if (!starts(name,"cp-") || entry.path().extension()!=".meta") continue;
            int index = std::stoi(name.substr(3));
            if (!fs::exists(directory / page_name(index,"cp-", ".pid"))) continue;
            auto metadata = Json::parse(read(entry.path()), nullptr, false);
            if (!metadata.is_object() || metadata.value("kind", "") != "engine" ||
                !metadata.contains("inputs") || !metadata["inputs"].is_array())
                throw RebuildRequired("Checkpoint input metadata unavailable");
            size_t consumed = 0;
            for (const auto &input : metadata["inputs"]) {
                if (!input.is_array() || input.size()!=2 || !input[0].is_string() || !input[1].is_number_unsigned())
                    throw RebuildRequired("Checkpoint input metadata incomplete");
                if (fs::weakly_canonical(directory / input[0].get<std::string>()) == target)
                    consumed = std::max(consumed, input[1].get<size_t>());
            }
            if (consumed <= changed) checkpoint = std::max(checkpoint, index);
        }
        if (!checkpoint) throw RebuildRequired("Changed input was consumed before body checkpoints");
        return checkpoint;
    }
    void prepare(const std::map<std::string, std::string> &overlays) {
        std::vector<fs::path> files;
        for (auto it = fs::recursive_directory_iterator(project); it != fs::recursive_directory_iterator(); ++it) {
            const auto &entry = *it;
            if (entry.is_directory() && (starts(entry.path().filename().string(), ".") || entry.path().filename()=="node_modules")) {
                it.disable_recursion_pending();
                continue;
            }
            if (entry.is_regular_file()) {
                auto rel = entry.path().lexically_relative(project);
                bool hidden = false;
                for (const auto &part : rel) {
                    if (starts(part.string(), ".")) {
                        hidden = true;
                    }
                }
                if (!hidden && words(".tex .sty .cls .bib .bst .bbl .png .jpg .jpeg .pdf .eps .ps .otf .ttf .tfm .map .enc .cfg .def .clo .fd .ldf .bbx .cbx .lbx .ist .csv .dat .txt .lua")
                                   .count(extension(entry.path()))) {
                    files.push_back(rel);
                }
            }
        }
        std::sort(files.begin(), files.end());
        for (const auto &file : files) {
            auto name = file.generic_string();
            // Resolve containment before copying, including symlink targets.
            auto source = inside(project, name);
            fs::create_directories((mirror / file).parent_path());
            auto data = overlays.count(name) ? overlays.at(name) : read(source);
            // Match text-mode source loading on both platforms. Editor buffers
            // retain their supplied newlines so their source offsets stay exact.
            if (extension(file) == ".tex" && !overlays.count(name)) {
                replace_all(data, "\r\n", "\n");
                replace_all(data, "\r", "\n");
            }
            if (!full && extension(file) == ".tex" && (live || name != options.main)) {
                data = sources.index(data, name);
            }
            if (cache) {
                if (file != main_parent / (fs::path(options.main).stem().string()+".pdf") && file != main_parent / "main.pdf") cache->put(name, data);
            } else write(mirror / file, data);
        }
        // Unsaved, newly created project files may not exist on disk yet.
        for (const auto &[name, data] : overlays) {
            auto target = inside(mirror, name);
            if (full || live) {
                if (!full && extension(name)==".tex" && (live || name!=options.main)) sources.index(data,name);
                fs::create_directories(target.parent_path());
                if (cache) cache->put(name, data); else write(target, data);
            }
        }
        if (full) return;
        for (const auto *name : {"snapshot.lua", "page_stream.lua", "provenance.lua", "inputs.lua"}) {
            fs::copy_file(assets / name, directory / name, fs::copy_options::overwrite_existing);
        }
        fs::copy_file(runtime / "bako_snapshot.so", directory / "bako_snapshot.so",
                      fs::copy_options::overwrite_existing);
        if (live) {
            sources.manifest(directory / "bako-sources.tsv", mirror);
            write(directory / "bako-driver.tex",
                  "\\directlua{dofile('inputs.lua')}%\n"
                  "\\AtBeginDocument{\\directlua{dofile('provenance.lua');dofile('snapshot.lua');bako_live_begin()}}%\n"
                  "\\AtEndDocument{\\directlua{bako_live_end()}}%\n"
                  "\\input{\\detokenize{" + fs::path(options.main).filename().string() + "}}%\n");
            cache->inputs["@runtime"] = digest(read(assets / "snapshot.lua") + read(assets / "provenance.lua") + read(assets / "page_stream.lua") + read(assets / "inputs.lua") + read(runtime / "bakoma-backend") + read(runtime / "bakoma-luahbtex") + read(runtime / "bako_snapshot.so"));
            cache->finish_inputs();
            return;
        }
        auto root = read(directory / "main.tex");
        std::string warm = R"TEX(\begingroup\setbox0=\vbox{\hsize=\textwidth
{\Large\bfseries Acceptance}\par English 中文排版
$x+\frac{a_{1}+b^{2}}{c+d}+\alpha+\sum_{j=1}^{n}j+\int_{0}^{1}t^{2}\,dt$
\begin{tikzpicture}\draw (0,0)--(1,0);\node[rotate=15] at (0,0) {Label $x_{1}$};\end{tikzpicture}
}\immediate\saveboxresource0\endgroup
)TEX";
        replace_all(root, "\\begin{document}",
                    "\\directlua{dofile('provenance.lua')}\n\\directlua{dofile('snapshot.lua')}"
                    "\n\\begin{document}\n" +
                        warm + reset);
        std::regex input(R"(\\input\{pages/page-(\d+)\.tex\})");
        std::string patched;
        size_t previous = 0;
        for (auto it = std::sregex_iterator(root.begin(), root.end(), input);
             it != std::sregex_iterator(); ++it) {
            patched += root.substr(previous, it->position() - previous) +
                       "\\directlua{bako_checkpoint(" + std::to_string(std::stoi((*it)[1])) + ")}" +
                       it->str();
            previous = it->position() + it->length();
        }
        patched += root.substr(previous);
        write(directory / "main.tex", patched);
        sources.manifest(directory / "bako-sources.tsv");
    }

    Json full_frame(int page) {
        auto frame = renderer.render(page, sources, {}, false);
        frame["ok"] = true;
        frame["provisional"] = !converged;
        frame["outputMode"] = "full-build";
        frame["sourceSync"] = "unavailable";
        frame["compiler"] = options.compiler;
        frame["session"] = directory.string();
        build_tools->annotate(frame, fs::path(options.main).stem().string(), converged);
        return frame;
    }

    Json full_start(int page) {
        build_tools->reset();
        auto started = Clock::now();
        auto stem = fs::path(options.main).stem().string();
        full_ready = false;
        // Keep any renderer's open PDF inode immutable while the next run writes.
        fs::remove(directory / (stem + ".pdf"));
        converged = false;
        int passes = 0;
        for (; passes < 6; ++passes) {
            auto previous_aux = build_tools->state();
            process = spawn(true);
            auto run = Clock::now();
            int status = 0;
            for (;;) {
                auto ended = waitpid(process, &status, WNOHANG);
                if (ended == process) break;
                if (ended < 0 && errno != EINTR) throw std::runtime_error("Cannot wait for compiler");
                if ((cancel && cancel->load()) || elapsed(run) > 90000) {
                    stop_process();
                    throw std::runtime_error("Compilation cancelled or timed out");
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }
            process = -1;
            if (!WIFEXITED(status) || WEXITSTATUS(status))
                throw std::runtime_error(options.compiler + " failed: " + error_log());
            bool tools_changed = build_tools->update(stem);
            if (!tools_changed && build_tools->state() == previous_aux) {
                converged = true;
                ++passes;
                break;
            }
        }
        renderer.seed(directory / (stem + ".pdf"), {});
        if (!renderer.pages()) throw std::runtime_error("The document produced no pages");
        full_ready = true;
        auto result = full_frame(page);
        result["compileMs"] = elapsed(started) - result["renderMs"].get<double>();
        result["pipelineMs"] = elapsed(started);
        result["passes"] = passes;
        return result;
    }

  public:
    fs::path directory;
    unsigned generation = 0;
    Sources sources;
    Renderer renderer;
    std::atomic<bool> *cancel = nullptr;
    Engine(fs::path p, fs::path a, fs::path r,
           const std::map<std::string, std::string> &overlays = {},
           std::atomic<bool> *stop = nullptr, ProjectOptions config = {})
        : project(fs::canonical(p)), assets(std::move(a)), runtime(std::move(r)), options(std::move(config)), cancel(stop) {
        if (options.main.empty() || fs::path(options.main).is_absolute())
            throw std::runtime_error("Main file must be relative to and inside the project root");
        auto root = read(inside(project, options.main));
        options.main = fs::path(options.main).lexically_normal().generic_string();
        main_parent = fs::path(options.main).parent_path();
        const bool fixture = options.main == "main.tex" && root.find("\\input{pages/page-001.tex}") != std::string::npos &&
            root.find("\\newcommand{\\globalword}{global}") != std::string::npos &&
            root.find("\\usepackage{tikz}") != std::string::npos;
        if (!words("auto full incremental").count(options.mode) ||
            !words("lualatex xelatex pdflatex").count(options.compiler))
            throw std::runtime_error("Invalid preview mode or LaTeX compiler");
        full = options.mode == "full";
        live = !full && !fixture;
        if (!full) options.compiler = "lualatex";
        if (live) {
            cache = std::make_unique<BuildCache>(project, options.main+":live", options.compiler, main_parent);
            mirror = cache->directory;
            directory = mirror / main_parent;
            fs::create_directories(directory);
            // Persistent files are data, not evidence that old PIDs still belong
            // to us. Remove stale checkpoint markers without signalling them.
            for (const auto &entry : fs::directory_iterator(directory)) {
                auto name = entry.path().filename().string();
                if (starts(name,"cp-") || name=="active.pid" || name=="pages.sock" || name=="internal.sock" ||
                    name=="completed.json" || name=="failed.json") fs::remove(entry.path());
            }
        } else {
            char name[] = "/tmp/bakoma-cpp-XXXXXX";
            auto path = mkdtemp(name);
            if (!path) throw std::runtime_error("Cannot create session");
            mirror = path;
            directory = mirror / main_parent;
            fs::create_directories(directory);
        }
        try {
            prepare(overlays);
            build_tools = std::make_unique<BuildTools>(directory, cancel, fs::path(options.main).stem().string());
            listener = Fd(socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0));
            sockaddr_un address = {};
            address.sun_family = AF_UNIX;
            // Resolve through a retained directory descriptor so deep project
            // paths do not overflow sockaddr_un's small pathname field.
            directory_fd = Fd(open(directory.c_str(), O_PATH | O_DIRECTORY | O_CLOEXEC));
            if (directory_fd.value < 0) throw std::runtime_error("Cannot open compiler directory");
            auto socket_path = (fs::path("/proc/self/fd") / std::to_string(directory_fd.value) / "pages.sock").string();
            strcpy(address.sun_path, socket_path.c_str());
            if (listener.value < 0 ||
                bind(listener.value, reinterpret_cast<sockaddr *>(&address), sizeof(address)) ||
                listen(listener.value, 4)) {
                throw std::runtime_error("Cannot bind page socket");
            }
            log_fd = open((directory / "engine-output.log").c_str(),
                          O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
            if (log_fd < 0) {
                throw std::runtime_error("Cannot open engine log");
            }
        } catch (...) {
            if (log_fd >= 0) {
                close(log_fd);
            }
            throw;
        }
    }
    ~Engine() {
        try {
            cleanup_after(0);
        } catch (...) {
        }
        stop_process();
        if (log_fd >= 0) {
            close(log_fd);
        }
    }
    Json start(int page = 0) {
        if (full) return full_start(page);
        auto started = Clock::now();
        const bool reuse = cache && cache->reusable(directory / "main.pdf", "lualatex");
        if (cache) cache->invalidate();
        if (!reuse) {
        process = spawn(true);
        auto start = Clock::now();
        int status = 0;
        for (;;) {
            auto ended = waitpid(process, &status, WNOHANG);
            if (ended == process) {
                break;
            }
            if (ended < 0) {
                if (errno == EINTR) {
                    continue;
                }
                throw std::runtime_error("Cannot wait for initial compiler process");
            }
            if ((cancel && cancel->load()) || elapsed(start) > 90000) {
                stop_process();
                throw std::runtime_error("Initial compilation cancelled or timed out");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        process = -1;
        if (!WIFEXITED(status) || WEXITSTATUS(status)) {
            throw std::runtime_error("Initial TeX compilation failed: " + error_log());
        }
        }
        Json result;
        converged = false;
        build_tools->update("main");
        int passes = reuse ? 0 : 1;
        for (; passes < 6; ++passes) {
            auto aux = build_tools->state();
            fs::remove(directory / "completed.json");
            fs::remove(directory / "failed.json");
            // A long preamble has not yet created this pass's active child.
            // Never interpret the previous pass's dead child as a new failure.
            fs::remove(directory / "active.pid");
            process = spawn(false);
            result = wait_done(false);
            bool tools_changed = build_tools->update("main");
            if (!tools_changed && build_tools->state() == aux) {
                converged = true;
                ++passes;
                break;
            }
            if (passes == 5) { ++passes; break; } // Keep the last complete PDF usable.
            cleanup_after(0);
            stop_process();
        }
        if (live) remember_inputs();
        build_limited = !converged;
        auto frame = display(page, result);
        frame["ok"] = true;
        frame["provisional"] = !converged;
        frame["passes"] = passes;
        build_tools->annotate(frame, "main", converged);
        frame["pipelineMs"] = elapsed(started);
        frame["session"] = directory.string();
        if (live) {
            frame["compilationMode"] = "live";
            frame["cacheReused"] = reuse;
            frame["sourceSync"] = "token-and-macro-origin";
            cache->save("main", "lualatex", converged);
        }
        return frame;
    }
    Json edit(const std::string &file, const std::string &source, int page) {
        if (full) return update_files({{file, source}}, page);
        if (live) {
            auto started = Clock::now();
            if (build_limited) throw RebuildRequired("Unstable auxiliary state requires a complete rebuild");
            if (extension(file) != ".tex") throw RebuildRequired("Package or asset edit requires rebuilding compiler checkpoints");
            if (!fs::is_regular_file(inside(mirror, file))) throw RebuildRequired("New source file requires rebuilding compiler checkpoints");
            const auto previous = read(inside(mirror, file));
            if (source == previous && !live_edit_failed) return navigate(page);
            size_t changed = 0;
            while (changed < previous.size() && changed < source.size() && previous[changed] == source[changed]) ++changed;
            int checkpoint = checkpoint_before(file, changed);
            live_edit_failed = true;
            cache->invalidate(); cache->put(file,source);
            sources.index(source, file);
            sources.manifest(directory / "bako-sources.tsv", mirror);
            available.erase(available.lower_bound(checkpoint-1), available.end());
            auto result = resume(checkpoint, std::max(page,checkpoint-1));
            live_edit_failed = false;
            converged = false;
            result["pipelineMs"] = elapsed(started); result["ok"] = true; result["provisional"] = true;
            result["compilationMode"] = "live"; result["sourceSync"] = "token-and-macro-origin";
            return result;
        }
        converged = false;
        auto started = Clock::now();
        std::smatch match;
        static const std::regex input(R"(pages/page-(\d{3})\.tex)");
        if (!std::regex_match(file, match, input)) {
            throw std::runtime_error("Structural edits require session rebuild");
        }
        int index = std::stoi(match[1]);
        auto rewritten = sources.index(source, file);
        auto mapped = Clock::now();
        write(inside(directory, file), rewritten);
        available.erase(available.lower_bound(index - 1), available.end());
        Json result;
        try {
            result = resume(index, page);
        } catch (...) {
            if (!seed_pdf.empty() && !fs::exists(directory / "main.pdf")) {
                write(directory / "main.pdf", seed_pdf);
            }
            throw;
        }
        result["mapMs"] = std::chrono::duration<double, std::milli>(mapped - started).count();
        result["pipelineMs"] = elapsed(started);
        result["provisional"] = true;
        result["ok"] = true;
        result["revision"] = ++revision;
        return result;
    }
    Json navigate(int page) {
        if (full) {
            if (!full_ready) throw std::runtime_error("The preview is stale. Fix the compilation error before changing pages.");
            auto started = Clock::now();
            auto result = full_frame(page);
            result["pipelineMs"] = elapsed(started);
            return result;
        }
        auto started = Clock::now();
        Json result;
        if (available.count(page)) {
            auto it = buffers.find(page);
            if (it != buffers.end()) {
                result = display(page, {{"streamed", true}});
            } else {
                result = renderer.render(page, sources, page_ids[page]);
                result["outputMode"] = "retained-page";
            }
        } else {
            result = resume(page + 1, page);
        }
        result["pipelineMs"] = elapsed(started);
        result["ok"] = true;
        result["provisional"] = !converged;
        build_tools->annotate(result, "main", converged);
        return result;
    }
    bool full_build() const { return full; }
    bool live_document() const { return live; }
    Json layout() { return renderer.layout(); }
    Json forward(const std::string &file, int line, int column, int preferred_page = 0) {
        if (full) return nullptr;
        std::vector<int> candidates;
        for (const auto &[page, ids] : page_ids) candidates.push_back(page);
        std::stable_sort(candidates.begin(),candidates.end(),[&](int a,int b){return std::abs(a-preferred_page)<std::abs(b-preferred_page);});
        // Headings can also occur in a contents page or running header. Keep
        // navigation near the user's viewport when a token has several outputs.
        for (int page : candidates) {
            const auto &ids=page_ids.at(page);
            if (!available.count(page)) continue;
            int best = -1, length = 2147483647;
            for (int id : ids) if (auto span = sources.find(id)) {
                if (span->file==file && line>=span->line && line<=span->endLine &&
                    (line>span->line || column>=span->column) &&
                    (line<span->endLine || column<span->endColumn) && span->end-span->start < length) {
                    best=id; length=span->end-span->start;
                }
            }
            if (best >= 0) {
                auto frame = navigate(page);
                for (const auto &row : frame.at("regionRows")) if (row.at(0)==best) {
                    Json result = Json::object();
                    const auto &fields=frame.at("regionFields");
                    for (size_t i=0;i<fields.size();++i) result[fields[i].get<std::string>()]=row[i];
                    result["page"]=page;
                    return result;
                }
            }
        }
        return nullptr;
    }
    Json update_files(const std::map<std::string, std::string> &overlays, int page) {
        if (!full) throw std::runtime_error("Batch updates require full-build mode");
        for (const auto &[file, source] : overlays) {
            auto target = inside(mirror, file);
            fs::create_directories(target.parent_path());
            write(target, source);
        }
        return full_start(page);
    }
};
} // namespace bako
