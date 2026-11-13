"""Create a portable source/data handoff with per-file hashes; exclude local binaries."""
from pathlib import Path
import hashlib, json, zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
files=[]
for directory in ['src','tests','benchmarks','assets','web','scripts','results/proposal','results/current','report/proposal','report/reproduced','.github']:
    for p in (ROOT/directory).rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or 'jobs' in p.parts or p.name in {'bunny.tar.gz','.run.lock'}:continue
        files.append(p)
files += [ROOT/p for p in ['Makefile','requirements.txt','README.md','README_CN.md','PROPOSAL_CHECKLIST.md','CHANGES_CN.md','EE451_Proposal.pdf','.gitignore']]
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
with zipfile.ZipFile(OUT/'EE451_complete.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for p in files:archive.write(p,'EE451_project/'+str(p.relative_to(ROOT)))
    archive.writestr('EE451_project/MANIFEST.sha256.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(OUT/'EE451_complete.zip') as archive:
    assert archive.testzip() is None
    for name,digest in manifest.items():assert hashlib.sha256(archive.read('EE451_project/'+name)).hexdigest()==digest
print(OUT/'EE451_complete.zip',len(files),'files; all hashes verified')
