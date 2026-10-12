#pragma once
#include "common.hpp"

namespace bako {
// VS Code changes use UTF-16 offsets in the document before the event. Apply
// every event in order even when rendering coalesces several queued revisions.
inline void apply_source_edit(std::map<std::string,std::string> &sources,
                              std::map<std::string,int> &versions,const Json &request) {
    const auto file=request.at("file").get<std::string>();
    const int version=request.value("sourceVersion",0);
    if(request.contains("source")) {
        sources[file]=request.at("source").get<std::string>();
        versions[file]=version;
        return;
    }
    auto found=sources.find(file);
    if(found==sources.end() || !versions.count(file) ||
       versions.at(file)!=request.at("baseVersion").get<int>() || version<=versions.at(file))
        throw std::runtime_error("Source edit base unavailable; send the complete buffer");
    const auto &source=found->second;
    // Byte boundaries for UTF-16 units; the middle of a surrogate pair is not
    // a valid UTF-8 boundary. Reject it rather than corrupting source text.
    std::vector<size_t> boundaries{0};
    for(size_t byte=0;byte<source.size();) {
        auto c=static_cast<unsigned char>(source[byte]);
        size_t count=c<0x80?1:c<0xe0?2:c<0xf0?3:4;
        if(count==4)boundaries.push_back(std::string::npos);
        byte+=count;
        if(byte>source.size())throw std::runtime_error("Invalid UTF-8 edit base");
        boundaries.push_back(byte);
    }
    if(request.at("baseLength").get<size_t>()!=boundaries.size()-1)
        throw std::runtime_error("Source edit length mismatch; send the complete buffer");
    struct Change {size_t start,end;std::string text;};
    std::vector<Change> changes;
    for(const auto &change:request.at("changes")) {
        auto offset=change.at("rangeOffset").get<size_t>(),length=change.at("rangeLength").get<size_t>();
        if(offset>=boundaries.size() || length>=boundaries.size()-offset ||
           boundaries[offset]==std::string::npos || boundaries[offset+length]==std::string::npos)
            throw std::runtime_error("Invalid source edit range");
        changes.push_back({boundaries[offset],boundaries[offset+length],change.at("text").get<std::string>()});
    }
    std::stable_sort(changes.begin(),changes.end(),[](const auto &a,const auto &b){return a.start<b.start;});
    std::string updated;updated.reserve(source.size());size_t cursor=0;
    for(const auto &change:changes) {
        if(change.start<cursor)throw std::runtime_error("Overlapping source edits");
        updated.append(source,cursor,change.start-cursor);updated+=change.text;cursor=change.end;
    }
    updated.append(source,cursor,std::string::npos);
    found->second=std::move(updated);versions[file]=version;
}
} // namespace bako
