#pragma once
#include "renderer.hpp"
#include <sys/file.h>

namespace bako {
inline std::string digest(const std::string &value) {
    fz_sha256 state;
    unsigned char bytes[32];
    fz_sha256_init(&state);
    fz_sha256_update(&state, reinterpret_cast<const unsigned char *>(value.data()), value.size());
    fz_sha256_final(&state, bytes);
    std::ostringstream out;
    for (auto c : bytes) out << std::hex << std::setw(2) << std::setfill('0') << unsigned(c);
    return out.str();
}
inline Json file_stamp(const fs::path &file) {
    return Json::array({fs::file_size(file), fs::last_write_time(file).time_since_epoch().count()});
}
class BuildCache {
    Fd lock;
    fs::path registry;
  public:
    fs::path directory;
    Json inputs = Json::object();
    BuildCache(const fs::path &project, const std::string &main, const std::string &compiler) {
        const char *cache = getenv("XDG_CACHE_HOME"), *home = getenv("HOME");
        auto root = cache && *cache ? fs::path(cache) : fs::path(home ? home : "/tmp") / ".cache";
        root /= "bakoma-revived";
        fs::create_directories(root);
        auto key=digest("v008\n" + project.string() + "\n" + main + "\n" + compiler).substr(0,24);
        directory = root / key;
        registry = root / (key+".json");
        if (fs::exists(registry)) try {
            auto name=Json::parse(read(registry)).at("directory").get<std::string>();
            if (fs::path(name).filename()==name && (name==key || starts(name,key+"-"))) directory=root/name;
        } catch(const std::exception &) {}
        fs::create_directories(directory);
        lock = Fd(open((directory / ".lock").c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600));
        if (lock.value < 0) throw std::runtime_error("Cannot lock the project cache");
        if (flock(lock.value, LOCK_EX | LOCK_NB)) {
            // Concurrent previews must never compile into one another's files.
            std::string pattern = (root / (key+"-XXXXXX")).string();
            std::vector<char> name(pattern.begin(), pattern.end()); name.push_back(0);
            auto created = mkdtemp(name.data());
            if (!created) throw std::runtime_error("Cannot create a separate preview cache");
            directory = created;
            lock = Fd(open((directory / ".lock").c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600));
            if (lock.value < 0 || flock(lock.value, LOCK_EX | LOCK_NB))
                throw std::runtime_error("Cannot lock the separate preview cache");
        }
    }
    void put(const std::string &file, const std::string &data) {
        auto target = inside(directory, file);
        fs::create_directories(target.parent_path());
        auto hash = digest(data);
        if (!fs::exists(target) || digest(read(target)) != hash) write(target, data);
        inputs[file] = hash;
    }
    void finish_inputs() {
        auto path = directory / ".bako-inputs.json";
        if (fs::exists(path)) {
            auto previous = Json::parse(read(path), nullptr, false);
            if (previous.is_object()) for (const auto &[file, value] : previous.items()) {
                if (!inputs.contains(file)) fs::remove(inside(directory, file));
            }
        }
        write(path, inputs.dump());
    }
    bool reusable(const fs::path &pdf, const std::string &compiler) {
        try {
            auto state = Json::parse(read(directory / ".bako-success.json"));
            if (state.at("inputs") != inputs || state.at("compiler") != file_stamp("/usr/bin/" + compiler) ||
                !fs::exists(pdf)) return false;
            for (const auto &[file, stamp] : state.at("dependencies").items())
                if (file_stamp(file) != stamp) return false;
            return state.value("converged", false);
        } catch (const std::exception &) { return false; }
    }
    void invalidate() { fs::remove(directory / ".bako-success.json"); }
    void save(const std::string &stem, const std::string &compiler, bool converged) {
        Json dependencies = Json::object();
        std::istringstream recorder(read(directory / (stem + ".fls")));
        std::string line;
        while (std::getline(recorder, line)) if (starts(line, "INPUT ")) {
            auto path = fs::weakly_canonical(directory / line.substr(6));
            auto relative = path.lexically_relative(directory);
            if (!relative.empty() && *relative.begin() == ".." && fs::is_regular_file(path))
                dependencies[path.string()] = file_stamp(path);
        }
        auto temporary = directory / ".bako-success.json.new";
        write(temporary, Json({{"inputs", inputs}, {"dependencies", dependencies},
              {"compiler", file_stamp("/usr/bin/" + compiler)}, {"converged", converged}}).dump());
        fs::rename(temporary, directory / ".bako-success.json");
        write(directory / ".bako-inputs.json", inputs.dump());
        auto pointer=registry.string()+"."+std::to_string(getpid())+".new";
        write(pointer,Json({{"directory",directory.filename().string()}}).dump());
        fs::rename(pointer,registry);
    }
};
}
