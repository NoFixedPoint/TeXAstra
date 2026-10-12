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
        std::vector<int> lines, supplementary;
        mutable std::map<int,Span> spans;
        std::string name;
        bool mapped = true;
        int base_offset=0, base_line=0, base_column=0;
        int slot=0;
        std::pair<int,int> position(int offset) const {
            auto line=std::upper_bound(lines.begin(),lines.end(),offset)-lines.begin()-1;
            int start=lines[line];
            int extra=int(std::lower_bound(supplementary.begin(),supplementary.end(),offset)-
                          std::lower_bound(supplementary.begin(),supplementary.end(),start));
            return {base_line+int(line),offset-start+extra+(line==0?base_column:0)};
        }
        Span &span(int offset) const {
            auto [it,inserted]=spans.try_emplace(offset);
            auto &s=it->second;
            if(inserted) {
                s.id=slot*1000000+offset;s.file=name;
                s.start=base_offset+offset;s.end=s.start+1;
                auto start=position(offset),end=position(offset+1);
                s.line=start.first;s.column=start.second;s.endLine=end.first;s.endColumn=end.second;
                s.text=rune(text[offset]);s.kind="token";
            }
            return s;
        }
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
        std::u32string next;
        try { next=unicode(source); }
        catch(const std::range_error &) {
            // Project discovery also visits unrelated, legacy-encoded drafts.
            // Leave their bytes intact for TeX, but do not invent UTF-8 offsets.
            // Keep an existing slot reserved so other files' IDs stay stable.
            if(it!=files.end()) {
                it->second.text.clear();it->second.spans.clear();
                it->second.mapped=false;
            }
            return source;
        }
        if(it==files.end()) {
            if(files.size()>=2146) throw std::runtime_error("Too many source files/blocks");
            File f;f.slot=int(files.size())+1;
            it=files.emplace(identity,std::move(f)).first;slots[it->second.slot]=&it->second;
        }
        current=&it->second;
        current->mapped=true;
        if(next.size()>=1000000) throw std::runtime_error("Source file/block exceeds one million characters");
        size_t prefix=0;
        while(prefix<next.size() && prefix<current->text.size() && next[prefix]==current->text[prefix]) ++prefix;
        // Only rendered origins need rich Span objects. Keep verified command
        // ranges in the unchanged prefix; materialize other spans on demand.
        if(current->name!=file || current->base_offset!=base_offset ||
           current->base_line!=base_line || current->base_column!=base_column) current->spans.clear();
        for(auto p=current->spans.begin();p!=current->spans.end();) {
            if(p->second.end>base_offset+int(prefix)) p=current->spans.erase(p);
            else ++p;
        }
        current->text=std::move(next);current->name=file;
        current->base_offset=base_offset;current->base_line=base_line;current->base_column=base_column;
        current->lines={0};current->supplementary.clear();
        for(size_t n=0;n<current->text.size();++n) {
            auto c=current->text[n];
            if(c=='\n')current->lines.push_back(int(n)+1);
            if(c>0xffff)current->supplementary.push_back(int(n));
        }
        return source;
    }
    void ranges(const fs::path &path) {
        std::ifstream in(path);int id,length;
        while(in>>id>>length) {
            auto found=slots.find(id/1000000);if(found==slots.end())continue;
            auto &f=*found->second;int offset=id%1000000;
            if(length<=0||offset<0||size_t(offset)+size_t(length)>f.text.size())continue;
            auto &s=f.span(offset);auto end=f.position(offset+length);
            s.end=s.start+length;s.endLine=end.first;s.endColumn=end.second;
            s.text=utf8(f.text.substr(offset,length));
            s.kind=(length>1&&f.text[offset]=='\\')?"macro-origin":"token";
        }
    }
    void manifest(const fs::path &path, const fs::path &root = {}) const {
        std::string out;
        for(const auto &[name,f]:files) if(f.mapped)
            out+=std::to_string(f.slot)+"\t"+(root / name).generic_string()+"\n";
        write(path,out);
    }
    const Span *find(int id) const {
        auto f=slots.find(id/1000000);if(f==slots.end())return nullptr;
        int offset=id%1000000;
        return offset>=0&&offset<int(f->second->text.size())?&f->second->span(offset):nullptr;
    }
    Json warnings() const{return Json::array();}
    Span range(int id, int length) const {
        auto original=find(id);
        if(!original)return {};
        Span result=*original;
        if(length<=0)return result;
        auto &f=*slots.at(id/1000000);int offset=id%1000000;
        if(size_t(offset)+size_t(length)>f.text.size())return {};
        auto end=f.position(offset+length);
        result.end=result.start+length;result.endLine=end.first;result.endColumn=end.second;
        result.text=utf8(f.text.substr(offset,length));
        result.kind=length>1&&f.text[offset]=='\\'?"macro-origin":"token";
        return result;
    }
    Json source_line(const std::string &name, int line) const {
        auto found=files.find(name);
        if(found==files.end() || !found->second.mapped) return nullptr;
        const auto &f=found->second;
        if(line<0 || line>=int(f.lines.size())) return nullptr;
        int start=f.lines[line], end=line+1<int(f.lines.size()) ? f.lines[line+1]-1 : int(f.text.size());
        while(start<end && space(f.text[start])) ++start;
        while(end>start && space(f.text[end-1])) --end;
        const auto first=f.position(start), last=f.position(end);
        return {{"file",name},{"start",start},{"end",end},{"line",first.first},{"column",first.second},
            {"endLine",last.first},{"endColumn",last.second},{"text",utf8(f.text.substr(start,end-start))},{"kind","source-line"}};
    }
};
} // namespace bako
