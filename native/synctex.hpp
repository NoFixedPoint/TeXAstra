#pragma once
#include "source.hpp"
#include <cmath>
#include <functional>

namespace bako {
// SyncTeX belongs to the selected external compiler. Keep its coarser source
// line results distinct from the patched engine's token-origin mappings.
class SyncTeX {
    fs::path mirror, directory, pdf;
    const Sources &sources;
    std::function<std::string(const std::vector<std::string> &)> run;
    using Record = std::map<std::string,std::string>;
    static std::vector<Record> records(const std::string &output) {
        std::vector<Record> result;
        std::istringstream input(output); std::string line;
        bool active=false;
        while(std::getline(input,line)) {
            if(!line.empty() && line.back()=='\r') line.pop_back();
            if(line=="SyncTeX result begin") { active=true; continue; }
            if(line=="SyncTeX result end") break;
            if(!active) continue;
            auto split=line.find(':'); if(split==std::string::npos) continue;
            auto key=line.substr(0,split);
            if(key=="Output") result.emplace_back();
            if(!result.empty()) result.back()[key]=line.substr(split+1);
        }
        return result;
    }
    Json source(const std::string &input, int line) const {
        auto path=fs::weakly_canonical(directory/fs::u8path(input));
        auto relative=path.lexically_relative(mirror);
        if(relative.empty() || relative.is_absolute() || *relative.begin()=="..") return nullptr;
        return sources.source_line(relative.generic_string(),line);
    }
public:
    SyncTeX(fs::path root, fs::path cwd, fs::path output, const Sources &indexed,
            std::function<std::string(const std::vector<std::string> &)> query)
        : mirror(std::move(root)), directory(std::move(cwd)), pdf(std::move(output)), sources(indexed), run(std::move(query)) {}
    Json backward(int page, double x, double y) const {
        if(page<0 || !std::isfinite(x) || !std::isfinite(y)) return nullptr;
        auto output=run({"edit","-o",std::to_string(page+1)+":"+std::to_string(x)+":"+std::to_string(y)+":"+pdf.u8string()});
        for(const auto &record:records(output)) {
            if(!record.count("Input") || !record.count("Line")) continue;
            auto location=source(record.at("Input"),std::stoi(record.at("Line"))-1);
            if(location.is_null()) continue;
            location["page"]=page;location["rect"]=Json::array({x,y-6,x+2,y+6});
            return location;
        }
        return nullptr;
    }
    Json forward(const std::string &file, int line, int column, int preferred_page) const {
        auto location=sources.source_line(file,line);
        if(location.is_null()) return nullptr;
        const auto input=inside(mirror,file);
        auto output=run({"view","-i",std::to_string(line+1)+":"+std::to_string(std::max(column,0))+":"+input.u8string(),"-o",pdf.u8string()});
        Json best=nullptr;int distance=2147483647;
        for(const auto &record:records(output)) {
            if(!record.count("Page") || !record.count("h") || !record.count("v") || !record.count("W") || !record.count("H")) continue;
            int page=std::stoi(record.at("Page"))-1;
            if(page<0 || std::abs(page-preferred_page)>=distance) continue;
            double x=std::stod(record.at("h")),y=std::stod(record.at("v")),w=std::stod(record.at("W")),h=std::stod(record.at("H"));
            if(!std::isfinite(x+y+w+h)) continue;
            best=location;best["page"]=page;best["rect"]=Json::array({x,y-std::max(h,1.0),x+std::max(w,1.0),y});
            distance=std::abs(page-preferred_page);
        }
        return best;
    }
};
}
