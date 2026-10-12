"""Kevin: response-bound UTF-8 diagnostic correction, never a native rewrite.

The production source diagnostic remains frozen. A private function clone can
recheck exactly the saved response using its explicit HTTP decoding evidence.
It is not a source-gap classification and cannot certify article acceptance.
"""
from pathlib import Path
import hashlib
import html
import json
import re
import types
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from . import tiempo_continuous_source as source

RULE_VERSION = 'tiempo-bound-utf8-diagnostic-correction-v1'
CLASSIFICATION = 'source_utf8_decoding_correction'
EXPLAINABLE_FLAGS = frozenset({
    'raw_visible_body_difference_requires_reading',
    'source_title_metadata_disagreement', 'visible_author_difference',
    'visible_summary_difference', 'visible_title_difference'})
RESEARCH_FLAGS = frozenset({'article_vs_discovery_day_difference',
    'suspicious_very_short_body_review_only', 'duplicate_canonical_requires_review',
    'duplicate_body_requires_review'})
ARTICLE_TAGS = frozenset({'article','div','center','a','img','p','header','ol','li',
    'h1','h2','h3','blockquote','i','strong','ul','footer','br','style','script',
    'em','b','span','u','small','sup','sub','hr'})
SHARE_HANDLERS = frozenset({
    "window.open('https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(document.URL) + '&t=' + encodeURIComponent(document.URL)); return false;",
    "window.open('https://twitter.com/intent/tweet?text=' + encodeURIComponent(document.title) + ':%20'  + encodeURIComponent(document.URL)); return false;",
    "window.open('mailto:?subject=' + encodeURIComponent(document.title) + '&body=' +  encodeURIComponent(document.URL)); return false;"})


def _digest(value):
    return hashlib.sha256(source.encoded(value)).hexdigest()


def _utf8(value):
    return isinstance(value, str) and value.strip().lower().replace('_', '-') in {'utf-8', 'utf8'}


def _charsets(value):
    return re.findall(r'charset\s*=\s*[\"\']?([^\s;\"\'>]+)', value or '', re.I)


def _private_diagnose(row, batch_path, raw):
    """No module-global monkey patch, and no arbitrary-byte decoding fallback."""
    calls = []
    def bound_soup(markup, *args, **kwargs):
        if isinstance(markup, bytes):
            if markup != raw:
                raise ValueError('Diagnostic encountered a different byte response')
            calls.append(hashlib.sha256(markup).hexdigest())
            markup = markup.decode('utf-8', errors='strict')
        return BeautifulSoup(markup, *args, **kwargs)
    namespace = dict(source.diagnose.__globals__)
    namespace['BeautifulSoup'] = bound_soup
    private = types.FunctionType(source.diagnose.__code__, namespace,
                                 source.diagnose.__name__, source.diagnose.__defaults__,
                                 source.diagnose.__closure__)
    record = private(row, Path(batch_path))
    if calls != [hashlib.sha256(raw).hexdigest()]:
        raise ValueError('Diagnostic did not read exactly the bound source once')
    return record


def classify_encoding_disagreement(row, raw_bytes, response_metadata, source_check, batch_path):
    """Return a reproducible decision; reject uncertainty without waiving flags."""
    reasons=[]; evidence={}
    def reject(reason):
        reasons.append(reason)
    def result(matched=False):
        return {'matched':matched, 'classification':CLASSIFICATION if matched else None,
                'rule_version':RULE_VERSION, 'rejection_reasons':sorted(set(reasons)),
                'evidence':evidence}
    r=response_metadata; observed=set(source_check.get('automatic_flags', []))
    unexplained=set(source_check.get('unexplained_flags', []))
    if not observed & EXPLAINABLE_FLAGS:
        reject('no_candidate_encoding_flags')
    if (source_check.get('critical_flags') or unexplained - EXPLAINABLE_FLAGS
            or observed - EXPLAINABLE_FLAGS - RESEARCH_FLAGS):
        reject('other_native_anomaly_remains')
    if (row.get('qa_status')!='success' or row.get('error') is not None
            or row.get('source_specific_error') or row.get('date_conflict')
            or not all(row.get(k) for k in ['title','main_text','date_published','canonical_url'])
            or source_check.get('collection_outcome')!='article_candidate'):
        reject('not_a_text_bearing_native_article_candidate')
    if (r.get('status')!=200 or r.get('error') is not None or r.get('curl_exit_code')!=0
            or r.get('body_text_limit_exceeded') is not False
            or r.get('final_url')!=row.get('final_url') or row.get('status')!=200):
        reject('response_not_complete_success')
    charsets=_charsets(r.get('content_type'))
    if ('text/html' not in str(r.get('content_type','')).lower() or len(charsets)!=1
            or not _utf8(charsets[0]) or not _utf8(r.get('body_encoding'))
            or r.get('body_encoding_source')!='http_charset'
            or row.get('content_type')!=r.get('content_type')):
        reject('missing_or_conflicting_http_utf8_evidence')
    if not isinstance(raw_bytes,bytes):
        reject('source_bytes_required'); return result()
    raw_sha=hashlib.sha256(raw_bytes).hexdigest()
    if (raw_sha!=row.get('snapshot_sha256') or raw_sha!=source_check.get('snapshot_sha256')
            or source_check.get('fields_sha256')!=source.fields_digest(row)
            or source_check.get('sample_id')!=row.get('sample_id')):
        reject('source_or_native_fields_binding_mismatch')
    try:
        text=raw_bytes.decode('utf-8',errors='strict')
    except UnicodeDecodeError:
        reject('invalid_utf8_bytes'); return result()
    soup=BeautifulSoup(text,'html.parser')
    if not re.search(r'</body>\s*</html>\s*\Z',text,re.I):
        reject('incomplete_saved_document')
    if any(len(soup.select(tag))!=1 for tag in ['html','head','body','article#article-post']):
        reject('ambiguous_document_envelope')
    declared=[t.get('charset') for t in soup.select('meta[charset]')]
    for tag in soup.select('meta[http-equiv]'):
        if str(tag.get('http-equiv','')).lower()=='content-type':
            declared+=_charsets(tag.get('content'))
        elif str(tag.get('http-equiv','')).lower()=='refresh':
            reject('unvalidated_meta_refresh')
    if not declared or any(not _utf8(v) for v in declared): reject('conflicting_html_charset')
    try:
        articles=[json.loads(t.get_text(),strict=False) for t in soup.select('script[type="application/ld+json"]')]
        if (len(articles)!=1 or not isinstance(articles[0],dict)
                or articles[0].get('@type') not in {'NewsArticle','Article'}):
            reject('unvalidated_jsonld_identity_shape')
        else:
            entity=articles[0].get('mainEntityOfPage')
            slug=urlsplit(row.get('canonical_url','')).path.strip('/').split('/')[-1]
            if entity!={'@type':'WebPage','@id':slug}:
                reject('jsonld_article_identity_mismatch')
            author=articles[0].get('author')
            if (not isinstance(author,dict) or set(author)!={'@type','name'}
                    or author.get('@type')!='Person'
                    or source.norm(author.get('name'))!=source.norm(row.get('authors'))):
                reject('jsonld_author_mismatch')
            native_title=source.norm(row.get('title'))
            raw_headline=source.norm(articles[0].get('headline'))
            if raw_headline!=native_title and source.norm(html.unescape(raw_headline or ''))!=native_title:
                reject('jsonld_headline_mismatch')
    except (ValueError,TypeError):reject('unparseable_jsonld_identity')
    title_channels=[t.get('content') for t in soup.select('meta[property="og:title"],meta[name="twitter:title"]')]
    title_channels += [soup.title.get_text()] if soup.title else []
    title_channels += [t.get_text(' ',strip=True) for t in soup.select('article#article-post header h1')]
    # DOM text has already undergone HTML parsing. Decoding it a second time
    # could conceal a real literal-entity disagreement with the original title.
    if not title_channels or any(source.norm(v)!=source.norm(row.get('title')) for v in title_channels):
        reject('literal_dom_headline_mismatch')
    # The correction must not turn an unexamined dynamic body into a known one.
    article=soup.select_one('article#article-post')
    body=article.select_one('.complementos-container') if article else None
    if body is None: reject('missing_recognized_body')
    else:
        if article.select('object,embed,canvas,svg,template,noscript,iframe,video,audio,source'):
            reject('unvalidated_dynamic_or_media_structure')
        for tag in [article,*article.find_all(True)]:
            if tag.name not in ARTICLE_TAGS:reject('unvalidated_article_tag')
            share=tag.find_parent('ul',class_='share-buttons') is not None
            for key,value in tag.attrs.items():
                if key.startswith('on') and not (key=='onclick' and tag.name=='a' and
                        share and value in SHARE_HANDLERS):
                    reject('unvalidated_article_event_handler')
                if key.startswith('data-') and not (
                        (tag.name=='blockquote' and 'twitter-tweet' in tag.get('class',[]) and key=='data-lang') or
                        (share and tag.name=='a' and key in {'data-link','data-text'})):
                    reject('unvalidated_dynamic_article_attributes')
                if key=='style' and re.search(r'url\s*\(|expression\s*\(|@import',str(value),re.I):
                    reject('unvalidated_style_media')
                if key in {'src','href'} and re.match(r'\s*(?:javascript|data|blob):',str(value),re.I):
                    reject('unvalidated_dynamic_link')
            if tag.name=='img' and any(k not in {'class','style','src','alt','width','height'} for k in tag.attrs):
                reject('unvalidated_image_attribute')
        for tag in article.select('script'):
            if (tag.get('src')!='https://platform.twitter.com/widgets.js'
                    or tag.get_text(strip=True) or tag.parent.select_one('blockquote.twitter-tweet') is None
                    or set(tag.attrs)-{'src','async','charset'} or tag.get('charset')!='utf-8'
                    or tag.find_parent(class_='complementos-container') is None):
                reject('unvalidated_article_script')
        for tag in article.select('style'):
            if re.sub(r'\s+','',tag.get_text())!='.video-container{max-width:100%;max-height:600px;margin:0auto;display:block;}':
                reject('unvalidated_article_style')
    evidence.update(snapshot_sha256=raw_sha, fields_sha256=source.fields_digest(row),
                    response_metadata_sha256=_digest(r), http_charset=charsets,
                    html_charsets=declared, declared_body_encoding=r.get('body_encoding'),
                    strict_utf8=True, native_checker_sha256=source.sha_file(source.__file__),
                    generic_title_metadata=[dict(t.attrs) for t in soup.select('meta[name="title"]')],
                    generic_title_scope='Raw generic title metadata is preserved, including malformed attributes; it is not repaired or asserted to equal the headline. Compared headline channels are the unchanged diagnostic channels.',
                    image_references_preserved=[dict(t.attrs) for t in article.select('img')] if article else [],
                    image_pixels_reviewed=False, video_content_reviewed=False)
    if reasons:return result()
    original=source.diagnose(row,Path(batch_path))
    corrected=_private_diagnose(row,batch_path,raw_bytes)
    original_flags=set(original['automatic_flags']); corrected_flags=set(corrected['automatic_flags'])
    # Extra frozen-plan/identity anomalies are never explained by this helper.
    if (not original_flags<=observed or observed-original_flags-RESEARCH_FLAGS
            or corrected_flags-RESEARCH_FLAGS):
        reject('independent_utf8_recheck_retains_anomaly')
    explained=original_flags-corrected_flags
    if not explained or not explained<=EXPLAINABLE_FLAGS or unexplained-explained:
        reject('flags_not_fully_explained_by_decoding')
    autodetected=BeautifulSoup(raw_bytes,'html.parser').original_encoding
    if _utf8(autodetected):reject('native_decoder_was_already_utf8')
    evidence.update(native_detected_encoding=autodetected,
                    original_diagnostic_sha256=_digest(original),
                    utf8_diagnostic_sha256=_digest(corrected),
                    original_automatic_flags=sorted(original_flags),
                    utf8_automatic_flags=sorted(corrected_flags),
                    explained_encoding_flags=sorted(explained),
                    source_judgment_flags_preserved=sorted(observed & RESEARCH_FLAGS),
                    original_native_flags_preserved=True,
                    corrected_scope='Exact bound saved response only; unchanged diagnostic function with explicit response-evidenced UTF-8 decoding; no native rewrite or AI/human acceptance.')
    return result(not reasons)
