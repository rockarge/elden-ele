#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rapor.py · Elden Ele

Ne yapar : Birleşik tabloyu, video incelemelerini ve (varsa) tutma grafiği noktalarını okur;
           "hangi video, hangi saniyede, neden kaybetti" raporunu yazar. Her hüküm kanıtıyla
           yazılır, kanıtı olmayan hüküm rapora girmez.
Girdi    : veri_birlestir.py çıktısı (ozet.json, tablo.csv); isteğe bağlı video_incele.py çıktısı
           (inceleme.json, her biri için --video-id) ve tutma.json
           ({"VIDEO_ID":[{"sn":0,"yuzde":100},{"sn":3,"yuzde":62}]}).
Çıktı    : RAPOR_KLASORU/rapor.md ve tek dosya rapor.html. Görüntüler küçültülüp html içine
           gömülür (ffmpeg varsa 480 piksel genişlik). rapor.md için kopyaları gorseller/ altına
           yazılır. --ayri-gorsel verilirse html de gorseller/ klasörünü gösterir, gömmez.
           --okuma DOSYA.md verilirse içeriği "Claude'un okuması" başlığıyla raporun başına konur.
Örnek    : python3 rapor.py --ozet birlesik/ozet.json --tablo birlesik/tablo.csv \
             --inceleme inceleme/video1/inceleme.json --video-id DfsnVrysiXm \
             --tutma tutma.json --cikti rapor
Not      : Yalnız Python standart kütüphanesi kullanır. İnternete çıkmaz.
"""
import argparse
import base64
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
         "Kasım", "Aralık"]
BANT_ADI = {"zayif": "zayıf", "orta_alti": "ortanın altı", "orta_ustu": "ortanın üstü", "guclu": "güçlü",
            "orta": "orta", "iyi": "iyi", "cok_iyi": "çok iyi", "az_sayi": "az sayı", "sira_disi": "sıra dışı", "": "hesaplanamadı"}
ISARET_ADI = {
    "aykiri_yuksek": "Görüntüleme, hesabın ortadaki videosunun en az 3 katı",
    "aykiri_dusuk": "Görüntüleme, hesabın ortadaki videosunun 0,4 katı ya da altı",
    "kanca_sorunu": "İlk saniyeler zayıf: kaydırma oranı hesap ortancasının en az 5 puan üstünde",
    "tutma_sorunu": "İzleme yüzdesi hesap ortancasının en az 5 puan altında",
    "gonderilmiyor": "Gönderme oranı en alt bantta",
    "az_sayi": "Gönderme sayısı az, oran oynak",
    "yeni": "Yayından 48 saatten az geçmiş; sayılar henüz oturmamış olabilir, hesap ortancasına katılmadı",
    "deneme": "Deneme Reels, yalnız takipçi olmayanlara gösterildi; hesap ortancasına katılmadı",
    "sure_tahmini": "Süre verilmedi; ortalama izleme süresi ile izleme yüzdesinden tahmin edildi",
    "erisim_yok_goruntuleme_kullanildi": "Erişim yok, oranlar görüntülemeye bölünerek hesaplandı",
}
ALAN_ADI = {"goruntuleme": "görüntüleme", "erisim": "erişim", "paylasim": "gönderme sayısı",
            "sure_sn": "süre", "ort_izleme_sn": "ortalama izleme süresi", "kaydirma_orani": "kaydırma oranı"}
CAGRI_ADI = {"gonder": "gönder", "paylas": "paylaş", "yorum": "yorum", "takip": "takip", "abone": "abone",
             "link": "link", "kaydet": "kaydet", "soru_kapanis": "kapanış sorusu (yorum)"}
NEDEN_ADI = {"benzerlik_dusuk": "karede belirgin değişiklik var (yeni öğe ya da yazı girmiş olabilir)",
             "parlaklik_farki": "kareler arasında parlaklık değişiyor",
             "ilk_kare_bos_sonra_dolu": "ilk kare boş, ardından görüntü geliyor",
             "kesme_var": "ilk 3 saniyede sahne kesmesi var"}
HTML_HEDEFI = 590_000   # rapor.html için bayt hedefi (600 KB altı); gömülü görüntüler buna göre küçültülür


def uyari_sade(u):
    """Teknik uyarıyı okurun anlayacağı cümleye çevirir."""
    k = str(u).lower()
    if "whisper" in k or "metne dökülemedi" in k:
        return "Konuşma otomatik metne dökülemedi; altyazı (srt) verirsen soru ve çağrı saniyeleri de ölçülür."
    return str(u)


def okuma_bloklari(yol):
    """Basit markdown dosyasını rapor bloklarına çevirir: başlık, madde, paragraf (kalın yazı korunur)."""
    if not os.path.isfile(yol):
        hata(f"Okuma dosyası bulunamadı: {yol}. Yolu kontrol et.")
    with open(yol, encoding="utf-8-sig") as f:
        satirlar = f.read().splitlines()
    bloklar, maddeler, paragraf = [], [], []

    def bosalt():
        if maddeler:
            bloklar.append(("liste", (list(maddeler),)))
            maddeler.clear()
        if paragraf:
            bloklar.append(("p", (" ".join(paragraf),)))
            paragraf.clear()
    for ham in satirlar:
        satir = ham.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", satir)
        madde = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", satir)
        if not satir:
            bosalt()
        elif m:
            bosalt()
            bloklar.append(("h3", (m.group(2).strip(),)))
        elif madde:
            if paragraf:
                bosalt()
            maddeler.append(madde.group(1).strip())
        elif maddeler:
            maddeler[-1] += " " + satir
        else:
            paragraf.append(satir)
    bosalt()
    return bloklar


SAYISAL = ["sure_sn", "goruntuleme", "erisim", "begeni", "yorum", "paylasim", "kaydetme", "ort_izleme_sn",
           "kaydirma_orani", "izleme_yuzdesi", "gonderme_orani", "begeni_orani", "ortanca_kati", "devam_orani"]


def hata(mesaj):
    print("HATA: " + mesaj, file=sys.stderr)
    sys.exit(1)


def sade(metin):
    m = str(metin or "").replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    m = unicodedata.normalize("NFKD", m)
    m = "".join(c for c in m if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", m)).strip()


def sayi(deger, ondalik=0):
    """1234.5 -> 1.234,5"""
    if deger is None:
        return "yok"
    s = f"{deger:,.{ondalik}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def esnek(deger):
    """Tam sayıysa ondalıksız, değilse tek ondalıklı yazar."""
    if deger is None:
        return "yok"
    return sayi(deger, 0) if abs(deger - round(deger)) < 0.05 else sayi(deger, 1)


def yuzde(deger, ondalik=1):
    return "yok" if deger is None else "%" + sayi(deger, ondalik)


def saniye(deger):
    return "yok" if deger is None else esnek(deger) + " saniye"


def sirada(deger, ek="de"):
    """16 -> '16. saniyede'"""
    return f"{esnek(deger)}. saniye{ek}"


EKLER = {"0": ("dan", "a"), "1": ("den", "e"), "2": ("den", "ye"), "3": ("ten", "e"), "4": ("ten", "e"),
         "5": ("ten", "e"), "6": ("dan", "ya"), "7": ("den", "ye"), "8": ("den", "e"), "9": ("dan", "a")}
ONLUK = {"1": ("dan", "a"), "2": ("den", "ye"), "3": ("tan", "a"), "4": ("tan", "a"), "5": ("den", "ye"),
         "6": ("tan", "a"), "7": ("ten", "e"), "8": ("den", "e"), "9": ("dan", "a")}


def sayi_eki(yazi, hangi):
    """Sayının okunuşuna göre ek: hangi=0 '-den', hangi=1 '-e'. Örnek: %100'den, %60'a."""
    rakamlar = re.sub(r"[^0-9]", "", yazi)
    if not rakamlar:
        return ""
    if rakamlar[-1] != "0" or len(rakamlar) == 1:
        return EKLER[rakamlar[-1]][hangi]
    if rakamlar[-2] != "0":
        return ONLUK[rakamlar[-2]][hangi]
    return ("den", "e")[hangi]


def den_e(once, sonra):
    a, b = yuzde(once, 0), yuzde(sonra, 0)
    return f"{a}'{sayi_eki(a, 0)} {b}'{sayi_eki(b, 1)}"


def tarih(deger):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", deger or "")
    if not m:
        return deger or "yok"
    return f"{int(m.group(3))} {AYLAR[int(m.group(2)) - 1]} {m.group(1)}"


def json_oku(yol, ne):
    if not os.path.isfile(yol):
        hata(f"{ne} bulunamadı: {yol}. Yolu kontrol et.")
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, UnicodeDecodeError):
        hata(f"{ne} okunamadı: {yol}. Dosya geçerli bir JSON değil; betiği yeniden çalıştırıp dosyayı yeniden üret.")


def tablo_oku(yol):
    if not os.path.isfile(yol):
        hata(f"Tablo bulunamadı: {yol}. Önce veri_birlestir.py çalıştır.")
    with open(yol, encoding="utf-8-sig", newline="") as f:
        satirlar = list(csv.DictReader(f))
    if not satirlar or "video_id" not in satirlar[0]:
        hata(f"{yol} beklenen tablo değil. Bu dosya veri_birlestir.py çıktısı olan tablo.csv olmalı.")
    for s in satirlar:
        for alan in SAYISAL:
            try:
                s[alan] = float(s[alan]) if s.get(alan) not in (None, "") else None
            except ValueError:
                s[alan] = None
        s["isaretler"] = [x for x in (s.get("isaret") or "").split(";") if x]
    return satirlar


def kimlik_coz(verilen, videolar, es_kimlikler):
    """Kullanıcının verdiği kimliği tablodaki video_id ile eşler."""
    if verilen is None:
        return None
    v = str(verilen).strip()
    idler = {x["video_id"]: x["video_id"] for x in videolar}
    if v in idler:
        return v
    if v in es_kimlikler and es_kimlikler[v] in idler:
        return es_kimlikler[v]
    kucuk = {k.lower(): k for k in idler}
    if v.lower() in kucuk:
        return kucuk[v.lower()]
    aday = [x["video_id"] for x in videolar if sade(v) and sade(v) in sade(x.get("baslik"))]
    return aday[0] if len(aday) == 1 else None


def dosyadan_esle(inceleme, videolar):
    """--video-id verilmemişse dosya adındaki ilk kelimeyle başlık arasında tek eşleşme arar."""
    if len(videolar) == 1:
        return videolar[0]["video_id"]
    kelimeler = sade(os.path.splitext(str(inceleme.get("dosya") or ""))[0]).split()
    if not kelimeler:
        return None
    aday = [x["video_id"] for x in videolar if kelimeler[0] in sade(x.get("baslik")).split()]
    return aday[0] if len(aday) == 1 else None


def cumleler(metin):
    """Altyazı satırlarını cümlelere toplar: [{'bas','son','yazi'}]."""
    sonuc, parca = [], None
    for m in metin or []:
        yazi = str(m.get("yazi") or "").strip()
        if not yazi or m.get("bas") is None:
            continue
        son = m.get("son") if m.get("son") is not None else m["bas"]
        if parca is None:
            parca = {"bas": float(m["bas"]), "son": float(son), "yazi": yazi, "n": 1}
        else:
            parca["yazi"] += " " + yazi
            parca["son"] = float(son)
            parca["n"] += 1
        if re.search(r"[.?!…][\"')\]]*$", yazi) or parca["n"] >= 8:
            sonuc.append(parca)
            parca = None
    if parca:
        sonuc.append(parca)
    return sonuc


def kisalt(yazi, uzunluk=220):
    yazi = re.sub(r"\s+", " ", yazi or "").strip()
    return yazi if len(yazi) <= uzunluk else yazi[:uzunluk - 3].rstrip() + "..."


def andaki_cumle(cumle_listesi, t):
    """t saniyesinde söylenen cümle; tam o anda konuşma yoksa en yakın önceki (en çok 3 saniye geride)."""
    for c in cumle_listesi:
        if c["bas"] <= t <= c["son"]:
            return c
    onceki = [c for c in cumle_listesi if c["son"] < t and t - c["son"] <= 3]
    return onceki[-1] if onceki else None


def araliktaki_cumleler(cumle_listesi, a, b):
    return [c for c in cumle_listesi if c["bas"] < b and c["son"] > a]


def en_yakin_kare(inceleme, t):
    kareler = [k for k in (inceleme.get("kareler") or []) if k.get("sn") is not None and k.get("dosya")]
    if not kareler:
        return None
    return min(kareler, key=lambda k: abs(float(k["sn"]) - t))


def tutma_duzelt(noktalar):
    temiz = []
    for n in noktalar or []:
        try:
            temiz.append((float(n["sn"]), float(n["yuzde"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(temiz)


def tutma_degeri(noktalar, t):
    """Tutma eğrisinde t saniyesindeki yüzde (iki nokta arası doğrusal). Aralık dışında None."""
    if len(noktalar) < 2 or t < noktalar[0][0] or t > noktalar[-1][0]:
        return None
    for (s1, y1), (s2, y2) in zip(noktalar, noktalar[1:]):
        if s1 <= t <= s2:
            return y1 if s2 == s1 else y1 + (y2 - y1) * (t - s1) / (s2 - s1)
    return None


def dusus_bul(noktalar):
    """Komşu iki nokta arasındaki en büyük 3 kayıp. Çok sık noktalı eğri (ör. YouTube'un 100 noktası)
    önce yaklaşık 20 aralığa seyreltilir; yoksa her aralık bir iki saniye olur ve kayıplar anlamsız küçülür."""
    if len(noktalar) > 25:
        adim = -(-len(noktalar) // 20)
        seyrek = noktalar[::adim]
        if seyrek[-1] != noktalar[-1]:
            seyrek.append(noktalar[-1])
        noktalar = seyrek
    dususler = [{"bas": s1, "son": s2, "puan": y1 - y2, "once": y1, "sonra": y2}
                for (s1, y1), (s2, y2) in zip(noktalar, noktalar[1:]) if y1 - y2 > 0]
    return sorted(dususler, key=lambda d: d["puan"], reverse=True)[:3]


SEYRELME_NOTU = "Geniş dağıtımda oran seyrelir; bu videoyu gönderme sayısı ve kaydırma oranıyla değerlendir."
ALT_BANTLAR = ("zayif", "orta_alti", "orta")   # gönderme oranında en alt iki basamak (iki yöntemde de)


def cagri_ani(c):
    """Çağrının anı olarak çağrı cümlesinin başladığı saniye alınır."""
    t = c.get("sn") if c.get("sn") is not None else c.get("kelime_sn")
    return None if t is None else float(t)


def cagri_yeri(c):
    """'66,3. saniyede (kelime 68,8. saniyede)' biçiminde yazar."""
    yazi = sirada(cagri_ani(c))
    try:
        kelime = float(c.get("kelime_sn"))
    except (TypeError, ValueError):
        return yazi
    return yazi if abs(kelime - cagri_ani(c)) < 0.05 else f"{yazi} (kelime {sirada(kelime)})"


def gonder_cagrilari(inc):
    """Gönder ve paylaş çağrıları. Kapanış sorusu (soru_kapanis) yorum çağrısıdır, buraya girmez."""
    return sorted((c for c in (inc.get("cagrilar") or [])
                   if c.get("tur") in ("gonder", "paylas") and cagri_ani(c) is not None), key=cagri_ani)


def altyazi_eksigi(inc):
    """Altyazının videonun sonunda kapsamadığı süre (saniye). Bilgi yoksa 0."""
    try:
        return float((inc.get("altyazi_kapsami") or {}).get("eksik_son_sn") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def hukumler(v, inc, tutma, ortancalar, sure_desenleri=None):
    """Hüküm listesi: her biri {'ad', 'hukum', 'kanit', 'oneri'}. Kanıtı olmayan hüküm üretilmez."""
    sonuc = []
    # Sıra dışı (ortancanın en az 3 katı görüntülenen) videoya olumsuz hüküm yazılmaz; ölçümler bilgi olarak kalır.
    if "aykiri_yuksek" in v.get("isaretler", []):
        return sonuc
    sure = (inc or {}).get("sure_sn") or v.get("sure_sn")
    ort = v.get("ort_izleme_sn")
    kaydirma = v.get("kaydirma_orani")
    ort_kaydirma = ortancalar.get("kaydirma_orani")
    if inc:
        metin_var = bool(inc.get("metin")) and inc.get("metin_kaynagi") != "yok"
        cl = cumleler(inc.get("metin"))
        soru = inc.get("ilk_soru_sn")
        ilk3 = str(inc.get("ilk_3sn_metin") or "").strip()
        # İlk sorunun saniyesi tek başına hüküm değildir (bilgi satırı olarak "Videonun içi"nde durur).
        # Hüküm ancak bu video hesabın ortancasından çok kaydırılıyorsa ve ilk soru 3. saniyeden sonraysa yazılır.
        if metin_var and soru is not None and float(soru) > 3 and kaydirma is not None \
                and ort_kaydirma is not None and kaydirma > ort_kaydirma:
            soru = float(soru)
            sc = andaki_cumle(cl, soru + 0.01)
            kanit = [f"Kaydırma oranı {yuzde(kaydirma)}, hesap ortancası {yuzde(ort_kaydirma)}.",
                     f"İlk soru {sirada(soru)} geliyor."]
            kanit.append(f"İlk 3 saniyede söylenen: \"{kisalt(ilk3)}\"." if ilk3 else "İlk 3 saniyede konuşma yok.")
            td = tutma_degeri(tutma, soru) if tutma else None
            if td is not None:
                kanit.append(f"Tutma grafiğine göre {sirada(soru)} izleyicinin yaklaşık {yuzde(td, 0)} kadarı kalmış.")
            if ort is not None and (ort < soru or (sc and ort < sc["son"])):
                kanit.append(f"Ortalama izleme süresi {saniye(ort)}; izleyicinin çoğu soruyu duymadan gidiyor.")
            kanit.append("İlk 3 saniyede iddia, soru, çerçeve ya da sahne ortası var mı, kareye ve metne bak.")
            sonuc.append({"ad": "ilk3", "hukum": "İlk 3 saniye izleyiciye kalması için sebep vermiyor olabilir.",
                          "kanit": " ".join(kanit),
                          "oneri": "İlk 3 saniyeye izleyicinin kalması için bir sebep koy: iddia, soru ya da sahnenin ortası."})
        # Gönderme: hüküm yalnız video gönderme oranında en alt iki basamaktaysa yazılır.
        # Oran iyiyse çağrı olsun olmasın hiçbir şey yazılmaz.
        if metin_var and sure and v.get("bant") in ALT_BANTLAR:
            gonderler = gonder_cagrilari(inc)
            temel = f"Gönderme oranı {yuzde(v.get('gonderme_orani'), 2)}, bant {BANT_ADI.get(v.get('bant'), v.get('bant'))}."
            if "az_sayi" in v.get("isaretler", []):
                temel += " Gönderme sayısı az, oran oynak."
            if not gonderler and altyazi_eksigi(inc) > 2:
                yer = (f"Altyazı videonun son {saniye(altyazi_eksigi(inc))}lik bölümünü kapsamıyor; "
                       "kapanışta çağrı olup olmadığı ölçülemedi.")
                oneri = ("Gönderme sebebini (duygu, kimlik ya da işe yarar bilgi) videonun ortasına gelmeden kur; "
                         "kapanış yalnız hatırlatsın.")
            elif not gonderler:
                yer = "Konuşma metninin tamamında gönder ya da paylaş çağrısı geçmiyor."
                oneri = "Videonun içine açık bir gönderme sebebi koy: kime gönderilsin ve neden."
            else:
                g = gonderler[0]
                kapanista = cagri_ani(g) >= float(sure) - 5
                yer = (f"İlk gönder çağrısı {cagri_yeri(g)}, video {saniye(float(sure))}"
                       + (", yani çağrı yalnız kapanışta" if kapanista else "") +
                       f". Söylenen: \"{kisalt(str(g.get('yazi') or ''))}\"")
                oneri = ("Gönderme sebebini (duygu, kimlik ya da işe yarar bilgi) videonun ortasına gelmeden kur; "
                         f"kapanış yalnız hatırlatsın. Şu an çağrı yalnız {sirada(cagri_ani(g))} geçiyor." if kapanista else
                         "Gönderme sebebini somutlaştır: bu video kime gönderilsin ve neden.")
            sonuc.append({"ad": "gonder", "hukum": "Gönderme sebebi zayıf.", "kanit": temel + " " + yer, "oneri": oneri})
        ses = inc.get("ses_baslangic_sn")
        if ses is not None and float(ses) > 0.5:
            sonuc.append({"ad": "ses", "hukum": "Ses geç başlıyor.",
                          "kanit": f"İlk ses {sayi(float(ses), 2)}. saniyede duyuluyor.",
                          "oneri": "Sesi ilk yarım saniyede başlat."})
        # İlk kare: inceleme "ilk_kare_bos" alanını verdiyse ve doğruysa hüküm yazılır. Alan yoksa bakılmaz.
        if inc.get("ilk_kare_bos") is True:
            sonuc.append({"ad": "ilk_kare", "hukum": "İlk kare boş: akışta video siyah ekranla açılıyor.",
                          "kanit": "İncelemede videonun ilk karesi boş (siyah) ölçüldü. Kare sayfasındaki ilk kareye bak.",
                          "oneri": "İlk kareye konuyu gösteren görsel ve tek satır yazı koy."})
        # İlk 3 saniyede görüntü: inceleme kendi ölçümünü verdiyse ona uyulur. Vermediyse ve kesme
        # ölçümü güvenilmez diye uyarı varsa hüküm yazılmaz. İkisi de yoksa kesme listesine bakılır.
        degisiyor = inc.get("ilk_3sn_gorsel_degisiyor")
        if isinstance(degisiyor, bool):
            if not degisiyor:
                benzerlik = inc.get("ilk_3sn_benzerlik")
                ek = (f" İlk 3 saniyedeki karelerin benzerlik ölçümü: {sayi(float(benzerlik), 2)}."
                      if isinstance(benzerlik, (int, float)) else "")
                sonuc.append({"ad": "goruntu", "hukum": "İlk 3 saniyede görüntü değişmiyor.",
                              "kanit": "İlk 3 saniyenin kareleri birbirine çok benziyor." + ek +
                                       " İlk karede yazı olup olmadığına kareye bakarak karar ver.",
                              "oneri": "İlk 3 saniyeye bir görüntü değişimi koy."})
        elif isinstance(inc.get("kesmeler_sn"), list) and not any(
                "kesme sayısı süreye göre düşük" in str(u).lower() for u in (inc.get("uyarilar") or [])):
            kesmeler = sorted(float(k) for k in inc["kesmeler_sn"])
            if not [k for k in kesmeler if k < 3.0]:
                ilk = f"İlk kesme {sirada(kesmeler[0])}." if kesmeler else "Videoda hiç kesme bulunamadı."
                sonuc.append({"ad": "goruntu", "hukum": "İlk 3 saniyede görüntü değişmiyor.",
                              "kanit": ilk + " İlk karede yazı olup olmadığına kareye bakarak karar ver.",
                              "oneri": "İlk 3 saniyeye bir görüntü değişimi koy."})
        # Ders blokları: hüküm yalnız izleyicinin orada gittiğine dair kanıt varsa yazılır (tutma grafiğinde
        # en sert 3 düşüşten biri bloğa denk geliyorsa ya da videoda tutma sorunu işareti varsa).
        bloklar = [b for b in (inc.get("ders_bloklari") or []) if b.get("bas") is not None and b.get("son") is not None]
        if metin_var and bloklar:
            denk = [(b, d) for b in bloklar for d in dusus_bul(tutma or [])
                    if d["bas"] < float(b["son"]) and d["son"] > float(b["bas"])]
            gerekce = None
            if denk:
                b0, d = denk[0]
                bloklar = [b for b in bloklar if any(b is x for x, _ in denk)]
                gerekce = (f"Tutma grafiğindeki en sert düşüşlerden biri bu bölüme denk geliyor: {esnek(d['bas'])} ile "
                           f"{esnek(d['son'])}. saniye arasında {esnek(d['puan'])} puan.")
            elif "tutma_sorunu" in v.get("isaretler", []):
                gerekce = (f"İzleme yüzdesi {yuzde(v.get('izleme_yuzdesi'))}, hesap ortancası "
                           f"{yuzde(ortancalar.get('izleme_yuzdesi'))}.")
            if gerekce:
                araliklar = ", ".join(f"{esnek(float(b['bas']))} ile {esnek(float(b['son']))}. saniye arası" for b in bloklar)
                nedenler = " ".join(kisalt(str(b.get("neden") or ""), 160) for b in bloklar if b.get("neden"))
                sonuc.append({"ad": "ders", "hukum": f"Ders anlatır gibi geçen bölüm izleyici kaybettiriyor olabilir: {araliklar}.",
                              "kanit": (gerekce + " " + nedenler).strip(),
                              "oneri": f"Açıklama bölümünü kısalt ya da ikiye böl: {araliklar}."})
    # Süre notu yalnız hesabın kendi kaydırma verisi "kısa videolar daha az kaydırılıyor" diyorsa yazılır.
    # İzleme yüzdesi deseni bilgi olarak raporda durur ama hüküm doğurmaz (yüzde, yapısı gereği kısa videoyu kayırır).
    destek = [d for d in (sure_desenleri or []) if d.get("tur") == "sure_kaydirma" and d.get("yon") == "kisa_iyi"
              and d.get("esik_sn") is not None and d.get("platform") in (None, v.get("platform"))]
    if destek and sure and "sure_tahmini" not in v.get("isaretler", []) and float(sure) > float(destek[0]["esik_sn"]) \
            and "kanca_sorunu" in v.get("isaretler", []) and kaydirma is not None:
        d = destek[0]
        fark = f", hesap ortancası {yuzde(ort_kaydirma)}" if ort_kaydirma is not None else ""
        sonuc.append({"ad": "sure", "hukum": "Süre notu: video hesabın süre ortancasından uzun ve çok kaydırılıyor.",
                      "kanit": (f"Süre {saniye(float(sure))}, hesabın süre ortancası {saniye(float(d['esik_sn']))}; "
                                f"kaydırma oranı {yuzde(kaydirma)}{fark}. Bu hesapta kısa videolar daha iyi gidiyor: {d.get('kanit', '')}"),
                      "oneri": f"Aynı konuyu {saniye(float(d['esik_sn']))} altında dene ve kaydırma oranını karşılaştır."})
    return sonuc


def resim_gom(yol):
    try:
        with open(yol, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return None


def gomme_hazirla(kaynaklar, butce):
    """Görüntüleri 480 piksel genişliğe küçültüp gömülecek veriye çevirir: {kaynak yolu: data adresi}.
    Toplam bütçeyi aşarsa kaliteyi adım adım düşürür. ffmpeg yoksa görüntüler olduğu gibi gömülür."""
    kaynaklar = list(dict.fromkeys(kaynaklar))
    if not kaynaklar:
        return {}
    if not shutil.which("ffmpeg"):
        print("Uyarı: ffmpeg bulunamadı, görüntüler küçültülmeden gömüldü; rapor.html büyük olabilir. "
              "Küçük dosya için ffmpeg kur ya da --ayri-gorsel kullan.")
        return {k: resim_gom(k) for k in kaynaklar}
    sonuc = {}
    with tempfile.TemporaryDirectory() as gecici:
        # ffmpeg jpeg ölçeği: 7 yaklaşık kalite 70; sayı büyüdükçe dosya küçülür. Bütçeye sığmazsa önce
        # kalite, sonra genişlik düşürülür.
        for genislik, kalite in ((480, 7), (480, 12), (480, 18), (480, 26), (360, 18), (360, 26), (280, 26)):
            sonuc, toplam = {}, 0
            for i, k in enumerate(kaynaklar):
                hedef = os.path.join(gecici, f"g{i}.jpg")
                try:
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", k, "-vf", f"scale='min({genislik},iw)':-2",
                                    "-q:v", str(kalite), hedef], check=True, capture_output=True, timeout=120)
                    veri = resim_gom(hedef)
                except (subprocess.SubprocessError, OSError):
                    veri = None
                veri = veri or resim_gom(k)
                sonuc[k] = veri
                toplam += len(veri or "")
            if toplam <= butce:
                break
    return sonuc


# ---------------------------------------------------------------------------
# Belge: bloklardan oluşur, sonra hem Markdown hem HTML olarak yazılır.
# ---------------------------------------------------------------------------

class Belge:
    def __init__(self, cikti, gom):
        self.bloklar = []
        self.cikti = cikti      # rapor klasörü
        self.gom = gom          # True ise görüntüler html içine gömülür
        self.kopyalanan = {}

    def resim_ekle(self, kaynak, hedef_adi, aciklama):
        """Görüntüyü rapor klasöründeki gorseller/ altına kopyalar ve bloğu ekler."""
        if kaynak not in self.kopyalanan:
            klasor = os.path.join(self.cikti, "gorseller")
            os.makedirs(klasor, exist_ok=True)
            hedef_adi = re.sub(r"[^A-Za-z0-9._-]+", "_", hedef_adi)
            try:
                shutil.copyfile(kaynak, os.path.join(klasor, hedef_adi))
            except OSError:
                self.ekle("p", f"{aciklama} (görüntü kopyalanamadı: {os.path.basename(kaynak)})")
                return
            self.kopyalanan[kaynak] = "gorseller/" + hedef_adi
        self.ekle("resim", self.kopyalanan[kaynak], aciklama, kaynak)

    def ekle(self, tur, *veri):
        self.bloklar.append((tur, veri))

    def markdown(self):
        c = []
        for tur, v in self.bloklar:
            if tur in ("h1", "h2", "h3"):
                c.append("#" * int(tur[1]) + " " + v[0])
            elif tur == "p":
                c.append(v[0])
            elif tur == "liste":
                c.append("\n".join("- " + m for m in v[0]))
            elif tur == "tablo":
                bas, satirlar = v
                def hc(x):
                    return str(x).replace("|", "/")
                c.append("\n".join(
                    ["| " + " | ".join(bas) + " |", "|" + "|".join(" --- " for _ in bas) + "|"] +
                    ["| " + " | ".join(hc(h) for h in s) + " |" for s in satirlar]))
            elif tur == "resim":
                c.append(f"![{v[1]}]({v[0]})")
            elif tur == "kutu":
                c.append(f"**{v[0]}**\n\n" + "\n".join("- " + m for m in v[1]))
        return "\n\n".join(c) + "\n"

    def html(self, baslik):
        def satir_ici(metin):
            m = html.escape(str(metin), quote=False)
            return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", m)
        c, acik = [], False
        # Görüntü bütçesi: hedeften yazının kaplayacağı yer düşülür (html etiketleri için pay bırakılır).
        butce = HTML_HEDEFI - int(len(self.markdown().encode("utf-8")) * 1.5) - len(SAYFA)
        gomulu = gomme_hazirla([v[2] for tur, v in self.bloklar if tur == "resim" and len(v) > 2 and v[2]],
                               max(butce, 100_000)) if self.gom else {}
        for tur, v in self.bloklar:
            if tur in ("h1", "h2", "h3"):
                c.append(f"<{tur}>{satir_ici(v[0])}</{tur}>")
            elif tur == "p":
                c.append(f"<p>{satir_ici(v[0])}</p>")
            elif tur == "liste":
                c.append("<ul>" + "".join(f"<li>{satir_ici(m)}</li>" for m in v[0]) + "</ul>")
            elif tur == "tablo":
                bas, satirlar = v
                c.append('<div class="kaydir"><table><thead><tr>' +
                         "".join(f"<th>{satir_ici(b)}</th>" for b in bas) + "</tr></thead><tbody>" +
                         "".join("<tr>" + "".join(f"<td>{satir_ici(h)}</td>" for h in s) + "</tr>" for s in satirlar) +
                         "</tbody></table></div>")
            elif tur == "resim":
                kaynak = gomulu.get(v[2]) or html.escape(v[0])
                sinif = "" if v[1].startswith("Kare sayfası") else ' class="tek"'
                c.append(f'<figure{sinif}><img src="{kaynak}" alt="{html.escape(v[1])}" loading="lazy">'
                         f'<figcaption>{satir_ici(v[1])}</figcaption></figure>')
            elif tur == "kutu":
                c.append(f'<div class="kutu"><strong>{satir_ici(v[0])}</strong><ul>' +
                         "".join(f"<li>{satir_ici(m)}</li>" for m in v[1]) + "</ul></div>")
            elif tur == "katla_ac":
                c.append(f"<details><summary>{satir_ici(v[0])}</summary>")
                acik = True
            elif tur == "katla_kapat" and acik:
                c.append("</details>")
                acik = False
        return SAYFA.replace("{{BASLIK}}", html.escape(baslik)).replace("{{GOVDE}}", "\n".join(c))


SAYFA = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{{BASLIK}}</title>
<style>
:root { --zemin:#ffffff; --yazi:#1b1b1f; --soluk:#62626b; --cizgi:#dcdce2; --kutu:#f4f4f7; --vurgu:#0b6b57; }
@media (prefers-color-scheme: dark) {
  :root { --zemin:#131316; --yazi:#ececf0; --soluk:#a0a0aa; --cizgi:#33333b; --kutu:#1d1d22; --vurgu:#5fd3b8; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--zemin); color:var(--yazi);
  font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif; }
main { max-width:780px; margin:0 auto; padding:20px 16px 56px; }
h1 { font-size:1.6rem; line-height:1.25; margin:8px 0 12px; }
h2 { font-size:1.25rem; margin:36px 0 10px; padding-top:18px; border-top:1px solid var(--cizgi); }
h3 { font-size:1.02rem; margin:22px 0 8px; color:var(--vurgu); }
p { margin:8px 0; }
ul { margin:8px 0; padding-left:22px; }
li { margin:6px 0; }
.kaydir { overflow-x:auto; margin:10px 0; border:1px solid var(--cizgi); border-radius:8px; }
table { border-collapse:collapse; width:100%; font-size:0.92rem; }
th, td { padding:7px 10px; text-align:left; border-bottom:1px solid var(--cizgi); vertical-align:top; }
th { background:var(--kutu); white-space:nowrap; }
tr:last-child td { border-bottom:0; }
figure { margin:12px 0; }
img { max-width:100%; height:auto; border-radius:8px; border:1px solid var(--cizgi); display:block; }
figure.tek img { max-width:220px; }
figcaption, .soluk { color:var(--soluk); font-size:0.88rem; margin-top:4px; }
details { margin:10px 0; border:1px solid var(--cizgi); border-radius:8px; padding:4px 12px; background:var(--kutu); }
summary { cursor:pointer; padding:8px 0; font-weight:600; }
details .kaydir { background:var(--zemin); }
.kutu { margin:12px 0; padding:10px 14px; border:1px solid var(--cizgi); border-radius:8px; background:var(--kutu); font-size:0.93rem; }
.kutu ul { margin:6px 0 2px; }
</style>
</head>
<body>
<main>
{{GOVDE}}
</main>
</body>
</html>
"""


def sira_disi_bolumu(b, videolar, incelemeler):
    """Hesabın sıra dışı videoları: her biri hesap ortancasıyla yan yana, altında yalnız ölçülmüş farklar."""
    secilen = [v for v in videolar if "aykiri_yuksek" in v["isaretler"]]
    if not secilen:
        return
    b.ekle("h2", "Hesabın sıra dışı videoları")
    b.ekle("p", "Görüntülemesi hesabın ortadaki videosunun en az 3 katı olan videolar. " + SEYRELME_NOTU.replace(
        "bu videoyu", "bu videoları"))

    def ortanca(degerler):
        d = sorted(x for x in degerler if x is not None)
        if not d:
            return None
        return d[len(d) // 2] if len(d) % 2 else (d[len(d) // 2 - 1] + d[len(d) // 2]) / 2

    for v in sorted(secilen, key=lambda x: x.get("ortanca_kati") or 0, reverse=True):
        # Ortanca, aynı platformdaki olağan videolardan (deneme ve yeni olmayan) hesaplanır.
        grup = [x for x in videolar if x.get("platform") == v.get("platform")
                and "deneme" not in x["isaretler"] and "yeni" not in x["isaretler"]]
        o = {a: ortanca([x.get(a) for x in grup]) for a in
             ("goruntuleme", "paylasim", "gonderme_orani", "kaydirma_orani", "devam_orani", "izleme_yuzdesi", "sure_sn")}
        b.ekle("h3", v.get("baslik") or v["video_id"])
        satirlar = [["Görüntüleme", sayi(v.get("goruntuleme")), sayi(o["goruntuleme"])],
                    ["Hesabın ortadaki videosuna göre kaç kat", sayi(v.get("ortanca_kati"), 1) + " kat", "1 kat"],
                    ["Gönderme sayısı", sayi(v.get("paylasim")), esnek(o["paylasim"])],
                    ["Gönderme oranı", yuzde(v.get("gonderme_orani"), 2), yuzde(o["gonderme_orani"], 2)]]
        if v.get("kaydirma_orani") is not None:
            satirlar.append(["Kaydırma oranı", yuzde(v["kaydirma_orani"]), yuzde(o["kaydirma_orani"])])
        if v.get("devam_orani") is not None:
            satirlar.append(["İzlemeye devam oranı", yuzde(v["devam_orani"]), yuzde(o["devam_orani"])])
        satirlar += [["İzleme yüzdesi", yuzde(v.get("izleme_yuzdesi")), yuzde(o["izleme_yuzdesi"])],
                     ["Süre", saniye(v.get("sure_sn")), saniye(o["sure_sn"])]]
        b.ekle("tablo", ["Ölçü", "Bu video", "Hesap ortancası"], satirlar)

        inc = (incelemeler.get(v["video_id"]) or (None, None))[0]
        ilk3 = str((inc or {}).get("ilk_3sn_metin") or "").strip()
        if inc:
            bilgi = ["**İlk 3 saniyede söylenen:** " + (f"\"{ilk3}\"" if ilk3 else "konuşma metni yok.")]
            metin_var = bool(inc.get("metin")) and inc.get("metin_kaynagi") != "yok"
            if metin_var:
                bilgi.append("**İlk soru:** " + (sirada(float(inc["ilk_soru_sn"])) + "." if inc.get("ilk_soru_sn") is not None
                                                 else "metinde soru cümlesi bulunamadı."))
            if inc.get("ses_baslangic_sn") is not None:
                bilgi.append(f"**Sesin başladığı an:** {sayi(float(inc['ses_baslangic_sn']), 2)}. saniye.")
            if isinstance(inc.get("ilk_kare_bos"), bool):
                bilgi.append("**İlk kare:** " + ("boş (siyah ya da tek renk)." if inc["ilk_kare_bos"] else "dolu, boş değil."))
            if metin_var:
                cagrilar = [c for c in (inc.get("cagrilar") or []) if cagri_ani(c) is not None]
                yer = "; ".join(f"{cagri_yeri(c)} {CAGRI_ADI.get(c.get('tur'), c.get('tur'))} çağrısı" for c in cagrilar) \
                    or "metinde çağrı bulunamadı"
                if not gonder_cagrilari(inc) and altyazi_eksigi(inc) > 2:
                    yer += f" (altyazı son {saniye(altyazi_eksigi(inc))}lik bölümü kapsamıyor; gönder çağrısı ölçülemedi)"
                bilgi.append(f"**Çağrının yeri:** {yer}.")
            b.ekle("liste", bilgi)

        # Yalnız ölçülmüş farklar yazılır; fark yoksa ya da ölçü yoksa satır çıkmaz.
        dersler = []
        k, ok = v.get("kaydirma_orani"), o["kaydirma_orani"]
        if k is not None and ok is not None and abs(k - ok) >= 5:
            if k < ok:
                en_dusuk = all(x.get("kaydirma_orani") is None or x["kaydirma_orani"] >= k for x in grup)
                yorum = "ilk 3 saniye bu hesabın en güçlüsü" if en_dusuk else "ilk 3 saniye hesabın ortasından daha iyi tutuyor"
                dersler.append(f"Kaydırma oranı ortancadan {esnek(ok - k)} puan düşük ({yuzde(k)}, ortanca {yuzde(ok)}): {yorum}."
                               + (f" İlk 3 saniyede söylenen: \"{ilk3}\"" if ilk3 else ""))
            else:
                dersler.append(f"Kaydırma oranı ortancadan {esnek(k - ok)} puan yüksek ({yuzde(k)}, ortanca {yuzde(ok)}): "
                               "video ilk 3 saniyeye rağmen yayılmış; bu videodan ilk saniye dersi çıkmaz.")
        d, od = v.get("devam_orani"), o["devam_orani"]
        if d is not None and od is not None and abs(d - od) >= 5:
            dersler.append(f"İzlemeye devam oranı ortancadan {esnek(abs(d - od))} puan {'yüksek' if d > od else 'düşük'} "
                           f"({yuzde(d)}, ortanca {yuzde(od)}).")
        i, oi = v.get("izleme_yuzdesi"), o["izleme_yuzdesi"]
        if i is not None and oi is not None and abs(i - oi) >= 5:
            dersler.append(f"İzleme yüzdesi ortancadan {esnek(abs(i - oi))} puan {'yüksek' if i > oi else 'düşük'} "
                           f"({yuzde(i)}, ortanca {yuzde(oi)}).")
        g, og = v.get("paylasim"), o["paylasim"]
        if g is not None and og:
            dersler.append(f"Gönderme sayısı {sayi(g)}; hesap ortancası {esnek(og)}, yani {sayi(g / og, 1)} katı. "
                           f"Görüntüleme ise ortancanın {sayi(v.get('ortanca_kati'), 1)} katı.")
        su, osu = v.get("sure_sn"), o["sure_sn"]
        if su is not None and osu and abs(su - osu) / osu >= 0.2:
            dersler.append(f"Süre {saniye(su)}, hesap ortancası {saniye(osu)}: video ortancadan "
                           f"{'uzun' if su > osu else 'kısa'}.")
        b.ekle("p", "**Bu videodan öğrenilecekler**")
        b.ekle("liste", dersler or ["Ölçülen sayılarda hesap ortancasından belirgin bir fark yok; görüntüleme dışında "
                                    "bu videoyu ayıran bir ölçü bulunamadı."])


def video_bolumu(b, v, inc, inc_klasor, tutma, ortancalar, katla, sure_desenleri=None, tutma_notu=None):
    ad = v.get("baslik") or v["video_id"]
    # Video incelendiyse gerçek süre incelemeden alınır; tahmini süre ve işareti kalkar.
    if inc and inc.get("sure_sn") and "sure_tahmini" in v["isaretler"]:
        v["sure_sn"] = float(inc["sure_sn"])
        v["isaretler"] = [i for i in v["isaretler"] if i != "sure_tahmini"]
    if katla:
        b.ekle("katla_ac", f"{ad} · gönderme oranı {yuzde(v.get('gonderme_orani'), 2)} · {BANT_ADI.get(v.get('bant') or '', v.get('bant'))}")
        b.ekle("h3", ad)
    else:
        b.ekle("h2", ad)
    payda = "görüntüleme" if "erisim_yok_goruntuleme_kullanildi" in v["isaretler"] else "erişim"
    sayilar = [
        ["Platform", v.get("platform") or "yok"], ["Yayın tarihi", tarih(v.get("yayin_tarihi"))],
        ["Süre", saniye(v.get("sure_sn"))], ["Görüntüleme", sayi(v.get("goruntuleme"))],
        ["Erişim", sayi(v.get("erisim"))], ["Beğeni", sayi(v.get("begeni"))], ["Yorum", sayi(v.get("yorum"))],
        ["Gönderme", sayi(v.get("paylasim"))], ["Kaydetme", sayi(v.get("kaydetme"))],
        ["Ortalama izleme süresi", saniye(v.get("ort_izleme_sn"))],
        ["Kaydırma oranı", yuzde(v.get("kaydirma_orani"))],
        ["İzlemeye devam oranı", yuzde(v.get("devam_orani"))],
        ["İzleme yüzdesi", yuzde(v.get("izleme_yuzdesi"))],
        [f"Gönderme oranı (gönderme / {payda})", yuzde(v.get("gonderme_orani"), 2)],
        ["Beğeni oranı", yuzde(v.get("begeni_orani"), 2)],
        ["Hesabın ortadaki videosuna göre kaç kat (görüntüleme)", "yok" if v.get("ortanca_kati") is None else sayi(v["ortanca_kati"], 2) + " kat"],
        ["Bant", "deneme Reels, banda sokulmadı" if "deneme" in v["isaretler"] else BANT_ADI.get(v.get("bant") or "", v.get("bant"))],
    ]
    # Bu platformda hiç ölçülmeyen satırlar gösterilmez (ör. YouTube'da kaydırma, Instagram'da devam oranı).
    if v.get("devam_orani") is None:
        sayilar = [x for x in sayilar if x[0] != "İzlemeye devam oranı"]
    elif v.get("kaydirma_orani") is None:
        sayilar = [x for x in sayilar if x[0] != "Kaydırma oranı"]
    b.ekle("tablo", ["Ölçü", "Değer"], sayilar)
    isaretler = []
    for i in v["isaretler"]:
        if i.startswith("eksik_veri:"):
            isaretler.append("Eksik veri: " + ALAN_ADI.get(i.split(":", 1)[1], i.split(":", 1)[1]))
        elif i == "kanca_sorunu" and v.get("kaydirma_orani") is None:
            isaretler.append("İlk saniyeler zayıf: izlemeye devam oranı hesap ortancasının en az 10 puan altında")
        else:
            isaretler.append(ISARET_ADI.get(i, i))
    b.ekle("p", "**İşaretler:** " + ("; ".join(isaretler) if isaretler else "yok") + ".")

    cl = cumleler((inc or {}).get("metin"))
    if inc:
        b.ekle("h3", "Videonun içi")
        satirlar = []
        ilk3 = str(inc.get("ilk_3sn_metin") or "").strip()
        satirlar.append("**İlk 3 saniyede söylenen:** " + (f"\"{ilk3}\"" if ilk3 else "konuşma metni yok."))
        if inc.get("metin_kaynagi") != "yok" and inc.get("metin"):
            if not gonder_cagrilari(inc) and altyazi_eksigi(inc) > 2:
                satirlar.append(f"**Kapanış ölçülemedi:** altyazı videonun son {saniye(altyazi_eksigi(inc))}lik bölümünü "
                                "kapsamıyor. Gönder çağrısı o bölümde olabilir; tam altyazıyı verince yeniden bakılır.")
            if inc.get("ilk_soru_sn") is not None:
                sc = andaki_cumle(cl, float(inc["ilk_soru_sn"]) + 0.01)
                satirlar.append(f"**İlk soru:** {sirada(float(inc['ilk_soru_sn']))}." + (f" \"{kisalt(sc['yazi'])}\"" if sc else ""))
            else:
                satirlar.append("**İlk soru:** metinde soru cümlesi bulunamadı.")
            cagrilar = [c for c in (inc.get("cagrilar") or []) if cagri_ani(c) is not None]
            if cagrilar:
                satirlar.append("**Çağrılar:** " + "; ".join(
                    f"{cagri_yeri(c)} {CAGRI_ADI.get(c.get('tur'), c.get('tur'))} çağrısı (\"{kisalt(str(c.get('yazi') or ''), 120)}\")"
                    for c in cagrilar) + ".")
            else:
                satirlar.append("**Çağrılar:** metinde çağrı bulunamadı.")
            bloklar = inc.get("ders_bloklari") or []
            if bloklar:
                satirlar.append("**Ders blokları:** " + "; ".join(
                    f"{esnek(float(x['bas']))} ile {esnek(float(x['son']))}. saniye arası" for x in bloklar) + ".")
        if inc.get("ses_baslangic_sn") is not None:
            satirlar.append(f"**Sesin başladığı an:** {sayi(float(inc['ses_baslangic_sn']), 2)}. saniye.")
        # İlk sahne kesmesi ve ilk 3 saniyedeki değişimin nedeni. Neden kod olarak gelir; yalnız tanınan
        # kodlar Türkçe yazılır, tanınmayan gösterilmez.
        kesmeler = sorted(float(k) for k in inc["kesmeler_sn"]) if isinstance(inc.get("kesmeler_sn"), list) else None
        if kesmeler is not None:
            kesme_yazi = f"sahne kesmesi ilk kez {sirada(kesmeler[0])}" if kesmeler else "videoda sahne kesmesi bulunamadı"
            nedenler = [NEDEN_ADI[k] for k in re.split(r"[;,]\s*", str(inc.get("ilk_3sn_degisim_nedeni") or "")) if k in NEDEN_ADI]
            if nedenler:
                satirlar.append("**İlk 3 saniyede görüntü:** " + "; ".join(nedenler + [kesme_yazi]) + ".")
            else:
                satirlar.append("**İlk sahne kesmesi:** " + kesme_yazi[0].upper() + kesme_yazi[1:] + ".")
        if inc.get("kesme_sikligi_10sn"):
            satirlar.append("**Kesme sıklığı (her 10 saniyelik dilimde kesme sayısı):** " +
                            ", ".join(str(x) for x in inc["kesme_sikligi_10sn"]) + ".")
        if inc.get("dakikada_kelime"):
            satirlar.append(f"**Konuşma hızı:** dakikada {esnek(float(inc['dakikada_kelime']))} kelime.")
        b.ekle("liste", satirlar)
        for u in dict.fromkeys(uyari_sade(u) for u in (inc.get("uyarilar") or [])):
            b.ekle("p", "Uyarı: " + u)

    def kare_ekle(t):
        if not inc:
            return
        k = en_yakin_kare(inc, t)
        if k and os.path.isfile(os.path.join(inc_klasor, k["dosya"])):
            b.resim_ekle(os.path.join(inc_klasor, k["dosya"]), f"{v['video_id']}_{k['dosya']}",
                         f"En yakın kare: {sirada(float(k['sn']), '')}")

    # Ortalama izleme tek bir "ayrılma anı" değildir; o saniyedeki cümle suçlu gibi gösterilmez.
    ozet_cumle = []
    if v.get("ort_izleme_sn") is not None:
        pay = f" (videonun {yuzde(v['izleme_yuzdesi'])} kadarı)" if v.get("izleme_yuzdesi") is not None else ""
        ozet_cumle.append(f"Ortalama izleme süresi {saniye(v['ort_izleme_sn'])}{pay}.")
    if v.get("kaydirma_orani") is not None:
        ozet_cumle.append(f"Kaydırma oranı {yuzde(v['kaydirma_orani'])}: izleyicinin bu kadarı ilk 3 saniyede geçti.")
    if v.get("devam_orani") is not None:
        ozet_cumle.append(f"İzlemeye devam oranı {yuzde(v['devam_orani'])}: videoyu görenlerin bu kadarı kaydırmayıp izledi.")
    if "yeni" in v["isaretler"]:
        ozet_cumle.append("Video yayınlanalı 48 saat olmadı; sayılar henüz oturmamış olabilir, birkaç gün sonra yeniden bak.")
    if "deneme" in v["isaretler"]:
        ozet_cumle.append("Deneme Reels, yalnız takipçi olmayanlara gösterildi; sayıları hesabın öbür videolarıyla kıyaslanmaz.")
    if "aykiri_yuksek" in v["isaretler"]:
        ozet_cumle.append(SEYRELME_NOTU)
    if "az_sayi" in v["isaretler"]:
        ozet_cumle.append(f"Gönderme sayısı az ({sayi(v.get('paylasim'))}), oran oynak: tek bir gönderme oranı belirgin değiştirir.")
    if tutma and len(tutma) >= 2:
        b.ekle("h3", "İzleyici nerede gitti")
        if ozet_cumle:
            b.ekle("p", " ".join(ozet_cumle))
        dususler = dusus_bul(tutma)
        satirlar = []
        for d in dususler:
            ilgili = araliktaki_cumleler(cl, d["bas"], d["son"])
            soz = kisalt(" ".join(c["yazi"] for c in ilgili)) if ilgili else ("konuşma yok" if cl else "metin verilmedi")
            satirlar.append([f"{esnek(d['bas'])} ile {esnek(d['son'])}. saniye arası",
                             f"{esnek(d['puan'])} puan ({den_e(d['once'], d['sonra'])})", soz])
        b.ekle("tablo", ["Aralık", "Kayıp", "O sırada söylenen"], satirlar)
        if tutma_notu:
            b.ekle("p", "Not: " + tutma_notu)
        if dususler:
            d = dususler[0]
            b.ekle("p", f"En sert düşüş {esnek(d['bas'])} ile {esnek(d['son'])}. saniye arasında: {esnek(d['puan'])} puan.")
            for d in dususler:
                kare_ekle(d["bas"])
    elif ozet_cumle:
        if not katla:
            b.ekle("h3", "İzleyici nerede gitti")
        b.ekle("p", " ".join(ozet_cumle))
        if not katla:
            b.ekle("p", "Tutma grafiği verilmedi; bu yüzden düşüşün hangi saniyelerde yığıldığı bilinmiyor.")

    anlar = [x for x in ((inc or {}).get("anlar") or []) if x.get("sn") is not None]
    if anlar:
        b.ekle("h3", "İstenen anlar")
        for x in anlar:
            soz = str(x.get("yazi") or "").strip()
            b.ekle("p", f"**{sirada(float(x['sn']), '')}:** " + (f"\"{kisalt(soz)}\"" if soz else "o anda konuşma yok ya da metin verilmedi."))
            yol = os.path.join(inc_klasor, str(x.get("kare") or ""))
            if x.get("kare") and os.path.isfile(yol):
                b.resim_ekle(yol, f"{v['video_id']}_{x['kare']}", f"İstenen an: {sirada(float(x['sn']), '')}")
            else:
                kare_ekle(float(x["sn"]))

    hl = hukumler(v, inc, tutma, ortancalar, sure_desenleri)
    if hl:
        b.ekle("h3", "Hükümler")
        b.ekle("liste", [f"**{h['hukum']}** Kanıt: {h['kanit']}" for h in hl])
        oneriler = [h["oneri"] for h in hl if h.get("oneri")][:3]
        if oneriler:
            b.ekle("h3", "Sonraki video için")
            b.ekle("liste", oneriler)
    elif "aykiri_yuksek" in v["isaretler"]:
        b.ekle("p", "Bu video hesabın sıra dışı videolarından; olumsuz hüküm yazılmadı. Ölçümleri \"Hesabın sıra dışı "
                    "videoları\" bölümünde hesap ortancasıyla yan yana duruyor.")
    elif inc:
        b.ekle("p", "Bu video için kanıtı olan bir hüküm çıkmadı.")
    if inc:
        temas = os.path.join(inc_klasor, "temas_sayfasi.jpg")
        if os.path.isfile(temas):
            b.ekle("h3", "Kare sayfası")
            b.resim_ekle(temas, f"{v['video_id']}_kare_sayfasi.jpg", "Kare sayfası: videodan kareler, altlarında saniyeleri")
    if katla:
        b.ekle("katla_kapat")


def main():
    ap = argparse.ArgumentParser(description="Elden Ele raporunu yazar.")
    ap.add_argument("--ozet", required=True, help="veri_birlestir.py çıktısı ozet.json")
    ap.add_argument("--tablo", required=True, help="veri_birlestir.py çıktısı tablo.csv")
    ap.add_argument("--inceleme", action="append", default=[], help="video_incele.py çıktısı inceleme.json")
    ap.add_argument("--video-id", action="append", default=[], dest="video_id",
                    help="Bir önceki --inceleme dosyasının tablodaki video kimliği")
    ap.add_argument("--tutma", help="Tutma grafiği noktaları (tutma.json)")
    ap.add_argument("--cikti", required=True, help="Rapor klasörü")
    ap.add_argument("--ayri-gorsel", action="store_true", dest="ayri_gorsel",
                    help="Görüntüleri html içine gömme; gorseller/ klasöründeki dosyaları göster.")
    ap.add_argument("--okuma", help="Raporun başına konacak yorum dosyası (basit markdown)")
    a = ap.parse_args()

    ozet = json_oku(a.ozet, "Özet dosyası")
    videolar = tablo_oku(a.tablo)
    es = ozet.get("es_kimlikler") or {}
    notlar = []
    if len(a.video_id) > len(a.inceleme):
        hata("--video-id sayısı --inceleme sayısından fazla. Her --inceleme için en çok bir --video-id ver.")

    incelemeler, sahipsiz = {}, []
    for i, yol in enumerate(a.inceleme):
        inc = json_oku(yol, "İnceleme dosyası")
        klasor = os.path.dirname(os.path.abspath(yol))
        verilen = a.video_id[i] if i < len(a.video_id) else None
        vid = kimlik_coz(verilen, videolar, es) if verilen else dosyadan_esle(inc, videolar)
        if vid is None:
            neden = (f"'{verilen}' kimliği tabloda bulunamadı" if verilen
                     else "--video-id verilmedi ve dosya adından video bulunamadı")
            notlar.append(f"{inc.get('dosya') or yol}: {neden}. İnceleme sayılarla eşlenmeden yazıldı. "
                          "Tablodaki video_id değerini --video-id ile ver.")
            sahipsiz.append((inc, klasor))
        else:
            incelemeler[vid] = (inc, klasor)

    tutmalar, tutma_not = {}, {}
    if a.tutma:
        ham = json_oku(a.tutma, "Tutma dosyası")
        if not isinstance(ham, dict):
            hata("Tutma dosyası beklenen biçimde değil. Örnek: {\"VIDEO_ID\":[{\"sn\":0,\"yuzde\":100},{\"sn\":3,\"yuzde\":62}]}")
        ham_not = ham.pop("not", None)
        tutma_notlari = ham_not if isinstance(ham_not, dict) else {}
        for anahtar, noktalar in ham.items():
            vid = kimlik_coz(anahtar, videolar, es)
            temiz = tutma_duzelt(noktalar)
            if vid is None:
                notlar.append(f"Tutma dosyasındaki '{anahtar}' kimliği tabloda bulunamadı, kullanılmadı.")
            elif len(temiz) < 2:
                notlar.append(f"Tutma dosyasında '{anahtar}' için en az iki nokta gerekli, kullanılmadı.")
            else:
                tutmalar[vid] = temiz
                if tutma_notlari.get(anahtar):
                    tutma_not[vid] = str(tutma_notlari[anahtar])

    ort = ozet.get("ortancalar") or {}
    platformlar = ozet.get("platformlar") or {}

    def p_ort(v):
        """Videonun kendi platformunun ortancaları; yoksa genel ortancalar."""
        d = platformlar.get(v.get("platform"))
        return (d.get("ortancalar") if isinstance(d, dict) else None) or ort
    sd = [d for d in (ozet.get("desenler") or []) if str(d.get("tur") or "").startswith("sure_")]
    os.makedirs(a.cikti, exist_ok=True)
    b = Belge(a.cikti, not a.ayri_gorsel)
    baslik = "Elden Ele raporu"
    b.ekle("h1", baslik)
    b.ekle("kutu", "Kelimeler", [
        "**Gönderme oranı:** videoyu birine gönderenlerin, videoya erişenlere (erişim yoksa görüntülemeye) oranı.",
        "**Kaydırma oranı:** videoyu ilk 3 saniyede kaydırıp geçenlerin yüzdesi.",
        "**İzleme yüzdesi:** ortalama izleme süresinin video süresine oranı.",
        "**Ortanca:** hesabın ortadaki değeri; videoların yarısı bunun altında, yarısı üstündedir.",
        "**Çeyrek:** videolar orana göre sıralanıp dört eşit gruba bölündüğünde her bir grup.",
        "**Bant:** videonun gönderme oranına göre bu hesabın içinde düştüğü basamak (zayıf, ortanın altı, ortanın üstü, güçlü).",
        "**Sıra dışı video:** görüntülemesi hesabın ortadaki videosunun en az 3 katı olan video. Banda sokulmaz.",
    ] + (["**İzlemeye devam oranı:** YouTube'da videoyu görüp kaydırmayan, izlemeyi sürdürenlerin yüzdesi. "
          "YouTube kaydırma oranı vermediği için onun yerine bakılır."] if any(v.get("devam_orani") is not None for v in videolar) else [])
      + (["**Deneme Reels:** Instagram'ın yalnız takipçi olmayanlara gösterdiği video. Hesap ortancasına katılmaz."]
         if any("deneme" in v["isaretler"] for v in videolar) else []))

    if a.okuma:
        okuma = okuma_bloklari(a.okuma)
        if okuma:
            b.ekle("h2", "Claude'un okuması")
            for tur, veri in okuma:
                b.ekle(tur, *veri)

    # 1. Hesap özeti
    b.ekle("h2", "Hesap özeti")
    yontem = ozet.get("bant_yontemi")
    def yontem_adi(y):
        if y == "yok_az_sayi":
            return ("bant hesaplanmadı. Bu platformda gönderme sayıları bant çıkaracak kadar büyük değil; "
                    "izlemeye devam oranı ve izleme yüzdesine bakın.")
        return ("hesabın kendi çeyrekleri (en az 8 video olduğu için)" if y == "hesap_ceyrekleri" else
                "varsayılan eşikler (8'den az video olduğu için): %0,3 altı zayıf, %0,3 ile %0,6 arası orta, "
                "%0,6 ile %1,5 arası iyi, %1,5 üstü çok iyi")

    def ozet_satirlari(o, d=None):
        satirlar = []
        if d is not None:
            deneme, yeni = d.get("deneme_sayisi") or 0, d.get("yeni_sayisi") or 0
            ekler = ([f"{sayi(deneme)} tanesi deneme Reels"] if deneme else []) + \
                    ([f"{sayi(yeni)} tanesi 48 saatten yeni"] if yeni else [])
            satirlar.append(["Video sayısı", sayi(d.get("video_sayisi")) +
                             (f" ({', '.join(ekler)}; ortancalara katılmadı)" if ekler else "")])
        satirlar += [["Görüntüleme ortancası", sayi(o.get("goruntuleme"))],
                     ["Gönderme oranı ortancası", yuzde(o.get("gonderme_orani"), 2)]]
        if o.get("kaydirma_orani") is not None:
            satirlar.append(["Kaydırma oranı ortancası", yuzde(o.get("kaydirma_orani"))])
        if o.get("devam_orani") is not None:
            satirlar.append(["İzlemeye devam oranı ortancası", yuzde(o.get("devam_orani"))])
        satirlar.append(["İzleme yüzdesi ortancası", yuzde(o.get("izleme_yuzdesi"))])
        return satirlar

    cok_platform = len([d for d in platformlar.values() if isinstance(d, dict)]) > 1
    if cok_platform:
        # Platformlar birbirine karıştırılmaz; her birinin ortancası ayrı gösterilir.
        b.ekle("p", f"Toplam {sayi(ozet.get('video_sayisi', len(videolar)))} video. Platformlar ayrı ayrı "
                    "değerlendirildi; bir platformun sayıları ötekinin ortancasıyla kıyaslanmaz.")
        for p, d in platformlar.items():
            b.ekle("h3", str(p))
            b.ekle("tablo", ["Ölçü", "Değer"], ozet_satirlari(d.get("ortancalar") or {}, d) +
                   [["Bant yöntemi", yontem_adi(d.get("bant_yontemi"))]])
    else:
        tek = next((d for d in platformlar.values() if isinstance(d, dict)), None)
        b.ekle("tablo", ["Ölçü", "Değer"],
               [["Platform", ", ".join(str(p) for p in platformlar) or "yok"]] +
               (ozet_satirlari(ort, tek) if tek else
                [["Video sayısı", sayi(ozet.get("video_sayisi", len(videolar)))]] + ozet_satirlari(ort)) +
               [["Bant yöntemi", yontem_adi(yontem)]])
    for _ in (1,):
        for p, d in platformlar.items():
            e = (d or {}).get("bant_esikleri") or {}
            if (d or {}).get("bant_yontemi") == "hesap_ceyrekleri" and e:
                on = f"{p}: " if len(platformlar) > 1 else ""
                alt = ("hiç gönderilmeyen videolar zayıf" if not e.get("alt_ceyrek") else f"{yuzde(e.get('alt_ceyrek'), 2)} altı zayıf")
                b.ekle("p", f"{on}Bant sınırları (gönderme oranı): {alt}, "
                            f"{yuzde(e.get('ortanca'), 2)} altı ortanın altı, {yuzde(e.get('ust_ceyrek'), 2)} altı ortanın üstü, "
                            "üstü güçlü. Bantlar bu hesabın kendi videolarına göredir; başka hesapla kıyas değildir.")
    desenler = ozet.get("desenler") or []
    b.ekle("h3", "Desenler")
    if desenler:
        b.ekle("liste", [f"**{d['desen'][0].upper() + d['desen'][1:]}.** {d['kanit']} ({sayi(d.get('video_sayisi'))} video)"
                         for d in desenler])
    else:
        b.ekle("p", "En az 3 videoda tekrar eden bir desen bulunamadı.")
    for u in ozet.get("uyarilar") or []:
        if "etiket" in str(u):
            b.ekle("p", str(u))

    b.ekle("h3", "Bütün videolar")
    devam_var = any(v.get("devam_orani") is not None for v in videolar)
    kaydirma_var = any(v.get("kaydirma_orani") is not None for v in videolar)

    def ilk_saniye(v):
        """Kaydırma oranı varsa o, yoksa izlemeye devam oranı."""
        if v.get("kaydirma_orani") is not None:
            return yuzde(v["kaydirma_orani"])
        if v.get("devam_orani") is not None:
            return yuzde(v["devam_orani"])
        return "yok"

    def bant_yazi(v):
        ad = "deneme" if "deneme" in v["isaretler"] else BANT_ADI.get(v.get("bant") or "", v.get("bant"))
        return ad + (" (yeni)" if "yeni" in v["isaretler"] else "")

    # Birden çok platform varsa her platform kendi tablosunu alır; böylece telefonda ilk sütunlar sığar
    # ve sütun başlığı o platformun ölçüsünü (kaydırma ya da devam oranı) taşır.
    gruplar = [(p, [v for v in videolar if v.get("platform") == p]) for p in platformlar] if cok_platform \
        else [(None, videolar)]
    kalan = [v for v in videolar if not any(v in g for _, g in gruplar)]
    if kalan:
        gruplar.append(("diğer", kalan))
    for p, grup in gruplar:
        if not grup:
            continue
        if p:
            b.ekle("p", f"**{p}**")
        devam_var = any(v.get("devam_orani") is not None for v in grup)
        kaydirma_var = any(v.get("kaydirma_orani") is not None for v in grup)
        ilk_baslik = "Kaydırma oranı" if not devam_var else ("İzlemeye devam oranı" if not kaydirma_var else "Kaydırma ya da devam oranı")
        b.ekle("tablo", ["Video", "Gönderme oranı", "Bant", ilk_baslik, "İzleme yüzdesi", "Görüntüleme", "Erişim",
                         "Gönderme", "Süre", "Yayın"],
               [[v.get("baslik") or v["video_id"],
                 yuzde(v.get("gonderme_orani"), 2) + (" (az sayı)" if "az_sayi" in v["isaretler"] and v.get("bant") != "az_sayi" else ""),
                 bant_yazi(v), ilk_saniye(v), yuzde(v.get("izleme_yuzdesi")), sayi(v.get("goruntuleme")),
                 sayi(v.get("erisim")), sayi(v.get("paylasim")),
                 saniye(v.get("sure_sn")) + (" (tahmin)" if "sure_tahmini" in v["isaretler"] else ""),
                 tarih(v.get("yayin_tarihi"))] for v in grup])
    if any(v.get("bant") == "sira_disi" for v in videolar):
        b.ekle("p", "\"Sıra dışı\" yazan videolar oran bandına sokulmadı. " + SEYRELME_NOTU.replace("bu videoyu", "bu videoları"))
    if any("az_sayi" in v["isaretler"] for v in videolar):
        b.ekle("p", "\"Az sayı\" yazan videolarda gönderme sayısı 10'un altında; oranları oynaktır, tek başına hüküm çıkarma.")

    sira_disi_bolumu(b, videolar, incelemeler)

    # 2. Video başına
    detayli = [v for v in videolar if v["video_id"] in incelemeler or v["video_id"] in tutmalar]
    digerleri = [v for v in videolar if v not in detayli]
    for v in detayli:
        inc, klasor = incelemeler.get(v["video_id"], (None, None))
        video_bolumu(b, v, inc, klasor, tutmalar.get(v["video_id"]), p_ort(v), katla=False, sure_desenleri=sd,
                     tutma_notu=tutma_not.get(v["video_id"]))
    for inc, klasor in sahipsiz:
        sahte_v = {"video_id": str(inc.get("dosya") or "video"), "baslik": str(inc.get("dosya") or "video"),
                   "isaretler": [], "sure_sn": inc.get("sure_sn")}
        video_bolumu(b, sahte_v, inc, klasor, None, ort, katla=False, sure_desenleri=sd)
    if digerleri:
        b.ekle("h2", "Diğer videolar" if detayli or sahipsiz else "Videolar")
        if not a.inceleme:
            b.ekle("p", "Video dosyası incelenmedi; bu bölüm yalnız sayılara dayanır. Saniye saniye hüküm için "
                        "videoyu video_incele.py ile incele ve çıktısını bu rapora ver.")
        for v in digerleri:
            video_bolumu(b, v, None, None, None, p_ort(v), katla=True, sure_desenleri=sd)

    # Rakip
    rakip = ozet.get("rakip") or []
    if rakip:
        b.ekle("h2", "Rakip hesaplar")
        aykiri = [r for r in rakip if r.get("aykiri") or (r.get("aykiri") is None and (r.get("ortanca_kati") or 0) >= 3)]
        if aykiri:
            b.ekle("p", "Kendi hesabının ortancasının en az 3 katı görüntülenen rakip videoları (hesap, bu videoyu olağan videosundan çok daha fazla izletmiş):")
            b.ekle("tablo", ["Hesap", "Video", "Görüntüleme", "Hesabın ortadaki videosuna göre kaç kat"],
                   [[r.get("hesap"), r.get("video"), sayi(r.get("goruntuleme")),
                     sayi(r.get("ortanca_kati"), 1) + " kat"] for r in aykiri])
        else:
            b.ekle("p", f"{sayi(len(rakip))} rakip videosu içinde hesabının ortancasının 3 katını geçen yok.")

    # Uyarılar
    uyarilar = list(ozet.get("uyarilar") or []) + notlar
    for dosya, sutunlar in (ozet.get("taninmayan_sutunlar") or {}).items():
        if sutunlar:
            uyarilar.append(f"{dosya} dosyasında tanınmayan ve yok sayılan sütunlar: {', '.join(sutunlar)}.")
    if uyarilar:
        b.ekle("h2", "Uyarılar")
        b.ekle("liste", uyarilar)

    md_yolu, html_yolu = os.path.join(a.cikti, "rapor.md"), os.path.join(a.cikti, "rapor.html")
    with open(md_yolu, "w", encoding="utf-8") as f:
        f.write(b.markdown())
    with open(html_yolu, "w", encoding="utf-8") as f:
        f.write(b.html(baslik))
    print(f"Rapor yazıldı: {md_yolu} ve {html_yolu}")
    print(f"{len(videolar)} video; {len(incelemeler) + len(sahipsiz)} inceleme, {len(tutmalar)} tutma grafiği kullanıldı.")
    for n in notlar:
        print("Uyarı: " + n)


if __name__ == "__main__":
    main()
