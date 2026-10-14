"""Build a static central library from an owner's prepared data/artwork folder."""
import argparse,hashlib,html,json,re,shutil
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath

PROFILES={'bot':('catalog.json','infusers.json','build-catalog.json'),'exporter':('build-refs.json','build-catalog.json')}

def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
def digest(data):return hashlib.sha256(data).hexdigest()

def build_library(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output==source or output.is_relative_to(source):raise ValueError('Publish outside the source library folder.')
    output.mkdir(parents=True,exist_ok=True);(output/'objects').mkdir(exist_ok=True)
    data={name:json.loads((source/'data'/name).read_text('utf8')) for name in {n for names in PROFILES.values() for n in names}}
    images=set()
    for item in data['catalog.json']['cards']+data['catalog.json']['monsters']+data['infusers.json']+list(data['build-catalog.json'].values()):
        for key in ('image','thumbnail'):
            if item.get(key):images.add(item[key])
    all_files={}
    def add(rel,raw,suffix):
        sha=digest(raw);location=f'objects/{sha}.{suffix}';target=output/location
        if not target.exists():target.write_bytes(raw)
        elif digest(target.read_bytes())!=sha:raise ValueError('Existing central object failed its integrity check.')
        all_files[rel]={'sha256':sha,'size':len(raw),'url':location}
    for name,value in data.items():add('data/'+name,encoded(value),'json')
    for rel in sorted(images):
        p=PurePosixPath(rel)
        if str(p)!=rel or not rel.startswith('assets/') or p.is_absolute() or '..' in p.parts or '\\' in rel or ':' in rel or not rel.endswith('.png'):raise ValueError('Invalid artwork path.')
        raw=(source/rel).read_bytes()
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Artwork must be PNG.')
        if len(raw)>25*1024*1024:raise ValueError('Artwork exceeds the static host file limit.')
        add(rel,raw,'png')
    revision=digest(encoded(all_files));release=output/'releases'/revision;release.mkdir(parents=True,exist_ok=True)
    profiles={}
    for profile,names in PROFILES.items():
        paths={'data/'+name for name in names}
        if profile=='bot':paths.update(images)
        index={'schema':1,'profile':profile,'revision':revision,'game_version':data['catalog.json']['version'],'files':{p:all_files[p] for p in sorted(paths)}}
        raw=encoded(index);filename=f'{profile}-index.json';(release/filename).write_bytes(raw)
        profiles[profile]={'url':f'releases/{revision}/{filename}','sha256':digest(raw),'size':len(raw)}
    manifest={'schema':1,'revision':revision,'game_version':data['catalog.json']['version'],'published_at':datetime.now(timezone.utc).isoformat(),'profiles':profiles}
    (output/'manifest.json').write_bytes(encoded(manifest))
    # Old objects/releases are deliberately retained so existing clients and rollbacks keep working.
    (output/'_headers').write_text('/manifest.json\n  Cache-Control: public, max-age=60, must-revalidate\n  Access-Control-Allow-Origin: *\n/objects/*\n  Cache-Control: public, max-age=31536000, immutable\n/releases/*\n  Cache-Control: public, max-age=31536000, immutable\n',encoding='utf8')
    (output/'404.html').write_text('<!doctype html><title>Not found</title><h1>Library file not found</h1>',encoding='utf8')
    version=html.escape(str(manifest['game_version']))
    (output/'index.html').write_text(f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>FLASK shared library</title><style>body{{max-width:680px;margin:10vh auto;padding:24px;background:#191622;color:#eee8df;font:18px system-ui}}a{{color:#dbc08d}}p{{line-height:1.6}}</style><h1>FLASK shared library</h1><p>The shared artwork and game data used by Pocket Cauldron and FLASK Build Exporter.</p><p>Game snapshot: {version}<br>{len(data["catalog.json"]["cards"])} flask cards · {len(data["infusers.json"])} infusers · {len(data["catalog.json"]["monsters"])} monsters</p><p>The apps refresh from this library automatically.</p><p><a href="downloads/FLASK-Share-Build-Windows.zip">Download FLASK Share Build for Windows</a></p><p><a href="manifest.json">Library manifest</a> · <a href="https://github.com/georgekitoshvili/pocket-cauldron">Bot source</a> · <a href="https://github.com/georgekitoshvili/pocket-cauldron">Exporter source</a></p><p><small>Unofficial community library. Game content belongs to its respective creators.</small></p>',encoding='utf8')
    files=[p for p in output.rglob('*') if p.is_file()]
    if len(files)>20000:raise ValueError('Library exceeds the selected static host file-count limit.')
    return {'revision':revision,'image_paths':len(images),'objects':len(list((output/'objects').iterdir())),'static_files':len(files),'manifest':manifest}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();result=build_library(args.source,args.output)
    print(json.dumps({k:v for k,v in result.items() if k!='manifest'},indent=2))
