import asyncio,json,sys,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fixtures import workspace,source_library,party,Host
from tools.publish_library import build_library
from library_client import LibraryClient
from lookup import Catalog,parse_message,Match
from builds import BuildCatalog
from build_protocol import encode_code,decode_code,validate_build
from bot import FlaskBot,BuildView,ResultsView,help_text,lookup_response,info_response,monster_response,build_response,payload

class DataTests(unittest.TestCase):
    def test_unavailable_artwork_still_shows_card_text(self):
        with workspace() as root:
            source=source_library(root/'source');site=root/'site';build_library(source,site);host=Host(site)
            snap=LibraryClient(url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch).ensure()
            catalog=Catalog(snapshot=snap);host.offline=True
            es,fs=payload(catalog,catalog.search('Test Bolt')[0][0])
            self.assertFalse(fs);self.assertIn('Deal 5 Damage',es[0].description)
            self.assertIn('Artwork temporarily unavailable',es[0].footer.text)

    def test_parser_and_help_examples(self):
        self.assertEqual(parse_message('flask info Test Bolt level 3'),('info Test Bolt',3))
        self.assertEqual(parse_message('flask info infuser Bright'),('infuser Bright',None))
        self.assertEqual(parse_message('flask monster Test Beast'),('monster Test Beast',None))
        self.assertEqual(parse_message('FLASH show Test Bolt'),('Test Bolt',None))
        self.assertIsNone(parse_message('pt info Test Bolt'))
        for topic in ('','info','infuser','monster','party'):self.assertLessEqual(len(help_text(topic)),2000)

    def test_records_have_valid_images_descriptions_and_category_filters(self):
        with workspace() as root:
            catalog=Catalog(root=source_library(root/'source'))
            for m in catalog.matches:
                for page in range(catalog.pages(m)):
                    es,fs=payload(catalog,m,page)
                    try:
                        self.assertLessEqual(sum(len(e) for e in es),6000)
                        for f in fs:self.assertTrue(f.fp.read())
                    finally:
                        for f in fs:f.close()
            matches,exact=catalog.search('infuser Bright');self.assertTrue(exact);self.assertEqual(matches[0].kind,'infuser')
            self.assertTrue(all(m.kind=='monster' for m in catalog.search('monster Test')[0]))

    def test_unavailable_card_level_and_infuser_level_are_rejected(self):
        with workspace() as root:
            c=Catalog(root=source_library(root/'source'))
            for query in ('card Test Guard','infuser Bright'):
                with self.assertRaises(ValueError):c.page(c.search(query)[0][0],level=1)

class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.context=workspace();self.root=self.context.__enter__();self.catalog=Catalog(root=source_library(self.root/'source'))
    async def asyncTearDown(self):self.context.__exit__(None,None,None)

    async def test_four_commands_registered(self):
        bot=FlaskBot(self.catalog)
        try:
            group=bot.tree.get_command('flask')
            for name in ('help','info','monster','party'):self.assertIsNotNone(group.get_command(name))
        finally:await bot.close()

    async def test_infuser_information_and_complete_list(self):
        send=AsyncMock();await info_response(self.catalog,'infuser Bright',1,send)
        self.assertIn('+2 Damage',send.call_args.kwargs['embeds'][0].description)
        await info_response(self.catalog,'infuser',1,send)
        for name in ('Bright','Quick'):self.assertIn(name,send.call_args.kwargs['content'])

    async def test_monster_duplicates_and_slots(self):
        send=AsyncMock();await monster_response(self.catalog,'Test Beast',1,send)
        es=send.call_args.kwargs['embeds'];self.assertIn('×2',es[1].title);self.assertIn('1, 2',es[1].footer.text)

    async def test_partial_query_offers_a_menu(self):
        send=AsyncMock();await lookup_response(self.catalog,'Test',1,send)
        self.assertIsInstance(send.call_args.kwargs['view'],ResultsView)

    async def test_party_preserves_empty_slots_levels_snacks_and_multiple_infusers(self):
        b=party();self.assertEqual(decode_code(encode_code(b)),b)
        send=AsyncMock();await build_response(self.catalog,BuildCatalog(root=self.catalog.root),None,1,send,encode_code(b))
        view=send.call_args.kwargs['view'];self.assertIsInstance(view,BuildView);self.assertEqual(view.build,b)
        view.select._values=['0:0'];interaction=type('Interaction',(),{'response':AsyncMock(),'edit_original_response':AsyncMock()})()
        await view.pick(interaction);interaction.response.defer.assert_awaited_once();es=interaction.edit_original_response.call_args.kwargs['embeds']
        self.assertIn('Test Snack',es[0].description);self.assertIn('Slot 2',es[1].title);self.assertIn('Slot 3',es[2].title)
        effects=' '.join(f.value for f in es[1].fields);self.assertIn('+2 Damage',effects);self.assertIn('Activate twice',effects)
        self.assertLessEqual(sum(len(e) for e in es),6000)

    async def test_raw_save_is_not_downloaded_by_bot(self):
        a=type('Attachment',(),{'filename':'SavedGame.rbs','size':10,'read':AsyncMock()})();send=AsyncMock()
        await build_response(self.catalog,BuildCatalog(root=self.catalog.root),a,1,send);a.read.assert_not_awaited()

    async def test_another_user_cannot_edit_party(self):
        view=BuildView(self.catalog,BuildCatalog(root=self.catalog.root),party(),1)
        interaction=type('Interaction',(),{'user':type('User',(),{'id':2})(),'response':AsyncMock()})()
        self.assertFalse(await view.interaction_check(interaction));self.assertTrue(interaction.response.send_message.call_args.kwargs['ephemeral'])

    async def test_text_party_and_help_routes(self):
        bot=FlaskBot(self.catalog)
        def message(text):return type('Message',(),{'content':text,'author':type('Author',(),{'id':7,'bot':False})(),'attachments':[],'channel':type('Channel',(),{'send':AsyncMock()})()})()
        try:
            h=message('flask help');await bot.on_message(h);self.assertIn('flask info',h.channel.send.call_args.args[0])
            m=message('flask party '+encode_code(party()));await bot.on_message(m);self.assertIn('embeds',m.channel.send.call_args.kwargs)
        finally:await bot.close()

    async def test_running_bot_switches_to_published_revision(self):
        with workspace() as root:
            source=source_library(root/'source');site=root/'site';build_library(source,site);host=Host(site)
            client=LibraryClient(url='https://library.test/manifest.json',cache=root/'cache',fetcher=host.fetch)
            catalog=Catalog(snapshot=client.ensure());bot=FlaskBot(catalog)
            data=json.loads((source/'data/catalog.json').read_text('utf8'))
            data['cards'][0]['descriptions']['1']='Updated effect.'
            (source/'data/catalog.json').write_text(json.dumps(data),encoding='utf8');build_library(source,site)
            try:
                with patch('bot.asyncio.sleep',new=AsyncMock(side_effect=[None,asyncio.CancelledError()])):
                    with self.assertRaises(asyncio.CancelledError):await bot.refresh_library()
                self.assertNotEqual(bot.catalog.library.revision,catalog.library.revision)
                self.assertEqual(bot.catalog.cards[1]['descriptions']['1'],'Updated effect.')
                self.assertEqual(bot.build_catalog.library.revision,bot.catalog.library.revision)
                self.assertNotEqual(catalog.cards[1]['descriptions']['1'],'Updated effect.')
            finally:await bot.close()

if __name__=='__main__':unittest.main()
