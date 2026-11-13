# Stanford Bunny
Source and credit: Stanford University Computer Graphics Laboratory.
https://graphics.stanford.edu/data/3Dscanrep/

The source permits research use and free redistribution with attribution; commercial use requires permission. This dataset is not relicensed by this project. The reconstruction has 35,947 vertices and 69,451 triangles, including five bottom holes reported by Stanford.

Reproduce the packaged OBJ (no simplification):
```
curl -L --fail https://graphics.stanford.edu/pub/3Dscanrep/bunny.tar.gz -o assets/bunny.tar.gz
python3 scripts/prepare_bunny.py
```
The converter reads only `bunny/reconstruction/bun_zipper.ply`, preserves coordinates and winding, fan-triangulates polygons, validates indices and records SHA-256 checksums. Runtime normalizes height to 3 units, grounds the mesh and offsets it to x=-1.1. The BVH includes every loaded triangle.
