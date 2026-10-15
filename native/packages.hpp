#pragma once
#include "common.hpp"
#include <functional>
extern char **environ;

namespace bako {
// Only the selected distribution's package manager owns installed files.
class Packages {
    fs::path bin, root, work;
    std::atomic<bool> *cancel;
    std::string run(const fs::path &program, std::vector<std::string> args, int seconds = 300) {
        if (cancel && cancel->load()) throw std::runtime_error("Package installation cancelled");
#ifdef _WIN32
        std::map<std::wstring, std::wstring> env;
        if (program.filename() == "perl.exe") {
            env[L"PERL5LIB"] = (root / "tlpkg/tlperl/lib").native();
            env[L"PATH"] = (root / "tlpkg/tlperl/bin").native() + L";" + bin.native() + L";" +
                windows::wide(getenv("PATH") ? getenv("PATH") : "");
        }
        return run_logged(program, args, work, work / "manager.log", seconds, cancel, std::move(env));
#else
        args.insert(args.begin(), program.string());
        std::vector<char *> argv;
        for (auto &arg : args) argv.push_back(arg.data());
        argv.push_back(nullptr);
        Fd log(open((work / "manager.log").c_str(), O_CREAT | O_TRUNC | O_WRONLY | O_CLOEXEC, 0600));
        if (log.value < 0) throw std::runtime_error("Cannot open package manager log");
        posix_spawn_file_actions_t actions;
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addchdir_np(&actions, work.c_str());
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0);
        posix_spawn_file_actions_adddup2(&actions, log.value, 1);
        posix_spawn_file_actions_adddup2(&actions, log.value, 2);
        posix_spawnattr_t attr;
        posix_spawnattr_init(&attr);
        isolate_spawn(actions, attr);
        pid_t pid = -1;
        int error = posix_spawn(&pid, program.c_str(), &actions, &attr, argv.data(), environ);
        posix_spawn_file_actions_destroy(&actions); posix_spawnattr_destroy(&attr);
        if (error) throw std::runtime_error("Cannot run package manager: " + std::string(strerror(error)));
        auto started = Clock::now(); int status = 0;
        for (;;) {
            auto ended = waitpid(pid, &status, WNOHANG);
            if (ended == pid) break;
            if ((ended < 0 && errno != EINTR) || (cancel && cancel->load()) || elapsed(started) > seconds * 1000) {
                kill(-pid, SIGKILL);
                while (waitpid(pid, nullptr, 0) < 0 && errno == EINTR) {}
                throw std::runtime_error("Package manager cancelled or timed out");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        auto output = read(work / "manager.log");
        if (!WIFEXITED(status) || WEXITSTATUS(status))
            throw std::runtime_error("Package manager failed:\n" + output.substr(output.size() > 8000 ? output.size() - 8000 : 0));
        return output;
#endif
    }
    std::string manager(std::vector<std::string> args) {
#ifdef _WIN32
        // TeX Live ships tlmgr.bat. Invoke its bundled Perl directly: no shell
        // quoting, PATH fallback, or command interpretation of document text.
        auto perl = root / "tlpkg/tlperl/bin/perl.exe";
        auto script = root / "texmf-dist/scripts/texlive/tlmgr.pl";
        if (!fs::is_regular_file(perl) || !fs::is_regular_file(script))
            throw std::runtime_error("Selected TeX Live has no bundled tlmgr/Perl");
        args.insert(args.begin(), script.u8string());
        return run(perl, std::move(args));
#else
        auto program = bin / "tlmgr";
        if (!fs::is_regular_file(program) || access(program.c_str(), X_OK))
            throw std::runtime_error("Selected TeX Live has no executable tlmgr package manager");
        return run(program, std::move(args));
#endif
    }
  public:
    using Progress = std::function<void(const std::string &)>;
    Packages(fs::path selected, fs::path texmf_root, std::atomic<bool> *stop = nullptr)
        : bin(std::move(selected)), root(std::move(texmf_root)), cancel(stop) {
#ifdef _WIN32
        work = windows::temporary_directory(fs::temp_directory_path(), "texastra-packages-");
#else
        auto pattern = (fs::temp_directory_path() / "texastra-packages-XXXXXX").string();
        std::vector<char> name(pattern.begin(), pattern.end()); name.push_back(0);
        auto created = mkdtemp(name.data());
        if (!created) throw std::runtime_error("Cannot create package manager directory");
        work = created;
#endif
    }
    ~Packages() { std::error_code ignored; fs::remove_all(work, ignored); }
    static std::string missing(const std::string &log) {
        static const std::regex diagnostic(R"((?:File [`']([^`'\r\n]+)[`'] not found|I can't find file [`']([^`'\r\n]+)[`']))");
        std::smatch match;
        if (!std::regex_search(log, match, diagnostic)) return {};
        auto name = match[1].matched ? match[1].str() : match[2].str();
        // Paths and non-TeX assets belong to the project. A basename still has
        // to be an exact runtime-file match in the distribution's catalogue.
        static const std::regex safe(R"([A-Za-z0-9][A-Za-z0-9_.+-]*\.(sty|cls|clo|def|cfg|fd|ldf|tex|lua|bbx|cbx|lbx|bst|tfm|vf|enc|map))");
        return std::regex_match(name, safe) ? name : "";
    }
    static std::set<std::string> providers(const std::string &listing, const std::string &file) {
        std::set<std::string> found;
        std::istringstream lines(listing); std::string line, package;
        const std::regex header(R"(^([A-Za-z0-9][A-Za-z0-9_.+-]*):\s*$)");
        std::smatch match;
        while (getline_crlf(lines, line)) {
            if (std::regex_match(line, match, header)) { package = match[1]; continue; }
            if (line.empty() || (line[0] != ' ' && line[0] != '\t')) { package.clear(); continue; }
            auto first = line.find_first_not_of(" \t");
            if (first == std::string::npos) continue;
            auto path = line.substr(first);
            if (!package.empty() && (starts(path, "texmf-dist/tex/") || starts(path, "texmf-dist/fonts/") || starts(path, "texmf-dist/bibtex/bst/")) &&
                fs::path(path).filename().string() == file) found.insert(package);
        }
        return found;
    }
    Json install(const std::string &file, const Progress &progress) {
        try {
            // OS-owned TeX Live installations must remain owned by that OS.
            if (!fs::is_regular_file(root / "tlpkg/texlive.tlpdb"))
                throw std::runtime_error("This TeX Live installation is OS-managed or has no tlmgr database. Install the missing package with the OS package manager (apt on Debian/Ubuntu), or select an upstream TeX Live installation for automatic installation.");
            progress("Finding a TeX Live package for " + file + "...");
            std::string pattern = "/";
            for (char c : file) { if (c == '.' || c == '+') pattern += '\\'; pattern += c; }
            pattern += "$";
            auto matches = providers(manager({"search", "--global", "--file", pattern}), file);
            if (matches.empty()) throw std::runtime_error("No package provides this file in the selected repository. Check the project filename and local assets.");
            if (matches.size() != 1) throw std::runtime_error("Multiple packages provide this file; resolve the ambiguity with the selected tlmgr package manager.");
            auto package = *matches.begin();
            progress("Installing TeX Live package " + package + " for " + file + "...");
            manager({"install", package});
            auto resolved = run(tool_path(bin, "kpsewhich"), {"--", file}, 15);
            while (!resolved.empty() && (resolved.back() == '\n' || resolved.back() == '\r')) resolved.pop_back();
            if (!fs::is_regular_file(fs::u8path(resolved))) throw std::runtime_error("tlmgr completed but kpsewhich still cannot resolve the file");
            return {{"file", file}, {"package", package}, {"resolved", resolved}};
        } catch (const std::exception &e) {
            throw std::runtime_error("Automatic package installation for '" + file + "' in " + bin.u8string() + " failed. Check this distribution's package manager, repository/network access and write permissions.\n" + e.what());
        }
    }
};
} // namespace bako
