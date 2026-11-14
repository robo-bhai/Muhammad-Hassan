"""
Voice / Urdu search madad.

Customer Urdu (اردو) mein bolta ya likhta hai ("دودھ") lekin products aksar English ya Roman Urdu naam se hote hain
("Milk", "Doodh"). Ye module search text ko kai milte-julte lafzon (variants) mein badalta hai, aur search un sab mein se
kisi ek se bhi match kar leta hai (OR). Roman Urdu <-> English bhi chalta hai (doodh <-> milk).

Naya lafz jodna ho: WORDS mein ek line barhayen: 'urdu': ['english', 'roman urdu', ...]
"""
import re
from functools import reduce
from operator import or_

from django.db.models import Q

# Urdu lafz -> [English, Roman Urdu, ...]  (pehla English hona behtar hai)
WORDS = {
    'دودھ': ['milk', 'doodh'],
    'دہی': ['yogurt', 'dahi', 'curd'],
    'مکھن': ['butter', 'makhan'],
    'پنیر': ['cheese', 'paneer'],
    'انڈے': ['egg', 'anda', 'eggs'],
    'انڈا': ['egg', 'anda', 'eggs'],
    'چاول': ['rice', 'chawal'],
    'آٹا': ['flour', 'atta'],
    'میدہ': ['maida', 'flour'],
    'چینی': ['sugar', 'cheeni'],
    'نمک': ['salt', 'namak'],
    'تیل': ['oil', 'tel'],
    'گھی': ['ghee'],
    'چائے': ['tea', 'chai'],
    'کافی': ['coffee'],
    'پانی': ['water', 'pani'],
    'جوس': ['juice'],
    'بسکٹ': ['biscuit', 'biscuits'],
    'ڈبل روٹی': ['bread', 'double roti'],
    'روٹی': ['roti', 'bread'],
    'نان': ['naan'],
    'دال': ['lentil', 'daal', 'dal'],
    'چنا': ['chickpea', 'chana'],
    'مرغی': ['chicken', 'murghi'],
    'چکن': ['chicken'],
    'گوشت': ['meat', 'gosht', 'beef', 'mutton'],
    'بیف': ['beef'],
    'مٹن': ['mutton'],
    'مچھلی': ['fish', 'machli'],
    'پیاز': ['onion', 'pyaz'],
    'ٹماٹر': ['tomato', 'tamatar'],
    'آلو': ['potato', 'aloo'],
    'لہسن': ['garlic', 'lehsan'],
    'ادرک': ['ginger', 'adrak'],
    'مرچ': ['chilli', 'mirch'],
    'ہلدی': ['turmeric', 'haldi'],
    'دھنیا': ['coriander', 'dhania'],
    'سیب': ['apple', 'seb'],
    'کیلا': ['banana', 'kela'],
    'کیلے': ['banana', 'kela'],
    'آم': ['mango', 'aam'],
    'مالٹا': ['orange', 'malta'],
    'سنتری': ['orange', 'santra'],
    'انگور': ['grapes', 'angoor'],
    'تربوز': ['watermelon', 'tarbooz'],
    'سبزی': ['vegetable', 'sabzi'],
    'سبزیاں': ['vegetables', 'sabzi'],
    'پھل': ['fruit', 'phal'],
    'صابن': ['soap', 'sabun'],
    'شیمپو': ['shampoo'],
    'ٹوتھ پیسٹ': ['toothpaste', 'tooth paste'],
    'سرف': ['detergent', 'surf'],
    'ٹشو': ['tissue'],
    'پیزا': ['pizza'],
    'برگر': ['burger'],
    'بریانی': ['biryani'],
    'کباب': ['kabab', 'kebab'],
    'سموسہ': ['samosa'],
    'سموسے': ['samosa'],
    'چپس': ['chips'],
    'چاکلیٹ': ['chocolate'],
    'آئس کریم': ['ice cream'],
    'کولڈ ڈرنک': ['cold drink', 'soft drink'],
    'بوتل': ['bottle'],
    'شہد': ['honey', 'shehad'],
    'کھجور': ['dates', 'khajoor'],
    'بادام': ['almond', 'badam'],
    'ناشتہ': ['breakfast', 'nashta'],
    'مصالحہ': ['spice', 'masala'],
    'مصالحے': ['spices', 'masala'],
}

_DIACRITICS = re.compile('[\u064B-\u065F\u0670\u0640]')
_URDU_CHARS = re.compile('[\u0600-\u06FF]')
MAX_VARIANTS = 8
# Bolne mein aam lafz jo search ke kaam ke nahi ("دودھ چاہیے", "چائے کی پتی")
STOP_WORDS = {'کی', 'کا', 'کے', 'اور', 'میں', 'سے', 'کو', 'پر', 'دیں', 'دو', 'چاہیے', 'چاہئے', 'لاؤ', 'ہے', 'ہیں',
              'والا', 'والی', 'والے', 'مجھے', 'ایک', 'کچھ', 'تلاش', 'دکھاؤ', 'دکھائیں', 'ڈھونڈو'}


def normalize(text):
    """Urdu likhai ke farq (ي/ی, ك/ک, ة/ہ, zabar-zer) mita kar ek shakal mein."""
    t = (text or '').strip().lower()
    t = _DIACRITICS.sub('', t)
    t = (t.replace('\u064A', '\u06CC').replace('\u0649', '\u06CC').replace('\u06D2', '\u06D2')
          .replace('\u0643', '\u06A9').replace('\u0629', '\u06C1').replace('\u06BE', '\u06BE'))
    t = t.replace('\u06C3', '\u06C1')
    return re.sub(r'\s+', ' ', t)


def has_urdu(text):
    return bool(_URDU_CHARS.search(text or ''))


_NORM_WORDS = {normalize(k): v for k, v in WORDS.items()}
_PHRASES = sorted(_NORM_WORDS, key=lambda k: -len(k.split()))          # lambe jumle pehle
_LATIN_INDEX = {}                                                      # 'doodh' / 'milk' -> baqi alternatives
for _alts in WORDS.values():
    for _a in _alts:
        _LATIN_INDEX.setdefault(_a.lower(), [])
        for _b in _alts:
            if _b.lower() != _a.lower() and _b.lower() not in _LATIN_INDEX[_a.lower()]:
                _LATIN_INDEX[_a.lower()].append(_b.lower())


def search_variants(text):
    """Search text -> [asli text, aur milte julte lafz...] (kam az kam ek, zyada se zyada MAX_VARIANTS)."""
    raw = (text or '').strip()
    if not raw:
        return []
    variants = [raw]

    if has_urdu(raw):
        norm = normalize(raw)
        # lafz ba lafz: har lafz ke liye uske alternatives (lambe jumle pehle pehchane jate hain)
        stop = {normalize(w) for w in STOP_WORDS}
        words = [w for w in norm.split(' ') if w and w not in stop] or norm.split(' ')
        i, parts, unmapped = 0, [], False
        while i < len(words):
            matched = False
            for ph in _PHRASES:
                n = len(ph.split())
                if ' '.join(words[i:i + n]) == ph:
                    parts.append(_NORM_WORDS[ph])
                    i += n
                    matched = True
                    break
            if not matched:
                unmapped = True
                i += 1
        if parts and not unmapped:                       # poora jumla pehchana gaya: milta julta jumla bhi
            depth = max(len(p) for p in parts)
            for j in range(depth):
                v = ' '.join(p[min(j, len(p) - 1)] for p in parts)
                if v and v not in variants:
                    variants.append(v)
        if len(parts) > 1 or unmapped:                   # alag alag lafz bhi (milk, sugar...) - ek hi match kafi
            for p in parts:
                for alt in p:
                    if alt not in variants:
                        variants.append(alt)
    else:
        low = raw.lower()
        for alt in _LATIN_INDEX.get(low, []):          # poora text ek jana-pehchana lafz ho (doodh <-> milk)
            if alt not in variants:
                variants.append(alt)
    return variants[:MAX_VARIANTS]


def q_any(fields, text):
    """fields ki kisi bhi field mein text ya uske kisi variant ka icontains match (OR)."""
    terms = search_variants(text) or [text]
    return reduce(or_, (Q(**{f'{f}__icontains': t}) for f in fields for t in terms))
