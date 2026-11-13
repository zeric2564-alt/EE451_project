"""Geometry-independent integration checks for profiling, images and loader errors."""
import csv, json, os, subprocess, tempfile, unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
class ProposalTests(unittest.TestCase):
    def run_render(self,*args):
        return json.loads(subprocess.check_output([str(ROOT/'raytrace'),*map(str,args)],cwd=ROOT,text=True))
    def test_regions_are_schedule_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            region=Path(tmp)/'regions.csv';raw=Path(tmp)/'pixels.f64';threads=Path(tmp)/'threads.csv'
            for scene in ['room','uneven','bunny']:
                base=['--scene',scene,'--width',67,'--height',39,'--spp',3,'--raw',raw]
                plain=self.run_render(*base);pixels=raw.read_bytes()
                expected=None
                for mode,tile in [('serial',16),('row-static',8),('row-dynamic',32),('tile-static',8),('tile-dynamic',64)]:
                    r=self.run_render(*base,'--mode',mode,'--threads',4,'--tile',tile,'--regions',region,'--diagnostics',threads)
                    rows=list(csv.DictReader(region.read_text().splitlines()))
                    self.assertEqual(len(rows),6)
                    self.assertEqual(sum(int(c['width'])*int(c['height']) for c in rows),67*39)
                    self.assertEqual(r['hash'],plain['hash']);self.assertEqual(raw.read_bytes(),pixels)
                    if expected is None:expected=rows
                    else:self.assertEqual(rows,expected)
                    workers=list(csv.DictReader(threads.read_text().splitlines()))
                    self.assertEqual(sum(int(t['pixels']) for t in workers),67*39)
                    self.assertGreaterEqual(sum(int(c['rays']) for c in rows),67*39*3)
                    self.assertEqual(r['diagnostic'],True)
    def test_png_matches_ppm_and_timings(self):
        with tempfile.TemporaryDirectory() as tmp:
            png=Path(tmp)/'image.png';ppm=Path(tmp)/'image.ppm';csvfile=Path(tmp)/'timing.csv'
            args=['--scene','room','--width',33,'--height',35,'--spp',4]
            r=self.run_render(*args,'--output',png,'--timing',csvfile)
            self.run_render(*args,'--output',ppm)
            with Image.open(png) as a,Image.open(ppm) as b:
                self.assertEqual(a.size,(33,35));self.assertEqual(a.tobytes(),b.tobytes())
                self.assertGreater(max(a.tobytes()),0)
            records=list(csv.DictReader(csvfile.read_text().splitlines()))
            self.assertEqual(len(records),1)
            self.assertAlmostEqual(float(records[0]['render_s']),r['render_s'])
            self.assertGreater(r['png_s'],0)
            self.assertGreaterEqual(r['task_prepare_s'],0)
            self.assertEqual(float(records[0]['task_prepare_s']),r['task_prepare_s'])
            self.assertAlmostEqual(r['setup_plus_render_s'],r['setup_s']+r['task_prepare_s']+r['render_s'],places=8)
            self.assertGreater(r['end_to_end_s'],r['render_s']+r['loading_s']+r['bvh_s'])
    def test_bad_mesh_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            mesh=Path(tmp)/'bad.obj'
            for text in ['','v 0 0 0\nf 0 0 0','v nan 0 0','v 0 0 0\nf 2 3 4']:
                mesh.write_text(text)
                p=subprocess.run([str(ROOT/'raytrace'),'--scene','bunny','--mesh',str(mesh)],cwd=ROOT,capture_output=True)
                self.assertNotEqual(p.returncode,0)
if __name__=='__main__':unittest.main()
