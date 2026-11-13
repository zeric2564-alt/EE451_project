#include "core.hpp"
#include <omp.h>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

using Clock=std::chrono::steady_clock;
double seconds(Clock::time_point a){return std::chrono::duration<double>(Clock::now()-a).count();}
struct Options {
    std::string scene="many",mode="serial",output,raw,diagnostics;
    int width=400,height=225,spp=32,depth=10,threads=1,tile=16,chunk=1,repeats=1,warmup=0;
    uint64_t seed=451;
};
int positive(const std::string& s){size_t end=0;long long n=std::stoll(s,&end);if(end!=s.size()||n<1||n>1000000)throw std::runtime_error("invalid positive integer: "+s);return static_cast<int>(n);}
Options parse(int argc,char** argv){
    Options o;
    for(int i=1;i<argc;++i){std::string k=argv[i];
        if(k=="--help"){std::cout<<"raytrace --scene simple|many|clustered --mode serial|row-static|row-dynamic|tile-static|tile-dynamic\n"
          <<"  --width N --height N --spp N --depth N --threads N --tile N --chunk N\n"
          <<"  --seed N --repeats N --warmup 0|1 --output image.ppm --raw image.f64 --diagnostics threads.csv\n";std::exit(0);}
        if(i+1==argc)throw std::runtime_error("missing value for "+k);
        std::string v=argv[++i];
        if(k=="--scene")o.scene=v;else if(k=="--mode")o.mode=v;else if(k=="--output")o.output=v;
        else if(k=="--raw")o.raw=v;else if(k=="--diagnostics")o.diagnostics=v;
        else if(k=="--width")o.width=positive(v);else if(k=="--height")o.height=positive(v);
        else if(k=="--spp")o.spp=positive(v);else if(k=="--depth")o.depth=positive(v);
        else if(k=="--threads")o.threads=positive(v);else if(k=="--tile")o.tile=positive(v);
        else if(k=="--chunk")o.chunk=positive(v);else if(k=="--repeats")o.repeats=positive(v);
        else if(k=="--warmup"){if(v!="0"&&v!="1")throw std::runtime_error("warmup must be 0 or 1");o.warmup=v=="1";}
        else if(k=="--seed"){size_t end=0;o.seed=std::stoull(v,&end);if(end!=v.size()||v[0]=='-')throw std::runtime_error("invalid seed");}
        else throw std::runtime_error("unknown argument: "+k);
    }
    if(o.mode!="serial"&&o.mode!="row-static"&&o.mode!="row-dynamic"&&o.mode!="tile-static"&&o.mode!="tile-dynamic")throw std::runtime_error("unknown mode");
    if(static_cast<uint64_t>(o.width)*o.height>100000000ULL)throw std::runtime_error("image too large");
    if(o.threads>1024||o.depth>1000)throw std::runtime_error("threads/depth exceed safety limits");
    return o;
}
struct alignas(64) Stat {uint64_t tasks=0,pixels=0;double active_s=0,finish_s=0;};
struct RenderResult {double time;int actual;std::vector<Stat> stats;};
RenderResult render(const rt::Scene& scene,const Options& o,std::vector<rt::Vec>& image){
    rt::Camera camera(static_cast<double>(o.width)/o.height);
    bool diagnostic=!o.diagnostics.empty(),tiled=o.mode.rfind("tile",0)==0;
    int nx=(o.width+o.tile-1)/o.tile,ny=(o.height+o.tile-1)/o.tile;
    int tasks=tiled?nx*ny:o.height,actual=1;
    std::vector<Stat> stats(static_cast<size_t>(o.threads));
    auto run=[&](int task){
        int x0=0,x1=o.width,y0=task,y1=task+1;
        if(tiled){x0=(task%nx)*o.tile;x1=std::min(x0+o.tile,o.width);y0=(task/nx)*o.tile;y1=std::min(y0+o.tile,o.height);}
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x)image[static_cast<size_t>(y)*o.width+x]=rt::pixel(scene,camera,x,y,o.width,o.height,o.spp,o.depth,o.seed);
        return static_cast<uint64_t>(x1-x0)*(y1-y0);
    };
    bool dynamic=o.mode.find("dynamic")!=std::string::npos;
    // Static uses contiguous blocks by default; dynamic chunk counts rows/tiles.
    omp_set_schedule(dynamic?omp_sched_dynamic:omp_sched_static,dynamic?o.chunk:0);
    auto start=Clock::now();
    if(o.mode=="serial"){
        for(int t=0;t<tasks;++t)run(t);
        if(diagnostic){stats[0].tasks=static_cast<uint64_t>(tasks);stats[0].pixels=static_cast<uint64_t>(o.width)*o.height;stats[0].active_s=seconds(start);stats[0].finish_s=stats[0].active_s;}
    }else{
        #pragma omp parallel num_threads(o.threads)
        {
            int id=omp_get_thread_num();
            #pragma omp single
            actual=omp_get_num_threads();
            #pragma omp for schedule(runtime)
            for(int t=0;t<tasks;++t){
                if(diagnostic){auto a=Clock::now();uint64_t p=run(t);stats[id].active_s+=seconds(a);++stats[id].tasks;stats[id].pixels+=p;stats[id].finish_s=seconds(start);}
                else run(t);
            }
        }
    }
    return {seconds(start),actual,std::move(stats)};
}
uint64_t hash_image(const std::vector<rt::Vec>& image){
    uint64_t h=14695981039346656037ULL;
    for(auto p:image)for(double d:{p.x,p.y,p.z}){uint64_t bits;std::memcpy(&bits,&d,8);for(int i=0;i<8;++i){h^=(bits>>(8*i))&255;h*=1099511628211ULL;}}
    return h;
}
int main(int argc,char** argv){try{
    auto process_start=Clock::now();Options o=parse(argc,argv);omp_set_dynamic(0);
    auto setup_start=Clock::now();auto scene=rt::make_scene(o.scene);
    std::vector<rt::Vec> image(static_cast<size_t>(o.width)*o.height);double setup=seconds(setup_start);
    if(o.warmup)render(scene,o,image);
    for(int repeat=0;repeat<o.repeats;++repeat){
        auto r=render(scene,o,image);uint64_t hash=hash_image(image);
        std::cout<<std::setprecision(10)<<"{\"scene\":\""<<o.scene<<"\",\"mode\":\""<<o.mode<<"\",\"threads\":"<<o.threads<<",\"actual_threads\":"<<r.actual
          <<",\"width\":"<<o.width<<",\"height\":"<<o.height<<",\"spp\":"<<o.spp<<",\"depth\":"<<o.depth<<",\"tile\":"<<o.tile<<",\"chunk\":"<<o.chunk
          <<",\"seed\":"<<o.seed<<",\"spheres\":"<<scene.spheres.size()<<",\"repeat\":"<<repeat<<",\"setup_s\":"<<setup<<",\"render_s\":"<<r.time
          <<",\"setup_plus_render_s\":"<<setup+r.time<<",\"diagnostic\":"<<(o.diagnostics.empty()?"false":"true")<<",\"hash\":\""<<std::hex<<hash<<std::dec<<"\"}\n";
        if(!o.diagnostics.empty()){
            std::ofstream f(o.diagnostics);if(!f)throw std::runtime_error("cannot open diagnostics");
            f<<"thread,tasks,pixels,active_s,finish_s\n"<<std::setprecision(10);
            for(int t=0;t<r.actual;++t){auto s=r.stats[t];f<<t<<','<<s.tasks<<','<<s.pixels<<','<<s.active_s<<','<<s.finish_s<<'\n';}
        }
    }
    auto output_start=Clock::now();
    if(!o.output.empty()){
        std::ofstream f(o.output,std::ios::binary);if(!f)throw std::runtime_error("cannot open output");f<<"P6\n"<<o.width<<' '<<o.height<<"\n255\n";
        for(auto p:image)for(double d:{p.x,p.y,p.z}){if(!std::isfinite(d))throw std::runtime_error("nonfinite pixel");unsigned char v=static_cast<unsigned char>(256*std::clamp(std::sqrt(std::max(0.0,d)),0.0,.999));f.put(static_cast<char>(v));}
        if(!f)throw std::runtime_error("failed to write image");
    }
    if(!o.raw.empty()){
        std::ofstream f(o.raw,std::ios::binary);if(!f)throw std::runtime_error("cannot open raw output");
        for(auto p:image)for(double d:{p.x,p.y,p.z})f.write(reinterpret_cast<const char*>(&d),sizeof(d));
        if(!f)throw std::runtime_error("failed to write raw image");
    }
    std::cerr<<std::setprecision(8)<<"output_s="<<seconds(output_start)<<" process_s="<<seconds(process_start)<<'\n';
    return 0;
}catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 1;}}
