#include "core.hpp"
#include "png.hpp"
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
    std::string scene="many",mode="serial",output,raw,diagnostics,regions,timing,mesh="assets/bunny.obj";
    int width=400,height=225,spp=32,depth=10,threads=1,tile=16,chunk=1,repeats=1,warmup=0;
    uint64_t seed=451;
};
int positive(const std::string& s){size_t end=0;long long n=std::stoll(s,&end);if(end!=s.size()||n<1||n>1000000)throw std::runtime_error("invalid positive integer: "+s);return static_cast<int>(n);}
Options parse(int argc,char** argv){
    Options o;
    for(int i=1;i<argc;++i){std::string k=argv[i];
        if(k=="--help"){std::cout<<"raytrace --scene room|uneven|bunny|bunny-mixed|simple|many|clustered --mode serial|row-static|row-dynamic|tile-static|tile-dynamic\n"
          <<"  --width N --height N --spp N --depth N --threads N --tile N --chunk N\n"
          <<"  --seed N --repeats N --warmup 0|1 --output image.png --raw image.f64 --diagnostics threads.csv\n  --regions regions.csv --timing timings.csv --mesh assets/bunny.obj\n";std::exit(0);}
        if(i+1==argc)throw std::runtime_error("missing value for "+k);
        std::string v=argv[++i];
        if(k=="--scene")o.scene=v;else if(k=="--mode")o.mode=v;else if(k=="--output")o.output=v;
        else if(k=="--regions")o.regions=v;else if(k=="--timing")o.timing=v;else if(k=="--mesh")o.mesh=v;
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
struct RenderResult {double time,preparation;int actual;std::vector<Stat> stats;std::vector<rt::Counters> regions;};
RenderResult render(const rt::Scene& scene,const Options& o,std::vector<rt::Vec>& image){
    auto preparation_start=Clock::now();
    rt::Camera camera(static_cast<double>(o.width)/o.height,scene.dark);
    bool diagnostic=!o.diagnostics.empty(),tiled=o.mode.rfind("tile",0)==0;
    int nx=(o.width+o.tile-1)/o.tile,ny=(o.height+o.tile-1)/o.tile;
    int tasks=tiled?nx*ny:o.height,actual=1;
    std::vector<Stat> stats(static_cast<size_t>(o.threads));
    int rx=(o.width+31)/32,ry=(o.height+31)/32;
    bool profiling=!o.regions.empty();
    // Worker-private region counters avoid atomics even when scheduling splits a region.
    std::vector<std::vector<rt::Counters>> counts(profiling?o.threads:0);
    if(profiling)for(auto& c:counts)c.resize(static_cast<size_t>(rx)*ry);
    auto run=[&](int task,int worker){
        int x0=0,x1=o.width,y0=task,y1=task+1;
        if(tiled){x0=(task%nx)*o.tile;x1=std::min(x0+o.tile,o.width);y0=(task/nx)*o.tile;y1=std::min(y0+o.tile,o.height);}
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x)image[static_cast<size_t>(y)*o.width+x]=rt::pixel(scene,camera,x,y,o.width,o.height,o.spp,o.depth,o.seed,profiling?&counts[worker][static_cast<size_t>(y/32)*rx+x/32]:nullptr);
        return static_cast<uint64_t>(x1-x0)*(y1-y0);
    };
    bool dynamic=o.mode.find("dynamic")!=std::string::npos;
    // Static uses contiguous blocks by default; dynamic chunk counts rows/tiles.
    omp_set_schedule(dynamic?omp_sched_dynamic:omp_sched_static,dynamic?o.chunk:0);
    double preparation=seconds(preparation_start);
    auto start=Clock::now();
    if(o.mode=="serial"){
        for(int t=0;t<tasks;++t)run(t,0);
        if(diagnostic){stats[0].tasks=static_cast<uint64_t>(tasks);stats[0].pixels=static_cast<uint64_t>(o.width)*o.height;stats[0].active_s=seconds(start);stats[0].finish_s=stats[0].active_s;}
    }else{
        #pragma omp parallel num_threads(o.threads)
        {
            int id=omp_get_thread_num();
            #pragma omp single
            actual=omp_get_num_threads();
            #pragma omp for schedule(runtime)
            for(int t=0;t<tasks;++t){
                if(diagnostic){auto a=Clock::now();uint64_t p=run(t,id);stats[id].active_s+=seconds(a);++stats[id].tasks;stats[id].pixels+=p;stats[id].finish_s=seconds(start);}
                else run(t,id);
            }
        }
    }
    double elapsed=seconds(start);
    std::vector<rt::Counters> regions(profiling?static_cast<size_t>(rx)*ry:0);
    for(const auto& worker:counts)for(size_t i=0;i<regions.size();++i){
        regions[i].rays+=worker[i].rays;regions[i].path_depth+=worker[i].path_depth;
        regions[i].node_visits+=worker[i].node_visits;regions[i].triangle_tests+=worker[i].triangle_tests;
    }
    return {elapsed,preparation,actual,std::move(stats),std::move(regions)};
}
uint64_t hash_image(const std::vector<rt::Vec>& image){
    uint64_t h=14695981039346656037ULL;
    for(auto p:image)for(double d:{p.x,p.y,p.z}){uint64_t bits;std::memcpy(&bits,&d,8);for(int i=0;i<8;++i){h^=(bits>>(8*i))&255;h*=1099511628211ULL;}}
    return h;
}
int main(int argc,char** argv){try{
    auto process_start=Clock::now();Options o=parse(argc,argv);omp_set_dynamic(0);
    auto setup_start=Clock::now();auto load_start=Clock::now();
    auto scene=rt::make_scene(o.scene,o.mesh,false);double loading=seconds(load_start);
    auto bvh_start=Clock::now();scene.build();double bvh=seconds(bvh_start);
    std::vector<rt::Vec> image(static_cast<size_t>(o.width)*o.height);double setup=seconds(setup_start);
    if(o.warmup)render(scene,o,image);
    std::ofstream timing;
    if(!o.timing.empty()){timing.open(o.timing);if(!timing)throw std::runtime_error("cannot open timing CSV");
        timing<<"scene,mode,threads,actual_threads,width,height,spp,depth,tile,chunk,seed,repeat,triangles,loading_s,bvh_s,task_prepare_s,render_s,png_s,output_s,end_to_end_s,hash\n";}
    for(int repeat=0;repeat<o.repeats;++repeat){
        auto r=render(scene,o,image);uint64_t hash=hash_image(image);
        if(!o.diagnostics.empty()){
            std::ofstream f(o.diagnostics);if(!f)throw std::runtime_error("cannot open diagnostics");
            f<<"thread,tasks,pixels,active_s,finish_s\n"<<std::setprecision(10);
            for(int t=0;t<r.actual;++t){auto st=r.stats[t];f<<t<<','<<st.tasks<<','<<st.pixels<<','<<st.active_s<<','<<st.finish_s<<'\n';}
            if(!f)throw std::runtime_error("failed to write diagnostics");
        }
        if(!o.regions.empty()){
            std::ofstream f(o.regions);if(!f)throw std::runtime_error("cannot open region CSV");
            f<<"x,y,width,height,rays,path_depth,node_visits,triangle_tests\n";
            int nx=(o.width+31)/32;
            for(size_t i=0;i<r.regions.size();++i){auto c=r.regions[i];int x=static_cast<int>(i%nx)*32,y=static_cast<int>(i/nx)*32;
                f<<x<<','<<y<<','<<std::min(32,o.width-x)<<','<<std::min(32,o.height-y)<<','<<c.rays<<','<<c.path_depth<<','<<c.node_visits<<','<<c.triangle_tests<<'\n';}
            if(!f)throw std::runtime_error("failed to write regions");
        }
    auto output_start=Clock::now();
    double png_s=0;
    bool is_png=o.output.size()>=4&&o.output.substr(o.output.size()-4)==".png";
    if(!o.output.empty()&&is_png){
        auto png_start=Clock::now();png::Bytes bytes;bytes.reserve(image.size()*3);
        for(auto p:image)for(double d:{p.x,p.y,p.z}){if(!std::isfinite(d))throw std::runtime_error("nonfinite pixel");bytes.push_back(static_cast<unsigned char>(256*std::clamp(std::sqrt(std::max(0.0,d)),0.0,.999)));}
        png::write(o.output,o.width,o.height,bytes);png_s=seconds(png_start);
    }
    if(!o.output.empty()&&!is_png){
        std::ofstream f(o.output,std::ios::binary);if(!f)throw std::runtime_error("cannot open output");f<<"P6\n"<<o.width<<' '<<o.height<<"\n255\n";
        for(auto p:image)for(double d:{p.x,p.y,p.z}){if(!std::isfinite(d))throw std::runtime_error("nonfinite pixel");unsigned char v=static_cast<unsigned char>(256*std::clamp(std::sqrt(std::max(0.0,d)),0.0,.999));f.put(static_cast<char>(v));}
        if(!f)throw std::runtime_error("failed to write image");
    }
    if(!o.raw.empty()){
        std::ofstream f(o.raw,std::ios::binary);if(!f)throw std::runtime_error("cannot open raw output");
        for(auto p:image)for(double d:{p.x,p.y,p.z})f.write(reinterpret_cast<const char*>(&d),sizeof(d));
        if(!f)throw std::runtime_error("failed to write raw image");
    }
    double output_s=seconds(output_start),end_to_end=seconds(process_start);
    std::cout<<std::setprecision(10)<<"{\"scene\":\""<<o.scene<<"\",\"mode\":\""<<o.mode<<"\",\"threads\":"<<o.threads<<",\"actual_threads\":"<<r.actual
      <<",\"width\":"<<o.width<<",\"height\":"<<o.height<<",\"spp\":"<<o.spp<<",\"depth\":"<<o.depth<<",\"tile\":"<<o.tile<<",\"chunk\":"<<o.chunk
      <<",\"seed\":"<<o.seed<<",\"spheres\":"<<scene.spheres.size()<<",\"triangles\":"<<scene.triangles.size()<<",\"repeat\":"<<repeat
      <<",\"loading_s\":"<<loading<<",\"bvh_s\":"<<bvh<<",\"setup_s\":"<<setup<<",\"task_prepare_s\":"<<r.preparation<<",\"render_s\":"<<r.time<<",\"setup_plus_render_s\":"<<setup+r.preparation+r.time
      <<",\"png_s\":"<<png_s<<",\"output_s\":"<<output_s<<",\"end_to_end_s\":"<<end_to_end
      <<",\"diagnostic\":"<<((o.diagnostics.empty()&&o.regions.empty())?"false":"true")<<",\"hash\":\""<<std::hex<<hash<<std::dec<<"\"}\n";
    if(timing.is_open()){timing<<std::setprecision(10)<<o.scene<<','<<o.mode<<','<<o.threads<<','<<r.actual<<','<<o.width<<','<<o.height<<','<<o.spp<<','<<o.depth<<','<<o.tile<<','<<o.chunk<<','<<o.seed<<','<<repeat<<','<<scene.triangles.size()<<','<<loading<<','<<bvh<<','<<r.preparation<<','<<r.time<<','<<png_s<<','<<output_s<<','<<end_to_end<<','<<std::hex<<hash<<std::dec<<'\n';timing.flush();if(!timing)throw std::runtime_error("failed to write timings");}
    }

    return 0;
}catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 1;}}
