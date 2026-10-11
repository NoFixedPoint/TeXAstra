#pragma once
#include <json.hpp>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <codecvt>
#include <locale>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

namespace bako {
using Json = nlohmann::json;
namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
inline double elapsed(Clock::time_point from) {
    return std::chrono::duration<double, std::milli>(Clock::now() - from).count();
}
inline std::string read(const fs::path &p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) {
        throw std::runtime_error("Cannot read " + p.string());
    }
    return {std::istreambuf_iterator<char>(f), {}};
}
inline void write(const fs::path &p, const std::string &data) {
    std::ofstream f(p, std::ios::binary);
    if (!f || !f.write(data.data(), data.size())) {
        throw std::runtime_error("Cannot write " + p.string());
    }
}
inline std::string page_name(int n, const std::string &prefix, const std::string &suffix) {
    std::ostringstream out;
    out << prefix << std::setw(3) << std::setfill('0') << n << suffix;
    return out.str();
}
inline std::u32string unicode(const std::string &s) {
    std::wstring_convert<std::codecvt_utf8<char32_t>, char32_t> cv;
    return cv.from_bytes(s);
}
inline std::string utf8(const std::u32string &s) {
    std::wstring_convert<std::codecvt_utf8<char32_t>, char32_t> cv;
    return cv.to_bytes(s);
}
inline std::string rune(int c) {
    return utf8(std::u32string(1, c < 0 ? 0xfffd : c));
}
inline bool space(char32_t c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\f' || c == '\v' || c == 0xa0 ||
           c == 0x3000;
}
inline bool letter(char32_t c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '@';
}
inline bool starts(const std::string &s, const std::string &prefix) {
    return s.compare(0, prefix.size(), prefix) == 0;
}
inline void replace_all(std::string &s, const std::string &before, const std::string &after) {
    size_t pos = 0;
    while ((pos = s.find(before, pos)) != std::string::npos) {
        s.replace(pos, before.size(), after);
        pos += after.size();
    }
}
inline std::set<std::string> words(const char *s) {
    std::istringstream in(s);
    std::set<std::string> out;
    std::string word;
    while (in >> word) {
        out.insert(word);
    }
    return out;
}
inline std::string base64(const unsigned char *bytes, size_t size) {
    static const char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    out.reserve((size + 2) / 3 * 4);
    for (size_t i = 0; i < size; i += 3) {
        unsigned v = unsigned(bytes[i]) << 16;
        if (i + 1 < size) {
            v |= unsigned(bytes[i + 1]) << 8;
        }
        if (i + 2 < size) {
            v |= bytes[i + 2];
        }
        out += alphabet[(v >> 18) & 63];
        out += alphabet[(v >> 12) & 63];
        out += i + 1 < size ? alphabet[(v >> 6) & 63] : '=';
        out += i + 2 < size ? alphabet[v & 63] : '=';
    }
    return out;
}
inline std::string base64(const std::string &s) {
    return base64(reinterpret_cast<const unsigned char *>(s.data()), s.size());
}
struct Fd {
    int value = -1;
    explicit Fd(int n = -1) : value(n) {}
    ~Fd() {
        if (value >= 0) {
            ::close(value);
        }
    }
    Fd(const Fd &) = delete;
    Fd &operator=(const Fd &) = delete;
    Fd(Fd &&other) noexcept : value(other.value) {
        other.value = -1;
    }
    Fd &operator=(Fd &&other) noexcept {
        if (value >= 0) {
            ::close(value);
        }
        value = other.value;
        other.value = -1;
        return *this;
    }
};
inline void send_all(int fd, const std::string &s) {
    size_t sent = 0;
    while (sent < s.size()) {
        auto n = ::send(fd, s.data() + sent, s.size() - sent, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) {
            continue;
        }
        if (n <= 0) {
            throw std::runtime_error("Socket send failed");
        }
        sent += n;
    }
}
inline std::string receive_exact(int fd, size_t size) {
    std::string out(size, '\0');
    size_t offset = 0;
    while (offset < size) {
        auto n = recv(fd, out.data() + offset, size - offset, 0);
        if (n < 0 && errno == EINTR) {
            continue;
        }
        if (n <= 0) {
            throw std::runtime_error("Truncated page message");
        }
        offset += n;
    }
    return out;
}
inline fs::path inside(const fs::path &root, const std::string &relative) {
    fs::path p = fs::weakly_canonical(root / relative);
    auto rel = p.lexically_relative(fs::canonical(root));
    if (rel.empty() || rel.is_absolute() || *rel.begin() == "..") {
        throw std::runtime_error("Source path escapes project");
    }
    return p;
}
} // namespace bako
