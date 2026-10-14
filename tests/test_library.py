import hashlib,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fixtures import workspace,source_library,Host
from library_client import LibraryClient,LibraryError,valid_path
from tools.publish_library import build_library

class LibraryTests(unittest.TestCase):
    def setup_library(self,root):
        source=source_library(root/'source');site=root/'site';build_library(source,site)
        return source,site,Host(site)

    def test_bot_downloads_metadata_then_artwork_on_demand(self):
        with workspace() as root:
            _,site,host=self.setup_library(root)
            client=LibraryClient(url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch)
            snap=client.refresh(offline_ok=False)
            self.assertFalse(any(p.endswith('.png') for p in host.calls))
            path=snap.file('assets/test.png');self.assertTrue(path.exists())
            calls=len(host.calls);self.assertEqual(snap.file('assets/test.png'),path);self.assertEqual(len(host.calls),calls)

    def test_exporter_downloads_only_its_two_reference_files(self):
        with workspace() as root:
            _,site,host=self.setup_library(root)
            snap=LibraryClient('exporter',url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch).refresh(offline_ok=False)
            self.assertEqual(set(snap.files),{'data/build-refs.json','data/build-catalog.json'})
            self.assertFalse(any(p.endswith('.png') for p in host.calls))

    def test_offline_restart_keeps_verified_cache(self):
        with workspace() as root:
            _,_,host=self.setup_library(root);options=dict(url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch)
            first=LibraryClient(**options).refresh();first.file('assets/test.png');host.offline=True
            second=LibraryClient(**options).refresh()
            self.assertEqual(first.revision,second.revision);self.assertTrue(second.file('assets/test.png').exists())

    def test_first_run_offline_is_actionable(self):
        with workspace() as root:
            host=Host(root);host.offline=True
            with self.assertRaisesRegex(LibraryError,'no verified cache'):LibraryClient(url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch).refresh()

    def test_new_revision_activates_without_changing_old_snapshot(self):
        with workspace() as root:
            source,site,host=self.setup_library(root);client=LibraryClient(url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch)
            old=client.refresh();old_data=(old.root/'data/catalog.json').read_bytes()
            data=json.loads((source/'data/catalog.json').read_text('utf8'));data['cards'][0]['descriptions']['1']='Updated effect.'
            (source/'data/catalog.json').write_text(json.dumps(data),encoding='utf8');build_library(source,site)
            new=client.refresh(offline_ok=False)
            self.assertNotEqual(old.revision,new.revision);self.assertEqual((old.root/'data/catalog.json').read_bytes(),old_data)
            self.assertIn('Updated effect.',(new.root/'data/catalog.json').read_text('utf8'))

    def test_corrupted_update_cannot_replace_working_cache(self):
        with workspace() as root:
            _,_,host=self.setup_library(root);client=LibraryClient(url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch)
            old=client.refresh();manifest=json.loads((host.root/'manifest.json').read_bytes());host.overrides[manifest['profiles']['bot']['url']]=b'corrupted'
            self.assertEqual(client.refresh().revision,old.revision)
            with self.assertRaises(LibraryError):client.refresh(offline_ok=False)

    def test_path_traversal_and_insecure_host_are_rejected(self):
        for path in ('../.env','/absolute','assets/../../secret','C:/secret','assets\\secret','assets//secret'):
            with self.assertRaises(LibraryError):valid_path(path)
        with self.assertRaises(LibraryError):LibraryClient(url='http://insecure.test/manifest.json')

    def test_publisher_retains_old_objects_and_unchanged_content(self):
        with workspace() as root:
            source,site,_=self.setup_library(root);before={p.relative_to(site) for p in site.rglob('*') if p.is_file()}
            a=build_library(source,site);b=build_library(source,site)
            self.assertEqual(a['revision'],b['revision']);self.assertTrue(all((site/p).exists() for p in before))

if __name__=='__main__':unittest.main()
