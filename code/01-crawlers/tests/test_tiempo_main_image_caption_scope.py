"""Standalone main-image contract boundary; no generic outside prose removal."""
import unittest
from bs4 import BeautifulSoup
from crawler_core import tiempo_continuous_source as source

IMAGE='<div class="complemento-item m-t-md"><img class="img-responsive complemento-img" src="https://static.tiempo.com.mx/uploads/imagen/a.jpg" alt=""><p class="text-center">Imagen ilustrativa</p></div>'
def article(image=IMAGE,body='<p>Actual body.</p>'):
 return '<article id="article-post"><header><h1>Title</h1></header>'+image+'<blockquote><p>Actual lead.</p>Por: Author</blockquote><div class="complementos-container">'+body+'</div></article>'
class ScopeTests(unittest.TestCase):
 def test_exact_structural_caption_preserved_in_audit_not_body(self):
  for text in ['Imagen ilustrativa','Capturas de pantalla de video']:
   a=BeautifulSoup(article(IMAGE.replace('Imagen ilustrativa',text)),'html.parser').article;before=a.select_one('.complementos-container').get_text()
   record=source.remove_contract_main_image_captions(a);self.assertEqual(len(record),1);self.assertEqual(record[0]['caption_text'],text);self.assertEqual(a.select_one('.complementos-container').get_text(),before);self.assertIn('Actual lead',a.get_text())
 def test_extra_text_or_extra_tags_never_removed(self):
  variants=[IMAGE.replace('</div>','Additional news.</div>'),IMAGE.replace('</div>','<p>Extra news.</p></div>'),IMAGE.replace('Imagen ilustrativa','<b>Imagen ilustrativa</b>'),IMAGE.replace('<img ','<span>Extra</span><img '),IMAGE.replace('text-center','news-paragraph'),IMAGE.replace('static.tiempo.com.mx','outside.invalid'),IMAGE+IMAGE]
  for value in variants:
   with self.subTest(value=value):
    a=BeautifulSoup(article(value),'html.parser').article;raw=str(a);self.assertEqual(source.remove_contract_main_image_captions(a),[]);self.assertEqual(str(a),raw)
 def test_same_container_in_body_after_lead_or_nested_is_not_main_caption(self):
  variants=[article('',IMAGE),article().replace(IMAGE,'').replace('</blockquote>','</blockquote>'+IMAGE),article('<section>'+IMAGE+'</section>')]
  for value in variants:
   a=BeautifulSoup(value,'html.parser').article;raw=str(a);self.assertEqual(source.remove_contract_main_image_captions(a),[]);self.assertEqual(str(a),raw)
 def test_caption_removal_does_not_remove_adjacent_unexpected_news(self):
  a=BeautifulSoup(article(IMAGE+'<p>Important extra news outside.</p>'),'html.parser').article
  self.assertEqual(len(source.remove_contract_main_image_captions(a)),1);self.assertIn('Important extra news outside.',a.get_text())
 def test_wrong_lead_header_body_multiplicity_is_ambiguous(self):
  variants=[article().replace('</header>','</header><header></header>'),article().replace('</blockquote>','</blockquote><blockquote>Another lead</blockquote>'),article().replace('</article>','<div class="complementos-container">Another body</div></article>')]
  for value in variants:self.assertEqual(source.remove_contract_main_image_captions(BeautifulSoup(value,'html.parser').article),[])
 def test_html_parser_p_lead_wrapper_is_exact_not_arbitrary_nested(self):
  valid=article().replace('<blockquote>','<p class="lead"><blockquote>').replace('</blockquote>','</blockquote></p>')
  a=BeautifulSoup(valid,'html.parser').article;self.assertEqual(len(source.remove_contract_main_image_captions(a)),1)
  for value in [valid.replace('class="lead"','class="news"'),valid.replace('</blockquote></p>','</blockquote>Extra news.</p>'),valid.replace('</blockquote></p>','</blockquote><span>Extra</span></p>'),valid.replace('<p class="lead">','<section>'),valid.replace('</blockquote>','<blockquote>Another quote</blockquote></blockquote>')]:
   a=BeautifulSoup(value,'html.parser').article;self.assertEqual(source.remove_contract_main_image_captions(a),[])
if __name__=='__main__':unittest.main()
