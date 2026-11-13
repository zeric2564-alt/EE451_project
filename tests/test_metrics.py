import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from metrics import percentile,regional_ratio
class MetricTests(unittest.TestCase):
    def test_zero_work_has_no_ratio(self):self.assertEqual(regional_ratio([0]*256),('all zero',None))
    def test_zero_p10_uses_max_mean(self):self.assertEqual(regional_ratio([0]*9+[10]),('max/mean',10))
    def test_positive_p10_uses_quantiles(self):
        kind,ratio=regional_ratio(list(range(1,11)))
        self.assertEqual(kind,'P90/P10');self.assertAlmostEqual(ratio,9.1/1.9)
    def test_uniform_work(self):self.assertEqual(regional_ratio([7]*256),('P90/P10',1))
    def test_interpolated_quantiles(self):
        self.assertEqual(percentile([0,10],.5),5)
        self.assertEqual(percentile([4],.1),4)
if __name__=='__main__':unittest.main()
