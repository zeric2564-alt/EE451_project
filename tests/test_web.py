"""Exercise the actual HTTP/native-render boundary on an ephemeral loopback port."""
import importlib.util, json, threading, time, unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('viewer',ROOT/'web/server.py');viewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(viewer)
class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=viewer.ThreadingHTTPServer(('127.0.0.1',0),viewer.Handler)
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path,body=None,headers=None):
        data=None if body is None else json.dumps(body).encode()
        req=Request(self.base+path,data=data,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with urlopen(req,timeout=10) as r:return r.status,r.read()
        except HTTPError as e:return e.code,e.read()
    def test_page_and_rejections(self):
        status,body=self.request('/');self.assertEqual(status,200);self.assertIn(b'CPU rendering lab',body)
        for data in [{'scene':'unknown'},{'width':1},{'threads':-1},{'tile':0},{'scene':['bunny']},{'output':'/tmp/unauthorized'},{'spp':True}]:
            self.assertEqual(self.request('/api/jobs',data)[0],400)
        self.assertEqual(self.request('/api/jobs',{}, {'Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('/',headers={'Host':'example.com'})[0],403)
        self.assertEqual(self.request('/jobs/../../README.md')[0],404)
        self.assertEqual(self.request('/api/jobs/missing')[0],404)
    def test_render_lifecycle(self):
        status,body=self.request('/api/jobs',{'scene':'bunny','mode':'tile-dynamic','threads':2,'width':256,'spp':8,'tile':16})
        self.assertEqual(status,202);job=json.loads(body)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            status,body=self.request('/api/jobs/'+job['id']);self.assertEqual(status,200)
            result=json.loads(body)
            if result['status']!='running':break
            time.sleep(.05)
        self.assertEqual(result['status'],'done',result)
        self.assertEqual(result['result']['triangles'],69451);self.assertEqual(result['result']['actual_threads'],2)
        status,png=self.request(result['image']);self.assertEqual(status,200);self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
if __name__=='__main__':unittest.main()
