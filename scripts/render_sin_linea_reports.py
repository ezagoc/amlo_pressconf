from pathlib import Path
import os,subprocess
from pypdf import PdfReader
from PIL import Image,ImageDraw

root=Path(__file__).resolve().parents[1]
out=root/'outputs/sin-linea-20261026'
preview=out/'pdf-preview'
preview.mkdir(exist_ok=True)
env=dict(os.environ,FONTCONFIG_FILE=str(out/'fonts.conf'))
pages=[]
for pdf in sorted((out/'staged/repo/output/desc_stats').glob('*.pdf')):
    reader=PdfReader(pdf)
    assert len(reader.pages)>0
    for i,p in enumerate(reader.pages,1):
        assert len(p.extract_text().strip())>30,(pdf,i)
        prefix=preview/(pdf.stem+f'-{i}')
        subprocess.run(['pdftoppm','-f',str(i),'-l',str(i),'-scale-to','1500','-png','-singlefile',str(pdf),str(prefix)],
                       env=env,check=True,capture_output=True)
        pages.append((pdf.name,i,prefix.with_suffix('.png')))
for j in range(0,len(pages),2):
    group=pages[j:j+2]
    canvas=Image.new('RGB',(1500,1200*len(group)), 'white')
    draw=ImageDraw.Draw(canvas)
    for pos,(name,page,png) in enumerate(group):
        img=Image.open(png).convert('RGB');img.thumbnail((1500,1150))
        draw.text((10,pos*1200+5),name+f' p{page}',fill='black')
        canvas.paste(img,((1500-img.width)//2,pos*1200+35))
    canvas.save(preview/f'contact-{j//2+1}.png')
print('Rendered',len(pages),'pages for visual review')
