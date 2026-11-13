#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
#include <fstream>
#include <sstream>

namespace rt {
constexpr double pi = 3.14159265358979323846;
struct Vec {
    double x=0, y=0, z=0;
    double operator[](int i) const { return i==0?x:(i==1?y:z); }
    Vec operator-() const { return {-x,-y,-z}; }
    Vec& operator+=(Vec b) { x+=b.x;y+=b.y;z+=b.z;return *this; }
};
inline Vec operator+(Vec a,Vec b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
inline Vec operator-(Vec a,Vec b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
inline Vec operator*(Vec a,double b){return {a.x*b,a.y*b,a.z*b};}
inline Vec operator*(double b,Vec a){return a*b;}
inline Vec operator*(Vec a,Vec b){return {a.x*b.x,a.y*b.y,a.z*b.z};}
inline Vec operator/(Vec a,double b){return a*(1/b);}
inline double dot(Vec a,Vec b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline Vec cross(Vec a,Vec b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline double length(Vec v){return std::sqrt(dot(v,v));}
inline Vec unit(Vec v){return v/length(v);}
inline Vec minv(Vec a,Vec b){return {std::min(a.x,b.x),std::min(a.y,b.y),std::min(a.z,b.z)};}
inline Vec maxv(Vec a,Vec b){return {std::max(a.x,b.x),std::max(a.y,b.y),std::max(a.z,b.z)};}

// SplitMix64: no shared mutable RNG, independent of worker and task order.
inline uint64_t mix(uint64_t z){z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;z=(z^(z>>27))*0x94d049bb133111ebULL;return z^(z>>31);}
struct RNG {
    uint64_t state;
    uint64_t next(){state+=0x9e3779b97f4a7c15ULL;return mix(state);}
    double uniform(){return static_cast<double>(next()>>11)*0x1.0p-53;}
    Vec direction(){double z=2*uniform()-1,a=2*pi*uniform(),r=std::sqrt(std::max(0.0,1-z*z));return {r*std::cos(a),r*std::sin(a),z};}
};
struct Ray {Vec o,d; Vec at(double t)const{return o+d*t;}};
struct Hit {double t=0;Vec p,n;int material=0;bool front=true;};
enum class Kind {Diffuse,Metal,Glass,Light};
struct Counters { uint64_t rays=0,path_depth=0,node_visits=0,triangle_tests=0; };
struct Material {Kind kind;Vec color;double parameter=0;};
struct Box {
    Vec lo{INFINITY,INFINITY,INFINITY},hi{-INFINITY,-INFINITY,-INFINITY};
    void add(Box b){lo=minv(lo,b.lo);hi=maxv(hi,b.hi);}
    bool hit(const Ray& r,double near,double far)const{
        for(int a=0;a<3;++a){
            if(std::abs(r.d[a])<1e-15){if(r.o[a]<lo[a]||r.o[a]>hi[a])return false;continue;}
            double x=(lo[a]-r.o[a])/r.d[a],y=(hi[a]-r.o[a])/r.d[a];
            if(x>y)std::swap(x,y);
            near=std::max(near,x);far=std::min(far,y);
            if(far<near)return false;
        }return true;
    }
};
struct Sphere {
    Vec c;double radius;int material;
    Box bounds()const{Vec r{radius,radius,radius};return {c-r,c+r};}
    bool hit(const Ray& ray,double near,double far,Hit& h)const{
        Vec oc=ray.o-c;double a=dot(ray.d,ray.d),b=dot(oc,ray.d);
        double disc=b*b-a*(dot(oc,oc)-radius*radius);if(disc<0)return false;
        double root=(-b-std::sqrt(disc))/a;
        if(root<near||root>far){root=(-b+std::sqrt(disc))/a;if(root<near||root>far)return false;}
        h.t=root;h.p=ray.at(root);Vec outward=(h.p-c)/radius;
        h.front=dot(ray.d,outward)<0;h.n=h.front?outward:-outward;h.material=material;return true;
    }
};
struct Triangle {
    Vec a,b,c; int material;
    Box bounds()const {Vec e{1e-8,1e-8,1e-8};return {minv(a,minv(b,c))-e,maxv(a,maxv(b,c))+e};}
    bool hit(const Ray& ray,double near,double far,Hit& h)const {
        Vec e1=b-a,e2=c-a,p=cross(ray.d,e2);double det=dot(e1,p);
        if(std::abs(det)<1e-12)return false;
        Vec t=ray.o-a;double u=dot(t,p)/det;if(u<0||u>1)return false;
        Vec q=cross(t,e1);double v=dot(ray.d,q)/det;if(v<0||u+v>1)return false;
        double distance=dot(e2,q)/det;if(distance<near||distance>far)return false;
        h.t=distance;h.p=ray.at(distance);Vec n=unit(cross(e1,e2));
        h.front=dot(ray.d,n)<0;h.n=h.front?n:-n;h.material=material;return true;
    }
};
struct Node {Box box;int left=-1,right=-1,begin=0,end=0;};
struct Scene {
    std::vector<Material> materials;
    std::vector<Sphere> spheres;
    std::vector<Triangle> triangles;
    bool dark=false;
    Box bounds(int id)const{return id<static_cast<int>(spheres.size())?spheres[id].bounds():triangles[id-spheres.size()].bounds();}
    Vec center(int id)const{auto b=bounds(id);return (b.lo+b.hi)*.5;}
    bool primitive(int id,const Ray& r,double near,double far,Hit& h,Counters* count=nullptr)const{
        if(id<static_cast<int>(spheres.size()))return spheres[id].hit(r,near,far,h);
        if(count)++count->triangle_tests;
        return triangles[id-spheres.size()].hit(r,near,far,h);
    }
    void quad(Vec a,Vec b,Vec c,Vec d,int m){triangles.push_back({a,b,c,m});triangles.push_back({a,c,d,m});}
    void load_obj(const std::string& path){
        std::ifstream f(path);if(!f)throw std::runtime_error("cannot open mesh: "+path);
        std::vector<Vec> vertices;std::vector<std::array<int,3>> faces;std::string line;
        while(std::getline(f,line)){
            std::istringstream row(line);std::string tag;row>>tag;
            if(tag=="v"){Vec v;if(!(row>>v.x>>v.y>>v.z)||!std::isfinite(v.x)||!std::isfinite(v.y)||!std::isfinite(v.z))throw std::runtime_error("invalid OBJ vertex");vertices.push_back(v);}
            else if(tag=="f"){
                std::vector<int> ids;std::string part;
                while(row>>part){if(part[0]=='#')break;auto token=part.substr(0,part.find('/'));size_t end;int id=std::stoi(token,&end);if(end!=token.size()||id==0)throw std::runtime_error("invalid OBJ face");id=id<0?static_cast<int>(vertices.size())+id:id-1;if(id<0||id>=static_cast<int>(vertices.size()))throw std::runtime_error("OBJ index out of range");ids.push_back(id);}
                if(ids.size()<3)throw std::runtime_error("invalid OBJ face");
                for(size_t i=1;i+1<ids.size();++i)faces.push_back({ids[0],ids[i],ids[i+1]});
            }
        }
        if(vertices.empty()||faces.empty())throw std::runtime_error("empty OBJ");
        Box b;for(auto v:vertices)b.add({v,v});double height=b.hi.y-b.lo.y;if(height<=0)throw std::runtime_error("zero mesh height");
        for(auto& v:vertices)v=(v-Vec{(b.lo.x+b.hi.x)*.5,b.lo.y,(b.lo.z+b.hi.z)*.5})*(3/height)+Vec{-1.1,0,0};
        for(auto t:faces)triangles.push_back({vertices[t[0]],vertices[t[1]],vertices[t[2]],1});
    }
    std::vector<int> ids;
    std::vector<Node> nodes;
    int build_node(int begin,int end){
        int n=static_cast<int>(nodes.size());nodes.push_back({});
        Box bounds,centers;
        for(int i=begin;i<end;++i){auto c=center(ids[i]);bounds.add(this->bounds(ids[i]));centers.add({c,c});}
        nodes[n].box=bounds;nodes[n].begin=begin;nodes[n].end=end;
        if(end-begin<=4)return n;
        Vec extent=centers.hi-centers.lo;int axis=0;
        if(extent.y>extent.x)axis=1;
        if(extent.z>extent[axis])axis=2;
        int mid=begin+(end-begin)/2;
        std::nth_element(ids.begin()+begin,ids.begin()+mid,ids.begin()+end,[&](int a,int b){
            double x=center(a)[axis],y=center(b)[axis];return x==y?a<b:x<y;
        });
        int l=build_node(begin,mid),r=build_node(mid,end);
        nodes[n].left=l;nodes[n].right=r;return n;
    }
    void build(){ids.resize(spheres.size()+triangles.size());std::iota(ids.begin(),ids.end(),0);nodes.clear();if(!ids.empty())build_node(0,static_cast<int>(ids.size()));}
    bool hit_node(int n,const Ray& ray,double near,double far,Hit& result,Counters* count=nullptr)const{
        if(count)++count->node_visits;
        const auto& node=nodes[n];if(!node.box.hit(ray,near,far))return false;
        bool found=false;
        if(node.left<0){
            for(int i=node.begin;i<node.end;++i){Hit h;if(primitive(ids[i],ray,near,far,h,count)){found=true;far=h.t;result=h;}}
        }else{
            if(hit_node(node.left,ray,near,far,result,count)){found=true;far=result.t;}
            if(hit_node(node.right,ray,near,far,result,count))found=true;
        }return found;
    }
    bool hit(const Ray& r,Hit& h,Counters* count=nullptr)const{return !nodes.empty()&&hit_node(0,r,1e-5,INFINITY,h,count);}
    bool hit_linear(const Ray& r,Hit& result)const{
        bool found=false;double far=INFINITY;
        for(size_t i=0;i<spheres.size()+triangles.size();++i){Hit h;if(primitive(static_cast<int>(i),r,1e-5,far,h)){found=true;far=h.t;result=h;}}return found;
    }
};

inline Scene make_scene(const std::string& name,const std::string& mesh="assets/bunny.obj",bool build=true){
    Scene s;
    s.materials={{Kind::Diffuse,{.55,.58,.62},0},{Kind::Diffuse,{.18,.42,.72},0},
      {Kind::Diffuse,{.75,.22,.13},0},{Kind::Metal,{.88,.8,.62},.06},
      {Kind::Glass,{1,1,1},1.5},{Kind::Diffuse,{.25,.65,.34},0}};
    s.spheres.push_back({{0,-1000,0},1000,0});
    s.spheres.push_back({{0,1,0},1,4});
    s.spheres.push_back({{-2.2,1,0},1,1});
    s.spheres.push_back({{2.2,1,0},1,3});
    if(name=="room"){
        s.dark=true;s.spheres={{{-1, .8, 0},.8,1},{{1,.8,0},.8,3}};
        s.materials.push_back({Kind::Light,{8,8,8},0});
        s.quad({-3,0,-3},{3,0,-3},{3,0,3},{-3,0,3},0);
        s.quad({-3,0,-3},{-3,4,-3},{3,4,-3},{3,0,-3},0);
        s.quad({-3,0,3},{-3,4,3},{-3,4,-3},{-3,0,-3},2);
        s.quad({3,0,-3},{3,4,-3},{3,4,3},{3,0,3},5);
        s.quad({-3,4,-3},{-3,4,3},{3,4,3},{3,4,-3},0);
        s.quad({-1.8,3.98,-1.8},{1.8,3.98,-1.8},{1.8,3.98,1.8},{-1.8,3.98,1.8},6);
    }
    else if(name=="bunny"||name=="bunny-mixed"){
        s.spheres.resize(1);s.load_obj(mesh);
        if(name=="bunny-mixed"){for(auto& t:s.triangles)t.material=t.a.x<-1.1?3:4;s.spheres.push_back({{2,.8,1},.8,4});}
    }
    else if(name=="simple"){s.spheres.push_back({{.2,.45,2.1},.45,2});}
    else if(name=="many"||name=="clustered"||name=="uneven"){
        RNG rng{20261018};
        for(int a=-8;a<=8;++a)for(int b=-7;b<=7;++b){
            // Clustered scene deliberately puts most small geometry on one side.
            if((name=="clustered"||name=="uneven")&&a<1)continue;
            double x=.65*a+.18*rng.uniform(),z=.65*b+.18*rng.uniform();
            if(std::hypot(x,z)<1.3||std::hypot(x-2.2,z)<1.3||std::hypot(x+2.2,z)<1.3)continue;
            double radius=.16+.10*rng.uniform();
            s.spheres.push_back({{x,radius,z},radius,name=="uneven"?3+static_cast<int>(rng.next()%2):1+static_cast<int>(rng.next()%5)});
        }
    }else throw std::runtime_error("unknown scene: "+name);
    if(build)s.build();
    return s;
}
struct Camera {
    Vec eye,u,v,forward;double scale,aspect;
    explicit Camera(double ratio,bool room=false):eye{9,4,10},scale(std::tan(35*pi/360)),aspect(ratio){
        if(room){eye={0,2,8};scale=std::tan(42*pi/360);}
        forward=unit((room?Vec{0,2,0}:Vec{0,.7,0})-eye);u=unit(cross(forward,{0,1,0}));v=cross(u,forward);
    }
    Ray ray(double x,double y)const{return {eye,forward+u*((2*x-1)*scale*aspect)+v*((1-2*y)*scale)};}
};
inline Vec trace(const Scene& scene,Ray ray,RNG& rng,int depth,Counters* count=nullptr){
    Vec throughput{1,1,1};
    for(int bounce=0;bounce<depth;++bounce){
        if(count)++count->rays;
        Hit h;if(!scene.hit(ray,h,count)){
            if(scene.dark)return {};
            double a=.5*(unit(ray.d).y+1);
            return throughput*((1-a)*Vec{1,1,1}+a*Vec{.45,.65,1});
        }
        if(count)++count->path_depth;
        const auto& m=scene.materials[h.material];Vec d;
        if(m.kind==Kind::Light)return throughput*m.color;
        if(m.kind==Kind::Diffuse){d=h.n+rng.direction();if(dot(d,d)<1e-20)d=h.n;}
        else if(m.kind==Kind::Metal){Vec in=unit(ray.d);d=in-2*dot(in,h.n)*h.n+m.parameter*rng.direction();if(dot(d,h.n)<=0)return {};}
        else{
            Vec in=unit(ray.d);double eta=h.front?1/m.parameter:m.parameter;
            double c=std::min(dot(-in,h.n),1.0),sn=std::sqrt(std::max(0.0,1-c*c));
            double r0=(1-eta)/(1+eta);r0*=r0;double reflectance=r0+(1-r0)*std::pow(1-c,5);
            if(eta*sn>1||rng.uniform()<reflectance)d=in-2*dot(in,h.n)*h.n;
            else{Vec perp=eta*(in+c*h.n);d=perp-std::sqrt(std::abs(1-dot(perp,perp)))*h.n;}
        }
        throughput=throughput*m.color;ray={h.p,d};
    }return {}; // Fixed path-depth truncation, identical in all versions.
}
inline Vec pixel(const Scene& scene,const Camera& camera,int x,int y,int width,int height,int spp,int depth,uint64_t seed,Counters* count=nullptr){
    Vec sum;uint64_t id=static_cast<uint64_t>(y)*static_cast<uint64_t>(width)+static_cast<uint64_t>(x);
    for(int sample=0;sample<spp;++sample){
        RNG rng{mix(seed ^ mix(id+0x9e3779b97f4a7c15ULL) ^ mix(static_cast<uint64_t>(sample)+0xd1b54a32d192ed03ULL))};
        double sx=(x+rng.uniform())/width,sy=(y+rng.uniform())/height;
        sum+=trace(scene,camera.ray(sx,sy),rng,depth,count);
    }return sum/static_cast<double>(spp);
}
} // namespace rt
