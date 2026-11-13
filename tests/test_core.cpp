#include "core.hpp"
#include <iostream>
void check(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
int main(){try{
    rt::Sphere s{{0,0,-3},1,0};rt::Hit h;
    check(s.hit({{0,0,0},{0,0,-1}},1e-5,INFINITY,h),"sphere hit");
    check(std::abs(h.t-2)<1e-12&&h.front&&h.n.z==1,"sphere analytic distance/normal");
    check(!s.hit({{0,0,0},{0,1,0}},1e-5,INFINITY,h),"sphere miss");
    check(s.hit({{0,0,-3},{0,0,1}},1e-5,INFINITY,h)&&!h.front,"inside sphere");
    rt::Triangle triangle{{-1,-1,-3},{1,-1,-3},{0,1,-3},2};
    check(triangle.hit({{0,0,0},{0,0,-1}},1e-5,INFINITY,h),"triangle hit");
    check(std::abs(h.t-3)<1e-12&&h.front&&h.material==2,"triangle analytic distance/material");
    check(!triangle.hit({{2,0,0},{0,0,-1}},1e-5,INFINITY,h),"triangle miss");
    check(!triangle.hit({{0,0,-3},{1,0,0}},1e-5,INFINITY,h),"triangle parallel");
    check(triangle.hit({{0,0,-4},{0,0,1}},1e-5,INFINITY,h)&&!h.front,"triangle backface");
    rt::Triangle degenerate{{0,0,0},{0,0,0},{0,0,0},0};
    check(!degenerate.hit({{0,0,1},{0,0,-1}},1e-5,INFINITY,h),"degenerate triangle");
    rt::Box box{{-1,-1,-1},{1,1,1}};
    check(box.hit({{0,0,3},{0,0,-1}},0,INFINITY),"axis parallel bbox hit");
    check(!box.hit({{2,0,3},{0,0,-1}},0,INFINITY),"axis parallel bbox miss");
    rt::Scene empty;empty.build();check(!empty.hit({{0,0,0},{1,0,0}},h),"empty scene");
    rt::RNG rng{451};int rays=0;
    for(const std::string name:{"simple","many","clustered","room","uneven","bunny","bunny-mixed"}){
        auto scene=rt::make_scene(name);
        if(name=="bunny"||name=="bunny-mixed")check(scene.triangles.size()==69451,"Bunny triangle count");
        for(int i=0;i<(name.rfind("bunny",0)==0?1000:10000);++i){
            rt::Ray r{{14*rng.uniform()-7,8*rng.uniform(),14*rng.uniform()-7},rng.direction()};
            rt::Hit a,b;bool x=scene.hit(r,a),y=scene.hit_linear(r,b);
            check(x==y,"BVH vs brute force hit mismatch");
            if(x)check(std::abs(a.t-b.t)<1e-9&&a.material==b.material,"BVH vs brute force distance/material mismatch");
            ++rays;
        }
    }
    std::cout<<"PASS: analytic geometry, empty scene, BVH vs brute force "<<rays<<" rays\n";
}catch(const std::exception& e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}}
