"""Synthetic test data generated at runtime; no extracted game files are stored here."""
import base64,json,sys,tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

@contextmanager
def workspace():
    base=Path(__file__).resolve().parents[1]/'.test-temp';base.mkdir(exist_ok=True)
    temp=tempfile.TemporaryDirectory(prefix='test-',dir=base);path=Path(temp.name)
    try:yield path
    finally:
        assert path.resolve().parent==base.resolve()
        temp.cleanup()

def source_library(root,description='Deal 5 Damage.'):
    root=Path(root);(root/'data').mkdir(parents=True);(root/'assets').mkdir()
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==')
    # Generate a valid tiny image with Pillow only if this is the bot test suite.
    try:
        from PIL import Image
        Image.new('RGBA',(4,4),'purple').save(root/'assets/test.png')
    except ImportError:(root/'assets/test.png').write_bytes(png)
    image='assets/test.png'
    def card(i,name,level):return dict(id=i,name=name,aliases=[name],character='Test Alchemist',elements=['Solar'],available_level=level,descriptions={str(n):description+f' Tier {n}.' for n in range(level,5)},image=image,thumbnail=image)
    cards=[card(1,'Test Bolt',1),card(2,'Test Guard',2)]
    infusers=[dict(id=11,name='Bright',aliases=['Bright'],description='+2 Damage.',image=image),dict(id=12,name='Quick',aliases=['Quick'],description='Activate twice.',image=image)]
    monsters=[dict(id=9,name='Test Beast',aliases=['Test Beast'],image=image,variants=[dict(name='Front',health=100,health_variance=0,source='loadout',random_order=False,cards=[dict(id=1,level=2,slot=1,infusers=[]),dict(id=1,level=2,slot=2,infusers=[]),dict(id=2,level=3,slot=3,infusers=['Bright'])])])]
    entries={str(c['id']):dict(name=c['name'],category='Flask',image=image) for c in cards}
    entries.update({'3':dict(name='Test Alchemist',category='Character',image=image),'11':dict(name='Bright',category='Infuser',image=image),'12':dict(name='Quick',category='Infuser',image=image),'21':dict(name='Solar',category='Element',image=image),'31':dict(name='Test Snack',category='Snack',image=image),'41':dict(name='Test Mutation',category='Mutation',image=image)})
    values={'catalog.json':dict(version='test-1',cards=cards,monsters=monsters),'infusers.json':infusers,'build-catalog.json':entries,'build-refs.json':{'flask':{'id':1},'character':{'id':3}}}
    for name,value in values.items():(root/'data'/name).write_text(json.dumps(value),encoding='utf8')
    return root

def party():
    return dict(format='flask-build',schema=1,gameVersion='test-1',build=dict(characters=[dict(id=3,hp=100,mutation=41,snacks=[31],flasks=[None,dict(id=1,level=2,infusers=[11,12]),dict(id=1,level=3,infusers=[11])])],elementTokens=[dict(elementId=21,amount=2)]))

class Host:
    def __init__(self,root):self.root=Path(root);self.calls=[];self.offline=False;self.overrides={}
    def fetch(self,url,limit):
        if self.offline:raise OSError('Offline test')
        rel=urlsplit(url).path.lstrip('/');self.calls.append(rel)
        raw=self.overrides.get(rel,(self.root/rel).read_bytes())
        if len(raw)>limit:raise ValueError('Response exceeded limit')
        return raw
