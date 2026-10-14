"""Build presentation for the bot; portable codes live in build_protocol.py."""
import io,json,textwrap
from pathlib import Path
from build_protocol import validate_build
from library_client import LibraryClient,LibraryError

class BuildCatalog:
    def __init__(self,root=None,snapshot=None):
        self.library=snapshot if snapshot is not None else LibraryClient("bot").ensure() if root is None else None
        self.root=self.library.root if self.library else Path(root)
        self.entries=json.loads((self.root/'data/build-catalog.json').read_text('utf8'))
        self.cards={c['id']:c for c in json.loads((self.root/'data/catalog.json').read_text('utf8'))['cards']}

    def name(self,ident):return self.entries.get(str(ident),{}).get('name',f'Unknown #{ident}')

    def image(self,ident):
        rel=self.entries.get(str(ident),{}).get('image')
        if not rel:return None
        try:
            target=(self.library.file(rel) if self.library else self.root/rel).resolve()
        except (OSError,LibraryError):return None
        if not target.is_relative_to((self.root/'assets').resolve()):raise ValueError('Invalid bundled image path.')
        return target if target.is_file() else None

    def summary(self,build):
        b=build['build'];lines=[]
        tokens=', '.join(f"{self.name(t['elementId'])} x{t['amount']}" for t in b['elementTokens'] if t['amount'])
        if tokens:lines.append('Elements: '+tokens)
        lines.append('A saved team snapshot. Flask descriptions use base values; infuser effects and battle buffs are not recalculated.')
        return '\n'.join(lines)

    def character_text(self,c):
        lines=[f"HP: {c['hp']}"]
        if c['mutation']!=-1:lines.append('Mutation: '+self.name(c['mutation']))
        if c['snacks']:lines.append('Snacks: '+', '.join(self.name(n) for n in c['snacks']))
        for slot,f in enumerate(c['flasks'],1):
            if f is None:lines.append(f'{slot}. Empty');continue
            line=f"{slot}. {self.name(f['id'])} - Lv {f['level']}"
            if f['infusers']:line+=' ['+', '.join(self.name(n) for n in f['infusers'])+']'
            lines.append(line)
        return '\n'.join(lines)

    def render(self,build):
        from PIL import Image,ImageDraw,ImageFont
        build=validate_build(build);chars=build['build']['characters']
        width=1200;rowheight=365;height=130+rowheight*len(chars)
        canvas=Image.new('RGB',(width,height),'#15131d');draw=ImageDraw.Draw(canvas)
        font=ImageFont.load_default(size=18);small=ImageFont.load_default(size=14);heading=ImageFont.load_default(size=27)
        def text(x,y,value,f=font,color='#f0e8dc',columns=34,limit=3):
            lines=textwrap.wrap(value,width=columns,break_long_words=True) or ['']
            for i,line in enumerate(lines[:limit]):draw.text((x,y+i*22),line,font=f,fill=color)
        def picture(ident,box):
            path=self.image(ident)
            if path:
                with Image.open(path) as im:
                    im=im.convert('RGBA');im.thumbnail((box[2]-box[0],box[3]-box[1]))
                    canvas.paste(im,(box[0]+(box[2]-box[0]-im.width)//2,box[1]+(box[3]-box[1]-im.height)//2),im)
        draw.text((24,18),'Pocket Cauldron - exported build',font=heading,fill='#efd2a3')
        tokens=' | '.join(f"{self.name(t['elementId'])} x{t['amount']}" for t in build['build']['elementTokens'] if t['amount'])
        text(24,58,tokens,small,columns=150,limit=2)
        draw.text((24,105),'Saved snapshot | Slots left to right | Levels and infusers shown; base effects are not recalculated',font=small,fill='#bdb3cb')
        for i,c in enumerate(chars):
            y=130+i*rowheight;draw.rounded_rectangle((12,y+5,1188,y+rowheight-6),radius=12,fill='#282332')
            picture(c['id'],(20,y+45,190,y+235))
            text(24,y+12,self.name(c['id']),font,columns=18,limit=1)
            text(26,y+240,f"HP {c['hp']}",font,columns=18,limit=1)
            extra=[]
            if c['mutation']!=-1:extra.append('Mutation: '+self.name(c['mutation']))
            if c['snacks']:extra.append('Snacks: '+', '.join(self.name(n) for n in c['snacks']))
            text(26,y+270,' / '.join(extra),small,columns=23,limit=3)
            slots=c['flasks'];n=max(4,len(slots));cell=965/n
            for j,f in enumerate(slots):
                x=int(205+j*cell);cw=int(cell-10)
                draw.rounded_rectangle((x,y+15,x+cw,y+rowheight-22),radius=8,fill='#1c1924')
                draw.text((x+8,y+22),f'Slot {j+1}',font=small,fill='#bdb3cb')
                if f is None:
                    draw.text((x+8,y+150),'Empty',font=font,fill='#bdb3cb');continue
                picture(f['id'],(x+5,y+50,x+cw-5,y+218))
                columns=max(7,int(cw/10))
                text(x+8,y+220,self.name(f['id']),font,columns=columns,limit=2)
                text(x+8,y+265,f"Level {f['level']}",small,columns=columns,limit=1)
                if f['infusers']:text(x+8,y+289,', '.join(self.name(n) for n in f['infusers']),small,color='#c9acf0',columns=columns,limit=2)
        result=io.BytesIO();canvas.save(result,format='PNG');result.seek(0);return result
