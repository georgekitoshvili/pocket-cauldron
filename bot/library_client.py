"""Download versioned game data and lazy artwork from the shared HTTPS library."""
from __future__ import annotations
import hashlib,json,logging,os,re,shutil,threading,uuid
from http.client import HTTPException
from pathlib import Path,PurePosixPath
from urllib.parse import urljoin,urlsplit
from urllib.request import Request,urlopen

DEFAULT_LIBRARY_URL='https://pocket-cauldron-library.pages.dev/manifest.json'
LOG=logging.getLogger('flask_library')
_HASH=re.compile(r'^[a-f0-9]{64}$')
REQUIRED={'bot':{'data/catalog.json','data/infusers.json','data/build-catalog.json'},'exporter':{'data/build-refs.json','data/build-catalog.json'}}

class LibraryError(ValueError):pass

def cache_directory():
    override=os.getenv('FLASK_LIBRARY_CACHE')
    if override:return Path(override).expanduser()
    if os.name=='nt':return Path(os.getenv('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'PocketCauldron/library'
    return Path(os.getenv('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'pocket-cauldron/library'

def atomic_bytes(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_bytes(data);os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def parse_json(data):
    try:return json.loads(data)
    except (ValueError,UnicodeError,RecursionError) as exc:raise LibraryError('Invalid library JSON.') from exc

def valid_path(path):
    if not isinstance(path,str) or not path or '\\' in path or ':' in path:raise LibraryError('Invalid library file path.')
    p=PurePosixPath(path)
    if p.is_absolute() or any(x in ('..','.') or x.startswith('.') for x in p.parts) or str(p)!=path:raise LibraryError('Unsafe library file path.')
    return path

def descriptor(value):
    if not isinstance(value,dict) or not _HASH.fullmatch(str(value.get('sha256',''))):raise LibraryError('Invalid library file hash.')
    if type(value.get('size')) is not int or not 0<value['size']<=16*1024*1024:raise LibraryError('Invalid library file size.')
    valid_path(value.get('url'))
    return value

def download(url,limit):
    req=Request(url,headers={'User-Agent':'PocketCauldron-Library/1','Accept-Encoding':'identity'})
    with urlopen(req,timeout=15) as response:
        final=urlsplit(response.url)
        if final.scheme!='https':raise LibraryError('Library redirects must use HTTPS.')
        length=response.headers.get('Content-Length')
        if length and int(length)>limit:raise LibraryError('Library file is too large.')
        data=response.read(limit+1)
    if len(data)>limit:raise LibraryError('Library file is too large.')
    return data

class Snapshot:
    def __init__(self,client,index):
        self.client=client;self.index=index;self.revision=index['revision'];self.files=index['files']
        self.root=client.cache/'snapshots'/self.revision/client.profile

    def file(self,rel):
        valid_path(rel)
        if rel not in self.files:raise LibraryError('This file is absent from the current library.')
        dest=self.root/rel;entry=self.files[rel]
        with self.client.lock:
            if dest.is_file() and dest.stat().st_size==entry['size'] and hashlib.sha256(dest.read_bytes()).hexdigest()==entry['sha256']:return dest
            obj=self.client.cache/'objects'/entry['sha256']
            if not obj.is_file() or obj.stat().st_size!=entry['size'] or hashlib.sha256(obj.read_bytes()).hexdigest()!=entry['sha256']:
                raw=self.client.fetch(entry['url'],entry['size'])
                if len(raw)!=entry['size'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise LibraryError('Library download failed its integrity check.')
                atomic_bytes(obj,raw)
            dest.parent.mkdir(parents=True,exist_ok=True)
            atomic_bytes(dest,obj.read_bytes())
            return dest

class LibraryClient:
    def __init__(self,profile='bot',url=None,cache=None,fetcher=None):
        if profile not in REQUIRED:raise LibraryError('Unknown library profile.')
        self.profile=profile;self.url=url or os.getenv('FLASK_LIBRARY_URL') or DEFAULT_LIBRARY_URL
        parsed=urlsplit(self.url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise LibraryError('The library URL must be a public HTTPS manifest URL.')
        self.base=urljoin(self.url,'./');self.cache=Path(cache) if cache else cache_directory()
        self.fetcher=fetcher or download;self.lock=threading.RLock();self.current=None
        self.active=self.cache/('active-'+profile+'.json')

    def fetch(self,relative,limit):
        valid_path(relative)
        return self.fetcher(urljoin(self.base,relative),limit)

    def validate_index(self,index):
        if not isinstance(index,dict) or index.get('schema')!=1 or index.get('profile')!=self.profile or not _HASH.fullmatch(str(index.get('revision',''))):raise LibraryError('Unsupported library index.')
        files=index.get('files')
        if not isinstance(files,dict) or len(files)>20000 or not REQUIRED[self.profile]<=files.keys():raise LibraryError('Incomplete library index.')
        for rel,value in files.items():
            valid_path(rel);descriptor(value)
            if rel not in REQUIRED[self.profile] and not (self.profile=='bot' and rel.startswith('assets/') and rel.endswith('.png')):raise LibraryError('Unexpected file in library index.')
            if value['url']!='objects/'+value['sha256']+('.png' if rel.endswith('.png') else '.json'):raise LibraryError('Invalid object location.')
        return index

    def prepare(self,index):
        snap=Snapshot(self,self.validate_index(index));metadata={}
        for rel in REQUIRED[self.profile]:metadata[rel]=parse_json(snap.file(rel).read_bytes())
        if not isinstance(metadata['data/build-catalog.json'],dict):raise LibraryError('Invalid build catalog.')
        if self.profile=='exporter':
            if not isinstance(metadata['data/build-refs.json'],dict):raise LibraryError('Invalid build references.')
        else:
            catalog=metadata['data/catalog.json'];infusers=metadata['data/infusers.json']
            if not isinstance(catalog,dict) or not isinstance(catalog.get('cards'),list) or not isinstance(catalog.get('monsters'),list) or not isinstance(infusers,list):raise LibraryError('Invalid card catalog.')
            for entry in catalog['cards']+catalog['monsters']+infusers+list(metadata['data/build-catalog.json'].values()):
                if not isinstance(entry,dict):raise LibraryError('Invalid game record.')
                for key in ('image','thumbnail'):
                    rel=entry.get(key)
                    if rel is not None and (not isinstance(rel,str) or rel not in snap.files or not rel.startswith('assets/')):raise LibraryError('Artwork is missing from the library index.')
        return snap

    def refresh(self,offline_ok=True):
        with self.lock:
            try:
                root=parse_json(self.fetcher(self.url,64*1024))
                if not isinstance(root,dict) or root.get('schema')!=1 or not _HASH.fullmatch(str(root.get('revision',''))):raise LibraryError('Unsupported library manifest.')
                ref=descriptor(root.get('profiles',{}).get(self.profile))
                if ref['url']!=f"releases/{root['revision']}/{self.profile}-index.json":raise LibraryError('Invalid profile index path.')
                raw=self.fetch(ref['url'],ref['size'])
                if len(raw)!=ref['size'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise LibraryError('Library index failed its integrity check.')
                index=self.validate_index(parse_json(raw))
                if index['revision']!=root['revision']:raise LibraryError('Library revision mismatch.')
                snap=self.prepare(index)
                atomic_bytes(self.active,json.dumps({'url':self.url,'index':index},separators=(',',':')).encode())
                self.current=snap;return snap
            except (OSError,HTTPException,ValueError,TypeError,KeyError) as exc:
                if not offline_ok:raise LibraryError('Could not refresh the shared library: '+str(exc)) from exc
                if self.current:
                    LOG.warning('Library refresh failed; using the last verified cache: %s',exc);return self.current
                try:
                    active=parse_json(self.active.read_bytes())
                    if active['url']!=self.url:raise LibraryError('Cached library belongs to another host.')
                    snap=self.prepare(active['index']);self.current=snap
                    LOG.warning('Library unavailable; using verified cached data.');return snap
                except (OSError,ValueError,KeyError,TypeError):
                    raise LibraryError('The shared library could not be reached and no verified cache is available. Connect to the internet and try again.') from exc

    def ensure(self):return self.current or self.refresh()
