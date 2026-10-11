#pragma once
#include "source.hpp"

namespace bako {
// Checkpoint splitting is separate from engine-owned source tracking.
inline bool primitive_conditional(const std::string &name) {
    static const auto names = words("if ifcat ifnum ifdim ifodd ifvmode ifhmode ifmmode ifinner "
        "ifvoid ifhbox ifvbox ifx ifeof iftrue iffalse ifcase ifdefined ifcsname iffontchar ifincsname ifabsnum ifabsdim");
    return names.count(name) != 0;
}

struct DocumentBlock {
    std::string source;
    int offset = 0, line = 0, column = 0;
};
// Split only at top-level paragraph boundaries. A saved TeX process retains
// the partially built page, floats, macro state and everything before a block.
class LiveDocument {
  public:
    std::string prefix, suffix, original;
    std::vector<DocumentBlock> blocks;
    explicit LiveDocument(const std::string &source) : original(source) {
        auto u = unicode(source);
        std::u32string visible = u;
        bool comment = false;
        for (size_t i = 0; i < u.size(); ++i) {
            if (u[i] == '\n') comment = false;
            if (!comment && u[i] == '\\') { ++i; continue; }
            if (u[i] == '%') comment = true;
            if (comment) visible[i] = ' ';
        }
        const std::u32string begin = U"\\begin{document}", end = U"\\end{document}";
        auto a = visible.find(begin), b = visible.find(end, a == std::u32string::npos ? 0 : a + begin.size());
        if (a == std::u32string::npos || b == std::u32string::npos)
            throw std::runtime_error("Live preview needs explicit begin{document} and end{document} in the main file");
        a += begin.size();
        prefix = utf8(u.substr(0, a)); suffix = utf8(u.substr(b));
        std::vector<int> lines(u.size()+1), columns(u.size()+1);
        int line = 0, column = 0;
        for (size_t i = 0; i <= u.size(); ++i) {
            lines[i] = line; columns[i] = column;
            if (i < u.size()) { if (u[i] == '\n') { ++line; column=0; } else column += u[i]>0xffff ? 2 : 1; }
        }
        size_t start = a;
        std::vector<bool> groups;
        int arguments = 0, environments = 0, conditionals = 0;
        bool math = false, blank = false;
        auto push = [&](size_t finish) {
            if (finish > start) blocks.push_back({utf8(u.substr(start, finish-start)), int(start), lines[start], columns[start]});
            start = finish;
        };
        for (size_t i = a; i < b; ++i) {
            auto c = visible[i];
            if (c == '\\') {
                auto word_end=i+1;
                while (word_end<b && letter(visible[word_end])) ++word_end;
                auto command=utf8(visible.substr(i+1,word_end-i-1));
                if (primitive_conditional(command)) ++conditionals;
                else if (command=="fi" && conditionals) --conditionals;
                // TeX's skipped branch does not expand the Lua driver that
                // supplies later blocks. Keep the whole conditional together.
                // Its skipped text can even contain unmatched braces/environments.
                if (conditionals || command=="fi") {
                    i=word_end>i+1 ? word_end-1 : std::min(i+1,b-1);
                    blank=false;
                    continue;
                }
                if (visible.compare(i, 7, U"\\begin{") == 0) {
                    auto end=visible.find('}',i+7);
                    if (!words("appendices subappendices").count(utf8(visible.substr(i+7,end-i-7)))) ++environments;
                }
                else if (visible.compare(i, 5, U"\\end{") == 0) {
                    auto end=visible.find('}',i+5);
                    if (!words("appendices subappendices").count(utf8(visible.substr(i+5,end-i-5)))) environments = std::max(0, environments-1);
                }
                else if (i+1 < b && (visible[i+1]=='(' || visible[i+1]=='[')) math = true;
                else if (i+1 < b && (visible[i+1]==')' || visible[i+1]==']')) math = false;
                // A control symbol consumes its following character; a control
                // word leaves its brace arguments to the scanner below.
                if (i+1 < b && !letter(visible[i+1])) ++i;
                blank = false;
                continue;
            }
            if (conditionals) continue;
            if (c == '{') {
                size_t previous=i;
                while (previous>a && space(visible[previous-1])) --previous;
                bool argument=arguments>0 || (previous>a && visible[previous-1]==']');
                size_t word=previous;
                while (word>a && letter(visible[word-1])) --word;
                if (word>a && word<previous && visible[word-1]=='\\') {
                    auto command=utf8(visible.substr(word,previous-word));
                    argument=argument || !words("noindent par small footnotesize scriptsize tiny normalsize large Large LARGE huge Huge bfseries itshape rmfamily sffamily ttfamily centering raggedright raggedleft").count(command);
                }
                groups.push_back(argument); if(argument) ++arguments;
            }
            if (c == '}' && !groups.empty()) { if(groups.back()) --arguments; groups.pop_back(); }
            if (c == '$') { math = !math; if (i+1 < b && visible[i+1]=='$') ++i; }
            if (c == '\n') {
                if (blank && !arguments && !environments && !math) push(i+1);
                blank = true;
            } else if (c != ' ' && c != '\t' && c != '\r') blank = false;
        }
        push(b);
        if (blocks.empty()) blocks.push_back({"\n",int(a),lines[a],columns[a]});
        if (blocks.size()>2048) throw std::runtime_error("Live document exceeds 2048 paragraph blocks");
    }
    int first_change(const LiveDocument &next) const {
        if (prefix != next.prefix || suffix != next.suffix) return -1;
        size_t i = 0;
        while (i < blocks.size() && i < next.blocks.size() && blocks[i].source == next.blocks[i].source) ++i;
        return int(i)+1;
    }
    void generate(const fs::path &directory, const std::string &file, Sources &sources) const {
        fs::create_directories(directory / "bako-blocks");
        for (size_t i = 0; i < blocks.size(); ++i) {
            auto &b = blocks[i];
            auto name = page_name(int(i)+1, "block-", ".tex");
            auto rewritten = sources.index(b.source, file, "bako-blocks/"+name, b.offset, b.line, b.column, true);
            // A percent at EOF stops \input's end-line character adding glue.
            write(directory / "bako-blocks" / name, rewritten + "%\n");
        }
        sources.manifest(directory / "bako-sources.tsv");
        write(directory / "bako-block-count", std::to_string(blocks.size()));
        auto injection = std::string("\\directlua{dofile('provenance.lua')}\n") +
            "\\ifcsname pdfstringdefDisableCommands\\endcsname\\pdfstringdefDisableCommands{\\def\\bakoSet#1{}}\\fi\n"
            "\\directlua{dofile('snapshot.lua')}\n";
        auto main = prefix;
        auto where = main.rfind("\\begin{document}");
        main.insert(where, injection);
        std::string driver;
        for (int index=1;index<=2048;++index) driver += "\\directlua{bako_block("+std::to_string(index)+")}%\n";
        write(directory / "bako-driver.tex", driver);
        main += "\\input{bako-driver.tex}%\n" + suffix;
        write(directory / "main.tex", main);
    }
};
}
