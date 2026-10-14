#pragma once
#ifndef _WIN32
#include "common.hpp"
#include <iomanip>
namespace bako {
// One owner for all process groups and immutable pdfTeX checkpoints in a
// generated session. Source prefix checks are independent of rendered pages.
class PdfTeXState {
    fs::path directory;
    SocketDirectory socket_directory;
    std::set<pid_t> groups;
    std::map<fs::path,Json> dependencies;
    std::set<fs::path> outputs;
    std::string manifest;
    static std::string prefix_hash(const std::string &s,size_t n) {
        uint64_t h=UINT64_C(14695981039346656037);
        for(size_t i=0;i<n;++i){h^=static_cast<unsigned char>(s[i]);h*=UINT64_C(1099511628211);}
        std::ostringstream out;out<<std::hex<<std::setfill('0')<<std::setw(16)<<h;return out.str();
    }
    std::vector<std::pair<fs::path,Json>> checkpoints() const {
        std::vector<std::pair<fs::path,Json>> out;
        for(const auto &e:fs::directory_iterator(directory)) {
            auto name=e.path().filename().string();
            if(starts(name,"pdftex-cp-")&&e.path().extension()==".json")try {
                auto data=Json::parse(read(e.path()));int pid=data.at("pid");
                if(pid>1&&groups.count(getpgid(pid)))out.emplace_back(e.path(),std::move(data));
            }catch(const std::exception &){}
        }
        std::sort(out.begin(),out.end(),[](const auto &a,const auto &b){return a.first<b.first;});return out;
    }
    void retire(const std::pair<fs::path,Json> &cp) {
        int pid=cp.second.at("pid");
        if(groups.count(getpgid(pid)))kill(pid,SIGKILL);
        fs::remove(cp.first);auto socket=cp.first;socket.replace_extension(".sock");fs::remove(socket);
    }
public:
    int restored_pages=0, restored_serial=0;
    explicit PdfTeXState(fs::path path):directory(std::move(path)){}
    ~PdfTeXState(){clear();}
    void track(pid_t pid){if(pid>1)groups.insert(pid);}
    void clear() {
        for(pid_t group:groups)kill(-group,SIGKILL);
        groups.clear();dependencies.clear();
        std::error_code ignored;
        if(fs::is_directory(directory))for(const auto &e:fs::directory_iterator(directory)) {
            auto name=e.path().filename().string();
            if(starts(name,"pdftex-cp-")||starts(name,"pdftex-done."))fs::remove(e.path(),ignored);
        }
    }
    void remember(const std::string &stem) {
        manifest=read(directory/"bako-sources.tsv");
        auto states=checkpoints();std::set<fs::path> sources;outputs.clear();
        if(!states.empty())for(const auto &[file,data]:states.back().second.at("sources").items())sources.insert(fs::path(file));
        std::istringstream recorder(read(directory/(stem+".fls")));std::string line;
        std::vector<fs::path> inputs;
        while(getline_crlf(recorder,line)) {
            if(starts(line,"INPUT "))inputs.push_back(fs::weakly_canonical(directory/line.substr(6)));
            if(starts(line,"OUTPUT "))outputs.insert(fs::weakly_canonical(directory/line.substr(7)));
        }
        dependencies.clear();
        for(const auto &p:inputs)if(!sources.count(p)&&!outputs.count(p)&&fs::is_regular_file(p))dependencies[p]=file_stamp(p);
        // Keep useful page states separately from preamble/first-page states.
        int preamble=0,pages=0;
        for(auto it=states.rbegin();it!=states.rend();++it) {
            bool discard=it->second.at("pages")==0 ? ++preamble>12 : ++pages>64;
            if(discard)retire(*it);
        }
    }
    pid_t resume() {
        restored_pages=0;restored_serial=0;
        if(dependencies.empty())return -1;
        if(read(directory/"bako-sources.tsv")!=manifest)return -1;
        for(const auto &[p,stamp]:dependencies)if(!fs::is_regular_file(p)||file_stamp(p)!=stamp)return -1;
        auto states=checkpoints();
        for(auto it=states.rbegin();it!=states.rend();++it) {
            bool valid=true;
            for(const auto &[file,source]:it->second.at("sources").items()) {
                if(!fs::is_regular_file(file)){valid=false;break;}
                auto bytes=read(file);size_t frontier=source.at("frontier");
                if(frontier>bytes.size()||prefix_hash(bytes,frontier)!=source.at("hash")){valid=false;break;}
            }
            if(!valid)continue;
            std::set<fs::path> retained;
            for(const auto &p:it->second.value("outputs",Json::array()))retained.insert(p.get<std::string>());
            for(const auto &p:outputs)if(!retained.count(p)) {
                auto relative=p.lexically_relative(directory);
                if(!relative.empty()&&*relative.begin()!="..")fs::remove(p);
            }
            int serial=it->second.at("serial");
            for(const auto &cp:states)if(cp.second.at("serial").get<int>()>serial)retire(cp);
            fs::remove(directory/"pdftex-done.json");
            Fd dir(open(directory.c_str(),O_DIRECTORY|O_RDONLY|O_CLOEXEC));
            Fd socket(unix_socket(false));sockaddr_un address={};address.sun_family=AF_UNIX;
            auto name=it->first.filename();name.replace_extension(".sock");
            if(dir.value<0)return -1;
            auto path=socket_directory.path(directory,dir.value,name.string());
            if(path.size()>=sizeof(address.sun_path))return -1;
            strcpy(address.sun_path,path.c_str());
            if(connect(socket.value,reinterpret_cast<sockaddr*>(&address),sizeof(address)))continue;
            timeval timeout={5,0};setsockopt(socket.value,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
            if(::write(socket.value,"R",1)!=1)continue;
            char response[64]={};ssize_t n=::read(socket.value,response,sizeof(response)-1);
            if(n<=0)continue;
            pid_t pid=std::atoi(response);if(pid<=1)continue;
            restored_pages=it->second.at("pages");restored_serial=serial;return pid;
        }
        return -1;
    }
    bool wait(pid_t worker,std::atomic<bool> *cancel) {
        auto started=Clock::now();
        for(;;) {
            if(fs::is_regular_file(directory/"pdftex-done.json"))try {
                auto done=Json::parse(read(directory/"pdftex-done.json"));
                if(done.at("pid")==worker)return done.at("ok");
            }catch(const std::exception &){}
            if((cancel&&cancel->load())||elapsed(started)>90000){clear();throw std::runtime_error("pdfTeX update cancelled or timed out");}
            char state=process_state(worker);
            if(state=='Z'||state==0)return false;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }
};
} // namespace bako
#endif
