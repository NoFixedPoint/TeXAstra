#pragma once
#include "../cache.hpp"

namespace bako {
class Distribution {
    fs::path runtime, work;
    std::string run(const fs::path &program, std::vector<std::string> args, int seconds=30) {
        auto output = run_logged(program, args, work, work / "probe.log", seconds);
        while (!output.empty() && (output.back() == '\r' || output.back() == '\n')) output.pop_back();
        return output;
    }
    std::string kpse(std::vector<std::string> args) { return run(tool("kpsewhich"), std::move(args)); }
    Json dependencies(const fs::path &recorder) {
        Json result = Json::object();
        std::istringstream input(read(recorder)); std::string line;
        while (std::getline(input, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (!starts(line, "INPUT ")) continue;
            auto file = fs::weakly_canonical(work / fs::u8path(line.substr(6)));
            auto relative = file.lexically_relative(work);
            if ((relative.is_absolute() || relative.empty() || *relative.begin() == "..") && fs::is_regular_file(file))
                result[file.u8string()] = file_stamp(file);
        }
        return result;
    }
    static bool current(const Json &files) {
        if (!files.is_object() || files.empty()) return false;
        for (const auto &[name, stamp] : files.items()) {
            auto file = fs::u8path(name);
            if (!fs::is_regular_file(file) || file_stamp(file) != stamp) return false;
        }
        return true;
    }
    void configure(const std::string &selected, const std::string &compiler) {
        std::set<std::string> seen;
        auto add = [&](const fs::path &directory) {
            if (!fs::is_regular_file(tool_path(directory, "kpsewhich"))) return;
            auto path = fs::canonical(directory).u8string();
            if (seen.insert(path).second) report["candidates"].push_back(path);
        };
        std::istringstream paths(getenv("PATH") ? getenv("PATH") : ""); std::string part;
        while (std::getline(paths, part, ';')) if (!part.empty()) add(fs::u8path(part));
        for (const auto &root : {fs::path(L"C:/texlive"), fs::path(L"D:/texlive")})
            if (fs::is_directory(root)) for (const auto &entry : fs::directory_iterator(root))
                if (entry.is_directory()) add(entry.path() / "bin/windows");
        if (!selected.empty()) {
            bin = fs::u8path(selected);
            if (!bin.is_absolute() || !fs::is_regular_file(tool_path(bin, "kpsewhich")))
                throw std::runtime_error("texBinDirectory must name an absolute native Windows TeX Live directory containing kpsewhich.exe");
            bin = fs::canonical(bin); add(bin);
        } else {
            if (report["candidates"].empty()) throw std::runtime_error("No native Windows TeX Live installation found. Install TeX Live or set texastra.texBinDirectory.");
            bin = fs::u8path(report["candidates"][0].get<std::string>());
        }
        report["binDirectory"] = bin.u8string();
        auto path = bin.u8string() + ";" + (getenv("PATH") ? getenv("PATH") : "");
        setenv("PATH", path.c_str(), 1);
        auto version = kpse({"--version"});
        report["kpathseaVersion"] = version.substr(0, version.find('\n'));
        if (version.find("MiKTeX") != std::string::npos) throw std::runtime_error("The native runtime currently requires TeX Live; MiKTeX is not supported.");
        report["lookupOverrides"] = Json::object();
        for (const auto *name : {"TEXMFCNF", "TEXMFROOT", "TEXMFHOME", "TEXMFVAR", "TEXINPUTS", "BIBINPUTS", "BSTINPUTS"})
            if (const char *value = getenv(name)) report["lookupOverrides"][name] = value;
        auto config = kpse({"--var-value=TEXMFCNF"}), root = kpse({"--var-value=TEXMFROOT"});
        if (config.empty() || root.empty()) throw std::runtime_error("Selected kpsewhich did not resolve TeX Live configuration");
        setenv("TEXMFCNF", config.c_str(), 1); setenv("TEXMFROOT", root.c_str(), 1);
        report["texmfcnf"] = config; report["texmfRoot"] = root;
        report["tools"] = Json::object(); report["toolStamps"] = Json::object();
        for (const auto *name : {"kpsewhich", "lualatex", "xelatex", "pdflatex", "bibtex", "biber", "makeindex"}) {
            auto file = tool_path(bin, name);
            report["tools"][name] = fs::is_regular_file(file) ? Json(file.u8string()) : Json(nullptr);
            if (fs::is_regular_file(file)) report["toolStamps"][name] = file_stamp(file);
        }
        const auto backend = runtime / "texastra-backend.exe";
        version = run(backend, {"--compiler-worker", "--version"});
        report["bundledEngine"] = version.substr(0, version.find('\n'));
        report["bundledEngineSha256"] = digest(read(runtime / "texastra-engine.dll"));
        if (fs::is_regular_file(tool_path(bin, "lualatex"))) {
            version = run(tool("lualatex"), {"--version"});
            report["distributionEngine"] = version.substr(0, version.find('\n'));
        }
        auto identity = digest(Json::array({report["bundledEngineSha256"], bin.u8string(), config, root, report["lookupOverrides"], report["toolStamps"]}).dump());
        auto storage = windows::cache_root() / "formats-v1" / identity;
        fs::create_directories(storage);
        format_path = storage / "lualatex.fmt";
        auto manifest = storage / "dependencies.json";
        bool reused = false; Json format_inputs;
        if (fs::is_regular_file(format_path) && fs::is_regular_file(manifest)) {
            try { format_inputs = Json::parse(read(manifest)); reused = current(format_inputs); } catch (const std::exception &) {}
        }
        if (!reused) {
            run(backend, {"--compiler-worker", "--ini", "--interaction=nonstopmode", "--halt-on-error", "--recorder",
                          "--jobname=lualatex", "--progname=lualatex", "lualatex.ini"}, 90);
            if (!fs::is_regular_file(work / "lualatex.fmt")) throw std::runtime_error("Native format generation produced no format");
            format_inputs = dependencies(work / "lualatex.fls");
            auto temporary = storage / ("lualatex-" + std::to_string(getpid()) + ".new");
            fs::copy_file(work / "lualatex.fmt", temporary, fs::copy_options::overwrite_existing);
            replace_file(temporary, format_path);
            write(temporary, format_inputs.dump()); replace_file(temporary, manifest);
        }
        report["format"] = format_path.u8string(); report["formatReused"] = reused;
        report["formatOwnership"] = "Generated by the bundled engine in the TeXAstra cache; installed distribution formats are unchanged.";
        write(work / "check.tex", "\\documentclass{article}\n\\begin{document}TeXAstra preflight: $x^2$.\\end{document}\n");
        auto args = std::vector<std::string>{"--compiler-worker", "--fmt=" + format_path.u8string(), "--progname=lualatex",
            "--no-shell-escape", "--interaction=nonstopmode", "--halt-on-error", "--recorder", "check.tex"};
        if (compiler == "live") run(backend, args, 90);
        else run(tool(compiler), {"--no-shell-escape", "--interaction=nonstopmode", "--halt-on-error", "--recorder", "check.tex"}, 90);
        if (!fs::is_regular_file(work / "check.pdf")) throw std::runtime_error("Native compatibility compile produced no PDF");
        report["dependencies"] = dependencies(work / "check.fls");
        report["identity"] = digest(Json::array({identity, format_inputs, report["dependencies"]}).dump());
        report["preflightReused"] = false; report["ok"] = true;
    }
  public:
    fs::path bin, format_path;
    Json report = {{"schema", 1}, {"ok", false}, {"platform", "win32-x64"}, {"candidates", Json::array()},
                   {"packageMaintenance", "Use the selected distribution's package manager; TeXAstra does not install packages."}};
    Distribution(fs::path bundled, std::string selected, const std::string &compiler = "live") : runtime(std::move(bundled)) {
        try {
            work = windows::temporary_directory(windows::cache_root() / "environment-v1", "probe-");
            report["mode"] = compiler; configure(selected, compiler);
        } catch (const std::exception &error) { report["error"] = error.what(); }
        if (!work.empty()) { std::error_code ignored; fs::remove_all(work, ignored); }
    }
    void require_ready() const { if (!report.value("ok", false)) throw std::runtime_error(report.value("error", "Native LaTeX preflight failed")); }
    fs::path tool(const std::string &name) const {
        auto file = tool_path(bin, name);
        if (!fs::is_regular_file(file)) throw std::runtime_error("Required LaTeX tool '" + name + "' is missing from " + bin.u8string());
        return file;
    }
    std::string diagnose(std::string log) const {
        static const std::regex missing(R"(File [`']([^`']+)[`'] not found)"); std::smatch match;
        if (std::regex_search(log, match, missing)) log = "Missing LaTeX input '" + match[1].str() + "' in selected native distribution " + bin.u8string() + ". Check project assets or maintain packages with the distribution manager.\n" + log;
        return log;
    }
};
} // namespace bako
