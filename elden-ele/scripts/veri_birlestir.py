#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
veri_birlestir.py · Elden Ele

Ne yapar : Farklı kaynaklardan gelen video sayılarını (Meta Business Suite, TikTok Studio,
           YouTube Studio, elle doldurulmuş tablo) tek tabloda birleştirir; gönderme oranını,
           bandı ve işaretleri hesaplar; hesaptaki desenleri kanıtıyla yazar.
Girdi    : Bir ya da daha çok dosya: Meta Business Suite, TikTok Studio ya da YouTube Studio'dan
           indirilen CSV (openpyxl kuruluysa XLSX), elle doldurulmuş CSV, Instagram sahip verisi JSON'u
           (reels listesi) ve isteğe bağlı etiket.csv (video_id, etiket). Sütun adları Türkçe ya da
           İngilizce olabilir. İsteğe bağlı rakip tablosu (hesap, video, goruntuleme).
Çıktı    : KLASOR/tablo.csv ve KLASOR/ozet.json
Örnek    : python3 veri_birlestir.py hesap.csv meta.csv --rakip rakip.csv --cikti birlesik
Not      : Yalnız Python standart kütüphanesi kullanır. İnternete çıkmaz.
           "3,4 B" gibi değerlerde B harfi Türkçe "bin" sayılır.
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
import unicodedata

TABLO_SUTUNLARI = [
    "video_id", "baslik", "platform", "yayin_tarihi", "sure_sn", "goruntuleme", "erisim",
    "begeni", "yorum", "paylasim", "kaydetme", "ort_izleme_sn", "kaydirma_orani",
    "izleme_yuzdesi", "gonderme_orani", "begeni_orani", "ortanca_kati", "bant", "isaret",
    "devam_orani",
]

# Eş anlamlı sözlük. Sıra önceliktir: aynı dosyada iki sütun aynı alana düşerse
# listede önce gelen kazanır. Yazımlar aşağıdaki sade() biçimindedir.
ES_ANLAMLILAR = {
    "video_id": ["video id", "post id", "id", "content", "icerik", "video kimligi", "gonderi kimligi",
                 "icerik kimligi", "media id", "medya kimligi", "content id", "shortcode"],
    "baslik": ["baslik", "title", "video title", "video basligi", "video name", "video adi", "ad", "name",
               "description", "aciklama", "caption", "video description", "post", "metin"],
    "platform": ["platform"],
    "tur": ["post type", "gonderi turu", "icerik turu", "content type", "type", "tur"],
    "hesap": ["account username", "hesap kullanici adi", "account name", "hesap adi", "hesap", "account",
              "kanal", "channel", "kullanici adi", "username"],
    "yayin_tarihi": ["yayin tarihi", "publish time", "video publish time", "yayinlanma zamani",
                     "yayinlanma tarihi", "video yayinlanma zamani", "publish date", "post time",
                     "paylasim tarihi", "gonderi zamani", "posted", "date", "tarih", "time", "zaman", "timestamp"],
    "sure_sn": ["sure sn", "duration sec", "duration", "sure", "sure saniye", "video duration",
                "video suresi", "video length", "uzunluk", "length", "duration seconds"],
    "goruntuleme": ["goruntuleme", "views", "video views", "plays", "goruntulenme", "goruntulemeler",
                    "goruntulenmeler", "izlenme", "izlenmeler", "oynatma", "oynatmalar",
                    "video goruntuleme", "video goruntulemeleri", "total views", "toplam goruntuleme", "play count"],
    "erisim": ["erisim", "reach", "accounts reached", "erisilen hesaplar", "erisilen hesap",
               "ulasilan hesaplar", "hesaplara erisildi", "unique viewers", "tekil izleyiciler",
               "tekil goruntuleyenler", "total viewers", "toplam izleyici", "reached audience"],
    "begeni": ["begeni", "likes", "begeniler", "begenme", "begenmeler", "like count", "begenme sayisi"],
    "yorum": ["yorum", "comments", "yorumlar", "comments added", "eklenen yorumlar", "comment count"],
    "paylasim": ["paylasim", "shares", "sends", "paylasimlar", "gonderim", "gonderimler", "gonderme",
                 "gondermeler", "sharings"],
    "kaydetme": ["kaydetme", "saves", "kaydetmeler", "kaydedilenler", "kaydedenler", "favorites",
                 "favoriler"],
    "ort_izleme_sn": ["ort izleme sn", "average watch time", "ortalama izleme suresi", "avg watch time",
                      "average view duration", "ortalama goruntuleme suresi", "ortalama izlenme suresi",
                      "average time watched", "ortalama goruntulenme suresi", "ort izleme suresi"],
    "toplam_izleme_sn": ["total play time", "toplam oynatma suresi", "toplam izleme suresi",
                         "total watch time", "toplam izlenme suresi"],
    "toplam_izleme_saat": ["watch time hours", "izlenme suresi saat", "izlenme suresi saat olarak", "izlenme suresi saat cinsinden", "watch time"],
    "kaydirma_orani": ["kaydirma orani", "skip rate", "kaydirma", "swipe away rate", "swiped away",
                       "gecme orani", "atlama orani"],
    "izlemeyi_secen": ["stayed to watch", "viewed vs swiped away", "izlemeyi secenler",
                       "izlemeyi surdurenler", "goruntulendi kaydirmaya kiyasla", "izlemeye devam edildi", "izlemeye devam edenler", "izlemeye devam etti", "izlemeye devam orani", "stayed to watch vs swiped away", "goruntulendi kaydirildi karsisinda", "izlendi kaydirildi"],
    "izleme_yuzdesi": ["izleme yuzdesi", "average percentage viewed", "ortalama goruntuleme yuzdesi",
                       "goruntulenen ortalama yuzde", "ortalama izlenme yuzdesi", "avg watched pct", "ortalama goruntulenme yuzdesi"],
    "link": ["link", "permalink", "url", "video link", "baglanti", "kalici baglanti", "video url",
             "post link", "video baglantisi"],
    "etiket": ["etiket", "konu", "tag", "seri", "kategori"],
    "ort_izleme_ms": ["avg watch time ms", "average watch time ms"],
    "devam_goruntuleme": ["engaged views", "etkilesimli goruntuleme", "etkilesimli goruntulemeler", "etkilesimde bulunulan goruntulemeler", "etkilesimde bulunulan goruntuleme"],
    "deneme": ["is possible trial", "is trial", "trial", "deneme"],
    "gosterim": ["impressions", "gosterim", "gosterimler", "gosterim sayisi"],
}
SAYI_ALANLARI = ["goruntuleme", "erisim", "begeni", "yorum", "paylasim", "kaydetme", "gosterim",
                 "devam_goruntuleme", "ort_izleme_ms"]
ONDALIK_ALANLARI = ["kaydirma_orani", "izlemeyi_secen", "izleme_yuzdesi", "toplam_izleme_saat"]
SURE_ALANLARI = ["sure_sn", "ort_izleme_sn", "toplam_izleme_sn"]
BOS_DEGERLER = {"", "-", chr(0x2013), chr(0x2014), "n/a", "na", "yok", "null", "none", "nan"}

AYLAR = {"oca": 1, "ocak": 1, "jan": 1, "january": 1, "sub": 2, "subat": 2, "feb": 2, "february": 2,
         "mar": 3, "mart": 3, "march": 3, "nis": 4, "nisan": 4, "apr": 4, "april": 4, "may": 5,
         "mayis": 5, "haz": 6, "haziran": 6, "jun": 6, "june": 6, "tem": 7, "temmuz": 7, "jul": 7,
         "july": 7, "agu": 8, "agustos": 8, "aug": 8, "august": 8, "eyl": 9, "eylul": 9, "sep": 9,
         "sept": 9, "september": 9, "eki": 10, "ekim": 10, "oct": 10, "october": 10, "kas": 11,
         "kasim": 11, "nov": 11, "november": 11, "ara": 12, "aralik": 12, "dec": 12, "december": 12}


def hata(mesaj):
    print("HATA: " + mesaj, file=sys.stderr)
    sys.exit(1)


def sade(metin):
    """Başlığı karşılaştırılabilir hale getirir: küçük harf, Türkçe harfler sade, noktalama boşluk."""
    m = str(metin or "").replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    m = unicodedata.normalize("NFKD", m)
    m = "".join(c for c in m if not unicodedata.combining(c))
    m = re.sub(r"[^a-z0-9]+", " ", m)
    return re.sub(r"\s+", " ", m).strip()


SOZLUK = {}
for _alan, _liste in ES_ANLAMLILAR.items():
    for _sira, _ad in enumerate(_liste):
        SOZLUK.setdefault(sade(_ad), (_alan, _sira))


def alan_bul(sutun_adi):
    """Sütun adını sözlükteki alana çevirir. Bulamazsa (None, None)."""
    tam = sade(sutun_adi)
    if tam in SOZLUK:
        return SOZLUK[tam]
    parantezsiz = sade(re.sub(r"\([^)]*\)", " ", str(sutun_adi or "")))
    if parantezsiz and parantezsiz in SOZLUK:
        return SOZLUK[parantezsiz]
    # JSON alan adı: "playCount" -> "play count"
    ayrik = sade(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(sutun_adi or "")))
    if ayrik in SOZLUK:
        return SOZLUK[ayrik]
    return (None, None)


def tr_sayi(deger, ondalik=0):
    """1234.5 -> 1.234,5 (Türkçe biçim)."""
    if deger is None:
        return ""
    s = f"{deger:,.{ondalik}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def sayi_coz(ham, tam_sayi=True):
    """'1.234', '1,234', '12,5%', '1,2 B', '3.4K', '2 Mn' gibi değerleri sayıya çevirir."""
    if ham is None:
        return None
    if isinstance(ham, (int, float)):
        return float(ham)
    s = str(ham).strip().replace(" ", " ").replace(" ", " ")
    if s.lower() in BOS_DEGERLER:
        return None
    s = s.replace("%", "").replace("−", "-").strip()
    carpan = 1.0
    ek = re.search(r"([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\.?\s*$", s)
    if ek:
        e = sade(ek.group(1))
        ekler = {"b": 1e3, "bin": 1e3, "k": 1e3, "mn": 1e6, "m": 1e6, "milyon": 1e6, "mio": 1e6,
                 "mr": 1e9, "milyar": 1e9, "bn": 1e9}
        if e not in ekler:
            return None
        carpan = ekler[e]
        s = s[:ek.start()].strip()
    s = s.replace(" ", "").replace("'", "")
    if not re.fullmatch(r"-?[\d.,]+", s) or not re.search(r"\d", s):
        return None
    nokta, virgul = s.count("."), s.count(",")
    if nokta and virgul:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif nokta + virgul > 1:
        s = s.replace(".", "").replace(",", "")
    elif nokta + virgul == 1:
        ayrac = "." if nokta else ","
        sag = s.split(ayrac)[1]
        # Ekli değerde ("3,4 B") ayraç ondalıktır. Eksiz tam sayı alanında üç hane binliktir.
        if carpan == 1.0 and tam_sayi and len(sag) == 3:
            s = s.replace(ayrac, "")
        else:
            s = s.replace(ayrac, ".")
    try:
        return float(s) * carpan
    except ValueError:
        return None


def sure_coz(ham):
    """'69', '1:09', '0:01:09', '17.2s', '1 dk 9 sn', '0h:12m:30s' -> saniye."""
    if ham is None:
        return None
    if isinstance(ham, (int, float)):
        return float(ham)
    s = str(ham).strip().lower()
    if s in BOS_DEGERLER:
        return None
    if re.search(r"[a-zçğıöşü]", s):
        toplam, bulundu = 0.0, False
        for deger, birim in re.findall(r"(\d+(?:[.,]\d+)?)\s*(saniye|saat|dakika|sec|min|sa|dk|sn|h|m|s)", s):
            bulundu = True
            d = float(deger.replace(",", "."))
            if birim in ("saat", "sa", "h"):
                toplam += d * 3600
            elif birim in ("dakika", "dk", "min", "m"):
                toplam += d * 60
            else:
                toplam += d
        return toplam if bulundu else None
    if ":" in s:
        try:
            parcalar = [float(p.replace(",", ".")) for p in s.split(":")]
        except ValueError:
            return None
        toplam = 0.0
        for p in parcalar:
            toplam = toplam * 60 + p
        return toplam
    return sayi_coz(s, tam_sayi=False)


def tarih_coz(ham):
    """Tarihi YYYY-AA-GG biçimine çevirir. Çözemezse (ham metin, False) döner."""
    if ham is None:
        return ("", True)
    if hasattr(ham, "strftime"):
        return (ham.strftime("%Y-%m-%d"), True)
    s = str(ham).strip()
    if not s:
        return ("", True)
    if re.fullmatch(r"\d{9,13}(\.\d+)?", s):
        # Sayı olarak verilmiş zaman (1970'ten beri saniye ya da milisaniye)
        import datetime
        t = float(s)
        t = t / 1000 if t > 1e11 else t
        return (datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d"), True)
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, a, g = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if m:
            # Eğik çizgili biçim Meta dışa aktarımında ay/gün/yıl gelir; ilk sayı 12'den büyükse gün/ay.
            a, g, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if a > 12:
                a, g = g, a
        else:
            m = re.match(r"(\d{1,2})[.\-](\d{1,2})[.\-](\d{4})", s)
            if m:
                g, a, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                sd = sade(s)
                m1 = re.match(r"([a-z]+) (\d{1,2}) (\d{4})", sd)
                m2 = re.match(r"(\d{1,2}) ([a-z]+) (\d{4})", sd)
                if m1 and m1.group(1) in AYLAR:
                    a, g, y = AYLAR[m1.group(1)], int(m1.group(2)), int(m1.group(3))
                elif m2 and m2.group(2) in AYLAR:
                    g, a, y = int(m2.group(1)), AYLAR[m2.group(2)], int(m2.group(3))
                else:
                    return (s, False)
    if not (1 <= a <= 12 and 1 <= g <= 31):
        return (s, False)
    return (f"{y:04d}-{a:02d}-{g:02d}", True)


def an_coz(ham):
    """Yayın anını saat bilgisiyle çözer (UTC). Yalnız gün biliniyorsa o günün başı alınır. Çözemezse None."""
    if ham is None:
        return None
    s = str(ham).strip()
    try:
        if re.fullmatch(r"\d{9,13}(\.\d+)?", s):
            t = float(s)
            return datetime.datetime.fromtimestamp(t / 1000 if t > 1e11 else t, datetime.timezone.utc)
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", s)
        if m:
            return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                     int(m.group(4) or 0), int(m.group(5) or 0), tzinfo=datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    return None


def link_coz(link):
    """Linkten (platform, video kimliği, sade link) çıkarır."""
    if not link:
        return (None, None, None)
    l = str(link).strip()
    kisa = re.sub(r"^https?://(www\.|m\.)?", "", l.split("?")[0].split("#")[0]).rstrip("/").lower()
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reels?|p|tv)/([A-Za-z0-9_-]+)", l)
    if m:
        return ("instagram", m.group(1), kisa)
    m = re.search(r"tiktok\.com/.*?/video/(\d+)", l)
    if m:
        return ("tiktok", m.group(1), kisa)
    if "tiktok.com" in l:
        return ("tiktok", None, kisa)
    m = re.search(r"(?:youtube\.com/(?:shorts/|watch\?v=|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,})", l)
    if m:
        return ("youtube", m.group(1), "youtube/" + m.group(1).lower())
    if "youtube.com" in l or "youtu.be" in l:
        return ("youtube", None, kisa)
    return (None, None, kisa)


def platform_coz(deger):
    s = sade(deger)
    if not s:
        return None
    if "insta" in s or s in ("ig", "reels", "reel", "ig reel") or s.startswith("ig "):
        return "instagram"
    if "tiktok" in s or s == "tt":
        return "tiktok"
    if "youtube" in s or "short" in s or s == "yt":
        return "youtube"
    if "facebook" in s or s.startswith("fb"):
        return "facebook"
    return s


def satirlari_oku(yol):
    """Dosyayı satır listesi olarak okur (her satır hücre listesi)."""
    if not os.path.isfile(yol):
        hata(f"Dosya bulunamadı: {yol}. Yolu kontrol et.")
    uzanti = os.path.splitext(yol)[1].lower()
    if uzanti in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            hata(f"{os.path.basename(yol)} bir Excel dosyası ve bu ortamda Excel okuyucu yok. "
                 "Dosyayı CSV olarak dışa aktar, sonra yeniden dene.")
        kitap = openpyxl.load_workbook(yol, read_only=True, data_only=True)
        sayfa = kitap.worksheets[0]
        return [list(s) for s in sayfa.iter_rows(values_only=True)]
    if uzanti == ".xls":
        hata(f"{os.path.basename(yol)} eski Excel biçiminde. CSV olarak dışa aktar, sonra yeniden dene.")
    with open(yol, "rb") as f:
        ham = f.read()
    metin = None
    if ham[:2] in (b"\xff\xfe", b"\xfe\xff"):
        denenecek = ["utf-16"]
    else:
        denenecek = ["utf-8-sig", "cp1254"]
    for kod in denenecek:
        try:
            metin = ham.decode(kod)
            break
        except UnicodeDecodeError:
            continue
    if metin is None:
        hata(f"{os.path.basename(yol)} okunamadı. Dosyayı UTF-8 CSV olarak yeniden kaydet.")
    satirlar = metin.splitlines()
    while satirlar and (not satirlar[0].strip() or satirlar[0].lower().startswith("sep=")):
        satirlar.pop(0)
    if not satirlar:
        hata(f"{os.path.basename(yol)} boş görünüyor.")
    ornek = "\n".join(satirlar[:5])
    ayrac = max([",", ";", "\t", "|"], key=lambda a: ornek.count(a))
    return list(csv.reader(io.StringIO("\n".join(satirlar)), delimiter=ayrac))


def tabloyu_oku(yol):
    """Başlık satırını bulur. (başlıklar, veri satırları) döner."""
    satirlar = satirlari_oku(yol)
    en_iyi, en_iyi_sayi = 0, -1
    for i, satir in enumerate(satirlar[:15]):
        n = sum(1 for h in satir if h is not None and alan_bul(h)[0])
        if n > en_iyi_sayi:
            en_iyi, en_iyi_sayi = i, n
    basliklar = [str(h).strip() if h is not None else "" for h in satirlar[en_iyi]]
    veri = [s for s in satirlar[en_iyi + 1:] if any(str(h).strip() for h in s if h is not None)]
    return basliklar, veri, en_iyi_sayi


def json_mu(yol):
    if os.path.splitext(yol)[1].lower() == ".json":
        return True
    try:
        with open(yol, "rb") as f:
            return f.read(64).lstrip(b"\xef\xbb\xbf \t\r\n")[:1] in (b"{", b"[")
    except OSError:
        return False


DESTEKLENMEYEN = ("Bu dosya biçimi desteklenmiyor; YouTube için YouTube Studio'dan, TikTok için TikTok Studio'dan "
                  "CSV indir.")


def json_tablo(yol):
    """Instagram sahip verisi JSON'unu (reels listesi) (başlıklar, satırlar, tanınan sütun sayısı, platform)
    biçimine çevirir. Desteklenen tek JSON biçimi budur; başka JSON verilirse hata verir."""
    ad = os.path.basename(yol)
    if not os.path.isfile(yol):
        hata(f"Dosya bulunamadı: {yol}. Yolu kontrol et.")
    try:
        with open(yol, encoding="utf-8-sig") as f:
            veri = json.load(f)
    except (ValueError, UnicodeDecodeError):
        hata(f"{ad} geçerli bir JSON değil. Araç çıktısını eksiksiz, olduğu gibi dosyaya yapıştır.")
    liste = veri.get("reels") if isinstance(veri, dict) else veri
    if not isinstance(liste, list) or not liste or not all(isinstance(x, dict) for x in liste) \
            or not any("shortcode" in x for x in liste):
        hata(f"{ad}: {DESTEKLENMEYEN}")
    basliklar = list(dict.fromkeys(k for x in liste for k, v in x.items() if not isinstance(v, (dict, list))))
    satirlar = [[x.get(k) if not isinstance(x.get(k), (dict, list)) else None for k in basliklar] for x in liste]
    taninan = sum(1 for b in basliklar if alan_bul(b)[0])
    return basliklar, satirlar, taninan, "instagram"


def kaynak_oku(yol, uyarilar, taninmayan):
    """Bir kaynağı okur, satırları ortak alanlara çevirir."""
    ad = os.path.basename(yol)
    json_ipucu = None
    if json_mu(yol):
        basliklar, veri, taninan_sayi, json_ipucu = json_tablo(yol)
    else:
        basliklar, veri, taninan_sayi = tabloyu_oku(yol)
    if taninan_sayi < 2:
        hata(f"{ad} dosyasında tanıdığım sütun bulamadım. İlk satırda sütun adları olmalı "
             "(örnek: baslik, goruntuleme, erisim, paylasim). Sütun adlarını kontrol et.")
    # Bir alana birden çok sütun düşebilir (ör. Title ve Description, ya da playCount ve views).
    # Hepsi öncelik sırasıyla tutulur; satırda ilk dolu olan kullanılır.
    adaylar = {}
    for i, b in enumerate(basliklar):
        alan, sira = alan_bul(b)
        if alan is None:
            if b:
                taninmayan.setdefault(ad, []).append(b)
            continue
        adaylar.setdefault(alan, []).append((sira, i))
    esleme = {alan: [i for _, i in sorted(liste)] for alan, liste in adaylar.items()}
    sade_basliklar = {sade(b) for b in basliklar}
    # Dosyanın genel platform ipucu (satırda platform ya da link yoksa kullanılır).
    ipucu = None
    if {"content", "video title"} <= sade_basliklar or {"icerik", "video basligi"} <= sade_basliklar \
            or "average view duration" in sade_basliklar \
            or "ortalama goruntuleme suresi" in sade_basliklar:
        ipucu = "youtube"
    elif "total play time" in sade_basliklar or "toplam oynatma suresi" in sade_basliklar:
        ipucu = "tiktok"
    elif "accounts reached" in sade_basliklar or "permalink" in sade_basliklar:
        ipucu = "instagram"
    ipucu = json_ipucu or ipucu
    # Yalnız etiket taşıyan dosya (video_id, etiket): yeni video yaratmaz, var olanın etiketini doldurur.
    yalniz_etiket = "etiket" in esleme and not any(
        a in esleme for a in SAYI_ALANLARI + ONDALIK_ALANLARI + SURE_ALANLARI)
    if "gosterim" in esleme and "erisim" not in esleme:
        uyarilar.append(f"{ad}: Gösterim sütunu erişim yerine kullanılmadı, çünkü gösterim kişi sayısı "
                        "değildir. Gönderme oranı bu dosyada görüntülemeye bölünerek hesaplandı.")
    kayitlar = []
    for satir in veri:
        def al(alan):
            for i in esleme.get(alan, []):
                if i >= len(satir) or satir[i] is None:
                    continue
                d = satir[i]
                if isinstance(d, str):
                    d = d.strip()
                    if not d:
                        continue
                return d
            return None
        k = {"kaynak": ad, "yalniz_etiket": yalniz_etiket}
        kimlik = al("video_id")
        if isinstance(kimlik, float) and kimlik.is_integer():
            kimlik = int(kimlik)
        kimlik = str(kimlik).strip() if kimlik is not None else None
        if kimlik and sade(kimlik) in ("total", "toplam", "totals", "genel toplam"):
            continue
        baslik = al("baslik")
        k["baslik"] = re.sub(r"\s+", " ", str(baslik)).strip() if baslik is not None else None
        if k["baslik"] and sade(k["baslik"]) in ("total", "toplam") and not kimlik:
            continue
        k["link"] = str(al("link")) if al("link") else None
        lp, lk, lsade = link_coz(k["link"])
        k["link_sade"] = lsade
        k["kimlikler"] = [x for x in (kimlik, lk) if x]
        k["video_id"] = lk or kimlik
        k["platform"] = platform_coz(al("platform")) or lp or platform_coz(al("tur")) or ipucu
        tarih, tamam = tarih_coz(al("yayin_tarihi"))
        k["yayin_tarihi"] = tarih or None
        k["yayin_ani"] = an_coz(al("yayin_tarihi")) or an_coz(tarih)
        if not tamam:
            uyarilar.append(f"{ad}: '{tarih}' tarihi çözülemedi, olduğu gibi bırakıldı.")
        for alan in SAYI_ALANLARI:
            k[alan] = sayi_coz(al(alan), tam_sayi=True)
        for alan in ONDALIK_ALANLARI:
            k[alan] = sayi_coz(al(alan), tam_sayi=False)
        for alan in SURE_ALANLARI:
            k[alan] = sure_coz(al(alan))
        for alan in SAYI_ALANLARI + ONDALIK_ALANLARI + SURE_ALANLARI:
            if k[alan] is None and al(alan) is not None and str(al(alan)).strip().lower() not in BOS_DEGERLER:
                uyarilar.append(f"{ad}: '{al(alan)}' değeri ({alan}) sayıya çevrilemedi, boş sayıldı.")
        k["etiket"] = str(al("etiket")) if al("etiket") else None
        if k["ort_izleme_sn"] is None and k.get("ort_izleme_ms") is not None:
            k["ort_izleme_sn"] = k["ort_izleme_ms"] / 1000
        d = al("deneme")
        k["deneme"] = d is True or sade(d) in ("true", "evet", "1", "dogru", "deneme")
        if not k["video_id"] and not k["baslik"]:
            continue
        kayitlar.append(k)
    # Platformu belli olmayan satır, dosyadaki diğer satırların ortak platformunu alır.
    gorulen_platformlar = {k["platform"] for k in kayitlar if k["platform"]}
    if len(gorulen_platformlar) == 1:
        for k in kayitlar:
            k["platform"] = k["platform"] or next(iter(gorulen_platformlar))
    # Oran sütunu 0 ile 1 arasında verilmişse yüzdeye çevir.
    for alan in ("kaydirma_orani", "izlemeyi_secen", "izleme_yuzdesi"):
        degerler = [k[alan] for k in kayitlar if k[alan] is not None]
        if degerler and max(degerler) <= 1.0:
            for k in kayitlar:
                if k[alan] is not None:
                    k[alan] *= 100
            uyarilar.append(f"{ad}: {alan} sütunu 0 ile 1 arasında geldi, yüzdeye çevrildi.")
    return kayitlar


def birlestir(kayitlar, uyarilar):
    """Aynı videoyu (kimlik ya da link ile) tek kayıtta toplar. Dolu alan boş alanı tamamlar."""
    ata = list(range(len(kayitlar)))

    def kok(i):
        while ata[i] != i:
            ata[i] = ata[ata[i]]
            i = ata[i]
        return i

    gorulen = {}
    for i, k in enumerate(kayitlar):
        anahtarlar = ["id:" + x for x in k["kimlikler"]]
        if k["link_sade"]:
            anahtarlar.append("link:" + k["link_sade"])
        if not anahtarlar:
            anahtarlar.append("ad:" + sade(k["baslik"]) + "|" + (k["yayin_tarihi"] or ""))
        for a in anahtarlar:
            if a in gorulen:
                ata[kok(i)] = kok(gorulen[a])
            else:
                gorulen[a] = i
    gruplar = {}
    for i in range(len(kayitlar)):
        gruplar.setdefault(kok(i), []).append(i)
    sonuc, es_kimlikler, farklar = [], {}, {}
    alanlar = ["baslik", "platform", "yayin_tarihi", "yayin_ani", "etiket", "link"] + SAYI_ALANLARI + ONDALIK_ALANLARI + SURE_ALANLARI
    for _, uyeler in sorted(gruplar.items(), key=lambda g: min(g[1])):
        ilk = dict(kayitlar[uyeler[0]])
        ilk["kaynaklar"] = [ilk["kaynak"]]
        tum_kimlik = list(ilk["kimlikler"])
        for j in uyeler[1:]:
            d = kayitlar[j]
            if d["kaynak"] not in ilk["kaynaklar"]:
                ilk["kaynaklar"].append(d["kaynak"])
            tum_kimlik += [x for x in d["kimlikler"] if x not in tum_kimlik]
            for alan in alanlar:
                if ilk.get(alan) is None:
                    ilk[alan] = d.get(alan)
                elif d.get(alan) is not None and alan in SAYI_ALANLARI + SURE_ALANLARI:
                    a, b = ilk[alan], d[alan]
                    if abs(a - b) > max(1.0, 0.01 * max(abs(a), abs(b))):
                        farklar.setdefault((alan, ilk["kaynak"], d["kaynak"]), []).append(
                            f"{ilk.get('baslik') or ilk.get('video_id')}: {tr_sayi(a, 0 if a == int(a) else 1)} ve "
                            f"{tr_sayi(b, 0 if b == int(b) else 1)}")
            ilk["deneme"] = bool(ilk.get("deneme") or d.get("deneme"))
            if not ilk.get("video_id"):
                ilk["video_id"] = d.get("video_id")
        # Linkten çıkan kimlik varsa o kullanılır; kaynaklar arasında ortak olan odur.
        link_kimligi = link_coz(ilk.get("link"))[1]
        if link_kimligi:
            ilk["video_id"] = link_kimligi
        if not ilk.get("video_id"):
            ilk["video_id"] = "video_" + str(len(sonuc) + 1)
        for x in tum_kimlik:
            if x != ilk["video_id"]:
                es_kimlikler[x] = ilk["video_id"]
        sonuc.append(ilk)
    # Aynı alanın iki kaynakta farklı çıktığı videolar tek uyarıda toplanır.
    for (alan, k1, k2), ornekler in farklar.items():
        uyarilar.append(f"{alan} değeri {len(ornekler)} videoda iki kaynakta farklı ({k1} ve {k2}); ilk verilen "
                        f"dosyadaki ({k1}) kullanıldı. Örnek: {ornekler[0]}.")
    return sonuc, es_kimlikler


def ortanca(degerler):
    d = sorted(x for x in degerler if x is not None)
    if not d:
        return None
    n = len(d)
    return d[n // 2] if n % 2 else (d[n // 2 - 1] + d[n // 2]) / 2


def yuzdelik(degerler, p):
    """Doğrusal ara değerli yüzdelik (p 0 ile 1 arası)."""
    d = sorted(degerler)
    if not d:
        return None
    konum = (len(d) - 1) * p
    alt = int(konum)
    ust = min(alt + 1, len(d) - 1)
    return d[alt] + (d[ust] - d[alt]) * (konum - alt)


def hesapla(videolar, uyarilar, simdi):
    """Oranları, ortanca katını, bandı ve işaretleri yazar. Platform özetlerini döner."""
    for v in videolar:
        v["platform"] = v.get("platform") or "bilinmiyor"
        v["isaretler"] = []
        if v.get("ort_izleme_sn") is None and v.get("goruntuleme"):
            toplam = v.get("toplam_izleme_sn")
            if toplam is None and v.get("toplam_izleme_saat") is not None:
                toplam = v["toplam_izleme_saat"] * 3600
            if toplam is not None:
                v["ort_izleme_sn"] = toplam / v["goruntuleme"]
        payda = v.get("erisim")
        if not payda and v.get("goruntuleme"):
            payda = v["goruntuleme"]
            v["isaretler"].append("erisim_yok_goruntuleme_kullanildi")
        v["gonderme_orani"] = (v["paylasim"] / payda * 100) if (payda and v.get("paylasim") is not None) else None
        v["begeni_orani"] = (v["begeni"] / payda * 100) if (payda and v.get("begeni") is not None) else None
        if v.get("deneme"):
            v["isaretler"].append("deneme")
        # Yayından 48 saatten az geçmiş video: sayılar henüz oturmamış olabilir, ortancalara katılmaz.
        v["yeni"] = bool(v.get("yayin_ani") and datetime.timedelta(0) <= simdi - v["yayin_ani"] < datetime.timedelta(hours=48))
        if v["yeni"]:
            v["isaretler"].append("yeni")
        if not v.get("sure_sn") and v.get("ort_izleme_sn") and v.get("izleme_yuzdesi"):
            # Süre verilmemişse ortalama izleme süresi ile izleme yüzdesinden tahmin edilir.
            v["sure_sn"] = round(v["ort_izleme_sn"] / v["izleme_yuzdesi"] * 100)
            v["isaretler"].append("sure_tahmini")
        elif v.get("ort_izleme_sn") is not None and v.get("sure_sn") and v.get("izleme_yuzdesi") is None:
            v["izleme_yuzdesi"] = v["ort_izleme_sn"] / v["sure_sn"] * 100
        # Kaynak izleme yüzdesini kendisi verdiyse o değer korunur.
        # İzlemeye devam oranı: Studio yüzdeyi kendisi verdiyse o; vermediyse etkileşimli görüntüleme / görüntüleme.
        if v.get("izlemeyi_secen") is not None:
            v["devam_orani"] = v["izlemeyi_secen"]
        else:
            v["devam_orani"] = (v["devam_goruntuleme"] / v["goruntuleme"] * 100) \
                if (v.get("devam_goruntuleme") is not None and v.get("goruntuleme")) else None
    platformlar = {}
    for p in sorted({v["platform"] for v in videolar}):
        hepsi = [v for v in videolar if v["platform"] == p]
        # Deneme Reels yalnız takipçi olmayanlara gösterilir; ortanca ve çeyrek hesabına girmez, bant almaz.
        # Yeni videolar (48 saatten az) da ortancaya girmez ama hesabın eşikleriyle kıyaslanır.
        kiyaslanan = [v for v in hepsi if not v.get("deneme")]
        grup = [v for v in kiyaslanan if not v.get("yeni")]
        for v in hepsi:
            if v.get("deneme"):
                v["ortanca_kati"], v["bant"] = None, ""
                if v.get("paylasim") is not None and v["paylasim"] < 10:
                    v["isaretler"].append("az_sayi")
        ort = {a: ortanca([v.get(a) for v in grup])
               for a in ("goruntuleme", "gonderme_orani", "kaydirma_orani", "izleme_yuzdesi", "devam_orani")}
        oranlar = [v["gonderme_orani"] for v in grup if v["gonderme_orani"] is not None]
        sayili = [v for v in grup if v.get("paylasim") is not None]
        az = [v for v in sayili if v["paylasim"] < 10]
        if sayili and len(az) > 0.8 * len(sayili):
            # Gönderme sayıları çok küçükse oranlar tek bir göndermeyle oynar; bant hesaplanmaz.
            yontem, esikler = "yok_az_sayi", {}
            uyarilar.append(f"{p}: Bu platformda gönderme sayıları bant çıkaracak kadar büyük değil; "
                            "izlemeye devam oranı ve izleme yüzdesine bakın.")
        elif len(oranlar) >= 8:
            yontem = "hesap_ceyrekleri"
            c1, c2, c3 = yuzdelik(oranlar, 0.25), yuzdelik(oranlar, 0.5), yuzdelik(oranlar, 0.75)
            esikler = {"alt_ceyrek": round(c1, 3), "ortanca": round(c2, 3), "ust_ceyrek": round(c3, 3)}
        else:
            yontem = "varsayilan"
            esikler = {"zayif_ustu": 0.3, "orta_ustu": 0.6, "iyi_ustu": 1.5}
        # Ortancaya dayanan işaretler 4 videodan azında anlam taşımaz, konmaz.
        yeterli = len(grup) >= 4
        if not yeterli:
            uyarilar.append(f"{p}: yalnız {len(grup)} video var. Ortancaya dayanan işaretler "
                            "(aykırı, kanca sorunu, tutma sorunu) 4 videodan azında konmadı.")
        for v in kiyaslanan:
            v["ortanca_kati"] = (v["goruntuleme"] / ort["goruntuleme"]) \
                if (v.get("goruntuleme") is not None and ort["goruntuleme"]) else None
            o = v["gonderme_orani"]
            if o is None:
                v["bant"] = ""
            elif yontem == "yok_az_sayi":
                v["bant"] = "az_sayi"
            elif yontem == "hesap_ceyrekleri":
                v["bant"] = "zayif" if (o < c1 or o == 0) else "orta_alti" if o < c2 else "orta_ustu" if o < c3 else "guclu"
            else:
                v["bant"] = "zayif" if o < 0.3 else "orta" if o < 0.6 else "iyi" if o <= 1.5 else "cok_iyi"
            if yeterli and v["ortanca_kati"] is not None and v["ortanca_kati"] >= 3:
                v["isaretler"].append("aykiri_yuksek")
                # Geniş dağıtımda gönderme / görüntüleme oranı seyrelir; sıra dışı video oran bandına sokulmaz.
                if v["bant"]:
                    v["bant"] = "sira_disi"
            # Yeni videonun görüntülemesi hâlâ birikiyor; "aykırı düşük" denmez.
            if yeterli and not v.get("yeni") and v["ortanca_kati"] is not None and v["ortanca_kati"] <= 0.4:
                v["isaretler"].append("aykiri_dusuk")
            if yeterli and v.get("kaydirma_orani") is not None and ort["kaydirma_orani"] is not None \
                    and v["kaydirma_orani"] >= ort["kaydirma_orani"] + 5:
                v["isaretler"].append("kanca_sorunu")
            # Kaydırma oranı olmayan platformda (YouTube) izlemeye devam oranına bakılır: ortancanın 10 puan altı.
            if yeterli and v.get("kaydirma_orani") is None and v.get("devam_orani") is not None \
                    and ort["devam_orani"] is not None and v["devam_orani"] <= ort["devam_orani"] - 10:
                v["isaretler"].append("kanca_sorunu")
            if yeterli and v.get("izleme_yuzdesi") is not None and ort["izleme_yuzdesi"] is not None \
                    and v["izleme_yuzdesi"] <= ort["izleme_yuzdesi"] - 5:
                v["isaretler"].append("tutma_sorunu")
            if v["bant"] == "zayif":
                v["isaretler"].append("gonderilmiyor")
            if v.get("paylasim") is not None and v["paylasim"] < 10:
                v["isaretler"].append("az_sayi")
            for alan in ("goruntuleme", "paylasim", "sure_sn", "ort_izleme_sn", "kaydirma_orani"):
                if alan == "kaydirma_orani" and v.get("devam_orani") is not None:
                    continue
                if v.get(alan) is None:
                    v["isaretler"].append("eksik_veri:" + alan)
        platformlar[p] = {
            "video_sayisi": len(hepsi),
            "deneme_sayisi": len(hepsi) - len(kiyaslanan),
            "yeni_sayisi": len(kiyaslanan) - len(grup),
            "bant_yontemi": yontem,
            "bant_esikleri": esikler,
            "ortancalar": {a: (round(x, 2) if x is not None else None) for a, x in ort.items()},
        }
        if yontem == "varsayilan":
            uyarilar.append(f"{p}: gönderme oranı hesaplanabilen {len(oranlar)} video var, 8'den az. "
                            "Bant için hesabın kendi dağılımı yerine varsayılan eşikler kullanıldı.")
    return platformlar


PLATFORM_ADI = {"instagram": "Instagram", "youtube": "YouTube", "tiktok": "TikTok", "facebook": "Facebook"}


def kisa_ad(v, uzunluk=40):
    ad = v.get("baslik") or v.get("video_id") or ""
    return ad if len(ad) <= uzunluk else ad[:uzunluk - 3].rstrip() + "..."


def yuzde(x, ondalik=2):
    return "%" + tr_sayi(x, ondalik)


def desenleri_bul(videolar, uyarilar):
    """Yalnız veriyle desteklenen desenleri döner. En az 3 videoya dayanmayan desen yazılmaz."""
    desenler = []
    etiketsiz_platformlar = []
    platform_listesi = sorted({v["platform"] for v in videolar})
    for p in platform_listesi:
        grup = [v for v in videolar if v["platform"] == p and not v.get("deneme") and not v.get("yeni")]
        on = (p + ": ") if len(platform_listesi) > 1 else ""

        # 1) Süre ilişkisi: videolar hesabın kendi süre ortancasından ikiye bölünür (sabit eşik yok).
        #    Hem kaydırma oranına hem izleme yüzdesine bakılır. Her grupta en az 3 video şarttır.
        #    Süresi tahmin edilmiş videolar (sure_tahmini) bu desene girmez: süre izleme yüzdesinden
        #    türetildiği için desen kendi kendini doğrular.
        sureli = [v for v in grup if "sure_tahmini" not in v["isaretler"]]
        tahminli = len(grup) - len(sureli)
        esik = ortanca([v.get("sure_sn") for v in sureli])
        if tahminli and len([v for v in sureli if v.get("sure_sn") is not None]) < 6:
            ad_p = "YouTube" if p == "youtube" else p
            uyarilar.append(f"{ad_p} süreleri çıktıda yok; süre deseni için videoların sürelerini ekle "
                            "(ör. video_incele çıktısı ya da elle.csv).")
        for alan, tur, ad, dusuk_iyi in (("kaydirma_orani", "sure_kaydirma", "kaydırma oranı", True),
                                         ("izleme_yuzdesi", "sure_izleme", "izleme yüzdesi", False)):
            if esik is None:
                break
            olculen = [v for v in sureli if v.get("sure_sn") is not None and v.get(alan) is not None]
            kisa = [v for v in olculen if v["sure_sn"] <= esik]
            uzun = [v for v in olculen if v["sure_sn"] > esik]
            if len(kisa) < 3 or len(uzun) < 3:
                continue
            ok, ou = ortanca([v[alan] for v in kisa]), ortanca([v[alan] for v in uzun])
            if abs(ok - ou) < 5:
                continue
            kisa_iyi = (ok < ou) if dusuk_iyi else (ok > ou)
            kim = "Kısa" if kisa_iyi else "Uzun"
            sonuc = ("daha az kaydırılıyor" if dusuk_iyi else "daha yüksek oranda izleniyor")
            desenler.append({
                "desen": f"{on}{kim} videolar {sonuc}",
                "kanit": (f"Hesabın süre ortancası {tr_sayi(esik, 0 if esik == int(esik) else 1)} saniye. "
                          f"Bu süre ve altındaki {len(kisa)} videoda {ad} ortancası {yuzde(ok, 1)}; "
                          f"daha uzun {len(uzun)} videoda {yuzde(ou, 1)}. Fark {tr_sayi(abs(ok - ou), 1)} puan."),
                "video_sayisi": len(kisa) + len(uzun),
                "tur": tur, "platform": p, "esik_sn": esik, "yon": "kisa_iyi" if kisa_iyi else "uzun_iyi",
            })

        # 2) Konu grupları arasında gönderme oranı farkı. Yalnız "etiket" sütunu varsa bakılır;
        #    başlığın ilk kelimesinden konu çıkarılmaz. Etiketi boş videolar "etiketsiz" grubudur.
        oranli = [v for v in grup if v.get("gonderme_orani") is not None]
        if any(v.get("etiket") for v in grup):
            kume = {}
            for v in oranli:
                gorunen = (v.get("etiket") or "").strip() or "etiketsiz"
                kume.setdefault(sade(gorunen) or "etiketsiz", {"ad": gorunen, "videolar": []})["videolar"].append(v)
            bos = sum(1 for v in grup if not v.get("etiket"))
            if bos:
                uyarilar.append(f"{on}{bos} videonun etiketi boş; bu videolar \"etiketsiz\" grubu sayıldı.")
            for anahtar, k in sorted(kume.items()):
                icinde = k["videolar"]
                disinda = [v for v in oranli if v not in icinde]
                if len(icinde) < 3 or len(disinda) < 3:
                    continue
                oi, od = ortanca([v["gonderme_orani"] for v in icinde]), ortanca([v["gonderme_orani"] for v in disinda])
                if od <= 0 and oi <= 0:
                    continue
                if oi >= od * 1.5 or oi <= od / 1.5:
                    yon = "daha çok" if oi > od else "daha az"
                    liste = ", ".join(f"{kisa_ad(v, 30)} {yuzde(v['gonderme_orani'])}" for v in icinde)
                    az = sum(1 for v in icinde if "az_sayi" in v["isaretler"])
                    az_notu = f" Bu gruptaki {az} videoda gönderme sayısı 10'un altında, oranları oynak." if az else ""
                    desenler.append({
                        "desen": f"{on}\"{k['ad']}\" etiketli videolar {yon} gönderiliyor",
                        "kanit": (f"Bu gruptaki {len(icinde)} videonun gönderme oranı ortancası {yuzde(oi)}; "
                                  f"kalan {len(disinda)} videonun ortancası {yuzde(od)}. Grup: {liste}.{az_notu}"),
                        "video_sayisi": len(icinde), "tur": "konu", "platform": p,
                    })
        else:
            etiketsiz_platformlar.append(p)

        # 3) En çok ve en az gönderilen 3 video. Gönderme sayısı 10'un altındaki videolar listede kalır,
        #    yanlarına not düşülür. Listeler karışmasın diye en az 6 video gerekir.
        if len(oranli) >= 6 and not any(v.get("bant") == "az_sayi" for v in grup):
            def dok(liste):
                return "; ".join(
                    f"{kisa_ad(v, 30)} {yuzde(v['gonderme_orani'])} "
                    f"({tr_sayi(v['paylasim'])} gönderme / {tr_sayi(v.get('erisim') or v.get('goruntuleme'))} "
                    f"{'erişim' if v.get('erisim') else 'görüntüleme'})"
                    + (" (gönderme sayısı az, oran oynak)" if "az_sayi" in v["isaretler"] else "")
                    + (" (sıra dışı video; geniş dağıtımda oran seyrelir)" if "aykiri_yuksek" in v["isaretler"] else "")
                    for v in liste)
            sirali = sorted(oranli, key=lambda v: v["gonderme_orani"], reverse=True)
            desenler.append({"desen": f"{on}en çok gönderilen 3 video (oran)", "kanit": dok(sirali[:3]) + ".", "video_sayisi": 3})
            sayica = sorted(oranli, key=lambda v: v["paylasim"], reverse=True)
            desenler.append({"desen": f"{on}en çok gönderilen 3 video (sayı)", "kanit": dok(sayica[:3]) + ".", "video_sayisi": 3})
            # Sıra dışı (ortancanın en az 3 katı görüntülenen) videolar "en az" listesine girmez: geniş dağıtımda
            # oran seyrelir, düşük oran zayıflık göstermez.
            olagan = [v for v in sirali if "aykiri_yuksek" not in v["isaretler"]]
            if len(olagan) >= 6:
                cikan = len(sirali) - len(olagan)
                ek = (f" Sıra dışı {cikan} video bu listeye alınmadı; geniş dağıtımda oran seyrelir." if cikan else "")
                desenler.append({"desen": f"{on}en az gönderilen 3 video", "kanit": dok(olagan[-3:][::-1]) + "." + ek,
                                 "video_sayisi": 3})
    # Etiket uyarısı platform bazlıdır; etiketi olan platform için uyarı çıkmaz.
    etiketli = [p for p in platform_listesi if p not in etiketsiz_platformlar]
    if etiketsiz_platformlar and not etiketli:
        uyarilar.append("Konuya göre desen için tabloya 'etiket' sütunu ekle (ör. gündem, tarih).")
    elif etiketsiz_platformlar:
        uyarilar.append(f"{', '.join(PLATFORM_ADI.get(p, p) for p in etiketsiz_platformlar)} videolarında etiket yok; "
                        f"konu desenine yalnız {', '.join(PLATFORM_ADI.get(p, p) for p in etiketli)} için bakıldı.")
    return [d for d in desenler if d["video_sayisi"] >= 3]


def rakip_oku(yol, uyarilar):
    basliklar, veri, _ = tabloyu_oku(yol)
    sutun = {}
    for i, b in enumerate(basliklar):
        alan, sira = alan_bul(b)
        if sade(b) == "video":
            alan, sira = "baslik", -1
        if alan in ("hesap", "baslik", "goruntuleme") and (alan not in sutun or sira < sutun[alan][0]):
            sutun[alan] = (sira, i)
    eksik = [a for a in ("hesap", "baslik", "goruntuleme") if a not in sutun]
    if eksik:
        hata(f"Rakip dosyasında şu sütunlar bulunamadı: {', '.join(eksik)}. "
             "Dosyada üç sütun olmalı: hesap, video, goruntuleme.")
    hesaplar = {}
    for s in veri:
        def al(a):
            i = sutun[a][1]
            return s[i] if i < len(s) else None
        g = sayi_coz(al("goruntuleme"), tam_sayi=True)
        if g is None or not al("hesap"):
            continue
        hesaplar.setdefault(str(al("hesap")).strip(), []).append((str(al("baslik") or "").strip(), g))
    sonuc = []
    for hesap, liste in hesaplar.items():
        o = ortanca([g for _, g in liste])
        az = len(liste) < 3
        if az:
            uyarilar.append(f"Rakip {hesap}: yalnız {len(liste)} video var. Ortanca güvenilir değil, aykırı işareti konmadı.")
        for video, g in liste:
            kat = g / o if o else None
            sonuc.append({"hesap": hesap, "video": video, "goruntuleme": int(g),
                          "ortanca_kati": round(kat, 2) if kat is not None else None,
                          "hesap_ortancasi": int(o) if o is not None else None,
                          "aykiri": bool(kat is not None and kat >= 3 and not az)})
    sonuc.sort(key=lambda r: (r["ortanca_kati"] or 0), reverse=True)
    return sonuc


def hucre(deger, ondalik=None):
    """tablo.csv hücresi: makine okur, bu yüzden ondalık ayraç noktadır."""
    if deger is None:
        return ""
    if ondalik is None:
        return str(deger)
    if ondalik == 0 or float(deger) == int(deger) and ondalik == -1:
        return str(int(round(deger)))
    return f"{deger:.{abs(ondalik)}f}"


def main():
    ap = argparse.ArgumentParser(description="Video sayılarını tek tabloda birleştirir.")
    ap.add_argument("girdiler", nargs="+", help="CSV ya da XLSX dosyaları")
    ap.add_argument("--cikti", required=True, help="Çıktı klasörü")
    ap.add_argument("--rakip", help="Rakip tablosu (hesap, video, goruntuleme)")
    ap.add_argument("--simdi", help="Şu an yerine kullanılacak zaman (ör. 2026-11-20T12:00). Verilmezse bilgisayarın saati. "
                                    "Yayından 48 saat geçmemiş videolar buna göre 'yeni' sayılır.")
    a = ap.parse_args()

    uyarilar, taninmayan, kayitlar = [], {}, []
    for yol in a.girdiler:
        kayitlar += kaynak_oku(yol, uyarilar, taninmayan)
    etiket_kayitlari = [k for k in kayitlar if k.get("yalniz_etiket")]
    kayitlar = [k for k in kayitlar if not k.get("yalniz_etiket")]
    if not kayitlar:
        hata("Dosyalarda video satırı bulunamadı. Başlık satırının altında en az bir video olmalı.")
    videolar, es_kimlikler = birlestir(kayitlar, uyarilar)
    if etiket_kayitlari:
        bul = {v["video_id"]: v for v in videolar}
        bul.update({eski: bul[yeni] for eski, yeni in es_kimlikler.items() if yeni in bul})
        eslesmeyen = []
        for k in etiket_kayitlari:
            hedef = next((bul[x] for x in k["kimlikler"] if x in bul), None)
            if hedef is None:
                eslesmeyen.append(k.get("video_id") or k.get("baslik") or "?")
            elif k.get("etiket"):
                hedef["etiket"] = k["etiket"]
        if eslesmeyen:
            uyarilar.append("Etiket dosyasındaki şu kimlikler hiçbir videoyla eşleşmedi, kullanılmadı: "
                            + ", ".join(eslesmeyen) + ". Kimliği tablodaki video_id ile aynı yaz.")
    simdi = an_coz(a.simdi) if a.simdi else datetime.datetime.now(datetime.timezone.utc)
    if simdi is None:
        hata("--simdi değeri okunamadı. Örnek: --simdi 2026-11-20T12:00")
    platformlar = hesapla(videolar, uyarilar, simdi)
    for v in videolar:
        if v.get("gonderme_orani") is None:
            uyarilar.append(f"'{kisa_ad(v)}' için gönderme oranı hesaplanamadı (gönderme sayısı ya da erişim eksik).")
    videolar.sort(key=lambda v: (v.get("yayin_tarihi") or ""), reverse=True)

    os.makedirs(a.cikti, exist_ok=True)
    tablo_yolu = os.path.join(a.cikti, "tablo.csv")
    with open(tablo_yolu, "w", newline="", encoding="utf-8") as f:
        y = csv.writer(f)
        y.writerow(TABLO_SUTUNLARI)
        for v in videolar:
            y.writerow([
                v["video_id"], v.get("baslik") or "", v["platform"], v.get("yayin_tarihi") or "",
                hucre(v.get("sure_sn"), -1), hucre(v.get("goruntuleme"), 0), hucre(v.get("erisim"), 0),
                hucre(v.get("begeni"), 0), hucre(v.get("yorum"), 0), hucre(v.get("paylasim"), 0),
                hucre(v.get("kaydetme"), 0), hucre(v.get("ort_izleme_sn"), 1), hucre(v.get("kaydirma_orani"), 1),
                hucre(v.get("izleme_yuzdesi"), 1), hucre(v.get("gonderme_orani"), 2), hucre(v.get("begeni_orani"), 2),
                hucre(v.get("ortanca_kati"), 2), v.get("bant") or "", ";".join(v["isaretler"]),
                hucre(v.get("devam_orani"), 1),
            ])

    # Üstteki bant_yontemi, bant hesaplanabilen platformlar içinde en çok videosu olana aittir.
    bantli = [p for p in platformlar if platformlar[p]["bant_yontemi"] != "yok_az_sayi"] or list(platformlar)
    buyuk = max(bantli, key=lambda p: platformlar[p]["video_sayisi"])
    if len({p["bant_yontemi"] for p in platformlar.values()}) > 1:
        uyarilar.append("Platformların bant yöntemi farklı. Üstteki bant_yontemi en çok videosu olan "
                        f"platforma ({buyuk}) aittir; diğerleri platformlar bölümünde.")
    desenler = desenleri_bul(videolar, uyarilar)
    ozet = {
        "platformlar": platformlar,
        "video_sayisi": len(videolar),
        "ortancalar": {alan: (round(x, 2) if x is not None else None) for alan, x in (
            (alan, ortanca([v.get(alan) for v in videolar if not v.get("deneme") and not v.get("yeni")]))
            for alan in ("goruntuleme", "gonderme_orani", "kaydirma_orani", "izleme_yuzdesi", "devam_orani"))},
        "bant_yontemi": platformlar[buyuk]["bant_yontemi"] if platformlar[buyuk]["bant_yontemi"] != "yok_az_sayi" else "varsayilan",
        "desenler": desenler,
        "rakip": rakip_oku(a.rakip, uyarilar) if a.rakip else [],
        "taninmayan_sutunlar": taninmayan,
        "uyarilar": uyarilar,
        "es_kimlikler": es_kimlikler,
    }
    with open(os.path.join(a.cikti, "ozet.json"), "w", encoding="utf-8") as f:
        json.dump(ozet, f, ensure_ascii=False, indent=2)

    print(f"{len(kayitlar)} satır okundu, {len(videolar)} video tabloya yazıldı.")
    print(f"Bant yöntemi: {'hesabın kendi çeyrekleri' if ozet['bant_yontemi'] == 'hesap_ceyrekleri' else 'varsayılan eşikler'}")
    for d in ozet["desenler"]:
        print(f"Desen: {d['desen']}. {d['kanit']}")
    aykirilar = [r for r in ozet["rakip"] if r["aykiri"]]
    for r in aykirilar:
        print(f"Rakip aykırı: {r['hesap']} · {r['video']} · {tr_sayi(r['goruntuleme'])} görüntüleme, "
              f"hesap ortancasının {tr_sayi(r['ortanca_kati'], 1)} katı")
    for dosya, sutunlar in taninmayan.items():
        print(f"Yok sayılan sütunlar ({dosya}): {', '.join(sutunlar)}")
    for u in uyarilar:
        print("Uyarı: " + u)
    print(f"Yazıldı: {tablo_yolu} ve {os.path.join(a.cikti, 'ozet.json')}")


if __name__ == "__main__":
    main()
