#include "source.hpp"
#include "edits.hpp"
#include <cassert>
using namespace bako;
int main(int argc,char **argv) {
    assert(argc==2);
    Sources sources;
    for(const auto &source:std::vector<std::string>{u8"α😀\\command\ntext\n",u8"α😀\\command\nchanged\n",u8"α😀\\c\n", ""}) {
        sources.index(source,"paper.tex","",7,3,2);
        auto chars=unicode(source);int line=3,column=2;
        for(size_t n=0;n<chars.size();++n) {
            const auto *span=sources.find(1000000+int(n));
            assert(span&&span->start==7+int(n)&&span->line==line&&span->column==column);
            if(chars[n]=='\n'){++line;column=0;}else column+=chars[n]>0xffff?2:1;
            assert(span->endLine==line&&span->endColumn==column&&span->text==rune(chars[n]));
        }
        assert(!sources.find(1000000+int(chars.size())));
    }
    sources.index("\\command rest","paper.tex");
    write(argv[1],"1000000 8\n");sources.ranges(argv[1]);
    sources.index("\\command changed","paper.tex");
    assert(sources.find(1000000)->text=="\\command");
    sources.index("\\cmd changed","paper.tex");
    assert(sources.find(1000000)->text=="\\");
    // An unrelated legacy-encoded draft must not prevent indexing the project.
    // Preserve its bytes for TeX and retire any previous navigation mappings.
    const std::string legacy = "% legacy draft\n\xff\n";
    assert(sources.index(legacy,"paper.tex")==legacy);
    assert(!sources.find(1000000));
    sources.manifest(argv[1]);
    assert(read(argv[1]).find("paper.tex")==std::string::npos);
    sources.index("Other document", "other.tex");
    sources.index("Recovered", "paper.tex");
    assert(sources.find(1000000)->text=="R");
    assert(sources.find(2000000)->text=="O");
    sources.manifest(argv[1]);
    assert(read(argv[1]).find("paper.tex")!=std::string::npos);
    std::map<std::string,std::string> buffers;std::map<std::string,int> versions;
    apply_source_edit(buffers,versions,{{"file","a"},{"source",u8"a😀bé\r\nx"},{"sourceVersion",1}});
    Json edit={{"file","a"},{"baseVersion",1},{"sourceVersion",2},{"baseLength",8},
               {"changes",Json::array({{{"rangeOffset",7},{"rangeLength",1},{"text","last"}},
                                      {{"rangeOffset",3},{"rangeLength",1},{"text","B"}}})}};
    apply_source_edit(buffers,versions,edit);
    assert(buffers.at("a")==u8"a😀Bé\r\nlast");
    for(int fault=0;fault<4;++fault) {
        auto invalid=edit;invalid["baseVersion"]=2;invalid["sourceVersion"]=3;invalid["baseLength"]=11;
        if(fault==0)invalid["baseVersion"]=1;
        if(fault==1)invalid["baseLength"]=10;
        if(fault==2)invalid["changes"][0]["rangeOffset"]=2; // middle of surrogate pair
        if(fault==3)invalid["changes"][0]["rangeOffset"]=999;
        bool rejected=false;try{apply_source_edit(buffers,versions,invalid);}catch(const std::exception &){rejected=true;}
        assert(rejected&&buffers.at("a")==u8"a😀Bé\r\nlast"&&versions.at("a")==2);
    }
    std::cout<<"Unicode positions, retained command ranges, UTF-16 edits and invalid bases passed\n";
}
