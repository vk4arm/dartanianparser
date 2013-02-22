# coding=utf8
import sys
sys.path.append("../../conf")

import HTMLParser
import settings #from ../../conf module, see above
import re

from lxml import etree
from lxml import html

from StringIO import StringIO

find_text = etree.XPath("//*[not(self::script or self::style or self::noscript)]/text()[string-length() > 30]")

class Contexter:
    
    # вот тут то, что в example.py
    # но - класс "содержит в себе собранные во время работы дисклеймеры"
    # и метод clean, который их убивает. Впрочем, можнро пересоздать объект
    def __init__(self):
        self.phrases = {}
        self.disclaimers = {}
        self.ph_count = 0

    def clean(self):
        self.disclaimers={}

    def post_process(self, texts, article_key):

        buffer = []

        if not article_key in texts:
            return ''

        for text in texts[article_key]['texts']:
            if len(text) < 30: continue
            if text[0] in ["'", '"']: text = text[1:]
            if text[-1] in ["'", '"']: text = text[:-1]

            if ((text[-1] == '.' or text[-1] == '!' or text[-1] == '?') and len(text) < 50)  or '.' in text and text > 50:
                if not self.disclaimers.has_key(text):
                    if not self.phrases.has_key(text) and text != '':
                        buffer.append(text)

                        self.phrases[text] = 1
                        self.ph_count += 1
                    else:
                        self.disclaimers[text] = 1

            if self.ph_count == 1000:
                self.ph_count = 0
                self.phrases = {}

        return '\n \n'.join(buffer)


    def get_from_meta(self, name, text):

        contentMatch = re.match(r'.*?<meta([^>]*?)(?:name|property)=[\'\"][^>]*?%s[^>]*?[\'\"]([^>]*?)>' % name, text, re.I | re.U | re.S)

        if contentMatch is not None:

            content = "%s%s" % (contentMatch.group(1), contentMatch.group(2))

            metaMatch = re.match(r'.*content=[\'\"](.*?)[\'\"]', content, re.I | re.U | re.S)

            if metaMatch is not None:
                return HTMLParser.HTMLParser().unescape(metaMatch.group(1))

        return ''


    def capture_meta(self, text):

        #capturing meta
        titleMatch = re.match(r'.*<title>(.*?)</title>', text, re.I | re.U | re.S)

        if titleMatch is not None:
            title = titleMatch.group(1)
        else:
            title = self.get_from_meta('title', text)

        descr = self.get_from_meta('description', text)
        keywords = self.get_from_meta('keywords', text)
        author = self.get_from_meta('author', text)
        generator = self.get_from_meta('generator', text)

        return title, descr, keywords, author, generator


    def process_html(self, text):

        text = text.strip()
        text = text.decode('utf8','ignore')
        text = "%s" % text

        text = re.sub(r'\s+',' ',text)
        text = re.sub(r'<!--.*?-->','',text)

        title, descr, keywords, author, generator = self.capture_meta(text)

        text = re.sub(r'<(?i)head.*?>.*?<\/(?i)head>','',text)
        text = re.sub(r'<(?i)script.*?>.*?<\/(?i)script>','',text)
        text = re.sub(r'<(?i)noscript.*?>.*?<\/(?i)noscript>','',text)
        r = re.finditer(r"<(?i)a\s.*?>.{0,500}?</(?i)a>",text)
        for m in r:
            found = m.group()
            changeto = re.sub(r'<(?i)a\s.*?>','',found).replace(r'</(?i)a>','')
            text = text.replace(found,changeto)
        text = re.sub(r'<\/?(?i)(img|s|i|u|b|em|strong|span|font|center|basefont|big|small|tt|marquee|blockquote).*?>','',text)
        text = re.sub(r'<(?i)br\/?>','\n',text)
        # json remover....
        text = re.sub(r'\{".{0,30}?":.{0,2000}?\}','',text)
        text = re.sub(r'\{\'.{0,30}?\':.{0,2000}?\}','',text)

        try:
            tree = html.parse(StringIO(text))
        except Exception:
            print "Couldn't parse a tree"
            return None

        try:
            paths = [tree.getpath( text.getparent()) for text in find_text(tree)]
            ts = [text for text in find_text(tree)]
        except Exception:
            print "Couldn't get XPath paths"
            return None

        ppaths = dict(zip(paths, ts)) # get (xpath, txt chunks)

        texts = {}

        #preprocessing
        for p in paths:
            text = ppaths[p]

            if text is None: continue
            text = text.strip()
            k = re.sub("\[\d*?\]$",'', p)

            if not texts.has_key(k):
                texts[k]={
                'count':0,
                'total_len':0,
                'max_len': 0,
                'texts':[]
                }

            texts[k]['texts'].append(text)
            texts[k]['count'] += 1
            text_len = len(text)
            texts[k]['total_len'] += text_len
            if text_len > texts[k]['max_len']:
                texts[k]['max_len'] = text_len

        ord_txt = sorted(texts.iteritems(), key = lambda (k,data): data['total_len'])

        first = ord_txt[-1][1]
        second = ord_txt[-2][1]

        max_key = ord_txt[-1][0]
        pre_max_key = ord_txt[-2][0]

        if first['max_len'] < 500 and second['max_len']< 500:
#            print "Length of a pieces are insufficient"
            return None

        if first['count'] == 1 and second['count'] > 1:
            keys = [pre_max_key, max_key]
        elif first['count'] > 1 and second['count'] == 1:
            keys = [max_key, pre_max_key]
        elif first['count'] == second['count']:
            if first['total_len'] > second['total_len']:
                keys = [max_key, pre_max_key]
            else: keys = [pre_max_key, max_key]
        elif first['count'] < second['count']:
            keys = [pre_max_key, max_key]
        else:
            keys = [max_key, pre_max_key]

        if not texts.has_key(max_key) and not texts.has_key(pre_max_key):
            return None

        text1 = self.post_process(texts, keys[0])
        text2 = self.post_process(texts, keys[1])


        # и вот тут - то что в example во внутреннем цикле
        # Естественно то, что связано с работой с файлами нужно убрать.
        #Результат должен выглядеть так:
        return {
            'text1': text1, # текст самого большого текстового "слоя"
            'text2': text2, # текст следующего по размеру меньшего текстового слоя
            'title': title,
            'description': descr,
            'keywords': keywords, #keywords,
            'author': author,
            'generator': generator, # Это все их хидера и мета
        }

if __name__ == '__main__':

    ctxr = Contexter()

    def res_from_file(filename):

        with open(filename,'r') as f:
            return ctxr.process_html(f.read())

    if len(sys.argv) == 2:
        res = res_from_file(sys.argv[1])

        print "title: %s" %res['title']
        print "description: %s" %res['description']
        print "keywords: %s" %res['keywords']
        print "author: %s" %res['author']
        print "generator: %s" %res['generator']
    else:
        print "Usage: python <script> <file-to-test-parsing-on>"


