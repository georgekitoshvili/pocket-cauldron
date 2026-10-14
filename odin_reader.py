"""Bounded, data-only reader for Odin binary saves. Never instantiates saved types."""
import struct

class SaveError(ValueError): pass

class OdinReader:
    def __init__(self, data):
        if len(data)>16*1024*1024: raise SaveError('Save exceeds 16 MB.')
        self.data=data; self.pos=0; self.types={}; self.refs={}; self.entries=0

    def take(self,n):
        if n<0 or self.pos+n>len(self.data):raise SaveError('Truncated save.')
        b=self.data[self.pos:self.pos+n];self.pos+=n;return b

    def num(self,fmt):return struct.unpack('<'+fmt,self.take(struct.calcsize('<'+fmt)))[0]

    def string(self):
        wide=self.num('B'); n=self.num('i')
        if wide not in (0,1) or not 0<=n<=1000000:raise SaveError('Unsupported string.')
        return self.take(n*(wide+1)).decode('utf-16-le' if wide else 'latin1')

    def typename(self):
        tag=self.num('B')
        if tag==47:
            i=self.num('i');s=self.string();self.types[i]=s;return s
        if tag==48:
            i=self.num('i')
            if i not in self.types:raise SaveError('Unknown type reference.')
            return self.types[i]
        if tag==46:return None
        raise SaveError('Unsupported type marker.')

    def entry(self,depth=0):
        self.entries+=1
        if depth>100 or self.entries>300000:raise SaveError('Save nesting or entry limit exceeded.')
        tag=self.num('B');name=None
        named=tag in (1,3,9,11,13,50) or (15<=tag<=45 and tag%2==1)
        if named:name=self.string()
        if tag in (1,2,3,4):
            typ=self.typename();node={'$type':typ,'$items':[]}
            if tag in (1,2):
                ref=self.num('i');self.refs[ref]=node
            while True:
                key,value,end=self.entry(depth+1)
                if end==5:break
                if end:raise SaveError('Unexpected terminator inside node.')
                if key is None:node['$items'].append(value)
                else:node[key]=value
            value=node
        elif tag in (5,7,49):return None,None,tag
        elif tag==6:
            n=self.num('q')
            if not 0<=n<=100000:raise SaveError('Invalid array length.')
            value=[]
            for _ in range(n):
                _,v,end=self.entry(depth+1)
                if end:raise SaveError('Premature array terminator.')
                value.append(v)
            if self.num('B')!=7:raise SaveError('Missing array terminator.')
        elif tag==8:
            n=self.num('i');size=self.num('i')
            if not 0<=n<=1000000 or size not in (1,2,4,8,16):raise SaveError('Invalid primitive array.')
            value={'$primitive':self.take(n*size),'$count':n,'$size':size}
        elif tag in (9,10):value={'$ref':self.num('i')}
        elif tag in (11,12):value={'$external_index':self.num('i')}
        elif tag in (13,14):value={'$external_guid':self.take(16).hex()}
        elif tag in (50,51):value={'$external':self.string()}
        elif 15<=tag<=36:
            fmts=['b','B','h','H','i','I','q','Q','f','d',None]
            fmt=fmts[(tag-15)//2]
            value=self.num(fmt) if fmt else {'$decimal':self.take(16).hex()}
        elif tag in (37,38):value=self.take(2).decode('utf-16-le')
        elif tag in (39,40):value=self.string()
        elif tag in (41,42):value={'$guid':self.take(16).hex()}
        elif tag in (43,44):value=bool(self.num('B'))
        elif tag in (45,46):value=None
        else:raise SaveError(f'Unknown Odin tag {tag} at offset {self.pos-1}.')
        return name,value,None

    def read(self):
        _,root,end=self.entry()
        if end or not isinstance(root,dict):raise SaveError('Missing save root.')
        if self.pos<len(self.data) and self.take(1)!=b'1':raise SaveError('Unexpected trailing save data.')
        if self.pos!=len(self.data):raise SaveError('Trailing save data.')
        return root

    def resolve(self,value):
        seen=set()
        while isinstance(value,dict) and '$ref' in value:
            ref=value['$ref']
            if ref in seen or ref not in self.refs:raise SaveError('Invalid object reference.')
            seen.add(ref);value=self.refs[ref]
        return value

    def sequence(self,value):
        value=self.resolve(value)
        if value is None:return []
        if isinstance(value,list):return value
        if isinstance(value,dict):
            if '$primitive' in value:
                if value['$size']!=4:raise SaveError('Expected integer array.')
                return list(struct.unpack('<'+'i'*value['$count'],value['$primitive']))
            for item in value.get('$items',[]):
                if isinstance(item,list):return item
        raise SaveError('Expected saved list.')
