"""Convert official ASCII reconstructed PLY to triangulated OBJ without dependencies."""
from pathlib import Path
import tarfile, hashlib, json
root = Path(__file__).resolve().parents[1]
archive = root/'assets/bunny.tar.gz'
with tarfile.open(archive) as tar:
    source = tar.extractfile('bunny/reconstruction/bun_zipper.ply').read()
lines = iter(source.decode().splitlines())
nv = nf = 0
for line in lines:
    if line.startswith('element vertex '): nv = int(line.split()[-1])
    if line.startswith('element face '): nf = int(line.split()[-1])
    if line == 'end_header': break
vertices = [next(lines).split()[:3] for _ in range(nv)]
faces = []
for _ in range(nf):
    v = list(map(int, next(lines).split()))
    assert v[0] == len(v)-1 and all(0 <= n < nv for n in v[1:])
    for i in range(2, len(v)-1): faces.append((v[1]+1,v[i]+1,v[i+1]+1))
assert len(faces) == 69451
out = root/'assets/bunny.obj'
with out.open('w') as f:
    f.write('# Stanford Computer Graphics Laboratory, reconstructed Bunny\n')
    for v in vertices: f.write('v '+' '.join(v)+'\n')
    for v in faces: f.write('f '+' '.join(map(str,v))+'\n')
(root/'assets/bunny.metadata.json').write_text(json.dumps(dict(source='https://graphics.stanford.edu/pub/3Dscanrep/bunny.tar.gz',member='bunny/reconstruction/bun_zipper.ply',vertices=nv,triangles=len(faces),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),obj_sha256=hashlib.sha256(out.read_bytes()).hexdigest()),indent=2))
print(nv, len(faces))
