#pragma once
#include "common.hpp"

namespace bako {
inline const std::string reset = "\\bakoattr=0 ";
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


// Source text is indexed, never parsed or rewritten. LuaHBTeX supplies the
// token length after applying its own catcodes and control-sequence scanner.
class Sources {
    struct File {
        std::u32string text;
        std::vector<Span> spans;
        int slot=0;
    };
    std::map<std::string,File> files;
    std::unordered_map<int,File*> slots;
    File *current=nullptr;
public:
    std::string index(const std::string &source,const std::string &file,
                           const std::string &key="",int base_offset=0,
                           int base_line=0,int base_column=0,bool live=false) {
        (void)live;
        auto identity=key.empty()?file:key;
        auto it=files.find(identity);
        if(it==files.end()) {
            if(files.size()>=2146) throw std::runtime_error("Too many source files/blocks");
            File f;f.slot=int(files.size())+1;
            it=files.emplace(identity,std::move(f)).first;slots[it->second.slot]=&it->second;
        }
        current=&it->second;
        current->text=unicode(source);current->spans.clear();
        if(current->text.size()>=1000000) throw std::runtime_error("Source file/block exceeds one million characters");
        int line=base_line,column=base_column;
        for(size_t n=0;n<current->text.size();++n) {
            Span s;s.id=current->slot*1000000+int(n);s.file=file;
            s.start=base_offset+int(n);s.end=s.start+1;s.line=line;s.column=column;
            auto c=current->text[n];
            if(c=='\n'){++line;column=0;}else column+=c>0xffff?2:1;
            s.endLine=line;s.endColumn=column;s.text=rune(c);s.kind="token";
            current->spans.push_back(std::move(s));
        }
        return source;
    }
    void ranges(const fs::path &path) {
        std::ifstream in(path);int id,length;
        while(in>>id>>length) {
            auto found=slots.find(id/1000000);if(found==slots.end())continue;
            auto &f=*found->second;int offset=id%1000000;
            if(length<=0||offset<0||size_t(offset+length)>f.spans.size())continue;
            auto &s=f.spans[offset];const auto &last=f.spans[offset+length-1];
            s.end=s.start+length;s.endLine=last.line;s.endColumn=last.column+(f.text[offset+length-1]>0xffff?2:1);
            if(f.text[offset+length-1]=='\n'){++s.endLine;s.endColumn=0;}
            s.text=utf8(f.text.substr(offset,length));
            s.kind=(length>1&&f.text[offset]=='\\')?"macro-origin":"token";
        }
    }
    void manifest(const fs::path &path) const {
        std::string out;
        for(const auto &[name,f]:files) out+=std::to_string(f.slot)+"\t"+name+"\n";
        write(path,out);
    }
    const Span *find(int id) const {
        auto f=slots.find(id/1000000);if(f==slots.end())return nullptr;
        int offset=id%1000000;
        return offset>=0&&offset<int(f->second->spans.size())?&f->second->spans[offset]:nullptr;
    }
    Json warnings() const{return Json::array();}
};
} // namespace bako
