#pragma once
#include "cache.hpp"
extern char **environ;

namespace bako {
// Auxiliary tools run only between complete TeX passes, never on checkpoint edits.
class BuildTools {
    fs::path directory, store, bin;
    std::string source_stem;
    std::atomic<bool> *cancel;
    Json events = Json::array();
    Json diagnostics;
    std::map<std::string, std::string> resolved;

    fs::path executable(const std::string &name) {
        auto path=tool_path(bin,name);
        if (fs::is_regular_file(path) && access(path.c_str(), X_OK)==0) return path;
        throw std::runtime_error("Required LaTeX tool '" + name + "' is missing from selected external LaTeX distribution " + bin.string() + ". Install it using that distribution's package manager.");
    }
    std::string run(const fs::path &program, std::vector<std::string> arguments) {
#ifdef _WIN32
        return run_logged(program, arguments, directory, directory / ".bako-tool.log", 90, cancel);
#else
        arguments.insert(arguments.begin(), program.string());
        std::vector<char *> argv;
        for (auto &arg : arguments) argv.push_back(arg.data());
        argv.push_back(nullptr);
        Fd log(open((directory / ".bako-tool.log").c_str(), O_CREAT | O_TRUNC | O_WRONLY | O_CLOEXEC, 0600));
        if (log.value < 0) throw std::runtime_error("Cannot open auxiliary tool log");
        posix_spawn_file_actions_t actions;
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addchdir_np(&actions, directory.c_str());
        posix_spawn_file_actions_adddup2(&actions, log.value, 1);
        posix_spawn_file_actions_adddup2(&actions, log.value, 2);
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0);
        posix_spawn_file_actions_addclosefrom_np(&actions, 3);
        posix_spawnattr_t attr;
        posix_spawnattr_init(&attr);
        posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETSID);
        pid_t pid = -1;
        int error = posix_spawn(&pid, program.c_str(), &actions, &attr, argv.data(), environ);
        posix_spawn_file_actions_destroy(&actions);
        posix_spawnattr_destroy(&attr);
        if (error) throw std::runtime_error("Cannot start " + program.string() + ": " + strerror(error));
        auto started = Clock::now();
        int status = 0;
        for (;;) {
            auto ended = waitpid(pid, &status, WNOHANG);
            if (ended == pid) break;
            if ((ended < 0 && errno != EINTR) || (cancel && cancel->load()) || elapsed(started) > 90000) {
                kill(-pid, SIGKILL);
                while (waitpid(pid, nullptr, 0) < 0 && errno == EINTR) {}
                throw std::runtime_error(program.filename().string() + " cancelled or exceeded the 90 second auxiliary-tool limit.");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        auto output = read(directory / ".bako-tool.log");
        if (!WIFEXITED(status) || WEXITSTATUS(status)) {
            if (output.size() > 8000) output = output.substr(output.size()-8000);
            throw std::runtime_error(program.filename().string() + " failed in " + directory.string() + ":\n" + output);
        }
        return output;
#endif
    }
    std::string dependency(std::string name, const std::string &extension) {
        if (fs::path(name).extension().empty()) name += extension;
        auto local = directory / name;
        if (fs::is_regular_file(local)) return name + ":" + digest(read(local));
        // kpathsea owns distribution resources. Do not copy or maintain them.
        if (!resolved.count(name)) {
            try {
                auto result = run(executable("kpsewhich"), {"--", name});
                while (!result.empty() && (result.back()=='\n' || result.back()=='\r')) result.pop_back();
                if (!fs::is_regular_file(result)) throw std::runtime_error("not found");
                resolved[name] = result;
            } catch (const std::exception &) {
                throw std::runtime_error("Cannot resolve auxiliary-tool input '" + name + "'. Add it to the project or install it in the external LaTeX distribution.");
            }
        }
        return name + ":" + digest(read(resolved.at(name)));
    }
    static std::string xml_text(std::string value) {
        replace_all(value, "&quot;", "\""); replace_all(value, "&apos;", "'");
        replace_all(value, "&lt;", "<"); replace_all(value, "&gt;", ">"); replace_all(value, "&amp;", "&");
        return value;
    }
    void bibtex_inputs(const fs::path &file, std::set<fs::path> &seen, std::string &control) {
        auto path = inside(directory, file.generic_string());
        if (!seen.insert(path).second) return;
        auto data = read(path);
        static const std::regex entry(R"(\\(citation|bibdata|bibstyle|@input)\{([^}]*)\})");
        for (auto it=std::sregex_iterator(data.begin(),data.end(),entry); it!=std::sregex_iterator(); ++it) {
            std::string kind=(*it)[1], value=(*it)[2];
            if (kind=="@input") { bibtex_inputs(value,seen,control); continue; }
            control += it->str()+"\n";
            if (kind=="citation") continue;
            std::istringstream names(value);
            std::string name;
            while (std::getline(names,name,',')) {
                name=std::regex_replace(name,std::regex(R"(^\s+|\s+$)"),"");
                control += dependency(name,kind=="bibdata" ? ".bib" : ".bst")+"\n";
            }
        }
    }
    bool execute(const std::string &tool, const std::string &input, const std::string &output,
                 const std::string &control, std::vector<std::string> args) {
        auto program = executable(tool);
        std::string key = digest(Json({{"tool",program.string()}, {"stamp",file_stamp(program)},
            {"args",args}, {"input",control}}).dump());
        auto cached = store / (key+".json");
        std::string data, log;
        bool reused = false;
        if (fs::exists(cached)) try {
            auto saved = Json::parse(read(cached));
            data = saved.at("data").get<std::string>();
            log = saved.value("log", "");
            reused = saved.at("digest")==digest(data);
        } catch (const std::exception &) {}
        if (!reused) {
            bool existed=fs::is_regular_file(directory/output);
            auto previous=existed ? read(directory/output) : "";
            try {
                fs::remove(directory/output);
                log=run(program,std::move(args));
                if (!fs::is_regular_file(directory/output)) throw std::runtime_error(tool+" did not produce "+output);
            } catch (...) {
                // A failing tool may leave truncated TeX input. Restore the last
                // output so a repaired source can reach the next tool invocation.
                if (existed) write(directory/output,previous); else fs::remove(directory/output);
                throw;
            }
            data=read(directory/output);
            // Publish a complete immutable cache entry. Concurrent previews may
            // compute the same key, but never observe a partially written file.
            fs::create_directories(store);
            auto temporary=cached.string()+"."+std::to_string(getpid())+"."+
                std::to_string(Clock::now().time_since_epoch().count())+".new";
            write(temporary,Json({{"data",data},{"digest",digest(data)},{"log",log}}).dump());
            replace_file(temporary,cached);
        }
        bool changed=!fs::exists(directory/output) || read(directory/output)!=data;
        if (changed) write(directory/output,data);
        events.push_back({{"tool",tool},{"input",input},{"reused",reused}});
        static const std::regex warning(R"(Warning--|WARN -|[1-9][0-9]* rejected|[1-9][0-9]* errors)");
        if (std::regex_search(log,warning)) events.back()["warning"]=log.substr(0,4000);
        return changed || !reused; // A run must always be followed by a TeX pass.
    }
  public:
    BuildTools(fs::path dir, std::atomic<bool> *stop, std::string main_stem, fs::path selected_bin)
        : directory(std::move(dir)), bin(std::move(selected_bin)), source_stem(std::move(main_stem)), cancel(stop) {
#ifdef _WIN32
        store=windows::cache_root()/"auxiliary-v2";
#else
        const char *cache=getenv("XDG_CACHE_HOME"), *home=getenv("HOME");
        store=(cache && *cache ? fs::path(cache) : fs::path(home ? home : "/tmp")/".cache")/
            "bakoma-revived"/"auxiliary-v2";
#endif
    }
    void reset() { events=Json::array(); diagnostics=nullptr; resolved.clear(); }
    Json state() const {
        Json result=Json::object();
        for (const auto &entry : fs::recursive_directory_iterator(directory))
            if (entry.is_regular_file() && words(".aux .toc .out .lof .lot .nav .snm .ptc .bcf .idx .bbl .ind")
                .count(entry.path().extension().string()))
                result[entry.path().lexically_relative(directory).generic_string()]=digest(read(entry.path()));
        return result;
    }
    bool update(const std::string &stem) {
        bool changed=false;
        std::set<std::string> outputs;
        std::istringstream recorder(read(directory/(stem+".fls")));
        std::string line;
        while (std::getline(recorder,line)) if (starts(line,"OUTPUT ")) {
            auto path=fs::weakly_canonical(directory/line.substr(7)).lexically_relative(directory);
            if (!path.empty() && *path.begin()!="..") outputs.insert(path.generic_string());
        }
        if (outputs.count(stem+".bcf")) {
            auto control=read(directory/(stem+".bcf"));
            // Biber's generated XML enumerates local data sources, including
            // section-specific resources. Remote sources are deliberately explicit.
            static const std::regex datasource(R"(<bcf:datasource\b[^>]*>([^<]+)</bcf:datasource>)");
            std::string inputs=control;
            for (auto it=std::sregex_iterator(control.begin(),control.end(),datasource); it!=std::sregex_iterator(); ++it) {
                auto name=xml_text((*it)[1]);
                if (name.find("://")!=std::string::npos)
                    throw std::runtime_error("Remote Biber data sources are not supported; save '"+name+"' as a local project file.");
                inputs += "\n"+dependency(name,".bib");
            }
            changed |= execute("biber",stem+".bcf",stem+".bbl",inputs,{"--noconf","./"+stem});
        } else {
            for (const auto &file : outputs) if (fs::path(file).extension()==".aux") {
                auto data=read(directory/file);
                // Only bibliography-owning aux files start a job. Citations in
                // included aux files are fingerprinted recursively by the parent.
                if (data.find("\\bibdata{")==std::string::npos) continue;
                executable("bibtex"); // Report the required tool before resolving its inputs.
                std::set<fs::path> seen;
                std::string control;
                bibtex_inputs(file,seen,control);
                auto job=fs::path(file).replace_extension().generic_string();
                changed |= execute("bibtex",file,job+".bbl",control,{"./"+job});
            }
        }
        for (const auto &file : outputs) if (fs::path(file).extension()==".idx") {
            auto job=fs::path(file).replace_extension().generic_string();
            auto control=read(directory/file);
            std::vector<std::string> args={"-o","./"+job+".ind","-t","./"+job+".ilg"};
            auto style=(job==stem && fs::is_regular_file(directory/(source_stem+".ist")))
                ? source_stem+".ist" : job+".ist";
            if (fs::is_regular_file(directory/style)) {
                args.insert(args.end(),{"-s","./"+style});
                control += "\n"+dependency(style,".ist");
            }
            args.push_back("./"+file);
            changed |= execute("makeindex",file,job+".ind",control,args);
        }
        return changed;
    }
    void annotate(Json &frame, const std::string &stem, bool converged) {
        frame["buildTools"]=events;
        auto &warnings=frame["warnings"];
        if (!warnings.is_array()) warnings=Json::array();
        // Capture build diagnostics once; navigation and provisional edits must
        // neither reread changing logs nor invent a convergence-limit warning.
        if (diagnostics.is_null()) {
            diagnostics=Json::array();
            if (!converged) diagnostics.push_back({{"code","convergence-limit"},
                {"reason","References or generated files did not stabilize within six LaTeX passes. Check the LaTeX log for cyclic or changing auxiliary data."}});
            std::set<std::string> seen;
            for (const auto &event : events) if (event.contains("warning")) {
                auto warning=event["tool"].get<std::string>()+": "+event["warning"].get<std::string>();
                if (seen.insert(warning).second) diagnostics.push_back({{"code","auxiliary-tool-warning"},{"reason",warning}});
            }
            auto log=directory/(stem+".log");
            auto data=fs::exists(log) ? read(log) : "";
            if (data.find("undefined references")!=std::string::npos || data.find("undefined citations")!=std::string::npos ||
                (data.find("Citation")!=std::string::npos && data.find("undefined")!=std::string::npos))
                diagnostics.push_back({{"code","unresolved-references"},
                    {"reason","Some citations or references remain undefined. Check citation keys, labels, and bibliography data in the LaTeX log: "+log.string()}});
        }
        for (const auto &warning : diagnostics) warnings.push_back(warning);
    }
};
}
