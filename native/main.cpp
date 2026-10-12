#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "compiler.hpp"
#include "edits.hpp"
#include <deque>
#include <functional>

using namespace bako;
#ifdef _WIN32
int run_compiler_worker(const fs::path &, int, char **);
#endif

class Preview {
    fs::path project, assets, runtime;
    ProjectOptions options;
    std::mutex mutex, output_mutex;
    std::condition_variable changed;
    std::deque<Json> queue;
    std::atomic<bool> stopping{false}, cancel_build{false};
    std::atomic<unsigned> latest{0};
    std::atomic<unsigned> generation{0};
    std::unique_ptr<Engine> engine, candidate;
    std::map<std::string, std::string> overlays, candidate_sources;
    std::map<std::string,int> source_versions;
    std::thread builder;
    bool building = false;
    Json previous;
    Clock::time_point last_action = Clock::now();
    bool needs_convergence = false;
    void emit(const Json &message) {
        std::lock_guard<std::mutex> lock(output_mutex);
        auto started = Clock::now();
        auto payload = message.dump(-1, ' ', false, Json::error_handler_t::replace);
        const double serialize_ms = elapsed(started);
        auto writing = Clock::now();
        std::cout << payload << '\n' << std::flush;
        const double write_ms = elapsed(writing);
        if (message.value("type", "") == "frame") {
            // The write duration is known only after the payload has left this
            // process. Send a small correlated record, not a second full dump.
            Json timing = {{"type", "frame-transport"}, {"clientId", message.value("clientId", 0)},
                {"revision", message.value("revisionId", 0)}, {"generation", message.value("generation", 0)},
                {"purpose", message.value("purpose", "")}, {"phase", message.value("phase", "preview")},
                {"payloadBytes", payload.size()}, {"serializeMs", serialize_ms}, {"writeMs", write_ms}};
            std::cout << timing.dump() << '\n' << std::flush;
        }
    }
    void frame(Json result, const Json &request, bool converged = false) {
        result["type"] = "frame";
        result["engine"] = "cpp";
        result["revisionId"] = request.at("revision");
        result["clientId"] = request.value("clientId", 0);
        result["sentAt"] = converged ? Json(nullptr) : request.value("sentAt", Json(nullptr));
        result["isStale"] = request.at("revision").get<unsigned>() != latest.load();
        result["purpose"] = request.at("type");
        result["requestId"] = request.value("requestId", Json(nullptr));
        if (converged) {
            result["phase"] = result.value("provisional", false) ? "convergence-limited" : "converged";
        }
        emit(result);
    }
    void convergence() {
        if (builder.joinable()) {
            builder.join();
        }
        cancel_build = false;
        building = true;
        auto snapshot = overlays;
        auto request = previous;
        auto revision = latest.load();
        builder = std::thread([this, snapshot, request, revision] {
            std::unique_ptr<Engine> ready;
            try {
                ready = std::make_unique<Engine>(project, assets, runtime, snapshot, &cancel_build, options);
                auto result = ready->start(request.value("page", 0));
                std::lock_guard<std::mutex> lock(mutex);
                if (!cancel_build && !stopping && latest == revision) {
                    ready->generation=++generation;
                    result["generation"]=ready->generation;
                    result["pageSizes"]=ready->layout();
                    candidate = std::move(ready);
                    candidate_sources = snapshot;
                    frame(std::move(result), request, true);
                }
            } catch (const std::exception &e) {
                if (!cancel_build && !stopping && latest == revision) {
                    emit({{"type", "status"},
                          {"state", "error"},
                          {"revision", revision},
                          {"error", std::string("Convergence: ") + e.what()}});
                }
            }
            ready.reset();
            {
                std::lock_guard<std::mutex> lock(mutex);
                building = false;
            }
            changed.notify_one();
        });
    }

  public:
    Preview(fs::path p, fs::path a, fs::path r, ProjectOptions config)
        : project(std::move(p)), assets(std::move(a)), runtime(std::move(r)), options(std::move(config)) {}
    void run() {
        std::thread reader([this] {
            std::string line;
            while (std::getline(std::cin, line)) {
                try {
                    auto request = Json::parse(line);
                    auto kind = request.at("type").get<std::string>();
                    if (kind == "close") {
                        break;
                    }
                    const bool mutation = kind=="start" || kind=="edit" || kind=="reload";
                    auto revision = mutation ? ++latest : latest.load();
                    request["revision"] = revision;
                    if (mutation) cancel_build = true;
                    request["submittedMs"] =
                        std::chrono::duration<double, std::milli>(Clock::now().time_since_epoch())
                            .count();
                    if (mutation) emit({{"type", "status"},
                          {"state", "building"},
                          {"revision", revision},
                          {"clientId", request.value("clientId", 0)}});
                    {
                        std::lock_guard<std::mutex> lock(mutex);
                        queue.push_back(std::move(request));
                    }
                    changed.notify_one();
                } catch (const std::exception &e) {
                    emit({{"type", "status"}, {"state", "error"}, {"error", e.what()}});
                }
            }
            stopping = true;
            cancel_build = true;
            changed.notify_one();
        });
        while (!stopping) {
            std::deque<Json> requests;
            {
                std::unique_lock<std::mutex> lock(mutex);
                changed.wait_for(lock, std::chrono::milliseconds(100), [this] {
                    return stopping || !queue.empty() || candidate != nullptr;
                });
                if (stopping) {
                    break;
                }
                if (candidate) {
                    if (candidate_sources == overlays) {
                        engine = std::move(candidate);
                        engine->cancel = &stopping;
                    } else {
                        candidate.reset();
                    }
                }
                requests.swap(queue);
                if (requests.empty()) {
                    if (needs_convergence && !building && elapsed(last_action) >= 2000) {
                        needs_convergence = false;
                        convergence();
                    }
                    continue;
                }
            }
            // Coalesce edits, but do not discard independent viewport or sync
            // requests. Rendering a page is not a new source revision.
            auto selected=requests.begin();
            bool mutation=false;
            for (auto it=requests.begin();it!=requests.end();++it) {
                if (it->at("type")=="edit" || it->at("type")=="start" || it->at("type")=="reload") { selected=it; mutation=true; }
            }
            auto request = *selected;
            const double queue_ms =
                std::chrono::duration<double, std::milli>(Clock::now().time_since_epoch()).count() -
                request.at("submittedMs").get<double>();
            {
                std::lock_guard<std::mutex> lock(mutex);
                for (auto it=requests.rbegin();it!=requests.rend();++it) {
                    if (it->at("type")!="edit" && it->at("type")!="start" && it->at("type")!="reload" && &*it!=&*selected) queue.push_front(*it);
                }
            }
            if (mutation) { previous = request; last_action = Clock::now(); }
            int page = std::max(0, request.value("page", 0));
            std::set<std::string> edits;
            try {
                if (!mutation) {
                    if (!engine || request.at("revision").get<unsigned>() != latest ||
                        (request.contains("generation") && request.at("generation").get<unsigned>() != engine->generation)) {
                        emit({{"type","discard"},{"requestId",request.value("requestId",Json(nullptr))}});
                        continue;
                    }
                    if (request.at("type")=="sync-forward") {
                        emit({{"type","sync"},{"revisionId",request.at("revision")},{"generation",engine->generation},
                              {"requestId",request.value("requestId",Json(nullptr))},
                              {"location",engine->forward(request.at("file"),request.at("line"),request.at("column"),page)}});
                        continue;
                    }
                }
                bool reload = false;
                for (auto &r : requests) {
                    if (r.at("type") == "reload") { overlays.clear(); edits.clear(); reload = true; }
                    if (r.at("type") == "reload" || r.at("type") == "start") source_versions.clear();
                    if ((r.at("type") == "start" || r.at("type") == "reload") && r.contains("overlays")) {
                        for (const auto &[file, source] : r.at("overlays").items()) {
                            inside(project, file);
                            overlays[file] = source.get<std::string>();
                            edits.insert(file);
                        }
                    }
                    if (r.at("type") == "edit") {
                        auto file = r.at("file").get<std::string>();
                        inside(project, file);
                        apply_source_edit(overlays,source_versions,r);
                        edits.insert(file);
                    }
                }
                if (request.at("type")=="start" || reload) engine.reset();
                bool rebuild = !engine || edits.size() > 1 || (engine->full_build() && !edits.empty());
                for (const auto &file : edits) {
                    if (!std::regex_match(file, std::regex(R"(pages/page-\d{3}\.tex)"))) {
                        rebuild = true;
                    }
                }
                Json result;
                if (engine && engine->live_document() && edits.size() == 1) {
                    try { result = engine->edit(*edits.begin(), overlays.at(*edits.begin()), page); }
                    catch (const RebuildRequired &) {
                        engine.reset();
                        engine = std::make_unique<Engine>(project, assets, runtime, overlays, &stopping, options);
                        result = engine->start(page);
                    }
                } else if (engine && engine->full_build() && !edits.empty()) {
                    result = engine->update_files(overlays, page);
                } else if (rebuild) {
                    engine.reset();
                    engine =
                        std::make_unique<Engine>(project, assets, runtime, overlays, &stopping, options);
                    result = engine->start(page);
                } else if (!edits.empty()) {
                    result = engine->edit(*edits.begin(), overlays.at(*edits.begin()), page);
                } else {
                    result = engine->navigate(page);
                }
                result["requestToPayloadMs"] =
                    std::chrono::duration<double, std::milli>(Clock::now().time_since_epoch())
                        .count() -
                    request.at("submittedMs").get<double>();
                result["queueMs"] = queue_ms;
                if (mutation) {
                    engine->generation=++generation;
                    result["pageSizes"]=engine->layout();
                    needs_convergence = !engine->full_build() && result.value("provisional", false);
                }
                result["generation"]=engine->generation;
                frame(std::move(result), request);
            } catch (const std::exception &e) {
                if (!mutation) {
                    emit({{"type","query-error"},{"requestId",request.value("requestId",Json(nullptr))},{"error",e.what()}});
                    continue;
                }
                needs_convergence = false;
                if (request.at("revision").get<unsigned>() == latest) {
                    emit({{"type", "status"},
                          {"state", "error"},
                          {"revision", latest.load()},
                          {"error", e.what()}});
                }
            }
        }
        stopping = true;
        cancel_build = true;
        if (builder.joinable()) {
            builder.join();
        }
        candidate.reset();
        engine.reset();
        reader.join();
    }
};

int main(int argc, char **argv) {
#ifndef _WIN32
    signal(SIGPIPE, SIG_IGN);
#endif
    try {
#ifdef _WIN32
        wchar_t native_path[32768];
        auto length=GetModuleFileNameW(nullptr,native_path,32768);
        if(!length||length>=32768)throw std::runtime_error("Cannot resolve backend executable");
        fs::path executable=native_path, runtime=executable.parent_path();
        if(argc>1&&std::string(argv[1])=="--compiler-worker") {
            argv[1]=argv[0];
            return run_compiler_worker(runtime/"texastra-engine.dll",argc-1,argv+1);
        }
        _setmode(_fileno(stdin),_O_BINARY); _setmode(_fileno(stdout),_O_BINARY);
#endif
        std::map<std::string, std::string> args;
        for (int i = 1; i < argc; ++i) {
            std::string key = argv[i];
            if (key == "--sync" || key == "--environment") {
                args[key] = "1";
            } else {
                if (i + 1 == argc) {
                    throw std::runtime_error("Missing argument for " + key);
                }
                args[key] = argv[++i];
            }
        }
#ifndef _WIN32
        fs::path executable = executable_path(), runtime = executable.parent_path();
#endif
#ifdef _WIN32
        const char *default_checkpoint="windows";
#else
        const char *default_checkpoint="fork";
#endif
        std::string checkpoint =
            args.count("--checkpoint")
                ? args.at("--checkpoint")
                : (getenv("BAKO_CHECKPOINT_MODE") ? getenv("BAKO_CHECKPOINT_MODE") : default_checkpoint);
        if (checkpoint != default_checkpoint) {
            throw std::runtime_error(std::string("This runtime requires --checkpoint ")+default_checkpoint);
        }
        setenv("BAKO_CHECKPOINT_MODE", checkpoint.c_str(), 1);
#ifdef _WIN32
        if (!args.count("--assets")) args["--assets"] = runtime.u8string();
#endif
        ProjectOptions options;
        if (args.count("--main")) options.main = args.at("--main");
        if (args.count("--preview-mode")) options.mode = args.at("--preview-mode");
        if (args.count("--compiler")) options.compiler = args.at("--compiler");
        if (!words("auto full incremental").count(options.mode) || !words("lualatex xelatex pdflatex").count(options.compiler))
            throw std::runtime_error("Invalid render mode or LaTeX compiler");
        options.distribution=std::make_shared<Distribution>(runtime,args.count("--tex-bin")?args.at("--tex-bin"):"",
            options.mode=="full"?options.compiler:"live");
        if(args.count("--environment")) {
            std::cout<<options.distribution->report.dump(2)<<'\n';
            return options.distribution->report.value("ok",false)?0:1;
        }
        fs::path project = fs::canonical(args.at("--project")), assets = fs::canonical(args.at("--assets"));
        if(!args.count("--sync"))std::cout<<Json({{"type","environment"},{"report",options.distribution->report}}).dump()<<'\n'<<std::flush;
        if (args.count("--sync")) {
            std::unique_ptr<Engine> engine;
            std::map<std::string, std::string> overlays;
            std::map<std::string,int> source_versions;
            std::string line;
            while (std::getline(std::cin, line)) {
                try {
                    auto request = Json::parse(line);
                    auto kind = request.at("type");
                    if (kind == "close") {
                        break;
                    }
                    int page = request.value("page", 0);
                    Json result;
                    if (kind == "start" || kind == "reload") {
                        source_versions.clear();
                        if (kind == "reload") overlays.clear();
                        if (request.contains("overlays")) for (const auto &[file, source] : request.at("overlays").items()) {
                            inside(project, file);
                            overlays[file] = source.get<std::string>();
                        }
                        engine.reset();
                        engine = std::make_unique<Engine>(project, assets, runtime, overlays, nullptr, options);
                        result = engine->start(page);
                    } else if (!engine) {
                        throw std::runtime_error("Start the engine first");
                    } else if (kind == "edit") {
                        auto file = request.at("file").get<std::string>();
                        inside(project, file);
                        apply_source_edit(overlays,source_versions,request);
                        result = engine->edit(file, overlays.at(file), page);
                    } else if (kind == "sync-forward") {
                        result = {{"ok",true},{"location",engine->forward(request.at("file"),request.at("line"),request.at("column"),page)}};
                    } else {
                        result = engine->navigate(page);
                    }
                    std::cout << result.dump() << '\n' << std::flush;
                } catch (const std::exception &e) {
                    std::cout << Json({{"ok", false}, {"error", e.what()}}).dump() << '\n'
                              << std::flush;
                }
            }
            return 0;
        }
        Preview preview(project, assets, runtime, options);
        preview.run();
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
