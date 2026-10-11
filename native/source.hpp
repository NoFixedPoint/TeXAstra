#pragma once
#include "common.hpp"

namespace bako {
inline const std::string reset = "\\bakoattr=0 ";
inline bool primitive_conditional(const std::string &name) {
    static const auto names = words("if ifcat ifnum ifdim ifodd ifvmode ifhmode ifmmode ifinner "
        "ifvoid ifhbox ifvbox ifx ifeof iftrue iffalse ifcase ifdefined ifcsname iffontchar ifincsname ifabsnum ifabsdim");
    return names.count(name) != 0;
}
struct Span {
    int id = 0, start = 0, end = 0, line = 0, column = 0, endLine = 0, endColumn = 0;
    std::string file, text, kind;
    Json row(const Json &rect) const {
        return Json::array(
            {id, rect, file, start, end, line, column, endLine, endColumn, text, kind});
    }
    Json object() const {
        return {{"file", file},           {"start", start},   {"end", end},
                {"line", line},           {"column", column}, {"endLine", endLine},
                {"endColumn", endColumn}, {"text", text},     {"kind", kind}};
    }
};

// Port of the deliberately bounded source instrumenter. Offsets count Unicode
// scalars; editor columns count UTF-16 units. No claim of general TeX parsing.
class Sources {
    struct File {
        std::string source;
        std::vector<Span> spans;
        Json warnings = Json::array();
        int slot = 0;
    };
    std::map<std::string, File> files;
    std::unordered_map<int, File *> slots;
    File *current = nullptr;
    std::string filename;
    std::u32string text;
    std::vector<int> lines, columns;
    size_t i = 0;
    bool general = false;
    std::string reset = bako::reset;
    int origin_offset = 0;
    const std::set<std::string> symbols =
        words("alpha beta gamma delta epsilon theta lambda mu pi sigma phi omega Gamma Delta Theta "
              "Lambda Pi Sigma Phi Omega sum prod int infty partial nabla times cdot pm mp leq geq "
              "neq in notin subset supset approx to rightarrow leftarrow ldots cdots sin cos tan "
              "log ln exp lim");
    const std::set<std::string> text_args =
        words("section subsection subsubsection paragraph textbf textit emph textrm textsf texttt "
              "text operatorname");
    const std::set<std::string> math_args = words(
        "mathrm mathbf mathit mathsf mathtt mathcal mathbb overline underline hat bar vec tilde");
    const std::map<std::string, int> raw_args = {
        {"label", 1},  {"input", 1},  {"include", 1},    {"begin", 1},        {"end", 1},
        {"hspace", 1}, {"vspace", 1}, {"setcounter", 2}, {"addtocounter", 2}, {"rule", 2}};
    const std::map<std::string, int> fallback_args = {
        {"ref", 1}, {"pageref", 1}, {"eqref", 1}, {"cite", 1}, {"fixed", 0}, {"globalword", 0}};
    const std::set<std::string> structural =
        words("par newpage clearpage noindent quad qquad smallskip medskip bigskip displaystyle "
              "textstyle scriptstyle scriptscriptstyle");
    bool at(const std::u32string &value) const {
        return text.compare(i, value.size(), value) == 0;
    }
    std::string slice(size_t a, size_t b) const {
        return utf8(text.substr(a, b - a));
    }
    std::string mark(size_t a, size_t b, const std::string &kind = "token") {
        Span s;
        s.id = current->slot * 1000000 + int(current->spans.size());
        s.start = origin_offset + a;
        s.end = origin_offset + b;
        s.line = lines[a];
        s.column = columns[a];
        s.endLine = lines[b];
        s.endColumn = columns[b];
        s.file = filename;
        s.text = slice(a, b);
        s.kind = kind;
        current->spans.push_back(std::move(s));
        auto id = std::to_string(current->spans.back().id);
        return general ? "\\bakoSet{" + id + "}" : "\\bakoattr=" + id + " ";
    }
    std::string whitespace() {
        size_t a = i;
        while (i < text.size() && space(text[i])) {
            ++i;
        }
        return slice(a, i);
    }
    std::string group(char32_t open = '{', char32_t close = '}') {
        size_t a = i;
        if (i >= text.size() || text[i] != open) {
            return "";
        }
        int depth = 0;
        while (i < text.size()) {
            auto c = text[i++];
            if (c == '\\') {
                if (i < text.size()) {
                    ++i;
                }
            } else if (c == open) {
                ++depth;
            } else if (c == close && !--depth) {
                break;
            }
        }
        return slice(a, i);
    }
    std::string control() {
        size_t a = i++;
        if (i < text.size()) {
            if (letter(text[i])) {
                while (i < text.size() && letter(text[i])) {
                    ++i;
                }
            } else {
                ++i;
            }
        }
        return slice(a, i);
    }
    void opaque_field() {
        whitespace();
        if (i>=text.size()) return;
        if (std::u32string(U"}$^_&").find(text[i])!=std::u32string::npos) return;
        if (text[i]=='{') { group(); return; }
        if (text[i]!='\\') { ++i; return; }
        auto name=control().substr(1);
        // A field can start with a macro that still needs its arguments. Keep
        // accents and fractions intact, including unbraced script fields.
        if (name=="sqrt" && i<text.size() && text[i]=='[') group('[',']');
        int count=words("frac dfrac tfrac binom").count(name) ? 2 :
            (math_args.count(name) || text_args.count(name) ||
             words("sqrt dot ddot dddot ddddot breve check acute grave widehat widetilde mathnormal mathfrak mathscr boldsymbol pmb underbrace overbrace").count(name) ? 1 : 0);
        while (count--) opaque_field();
    }
    std::string argument(bool math) {
        auto ws = whitespace();
        if (i < text.size() && text[i] == '{') {
            ++i;
            return ws + "{" + sequence(math, '}') + "}";
        }
        size_t a = i;
        if (i < text.size()) {
            if (text[i] == '\\') {
                if (general) opaque_field(); else control();
            } else {
                ++i;
            }
        }
        return ws + "{" + mark(a, i) + slice(a, i) + "}";
    }
    std::string command(bool math) {
        size_t a = i;
        auto cmd = control();
        const auto control_end = i;
        auto name = cmd.substr(1);
        if (general && words("' ` ^ ~ = . u v H c k b d r").count(name)) {
            opaque_field();
            return mark(a, i, "macro-origin") + slice(a, i) + reset;
        }
        if (general && (name == "(" || name == "[" || name == ")" || name == "]"))
            return reset + cmd;
        if (general && name=="cdots") {
            auto saved=i; whitespace();
            if (i<text.size() && std::u32string(U"),.;:]!?").find(text[i])!=std::u32string::npos) {
                ++i;
                // amsmath peeks at the following delimiter to choose spacing.
                // Preserve that lookahead as one generated-content origin.
                return mark(a,i,"macro-origin")+slice(a,i)+reset;
            }
            i=saved;
        }
        if (symbols.count(name)) {
            return mark(a, i) + cmd + " " + reset;
        }
        if (name == "frac" || name == "dfrac" || name == "tfrac" || name == "binom") {
            auto first = argument(true);
            auto second = argument(true);
            return reset + cmd + first + second + reset;
        }
        if (name == "sqrt") {
            std::string option;
            if (i < text.size() && text[i] == '[') {
                option = group('[', ']');
            }
            return reset + cmd + option + argument(true) + reset;
        }
        const bool live_math_arg = general && words("widetilde widehat dot ddot dddot ddddot breve check acute grave mathnormal mathfrak mathscr boldsymbol pmb underbrace overbrace").count(name);
        if (general && (math_args.count(name) || live_math_arg)) {
            auto start=i;
            whitespace();
            if (i<text.size() && text[i]!='{') {
                opaque_field();
                // Bracing an originally unbraced nested accent can change its
                // placement. Keep its field grammar exactly as TeX received it.
                return mark(a,i,"macro-origin")+slice(a,i)+reset;
            }
            i=start;
        }
        if (text_args.count(name) || math_args.count(name) || live_math_arg) {
            if (i < text.size() && text[i] == '*') {
                cmd += '*';
                ++i;
            }
            std::string option;
            if (general && i<text.size() && text[i]=='[') option=group('[',']');
            auto arg=argument(math_args.count(name) || live_math_arg);
            if (general && text_args.count(name) && i<text.size() && (text[i]==',' || text[i]=='.')) {
                // LaTeX's italic-correction lookahead must see the punctuation,
                // not a provenance setter. The argument group restores this ID.
                auto punctuation=mark(i,i+1);auto raw=rune(text[i++]);
                return punctuation+cmd+option+arg+raw+reset;
            }
            return reset + cmd + option + arg + reset;
        }
        if (words("left right big Big bigl bigr Bigl Bigr").count(name)) {
            whitespace();
            if (i < text.size()) {
                if (text[i] == '\\') {
                    control();
                } else {
                    ++i;
                }
            }
            return mark(a, i) + slice(a, i) + " " + reset;
        }
        if (name == "pair") {
            auto arg = argument(math);
            auto origin = mark(a, i, "macro-origin");
            arg.insert(arg.size() - 1, origin);
            return origin + cmd + arg + reset;
        }
        if (fallback_args.count(name)) {
            for (int n = 0; n < fallback_args.at(name); ++n) {
                whitespace();
                group();
            }
            return mark(a, i, "macro-origin") + slice(a, i) + reset;
        }
        if (raw_args.count(name)) {
            if (general && i < text.size() && text[i] == '*') ++i;
            for (int n = 0; n < raw_args.at(name); ++n) {
                whitespace();
                group();
            }
            auto raw = slice(a, i);
            if (name == "begin" && i < text.size() && text[i] == '[' &&
                (general || raw.find("{tikzpicture}") != std::string::npos)) {
                raw += group('[', ']');
            }
            return reset + raw;
        }
        if (structural.count(name) || unicode(name).size() == 1) {
            return reset + cmd + (structural.count(name) ? " " : "");
        }
        current->warnings.push_back(
            {{"file", filename},
             {"offset", a},
             {"command", name},
             {"reason", "unknown command: arguments are not instrumented"}});
        if (general && i<text.size() && text[i]=='*') ++i;
        size_t end = i;
        if (general && !math && i < text.size() && text[i]=='$') {
            size_t closing=i+1;
            int braces=0;
            for (;closing<text.size();++closing) {
                auto c=text[closing];
                if (c=='\\') { ++closing; continue; }
                if (c=='%') { while(closing<text.size() && text[closing]!='\n') ++closing; continue; }
                if (c=='{') ++braces;
                else if (c=='}') --braces;
                else if (c=='$' && !braces) break;
            }
            if (closing<text.size()) {
                i=closing+1;
                return mark(a,i,"macro-origin")+slice(a,i);
            }
        }
        while (true) {
            whitespace();
            if (i < text.size() && (text[i] == '{' || text[i] == '[')) {
                auto c = text[i];
                group(c, c == '{' ? '}' : ']');
                end = i;
            } else {
                i = end;
                break;
            }
        }
        if (general) {
            auto result = mark(a,i,"macro-origin") + slice(a,i);
            if (i == control_end) {
                // Preserve TeX's skip-blanks state after a control word. The
                // inserted setter would otherwise turn its delimiter into glue.
                bool newline = false;
                while (i < text.size() && space(text[i])) {
                    if (text[i]=='\n') {
                        if (newline) { ++i; return result + " " + reset + "\\par\n"; }
                        newline=true;
                    }
                    ++i;
                }
                result += " ";
            }
            return result + reset;
        }
        return reset + slice(a, i) + " " + reset;
    }
    std::string tikz() {
        auto found = text.find(U"\\end{tikzpicture}", i);
        size_t end = found == std::u32string::npos ? text.size() : found + 17;
        std::string out = reset;
        while (i < end) {
            size_t node = text.find(U"\\node", i);
            bool matched = false;
            while (node < end) {
                size_t label = node + 5;
                if (label < text.size() && letter(text[label])) {
                    node = text.find(U"\\node", label);
                    continue;
                }
                while (label < end && text[label] != ';' && text[label] != '{' &&
                       text[label] != '}') {
                    ++label;
                }
                if (label < end && text[label] == '{') {
                    out += slice(i, label + 1);
                    i = label + 1;
                    out += sequence(false, '}') + "}";
                    matched = true;
                    break;
                }
                node = text.find(U"\\node", label);
            }
            if (!matched) {
                out += slice(i, end);
                i = end;
            }
        }
        return out + reset;
    }
    std::string sequence(bool math, char32_t stop = 0) {
        std::string out;
        out.reserve(text.size() * 12);
        while (i < text.size()) {
            auto c = text[i];
            if (c == stop) {
                ++i;
                break;
            }
            if (at(U"\\begin{tikzpicture}")) {
                out += tikz();
                continue;
            }
            if (general && at(U"\\begin{")) {
                auto close = text.find('}', i + 7);
                if (close != std::u32string::npos) {
                    auto environment = slice(i + 7, close);
                    if (!words("math displaymath equation equation* align align* gather gather* multline multline* itemize enumerate center quote quotation flushleft flushright appendices subappendices abstract proof theorem lemma proposition corollary remark definition").count(environment)) {
                        // Unknown environments can contain non-text grammars (table
                        // preambles, verbatim, graphics). Keep their contents intact.
                        auto ending = U"\\end{" + unicode(environment) + U"}";
                        auto opening = U"\\begin{" + unicode(environment) + U"}";
                        size_t end = close + 1; int depth = 1;
                        while (depth && end < text.size()) {
                            auto next_end = text.find(ending, end), next_begin = text.find(opening, end);
                            if (next_end == std::u32string::npos) { end = text.size(); break; }
                            if (next_begin < next_end) { ++depth; end = next_begin + opening.size(); }
                            else { --depth; end = next_end + ending.size(); }
                        }
                        size_t begin = i; i = end;
                        out += mark(begin, end, "macro-origin") + slice(begin, end) + reset;
                        continue;
                    }
                    if (words("math displaymath equation equation* align align* gather gather* multline multline*").count(environment)) math = true;
                }
            }
            if (general && (at(U"\\(") || at(U"\\["))) math = true;
            if (general && (at(U"\\)") || at(U"\\]"))) math = false;
            if (general && at(U"\\end{")) {
                auto close=text.find('}',i+5);
                if (close!=std::u32string::npos && words("math displaymath equation equation* align align* gather gather* multline multline*").count(slice(i+5,close))) math=false;
            }
            if (at(U"\\begin{align")) {
                math = true;
            }
            if (at(U"\\end{align")) {
                math = false;
            }
            if (c == '%') {
                auto end = text.find('\n', i);
                if (end == std::u32string::npos) {
                    end = text.size();
                }
                out += slice(i, end);
                i = end;
                continue;
            }
            if (c == '\\') {
                out += command(math);
                continue;
            }
            ++i;
            if (c == '$') {
                math = !math;
                if (general && i<text.size() && text[i]=='$') { ++i; out += reset+"$$"+(math?reset:""); }
                else out += reset + "$" + reset;
            } else if (c == '{') {
                out += "{" + sequence(math, '}') + "}";
            } else if ((c == '_' || c == '^') && math) {
                out += rune(c) + argument(true);
            } else if (general && c == '\'' && math) {
                size_t first=i-1;
                while(i<text.size() && text[i]=='\'') ++i;
                out += mark(first,i) + slice(first,i) + reset;
            } else if (space(c) || c == '&' || c == '}') {
                out += rune(c);
            } else if (c == '~') {
                out += reset + "~";
            } else {
                out += mark(i - 1, i) + rune(c);
            }
        }
        return out;
    }

  public:
    std::string instrument(const std::string &source, const std::string &file,
                           const std::string &key = "", int base_offset = 0,
                           int base_line = 0, int base_column = 0, bool live = false) {
        general = live;
        reset = live ? "\\bakoSet{0}" : bako::reset;
        origin_offset = base_offset;
        auto identity = key.empty() ? file : key;
        auto it = files.find(identity);
        if (it == files.end()) {
            File f;
            f.slot = files.size() + 1;
            it = files.emplace(identity, std::move(f)).first;
            slots[it->second.slot] = &it->second;
        }
        current = &it->second;
        current->source = source;
        current->spans.clear();
        current->warnings = Json::array();
        filename = file;
        text = unicode(source);
        i = 0;
        lines.resize(text.size() + 1);
        columns.resize(text.size() + 1);
        int line = base_line, column = base_column;
        for (size_t n = 0; n <= text.size(); ++n) {
            lines[n] = line;
            columns[n] = column;
            if (n < text.size()) {
                if (text[n] == '\n') {
                    ++line;
                    column = 0;
                } else {
                    column += text[n] > 0xffff ? 2 : 1;
                }
            }
        }
        bool conditional = false;
        if (general) for (size_t at=0; at<text.size(); ++at) {
            if (text[at]=='%') {
                while (at<text.size() && text[at]!='\n') ++at;
            } else if (text[at]=='\\') {
                auto end=at+1;
                while (end<text.size() && letter(text[end])) ++end;
                if (primitive_conditional(utf8(text.substr(at+1,end-at-1)))) { conditional=true; break; }
                at=end>at+1 ? end-1 : at+1;
            }
        }
        // Setters between a conditional and its operands can change which
        // branch TeX selects. Preserve this complete block as a macro origin.
        if (general && (conditional || std::regex_search(source, std::regex(R"(\\(def|gdef|edef|xdef|newcommand|renewcommand|catcode|verb)\b)")))) {
            i = text.size();
            return mark(0, i, "macro-origin") + source + reset;
        }
        return sequence(false);
    }
    const Span *find(int id) const {
        int slot = id / 1000000, offset = id % 1000000;
        auto found=slots.find(slot);
        if (found==slots.end()) return nullptr;
        const auto &f=*found->second;
        return offset < int(f.spans.size()) ? &f.spans[offset] : nullptr;
    }
    Json warnings() const {
        Json out = Json::array();
        for (const auto &pair : files) {
            for (const auto &warning : pair.second.warnings) {
                out.push_back(warning);
            }
        }
        return out;
    }
    Json export_spans() const {
        Json out = Json::object();
        for (const auto &span : current->spans) {
            out[std::to_string(span.id)] = span.object();
        }
        return out;
    }
};
} // namespace bako
