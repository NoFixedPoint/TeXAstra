#pragma once
#ifdef _WIN32
#include "windows/distribution.hpp"
#else
#include "cache.hpp"
extern char **environ;

namespace bako {
// Configure once, before worker threads. TeX, kpathsea and auxiliary tools then
// share one selected installation and lookup environment for this process.
class Distribution {
    fs::path runtime, work;
    std::string requested;
    std::string run(const fs::path &program, std::vector<std::string> args, int seconds=10) {
        args.insert(args.begin(), program.string());
        std::vector<char *> argv;
        for (auto &arg : args) argv.push_back(arg.data());
        argv.push_back(nullptr);
        Fd log(open((work/"probe.log").c_str(), O_CREAT|O_TRUNC|O_WRONLY|O_CLOEXEC, 0600));
        if (log.value<0) throw std::runtime_error("Cannot create distribution probe log");
        posix_spawn_file_actions_t actions;
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addchdir_np(&actions,work.c_str());
        posix_spawn_file_actions_addopen(&actions,0,"/dev/null",O_RDONLY,0);
        posix_spawn_file_actions_adddup2(&actions,log.value,1);
        posix_spawn_file_actions_adddup2(&actions,log.value,2);
        posix_spawn_file_actions_addclosefrom_np(&actions,3);
        posix_spawnattr_t attr;
        posix_spawnattr_init(&attr);
        posix_spawnattr_setflags(&attr,POSIX_SPAWN_SETSID);
        pid_t pid=-1;
        int error=posix_spawn(&pid,program.c_str(),&actions,&attr,argv.data(),environ);
        posix_spawn_file_actions_destroy(&actions);posix_spawnattr_destroy(&attr);
        if (error) throw std::runtime_error("Cannot run "+program.string()+": "+strerror(error));
        auto started=Clock::now();int status=0;
        for (;;) {
            auto ended=waitpid(pid,&status,WNOHANG);
            if (ended==pid) break;
            if ((ended<0&&errno!=EINTR)||elapsed(started)>seconds*1000) {
                kill(-pid,SIGKILL);while(waitpid(pid,nullptr,0)<0&&errno==EINTR){}
                throw std::runtime_error(program.filename().string()+" preflight timed out; check the selected installation.");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        auto output=read(work/"probe.log");
        if (output.size()>16000) output=output.substr(output.size()-16000);
        if (!WIFEXITED(status)||WEXITSTATUS(status)) throw std::runtime_error(program.filename().string()+":\n"+output);
        while(!output.empty()&&(output.back()=='\n'||output.back()=='\r'))output.pop_back();
        return output;
    }
    static bool executable(const fs::path &path) {
        return fs::is_regular_file(path)&&access(path.c_str(),X_OK)==0;
    }
    void discover() {
        std::set<std::string> seen;
        auto add=[&](const fs::path &directory) {
            if (!executable(directory/"kpsewhich"))return;
            auto value=fs::canonical(directory).string();
            if(seen.insert(value).second)report["candidates"].push_back(value);
        };
        std::istringstream paths(getenv("PATH")?getenv("PATH"):"");std::string part;
        while(std::getline(paths,part,':')) if(!part.empty())add(fs::absolute(part));
        // Upstream TeX Live installations need not be on the inherited PATH.
        if(fs::is_directory("/usr/local/texlive")) for(const auto &entry:fs::directory_iterator("/usr/local/texlive"))
            if(entry.is_directory())add(entry.path()/"bin/x86_64-linux");
        add("/usr/bin");
        if(!requested.empty()) {
            if(!fs::path(requested).is_absolute())throw std::runtime_error("texBinDirectory / --tex-bin must be an absolute Linux directory in the selected WSL instance.");
            if(!executable(fs::path(requested)/"kpsewhich"))throw std::runtime_error("Selected TeX binary directory has no executable kpsewhich: "+requested+". Select an installed TeX Live binary directory.");
            bin=fs::canonical(requested);add(bin);
        } else {
            if(report["candidates"].empty())throw std::runtime_error("No TeX Live installation found. Install TeX Live in the selected Linux/WSL environment, or set bakoma.texBinDirectory to its binary directory. BaKoMa does not install packages.");
            bin=report["candidates"][0].get<std::string>();
        }
        report["binDirectory"]=bin.string();
        auto path=bin.string()+":"+(getenv("PATH")?getenv("PATH"):"");
        setenv("PATH",path.c_str(),1);
    }
    std::string kpse(std::vector<std::string> args) { return run(bin/"kpsewhich",std::move(args)); }
    void configure(const std::string &compiler) {
        discover();
        report["lookupOverrides"]=Json::object();
        for(const auto *name:{"TEXMFCNF","TEXMF","TEXMFROOT","TEXMFDIST","TEXMFHOME","TEXMFVAR","TEXMFCONFIG","TEXFORMATS","TEXINPUTS","BIBINPUTS","BSTINPUTS","OSFONTDIR"})
            if(const char *value=getenv(name))report["lookupOverrides"][name]=value;
        // Ask the selected kpathsea, rather than guessing distro-specific paths.
        auto config=kpse({"--var-value=TEXMFCNF"});
        if(config.empty())throw std::runtime_error("Selected kpsewhich returned an empty TEXMFCNF search path.");
        setenv("TEXMFCNF",config.c_str(),1);
        report["texmfcnf"]=config;
        report["texmfRoot"]=kpse({"--var-value=TEXMFROOT"});
        auto version=kpse({"--version"});report["kpathseaVersion"]=version.substr(0,version.find('\n'));
        if(report["kpathseaVersion"].get<std::string>().find("MiKTeX")!=std::string::npos)
            throw std::runtime_error("MiKTeX integration is not supported by this Linux preview runtime. Select TeX Live.");
        Json identity={{"schema",1},{"bin",bin.string()},{"config",config},{"overrides",report["lookupOverrides"]},{"compiler",compiler}};
        // Recorder output starts after configuration lookup. Fingerprint these
        // separately, including newly added config files and filename databases.
        Json lookup=Json::object();std::string file;
        std::istringstream configs(kpse({"--all","texmf.cnf"}));
        while(std::getline(configs,file))if(fs::is_regular_file(file))lookup[fs::canonical(file).string()]=file_stamp(file);
        std::istringstream trees(kpse({"--expand-path=$TEXMFDBS"}));
        while(std::getline(trees,file,':')) {
            while(starts(file,"!"))file.erase(0,1);
            auto database=fs::path(file)/"ls-R";
            if(fs::is_regular_file(database))lookup[fs::canonical(database).string()]=file_stamp(database);
        }
        identity["lookupFiles"]=lookup;report["lookupFiles"]=lookup;
        report["tools"]=Json::object();
        report["toolStamps"]=Json::object();
        for(const auto *name:{"kpsewhich","lualatex","xelatex","pdflatex","bibtex","biber","makeindex"}) {
            auto path=bin/name;
            report["tools"][name]=executable(path)?Json(path.string()):Json(nullptr);
            if(executable(path)){identity[name]=file_stamp(path);report["toolStamps"][name]=identity[name];}
        }
        version=run(runtime/"bakoma-luahbtex",{"--version"});report["bundledEngine"]=version.substr(0,version.find('\n'));
        identity["engine"]=digest(read(runtime/"bakoma-luahbtex"));
        report["bundledEngineSha256"]=identity["engine"];
        if(executable(bin/"lualatex")) {
            version=run(bin/"lualatex",{"--version"});report["distributionEngine"]=version.substr(0,version.find('\n'));
        }
        if(compiler=="live") {
            std::string format;
            try {format=kpse({"--progname=lualatex","--engine=luahbtex","--format=fmt","lualatex.fmt"});}catch(const std::exception &){}
            if(!fs::is_regular_file(format))throw std::runtime_error("LuaLaTeX format lualatex.fmt is missing from the selected distribution. Maintain formats with that distribution's tools, or select another compatible installation.");
            format_path=fs::canonical(format);
            report["format"]=format_path.string();identity["format"]=Json::array({format_path.string(),file_stamp(format_path)});
        }
        auto state_path=work.parent_path()/("preflight-"+digest(identity.dump())+".json");
        Json dependencies;
        bool reused=false;
        if(fs::is_regular_file(state_path))try {
            dependencies=Json::parse(read(state_path)).at("dependencies");
            reused=dependencies.is_object()&&!dependencies.empty();
            for(const auto &[file,stamp]:dependencies.items()) if(file_stamp(file)!=stamp)reused=false;
        }catch(const std::exception &){reused=false;}
        if(!reused) {
            write(work/"check.tex","\\documentclass{article}\n\\begin{document}BaKoMa preflight: $x^2$.\\end{document}\n");
            std::vector<std::string> args={"--no-shell-escape","--interaction=nonstopmode","--halt-on-error","--recorder","check.tex"};
            fs::path program=runtime/"bakoma-luahbtex";
            if(compiler=="live")args.insert(args.begin(),{"--fmt="+format_path.string(),"--progname=lualatex"});
            else program=tool(compiler);
            try {run(program,args,30);}
            catch(const std::exception &e) {
                throw std::runtime_error("Selected LaTeX installation failed the compatibility compile ("+bin.string()+"). The bundled engine or selected format/packages may be incompatible. Select a compatible TeX Live installation; no formats or packages were modified.\n"+std::string(e.what()));
            }
            if(!fs::is_regular_file(work/"check.pdf"))throw std::runtime_error("Compatibility compile did not produce a PDF.");
            dependencies=Json::object();
            if(!format_path.empty())dependencies[format_path.string()]=file_stamp(format_path);
            std::istringstream recorder(read(work/"check.fls"));std::string line;
            while(std::getline(recorder,line))if(starts(line,"INPUT ")) {
                auto file=fs::weakly_canonical(work/line.substr(6));
                auto relative=file.lexically_relative(work);
                if(!relative.empty()&&*relative.begin()==".."&&fs::is_regular_file(file))dependencies[file.string()]=file_stamp(file);
            }
            auto temporary=state_path.string()+"."+std::to_string(getpid())+".new";
            write(temporary,Json({{"dependencies",dependencies}}).dump());fs::rename(temporary,state_path);
        }
        report["preflightReused"]=reused;report["dependencies"]=dependencies;
        report["identity"]=digest(Json::array({identity,dependencies}).dump());
        report["ok"]=true;
    }
  public:
    fs::path bin, format_path;
    Json report={{"schema",1},{"ok",false},{"candidates",Json::array()},
                 {"packageMaintenance","Use the selected distribution's package manager; BaKoMa never installs or updates packages."}};
    Distribution(fs::path bundled, std::string selected, const std::string &compiler="live")
        :runtime(std::move(bundled)),requested(std::move(selected)) {
        try {
            const char *cache=getenv("XDG_CACHE_HOME"),*home=getenv("HOME");
            auto root=(cache&&*cache?fs::path(cache):fs::path(home?home:"/tmp")/".cache")/"bakoma-revived"/"environment-v1";
            fs::create_directories(root);
            std::string pattern=(root/"probe-XXXXXX").string();std::vector<char> name(pattern.begin(),pattern.end());name.push_back(0);
            auto created=mkdtemp(name.data());if(!created)throw std::runtime_error("Cannot create isolated compatibility probe directory");
            work=created;report["mode"]=compiler;configure(compiler);
        }catch(const std::exception &e){report["error"]=e.what();}
        if(!work.empty()){std::error_code ignored;fs::remove_all(work,ignored);}
    }
    void require_ready() const {if(!report.value("ok",false))throw std::runtime_error(report.value("error","LaTeX distribution preflight failed"));}
    fs::path tool(const std::string &name) const {
        auto path=bin/name;
        if(!executable(path))throw std::runtime_error("Required LaTeX tool '"+name+"' is missing from selected external LaTeX distribution "+bin.string()+". Install it with that distribution's package manager.");
        return path;
    }
    std::string diagnose(std::string log) const {
        static const std::regex missing(R"(File [`']([^`']+)[`'] not found)");std::smatch match;
        if(std::regex_search(log,match,missing))log="Missing LaTeX input '"+match[1].str()+"' in selected distribution "+bin.string()+". If it is a package/class, install it using that distribution's package manager; if it is project-local, check the project root and filename.\n"+log;
        return log;
    }
};
}
#endif
