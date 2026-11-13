"""Verify self-contained HTML deliverables and decode every embedded raster asset."""
from pathlib import Path
from html.parser import HTMLParser
from io import BytesIO
import base64, json
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
class Inspector(HTMLParser):
    def __init__(self):super().__init__();self.images=0;self.sections=0;self.titles=0;self.scripts=[];self.in_script=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='section':self.sections+=1
        if tag=='title':self.titles+=1
        if tag=='script':
            assert 'src' not in attrs,'External script in offline artifact';self.in_script=True
        if tag=='img':
            src=attrs.get('src','');assert src.startswith('data:image/png;base64,'),'Non-embedded image'
            assert attrs.get('alt'),'Missing accessible image label'
            with Image.open(BytesIO(base64.b64decode(src.split(',',1)[1]))) as im:im.verify()
            self.images+=1
    def handle_endtag(self,tag):
        if tag=='script':self.in_script=False
    def handle_data(self,data):
        if self.in_script:self.scripts.append(data)
results={}
for name in ['report.html','presentation.html']:
    path=ROOT/'report/proposal'/name;parser=Inspector();text=path.read_text();parser.feed(text)
    assert parser.titles==1
    assert parser.images>=8
    if name=='presentation.html':assert parser.sections==10
    assert '69451' in text or '69,451' in text
    results[name]=dict(images_decoded=parser.images,slides=parser.sections,bytes=path.stat().st_size)
    for i,script in enumerate(parser.scripts):
        out=ROOT/'tmp'/f'{name}.{i}.js';out.parent.mkdir(exist_ok=True);out.write_text(script)
print(json.dumps(results,indent=2))
(ROOT/'results/proposal/artifact_checks.json').write_text(json.dumps(results,indent=2))
