#!/usr/bin/env python3
"""Loopback-only demonstration server; one bounded native render at a time."""
import argparse, json, os, secrets, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
JOBS=ROOT/'web/jobs'
JOBS.mkdir(exist_ok=True)
lock=threading.Lock()
jobs={}
MODES={'serial','row-static','row-dynamic','tile-static','tile-dynamic'}
SCENES={'room','uneven','bunny','bunny-mixed'}

def validate(data):
    if not isinstance(data,dict):raise ValueError('Expected an object')
    allowed={'scene','mode','width','spp','threads','tile'}
    if set(data)-allowed:raise ValueError('Unknown setting')
    result={'scene':'bunny','mode':'tile-dynamic','width':512,'spp':32,'threads':min(8,os.cpu_count() or 1),'tile':16}
    result.update(data)
    if result['scene'] not in SCENES or result['mode'] not in MODES:raise ValueError('Unknown scene or mode')
    for k,values in [('width',{256,512,1024}),('spp',{8,32,64,128}),('threads',set(range(1,min(8,os.cpu_count() or 1)+1))),('tile',{8,16,32,64})]:
        if type(result[k]) is not int or result[k] not in values:raise ValueError('Invalid '+k)
    return result

def render(job_id,settings):
    try:
        cmd=[str(ROOT/'raytrace')]
        for k,v in settings.items():cmd += ['--'+k,str(v)]
        cmd+=['--height',str(settings['width']),'--output',str(JOBS/(job_id+'.png'))]
        before=time.monotonic()
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=300,check=True)
        result=json.loads(p.stdout);result['process_wall_s']=time.monotonic()-before
        with lock:jobs[job_id].update(status='done',result=result,image='/jobs/'+job_id+'.png')
    except Exception as exc:
        with lock:jobs[job_id].update(status='error',error=str(exc))

class Handler(BaseHTTPRequestHandler):
    def send(self,status,body,content_type='application/json'):
        if not isinstance(body,bytes):body=json.dumps(body).encode()
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def local(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def do_GET(self):
        if not self.local():return self.send(403,{'error':'Local host required'})
        path=urlparse(self.path).path
        if path=='/':return self.send(200,(ROOT/'web/index.html').read_bytes(),'text/html; charset=utf-8')
        if path.startswith('/api/jobs/'):
            with lock:job=jobs.get(path.removeprefix('/api/jobs/'));payload=dict(job) if job else None
            return self.send(200 if payload else 404,payload or {'error':'Job not found'})
        if path.startswith('/jobs/'):
            name=path.removeprefix('/jobs/');job_id=name.removesuffix('.png')
            if name==job_id+'.png' and len(job_id)==32 and all(c in '0123456789abcdef' for c in job_id):
                f=JOBS/name
                if f.is_file():return self.send(200,f.read_bytes(),'image/png')
        self.send(404,{'error':'Not found'})
    def do_POST(self):
        if not self.local():return self.send(403,{'error':'Local host required'})
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:return self.send(403,{'error':'Same origin required'})
        if self.path!='/api/jobs':return self.send(404,{'error':'Not found'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<1 or size>4096:raise ValueError('Invalid request size')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
            settings=validate(json.loads(self.rfile.read(size)))
        except (ValueError,TypeError):return self.send(400,{'error':'Invalid render settings'})
        with lock:
            if any(j['status']=='running' for j in jobs.values()):return self.send(409,{'error':'A render is already running'})
            if len(jobs)>=100:return self.send(429,{'error':'Restart the demo server to begin a new session'})
            job_id=secrets.token_hex(16);jobs[job_id]={'id':job_id,'status':'running','settings':settings}
        threading.Thread(target=render,args=(job_id,settings),daemon=True).start()
        self.send(202,{'id':job_id,'status':'running'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    print(f'EE451 viewer: http://127.0.0.1:{server.server_port}',flush=True)
    server.serve_forever()
