#pragma once
#include <cstdint>
#include <fstream>
#include <vector>
#include <stdexcept>
namespace png {
using Bytes=std::vector<unsigned char>;
inline void u32(Bytes& b,uint32_t n){for(int i=24;i>=0;i-=8)b.push_back(static_cast<unsigned char>(n>>i));}
inline void chunk(Bytes& out,const char* name,const Bytes& data){
    u32(out,static_cast<uint32_t>(data.size()));size_t start=out.size();
    out.insert(out.end(),name,name+4);out.insert(out.end(),data.begin(),data.end());
    uint32_t crc=0xffffffff;
    for(size_t i=start;i<out.size();++i){crc^=out[i];for(int j=0;j<8;++j)crc=(crc>>1)^(0xedb88320U & (0U-(crc&1)));}
    u32(out,crc^0xffffffff);
}
// PNG RGB8 with standard zlib stored DEFLATE blocks. No external image library.
inline void write(const std::string& path,int w,int h,const Bytes& rgb){
    Bytes raw;raw.reserve(rgb.size()+h);
    for(int y=0;y<h;++y){raw.push_back(0);raw.insert(raw.end(),rgb.begin()+static_cast<size_t>(y)*w*3,rgb.begin()+static_cast<size_t>(y+1)*w*3);}
    Bytes z{0x78,0x01};uint32_t a=1,b=0;
    for(auto c:raw){a=(a+c)%65521;b=(b+a)%65521;}
    for(size_t i=0;i<raw.size();){size_t n=std::min<size_t>(65535,raw.size()-i);z.push_back(i+n==raw.size()?1:0);
        z.push_back(n&255);z.push_back(n>>8);z.push_back((~n)&255);z.push_back(((~n)>>8)&255);
        z.insert(z.end(),raw.begin()+i,raw.begin()+i+n);i+=n;}
    u32(z,(b<<16)|a);
    Bytes out{137,80,78,71,13,10,26,10},header;u32(header,w);u32(header,h);header.insert(header.end(),{8,2,0,0,0});
    chunk(out,"IHDR",header);chunk(out,"IDAT",z);chunk(out,"IEND",{});
    std::ofstream f(path,std::ios::binary);f.write(reinterpret_cast<const char*>(out.data()),static_cast<std::streamsize>(out.size()));
    if(!f)throw std::runtime_error("cannot write PNG: "+path);
}
}
