#pragma once
#include "compiler.hpp"
#include "packages.hpp"

namespace bako {
// Recovery always rebuilds from the caller's current source overlays. No
// checkpoint, renderer, auxiliary-tool cache or preflight survives maintenance.
inline Json recover_packages(ProjectOptions &options, const fs::path &runtime,
                             const std::function<Json()> &attempt,
                             const std::function<void()> &discard,
                             const std::function<Json()> &rebuild,
                             const Packages::Progress &progress,
                             std::atomic<bool> *cancel = nullptr) {
    std::set<std::string> attempted;
    bool retry = false;
    for (;;) {
        std::string error;
        try { return retry ? rebuild() : attempt(); }
        catch (const std::exception &e) { error = e.what(); }
        auto file = Packages::missing(error);
        if (!options.auto_install_packages || file.empty() || (cancel && cancel->load()))
            throw std::runtime_error(error);
        if (attempted.size() >= 16 || !attempted.insert(file).second)
            throw std::runtime_error(error + "\nAutomatic package recovery stopped: repeated missing file or 16-file retry limit.");
        // Join background compilers before touching the shared distribution or
        // process environment. Also discard state when the manager later fails.
        discard();
        auto selected = options.distribution->bin;
        auto previous = options.distribution->report;
        Packages packages(selected, fs::u8path(previous.value("texmfRoot", "")), cancel);
        Json installed;
        try { installed = packages.install(file, progress); }
        catch (const std::exception &e) { throw std::runtime_error(error + "\n" + e.what()); }
        progress("Package installed; checking LaTeX and rebuilding the document...");
        options.distribution = std::make_shared<Distribution>(runtime, selected.u8string(), options.mode == "full" ? options.compiler : "live", true);
        auto &report = options.distribution->report;
        report["packageInstallations"] = previous.value("packageInstallations", Json::array());
        report["packageInstallations"].push_back(installed);
        // Even an unchanged ls-R timestamp must not permit a warm cache after
        // this process has changed the distribution.
        if (report.value("ok", false))
            report["identity"] = digest(Json::array({report.at("identity"), report["packageInstallations"]}).dump());
        retry = true;
    }
}
} // namespace bako
