import base64,json,struct,sys,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_protocol import decode_build,validate_build,encode_code,decode_code,MAX_BUILD_BYTES
from export_build import export_bytes
from odin_reader import OdinReader,SaveError

def string(s):return b'\0'+struct.pack('<i',len(s))+s.encode('latin1')
def node(name,kind,fields):
    tag=b'\1'+string(name) if name else b'\2'
    return tag+b'/'+struct.pack('<i',len(kind))+string(kind)+struct.pack('<i',len(kind))+fields+b'\5'
def integer(name,n):return b'\x17'+string(name)+struct.pack('<i',n)
def external(name,guid):return b'2'+string(name)+string(guid)
def saved_list(name,kind,items):return node(name,kind,b'\6'+struct.pack('<q',len(items))+b''.join(items)+b'\7')
def fixture():
    flask=node(None,'FlaskInfo, Assembly-CSharp',external('flask_SA','flask')+integer('level',2)+saved_list('infusers','Infuser list',[]))
    character=node(None,'Character, Assembly-CSharp',external('charSARef','character')+integer('maxHP',100)+b'-'+string('charMutation')+saved_list('snackEffects','Snack list',[])+saved_list('timeslotList','Flask array',[flask,b'.']))
    player=node('playerData','PlayerData, Assembly-CSharp',saved_list('characterList','Character list',[character])+saved_list('elementTokens','Element dictionary',[])+b'\x27'+string('runIdentifier')+string('PRIVATE-RUN-ID'))
    return node(None,'SaveData, Assembly-CSharp',b'\x27'+string('gameVersion')+string('0.38.6')+player)
def build_fixture():
    return dict(format='flask-build',schema=1,gameVersion='test',build=dict(characters=[dict(id=2,hp=100,mutation=-1,snacks=[],flasks=[dict(id=1,level=2,infusers=[]),None])],elementTokens=[]))

class ExportTests(unittest.TestCase):
    def test_share_code_roundtrip_and_discord_message_limit(self):
        b=build_fixture();code=encode_code(b)
        self.assertEqual(decode_code(code),validate_build(b));self.assertLessEqual(len('flask build '+code),2000)
    def test_invalid_truncated_and_compressed_bomb_codes_rejected(self):
        bomb='FB1.'+base64.urlsafe_b64encode(zlib.compress(b' '*(MAX_BUILD_BYTES+1))).decode().rstrip('=')
        for code in ('bad','FB1.!','FB1.'+'a'*2000,encode_code(build_fixture())[:-8],bomb):
            with self.assertRaises(ValueError):decode_code(code)
    def test_save_export_allowlist_and_empty_slot(self):
        result=export_bytes(fixture(),{'flask':{'id':1},'character':{'id':2}});c=result['build']['characters'][0]
        self.assertEqual(c['flasks'][0],dict(id=1,level=2,infusers=[]))
        self.assertIsNone(c['flasks'][1]);self.assertEqual(c['hp'],100)
        self.assertNotIn('PRIVATE-RUN-ID',json.dumps(result));self.assertNotIn('playerData',result)
    def test_bad_binary_saves_rejected(self):
        for raw in (fixture()[:-4],b'\xff',b'\6'+struct.pack('<q',10000001)):
            with self.assertRaises(SaveError):OdinReader(raw).read()
    def test_unknown_reference_not_silently_omitted(self):
        with self.assertRaises(SaveError):export_bytes(fixture(),{'character':{'id':2}})
    def test_private_and_untrusted_fields_discarded(self):
        b=build_fixture();b['releaseToken']='SECRET';b['steamId']='SECRET'
        b['build']['characters'][0]['name']='@everyone';b['build']['characters'][0]['image']='C:/private'
        clean=json.dumps(decode_build(json.dumps(b).encode()))
        for value in ('SECRET','@everyone','C:/private'):self.assertNotIn(value,clean)
    def test_invalid_input_bounds(self):
        for level in (0,5,True,'2'):
            b=build_fixture();b['build']['characters'][0]['flasks'][0]['level']=level
            with self.assertRaises(ValueError):validate_build(b)
        with self.assertRaises(ValueError):decode_build(b' '*(MAX_BUILD_BYTES+1))
        with self.assertRaises(ValueError):decode_build(fixture())

if __name__=='__main__':unittest.main()
