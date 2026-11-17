#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_incele.py · Elden Ele video inceleme betiği

Ne yapar : Tek bir kısa videoyu saniye saniye inceler. Sesin başladığı anı, sessiz
           aralıkları, sahne kesmelerini bulur; kilit anlardan kare çıkarır; altyazıdan
           ilk soruyu, çağrıları (gönder, paylaş, yorum ...) ve ders gibi anlatılan
           blokları saptar.
Girdi    : VIDEO.mp4, isteğe bağlı altyazı (.srt, .vtt ya da düz .txt), isteğe bağlı
           ayrıca bakılacak saniyeler (--anlar).
Çıktı    : KLASOR/<video_adı>/inceleme.json, kare_*.jpg dosyaları ve temas_sayfasi.jpg
           Kareler: ilk dört saniye, her kesmenin hemen sonrası ve her 5 saniye.
Gereken  : Python 3.10+, ffmpeg ve ffprobe. Başka kütüphane gerekmez.
Örnek    : python3 video_incele.py video.mp4 --altyazi video.srt --anlar 16,17.5 --cikti cikti
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

SES_ESIGI_DB = -35
SESSIZLIK_EN_AZ_SN = 0.6
SAHNE_ESIGI = 0.3
KARE_GENISLIK = 540
EN_FAZLA_KARE = 40
DERS_EN_AZ_SN = 5.0
GORSEL_DEGISIM_ESIGI = 0.85
BOS_KARE_YAYILIM = 48
PARLAKLIK_FARKI_ESIGI = 10
ALTYAZI_YOK_UYARISI = (
    "Konuşma metne dökülemedi. Videonun srt altyazısını ver "
    "(CapCut, YouTube Studio altyazı indir ya da metni yapıştır)"
)


class Hata(Exception):
    """Kullanıcıya gösterilecek, ne yapacağını söyleyen hata."""


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------

def kucuk(s):
    """Türkçe kurallarıyla küçük harfe çevirir (I -> ı, İ -> i)."""
    return s.replace("İ", "i").replace("I", "ı").lower().replace("i̇", "i")


def yuvarla(x, hane=2):
    return round(float(x) + 0.0, hane)


def calistir(komut, zaman_asimi=900):
    """Komutu çalıştırır; (dönüş kodu, stdout, stderr) döndürür."""
    try:
        s = subprocess.run(komut, capture_output=True, timeout=zaman_asimi)
    except FileNotFoundError:
        raise Hata(
            "'%s' bulunamadı. Bu betik ffmpeg ve ffprobe ister. "
            "Kur (ör. 'apt install ffmpeg' ya da 'brew install ffmpeg') ve yeniden dene." % komut[0]
        )
    except subprocess.TimeoutExpired:
        raise Hata("ffmpeg işlemi çok uzun sürdü ve durduruldu. Daha kısa bir video ile dene.")
    return s.returncode, s.stdout.decode("utf-8", "replace"), s.stderr.decode("utf-8", "replace")


def suzgec_kacis(yol):
    """ffmpeg süzgeç değeri içinde dosya yolu için kaçış."""
    return yol.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


# ----------------------------------------------------------------------------
# Video bilgisi, ses, kesmeler
# ----------------------------------------------------------------------------

def video_bilgisi(yol):
    kod, cikti, hata = calistir([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", yol
    ])
    if kod != 0:
        raise Hata(
            "Bu dosya video olarak okunamadı: %s. Dosya bozuk ya da video değil. "
            "Videoyu mp4 olarak yeniden dışa aktarıp dene." % yol
        )
    try:
        veri = json.loads(cikti)
    except ValueError:
        raise Hata("ffprobe çıktısı okunamadı. Videoyu mp4 olarak yeniden dışa aktarıp dene.")
    akislar = veri.get("streams", [])
    goruntu = next((a for a in akislar
                    if a.get("codec_type") == "video"
                    and not (a.get("disposition") or {}).get("attached_pic")), None)
    ses_var = any(a.get("codec_type") == "audio" for a in akislar)
    if goruntu is None:
        raise Hata(
            "Dosyada görüntü akışı yok: %s. Yalnız ses dosyası verilmiş olabilir; videonun kendisini ver." % yol
        )
    sure = None
    for kaynak in (veri.get("format", {}).get("duration"), goruntu.get("duration")):
        try:
            sure = float(kaynak)
            break
        except (TypeError, ValueError):
            continue
    if not sure or sure <= 0:
        raise Hata("Videonun süresi okunamadı: %s. Videoyu mp4 olarak yeniden dışa aktarıp dene." % yol)
    gen, yuk = int(goruntu.get("width") or 0), int(goruntu.get("height") or 0)
    donme = 0
    try:
        donme = int(float((goruntu.get("tags") or {}).get("rotate", 0)))
    except ValueError:
        donme = 0
    for yan in goruntu.get("side_data_list") or []:
        if "rotation" in yan:
            try:
                donme = int(float(yan["rotation"]))
            except (TypeError, ValueError):
                pass
    if abs(donme) % 180 == 90:
        gen, yuk = yuk, gen
    return {"sure": sure, "genislik": gen, "yukseklik": yuk, "ses_var": ses_var}


def ses_incele(yol, sure, uyarilar):
    """İlk sesin başladığı anı ve 0.6 saniyeden uzun sessiz aralıkları bulur."""
    kod, _, hata = calistir([
        "ffmpeg", "-hide_banner", "-nostdin", "-i", yol, "-vn", "-map", "0:a:0",
        "-af", "silencedetect=noise=%ddB:d=0.05" % SES_ESIGI_DB, "-f", "null", "-"
    ])
    if kod != 0:
        uyarilar.append("Ses incelenemedi; ses başlangıcı ve sessiz aralıklar boş bırakıldı.")
        return None, []
    baslar = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", hata)]
    bitisler = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", hata)]
    araliklar = []
    for i, b in enumerate(baslar):
        s = bitisler[i] if i < len(bitisler) else sure
        araliklar.append((max(0.0, b), min(sure, s)))
    if araliklar and araliklar[0][0] <= 0.03:
        if araliklar[0][1] >= sure - 0.05:
            uyarilar.append("Videonun sesi baştan sona %d dB altında; ses yok sayıldı." % SES_ESIGI_DB)
            ses_baslangic = None
        else:
            ses_baslangic = yuvarla(araliklar[0][1])
    else:
        ses_baslangic = 0.0
    uzunlar = [[yuvarla(b), yuvarla(s)] for b, s in araliklar if s - b >= SESSIZLIK_EN_AZ_SN]
    return ses_baslangic, uzunlar


def kesmeleri_bul(yol, uyarilar):
    kod, _, hata = calistir([
        "ffmpeg", "-hide_banner", "-nostdin", "-i", yol, "-an", "-map", "0:v:0",
        "-vf", "select='gt(scene,%s)',showinfo" % SAHNE_ESIGI, "-f", "null", "-"
    ])
    if kod != 0:
        uyarilar.append("Sahne kesmeleri bulunamadı (ffmpeg görüntüyü işleyemedi).")
        return []
    zamanlar = []
    for satir in hata.splitlines():
        if "Parsed_showinfo" in satir and "pts_time:" in satir:
            m = re.search(r"pts_time:\s*(-?[\d.]+)", satir)
            if m:
                zamanlar.append(yuvarla(float(m.group(1))))
    return sorted(set(zamanlar))


# ----------------------------------------------------------------------------
# Kareler ve temas sayfası
# ----------------------------------------------------------------------------

def kare_adi(sn):
    return "kare_%05.1f.jpg" % sn


def kare_zamanlari(sure, kesmeler, anlar, uyarilar):
    """0,1,2,3 + her kesmenin 0.2 saniye sonrası + her 5 saniye (en fazla 40) + istenen anlar.

    Birbirine 1 saniyeden yakın kareler tekilleştirilir; öncelik sırası: ilk dört saniye,
    kesme kareleri, 5 saniyelik aralık kareleri. İstenen anlar her zaman alınır.
    """
    son = max(0.0, sure - 0.1)
    sabit = [float(t) for t in (0, 1, 2, 3) if t <= son]
    if not sabit:
        sabit = [0.0]
    adaylar = [round(min(k + 0.2, son), 1) for k in kesmeler]
    t = 5.0
    while t <= son:
        adaylar.append(t)
        t += 5.0
    ek = []
    for a in adaylar:
        if all(abs(a - b) >= 1.0 for b in sabit + ek):
            ek.append(a)
    ek.sort()
    yer = EN_FAZLA_KARE - len(sabit)
    if len(ek) > yer:
        adim = len(ek) / float(yer)
        ek = [ek[int(i * adim)] for i in range(yer)]
        uyarilar.append(
            "Kare sayısı %d ile sınırlı olduğu için kesme ve 5 saniyelik aralık karelerinin "
            "bir kısmı eşit aralıkla seçildi." % EN_FAZLA_KARE
        )
    hepsi = set(sabit + ek)
    an_kareleri = {}
    for a in anlar:
        t = round(min(max(a, 0.0), son), 1)
        an_kareleri[a] = t
        hepsi.add(t)
    return sorted(hepsi), an_kareleri


def kareleri_cikar(yol, zamanlar, klasor, uyarilar):
    kareler = []
    for t in zamanlar:
        ad = kare_adi(t)
        hedef = os.path.join(klasor, ad)
        kod, _, _ = calistir([
            "ffmpeg", "-hide_banner", "-nostdin", "-y", "-ss", "%.3f" % t, "-i", yol,
            "-map", "0:v:0", "-frames:v", "1", "-vf", "scale=%d:-2" % KARE_GENISLIK,
            "-q:v", "4", hedef
        ])
        if kod == 0 and os.path.isfile(hedef) and os.path.getsize(hedef) > 0:
            kareler.append({"sn": t, "dosya": ad})
        else:
            uyarilar.append("%s saniyesindeki kare çıkarılamadı." % ("%.1f" % t).replace(".", ","))
    return kareler


def kare_parlakligi(yol):
    """Karenin ortalama parlaklığı ve en koyu ile en açık nokta farkı (0 ile 255 arası). Ölçülemezse None."""
    kod, _, hata = calistir(["ffmpeg", "-hide_banner", "-nostdin", "-i", yol,
                             "-vf", "signalstats,metadata=mode=print", "-f", "null", "-"])
    if kod != 0:
        return None
    d = {}
    for ad in ("YAVG", "YMIN", "YMAX"):
        m = re.search(r"signalstats\." + ad + r"=([\d.]+)", hata)
        if not m:
            return None
        d[ad] = float(m.group(1))
    return {"ortalama": d["YAVG"], "yayilim": d["YMAX"] - d["YMIN"]}


def kare_bos_mu(p):
    """En koyu ve en açık nokta birbirine yakınsa kare boş sayılır (düz siyah, düz renk)."""
    return p is not None and p["yayilim"] < BOS_KARE_YAYILIM


def ilk_3sn_gorsel(kareler, klasor, uyarilar):
    """İlk karenin boş olup olmadığını ve 0. ile 3. saniye kareleri arasındaki değişimi ölçer.

    Kesme tespitinden bağımsızdır. Döndürür: (benzerlik, degisiyor, ilk_kare_bos, neden).
    Değişiyor sayılır: ssim eşiğin altındaysa, ilk kare boşken 3. saniye karesi doluysa
    ya da iki karenin ortalama parlaklığı 10 birimden fazla ayrışıyorsa.
    """
    dosyalar = {k["sn"]: k["dosya"] for k in kareler}
    p0 = kare_parlakligi(os.path.join(klasor, dosyalar[0.0])) if 0.0 in dosyalar else None
    ilk_bos = kare_bos_mu(p0) if p0 is not None else None
    if ilk_bos:
        uyarilar.append("İlk kare boş ya da tek renk; akışta video boş görünür.")
    if 0.0 not in dosyalar or 3.0 not in dosyalar:
        uyarilar.append("Video 3 saniyeden kısa ya da kareler çıkarılamadı; ilk 3 saniyenin görsel değişimi ölçülemedi.")
        return None, None, ilk_bos, None
    a, b = os.path.join(klasor, dosyalar[0.0]), os.path.join(klasor, dosyalar[3.0])
    p3 = kare_parlakligi(b)

    benzerlik = None
    kod, _, hata = calistir(["ffmpeg", "-hide_banner", "-nostdin", "-i", a, "-i", b,
                             "-lavfi", "[0:v][1:v]ssim", "-f", "null", "-"])
    m = re.search(r"SSIM.*All:\s*([\d.]+)", hata) if kod == 0 else None
    if m:
        benzerlik = max(0.0, min(1.0, float(m.group(1))))
    else:
        kod, _, hata = calistir(["ffmpeg", "-hide_banner", "-nostdin", "-i", a, "-i", b,
                                 "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-"])
        m = re.search(r"PSNR.*average:\s*(inf|[\d.]+)", hata) if kod == 0 else None
        if m:
            benzerlik = 1.0 if m.group(1) == "inf" else max(0.0, min(1.0, float(m.group(1)) / 50.0))
            uyarilar.append("ffmpeg ssim ölçemedi; ilk 3 saniyenin benzerliği psnr ile yaklaşık hesaplandı.")

    nedenler = []
    if benzerlik is not None and benzerlik < GORSEL_DEGISIM_ESIGI:
        nedenler.append("benzerlik_dusuk")
    if ilk_bos and p3 is not None and not kare_bos_mu(p3):
        nedenler.append("ilk_kare_bos_sonra_dolu")
    if p0 is not None and p3 is not None and abs(p0["ortalama"] - p3["ortalama"]) > PARLAKLIK_FARKI_ESIGI:
        nedenler.append("parlaklik_farki")
    if benzerlik is None and p3 is None:
        uyarilar.append("İlk 3 saniyenin görsel değişimi ölçülemedi (ffmpeg kareleri karşılaştıramadı).")
        return None, None, ilk_bos, None
    return (yuvarla(benzerlik, 3) if benzerlik is not None else None, bool(nedenler), ilk_bos,
            ";".join(nedenler) if nedenler else "degisim_yok")


def yazi_tipi_bul():
    adaylar = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for a in adaylar:
        if os.path.isfile(a):
            return a
    if shutil.which("fc-match"):
        try:
            kod, cikti, _ = calistir(["fc-match", "-f", "%{file}", "sans"], 20)
            if kod == 0 and os.path.isfile(cikti.strip()):
                return cikti.strip()
        except Hata:
            pass
    return None


def drawtext_var_mi():
    kod, cikti, _ = calistir(["ffmpeg", "-hide_banner", "-filters"], 30)
    return kod == 0 and re.search(r"\bdrawtext\b", cikti) is not None


def temas_sayfasi_yap(kareler, an_zamanlari, klasor, uyarilar):
    """Kareleri 4 sütunluk tek görüntüde birleştirir; her karenin altına saniyesini yazar."""
    if not kareler:
        uyarilar.append("Kare çıkarılamadığı için temas sayfası üretilmedi.")
        return False
    hedef = os.path.join(klasor, "temas_sayfasi.jpg")
    yazili = drawtext_var_mi()
    yazi_tipi = yazi_tipi_bul() if yazili else None
    satir = int(math.ceil(len(kareler) / 4.0))

    def uret(yazi_ile):
        with tempfile.TemporaryDirectory(prefix="eldenele_") as gecici:
            for i, k in enumerate(kareler, 1):
                kaynak = os.path.join(klasor, k["dosya"])
                hucre = os.path.join(gecici, "h_%04d.jpg" % i)
                suzgec = "scale=270:-2,pad=iw:ih+40:0:0:color=black"
                if yazi_ile:
                    etiket = ("%.1f" % k["sn"]).replace(".", ",") + " saniye"
                    renk = "white"
                    if k["sn"] in an_zamanlari:
                        etiket += " (istenen an)"
                        renk = "yellow"
                    metin_dosyasi = os.path.join(gecici, "y_%04d.txt" % i)
                    with open(metin_dosyasi, "w", encoding="utf-8") as f:
                        f.write(etiket)
                    cizim = "drawtext=textfile='%s':fontcolor=%s:fontsize=20:x=(w-text_w)/2:y=h-30" % (
                        suzgec_kacis(metin_dosyasi), renk)
                    if yazi_tipi:
                        cizim += ":fontfile='%s'" % suzgec_kacis(yazi_tipi)
                    suzgec += "," + cizim
                kod, _, _ = calistir(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", kaynak,
                                      "-vf", suzgec, "-frames:v", "1", "-q:v", "3", hucre])
                if kod != 0:
                    return False
            kod, _, _ = calistir([
                "ffmpeg", "-hide_banner", "-nostdin", "-y", "-framerate", "1",
                "-i", os.path.join(gecici, "h_%04d.jpg"),
                "-vf", "tile=4x%d:padding=6:margin=6:color=black" % satir,
                "-frames:v", "1", "-q:v", "3", hedef
            ])
            return kod == 0 and os.path.isfile(hedef)

    if yazili and uret(True):
        return True
    if uret(False):
        uyarilar.append(
            "Temas sayfası yazısız üretildi (ffmpeg kareye yazı çizemedi). "
            "Karelerin saniyesi inceleme.json içindeki kareler listesinde sırayla duruyor."
        )
        return True
    uyarilar.append("Temas sayfası üretilemedi; tek tek kare dosyalarına bak.")
    return False


# ----------------------------------------------------------------------------
# Altyazı okuma
# ----------------------------------------------------------------------------

ZAMAN_PARCA = r"(?:(\d{1,3}):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?"
ZAMAN_SATIRI = re.compile(r"^\s*" + ZAMAN_PARCA + r"\s*-+>\s*" + ZAMAN_PARCA)


def dosya_metni(yol):
    try:
        with open(yol, "rb") as f:
            ham = f.read()
    except OSError:
        raise Hata("Altyazı dosyası açılamadı: %s. Yolu kontrol et." % yol)
    if ham.startswith(b"\xff\xfe") or ham.startswith(b"\xfe\xff"):
        metin = ham.decode("utf-16", "replace")
    else:
        metin = None
        for kod in ("utf-8-sig", "cp1254"):
            try:
                metin = ham.decode(kod)
                break
            except UnicodeDecodeError:
                continue
        if metin is None:
            metin = ham.decode("utf-8", "replace")
    return metin.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")


def saniyeye(saat, dakika, saniye, kesir):
    k = float("0." + kesir) if kesir else 0.0
    return int(saat or 0) * 3600 + int(dakika) * 60 + int(saniye) + k


def yazi_temizle(s):
    s = re.sub(r"<[^>]*>", "", s)
    s = re.sub(r"\{\\[^}]*\}", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", s).strip()


def zamanli_altyazi_oku(metin):
    """srt ve vtt için ortak okuyucu. [{'bas','son','yazi'}] döndürür."""
    satirlar = metin.split("\n")
    parcalar = []
    i = 0
    while i < len(satirlar):
        m = ZAMAN_SATIRI.match(satirlar[i])
        if not m:
            i += 1
            continue
        g = m.groups()
        bas = saniyeye(g[0], g[1], g[2], g[3])
        son = saniyeye(g[4], g[5], g[6], g[7])
        i += 1
        yazilar = []
        while i < len(satirlar) and satirlar[i].strip() != "":
            if ZAMAN_SATIRI.match(satirlar[i]):
                break
            # Boş satırsız dosyalarda sıra numarası bir sonraki zaman satırının hemen üstünde olur
            if (satirlar[i].strip().isdigit() and i + 1 < len(satirlar)
                    and ZAMAN_SATIRI.match(satirlar[i + 1])):
                break
            yazilar.append(satirlar[i])
            i += 1
        yazi = yazi_temizle(" ".join(yazilar))
        if yazi and son >= bas:
            parcalar.append({"bas": yuvarla(bas, 3), "son": yuvarla(son, 3), "yazi": yazi})
    parcalar.sort(key=lambda p: p["bas"])
    return parcalar


def duz_metin_oku(metin, bas, son):
    """Zamansız metni cümlelere böler, zamanı harf sayısına göre tahmini dağıtır."""
    temiz = []
    for s in metin.split("\n"):
        s = s.strip()
        if not s or s.upper().startswith("WEBVTT") or s.isdigit():
            continue
        temiz.append(yazi_temizle(s))
    govde = " ".join(t for t in temiz if t)
    if not govde:
        return []
    cumleler = [c.strip() for c in re.split(r"(?<=[.!?…])\s+", govde) if c.strip()]
    toplam = float(sum(len(c) for c in cumleler)) or 1.0
    sure = max(0.1, son - bas)
    parcalar, t = [], bas
    for c in cumleler:
        d = sure * len(c) / toplam
        parcalar.append({"bas": yuvarla(t, 2), "son": yuvarla(t + d, 2), "yazi": c})
        t += d
    return parcalar


def altyazi_oku(yol, ses_baslangic, sure, uyarilar):
    if not os.path.isfile(yol):
        raise Hata("Altyazı dosyası bulunamadı: %s. Yolu kontrol et ya da --altyazi seçeneğini kaldır." % yol)
    metin = dosya_metni(yol)
    if not metin.strip():
        uyarilar.append("Altyazı dosyası boş: %s. Konuşma metni okunamadı." % os.path.basename(yol))
        return [], False
    parcalar = zamanli_altyazi_oku(metin)
    if parcalar:
        tasan = [p for p in parcalar if p["bas"] > sure + 1.0]
        if tasan:
            uyarilar.append(
                "Altyazıdaki %d satır videonun süresinden sonra başlıyor. Altyazı bu videoya ait olmayabilir."
                % len(tasan)
            )
        return parcalar, True
    uzanti = os.path.splitext(yol)[1].lower()
    parcalar = duz_metin_oku(metin, ses_baslangic or 0.0, sure)
    if parcalar:
        if uzanti in (".srt", ".vtt"):
            uyarilar.append("Altyazı dosyasında zaman satırı bulunamadı; dosya düz metin olarak okundu.")
        uyarilar.append(
            "Metin zaman bilgisi içermiyor. Saniyeler konuşmanın videoya eşit yayıldığı varsayımıyla "
            "tahmin edildi; ilk soru, çağrı ve ders bloğu saniyeleri kesin değildir. Kesin sonuç için srt ver."
        )
    else:
        uyarilar.append("Altyazı dosyasında okunabilir metin bulunamadı: %s." % os.path.basename(yol))
    return parcalar, False


def whisper_dene(yol, uyarilar):
    """faster-whisper kuruluysa ve model yerelde duruyorsa konuşmayı metne döker."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return []
    model = None
    for ad in ("small", "base", "tiny", "medium", "large-v3"):
        try:
            model = WhisperModel(ad, device="cpu", compute_type="int8", local_files_only=True)
            break
        except Exception:
            continue
    if model is None:
        uyarilar.append(
            "faster-whisper kurulu ama yerelde indirilmiş model yok; otomatik metne dökme yapılamadı."
        )
        return []
    try:
        bolumler, _ = model.transcribe(yol, language="tr")
        parcalar = []
        for b in bolumler:
            yazi = yazi_temizle(b.text or "")
            if yazi:
                parcalar.append({"bas": yuvarla(b.start, 2), "son": yuvarla(b.end, 2), "yazi": yazi})
        return parcalar
    except Exception as e:
        uyarilar.append("faster-whisper çalışırken hata verdi (%s); metin çıkarılamadı." % type(e).__name__)
        return []


# ----------------------------------------------------------------------------
# Metin incelemesi
# ----------------------------------------------------------------------------

KENAR = " \t\"'“”‘’«».,;:!?…()[]{}-–*"
CUMLE_SONU = re.compile(r"[.!?…]+[\"'”’»)\]]*$")


def sozcuk_temizle(s):
    return kucuk(s.strip(KENAR))


def sozcuklere_ayir(parcalar):
    """Her sözcüğe tahmini bir başlangıç saniyesi verir (satır içinde harf sayısına göre)."""
    sozcukler = []
    for pi, p in enumerate(parcalar):
        ham = p["yazi"].split()
        toplam = float(sum(len(h) + 1 for h in ham)) or 1.0
        sure = max(0.0, p["son"] - p["bas"])
        gecen = 0.0
        for h in ham:
            sozcukler.append({"ham": h, "temiz": sozcuk_temizle(h),
                              "sn": p["bas"] + sure * gecen / toplam,
                              "parca": pi, "parca_son": p["son"]})
            gecen += len(h) + 1
    return sozcukler


def cumlelere_ayir(parcalar, uyarilar):
    """Altyazı satırlarını birleştirip cümlelere böler."""
    sozcukler = sozcuklere_ayir(parcalar)
    if not sozcukler:
        return []
    noktalama_var = sum(1 for s in sozcukler if CUMLE_SONU.search(s["ham"])) >= max(1, len(parcalar) // 12)
    if not noktalama_var and len(parcalar) > 3:
        uyarilar.append(
            "Altyazıda noktalama yok; cümleler duraklamalara göre ayrıldı. "
            "Soru ve ders bloğu tespiti bu yüzden daha zayıf olabilir."
        )
    cumleler, simdiki = [], []

    def kapat():
        if simdiki:
            cumleler.append({
                "bas": simdiki[0]["sn"], "son": simdiki[-1]["parca_son"],
                "yazi": " ".join(s["ham"] for s in simdiki), "sozcukler": list(simdiki)})
            del simdiki[:]

    for i, s in enumerate(sozcukler):
        if simdiki and s["parca"] != simdiki[-1]["parca"]:
            # Nokta konmamış satırlarda cümle sınırı duraklamadan anlaşılır
            bosluk = parcalar[s["parca"]]["bas"] - parcalar[simdiki[-1]["parca"]]["son"]
            if noktalama_var:
                if bosluk >= 0.6:
                    kapat()
            elif bosluk >= 0.3 or len(simdiki) >= 25:
                kapat()
        simdiki.append(s)
        if CUMLE_SONU.search(s["ham"]):
            # "3." gibi sıra sayısı ya da "1.000" gibi sayı cümle bitirmez
            if re.fullmatch(r"\d+\.", s["ham"]) and i + 1 < len(sozcukler) \
                    and sozcukler[i + 1]["ham"][:1].islower():
                continue
            kapat()
    kapat()
    return cumleler


SORU_EKI = re.compile(
    r"^m[ıiuü]"
    r"(y[ıiuü]m|s[ıiuü]n|y[ıiuü]z|s[ıiuü]n[ıiuü]z|d[ıiuü]r|d[ıiuü]rlar|lar|ler"
    r"|yd[ıiuü]|yd[ıiuü]m|yd[ıiuü]n|yd[ıiuü]k|yd[ıiuü]n[ıiuü]z|yd[ıiuü]lar|yd[ıiuü]ler"
    r"|ym[ıiuü]ş|ym[ıiuü]ş[ıiuü]m|ym[ıiuü]şs[ıiuü]n|ym[ıiuü]ş[ıiuü]z)?$"
)
# "müdür" çoğu zaman yönetici anlamındadır; yanlış alarm vermemesi için soru eki sayılmaz
SORU_EKI_DEGIL = {"müdür"}
SORU_SOZCUKLERI = {
    "neden", "nasıl", "niye", "niçin", "kim", "kimin", "kime", "kimi", "kimler",
    "hangi", "hangisi", "hangileri", "kaç", "kaçı", "kaçıncı",
}


def soru_mu(cumle):
    """Soru işareti, ayrı yazılan soru eki ya da soru sözcüğü var mı?"""
    if "?" in cumle["yazi"]:
        return True
    s = [x["temiz"] for x in cumle["sozcukler"]]
    for i, w in enumerate(s):
        if i > 0 and w not in SORU_EKI_DEGIL and SORU_EKI.match(w):
            return True
        if w in SORU_SOZCUKLERI:
            sonraki = s[i + 1] if i + 1 < len(s) else ""
            # "buna neden oldu" bir soru değil, sebep bildirir
            if w == "neden" and sonraki.startswith("ol"):
                continue
            return True
        if w == "ne" and i + 1 < len(s) and s[i + 1] == "zaman":
            return True
    return False


def ilk_soru(cumleler):
    for c in cumleler:
        if soru_mu(c):
            return yuvarla(c["bas"])
    return None


EDIMLER = r"(et|edin|ediniz|etmeyi|etsene|edersen|edebilirsin|edebilirsiniz)"
CAGRI_KALIPLARI = [
    ("gonder", re.compile(
        r"\b(gönder|gönderin|gönderiniz|göndersene|göndermeyi|gönderebilirsin|gönderebilirsiniz"
        r"|gönderir m[iı]sin\w*|yolla|yollayın|yollasana|ilet|iletin)\b")),
    ("paylas", re.compile(
        r"\b(paylaş|paylaşın|paylaşınız|paylaşsana|paylaşmayı|paylaşabilirsin|paylaşabilirsiniz"
        r"|paylaşır m[ıi]sın\w*)\b")),
    ("yorum", re.compile(
        r"\b(yorumlara|yorumlarda|yoruma|yorumda"
        r"|yorum(unu|unuzu|larını|larınızı|lar)? (yaz|yazın|bırak|bırakın|yap|yapın|at|atın|belirt|belirtin)\w*)\b")),
    ("takip", re.compile(
        r"\b(takip " + EDIMLER + r"|takipte kal\w*|takibe al\w*)\b")),
    ("abone", re.compile(r"\babone ol(un|unuz|mayı|sana|ursan|abilirsin)?\b")),
    ("link", re.compile(
        r"\b(link\w*|bağlantıya tıkla\w*|(profildeki|biyografideki|açıklamadaki) bağlantı\w*)\b")),
    ("kaydet", re.compile(
        r"\b(kaydet|kaydedin|kaydediniz|kaydetsene|kaydetmeyi|kaydedebilirsin|kaydedebilirsiniz)\b")),
]


def cagrilari_bul(cumleler, sure):
    """Cümle içindeki çağrıları bulur.

    sn: çağrının geçtiği cümlenin başladığı saniye (ilk_soru_sn ile aynı ölçü).
    kelime_sn: çağrı sözcüğünün tahmini söylendiği an.
    """
    bulunan = []
    for c in cumleler:
        temizler = [x["temiz"] for x in c["sozcukler"]]
        duz, konumlar, yer = "", [], 0
        for w in temizler:
            konumlar.append(yer)
            duz += w + " "
            yer += len(w) + 1
        for tur, kalip in CAGRI_KALIPLARI:
            m = kalip.search(duz)
            if not m:
                continue
            sira = max(i for i, k in enumerate(konumlar) if k <= m.start())
            bulunan.append({"sn": yuvarla(c["bas"]), "tur": tur, "yazi": c["yazi"],
                            "kelime_sn": yuvarla(c["sozcukler"][sira]["sn"], 1)})
    # Kapanış sorusu: son 10 saniyeye denk gelen soru cümlesi yorum çağrısı sayılır
    for c in cumleler:
        if c["son"] >= sure - 10.0 and soru_mu(c):
            bulunan.append({"sn": yuvarla(c["bas"]), "tur": "soru_kapanis", "yazi": c["yazi"],
                            "kelime_sn": yuvarla(c["bas"], 1)})
    bulunan.sort(key=lambda x: (x["sn"], x["kelime_sn"]))
    return bulunan


TANIM_KALIPLARI = [
    (re.compile(r"\beski (dilde|türkçede|türkçe'de)\b"), "eski dilde"),
    (re.compile(r"\bosmanlıca\w*\b"), "Osmanlıca"),
    (re.compile(r"\bköken(i|ine|inde|inden|li)\b"), "kökeni"),
    (re.compile(r"\banlam(ı|ına|ında|ındadır)\b"), "anlamı"),
    (re.compile(r"\byani\b"), "yani"),
]
SIRA_KALIPLARI = [
    (re.compile(r"\b(ilk|birinci|ikinci|üçüncü|dördüncü|beşinci|son) olarak\b"), None),
    (re.compile(r"^(sonra|ardından|önce|daha sonra|bundan sonra)\b"), None),
    (re.compile(r"^(birincisi|ikincisi|üçüncüsü|dördüncüsü)\b"), None),
]
# Tek başına blok başlatmaz; başlamış bir tanım anlatımının sürdüğünü gösterir
DEVAM_KALIPLARI = re.compile(
    r"\b(demek|demektir|denir|denirdi|deniyor|deniyordu|diyoruz|diyorlar|derler|derdi|derlerdi"
    r"|adı verilir|adı verilirdi)\b|(mak|mek)$"
)


def ders_tetikleyici(cumle):
    duz = " ".join(x["temiz"] for x in cumle["sozcukler"] if x["temiz"])
    for kalip, ad in TANIM_KALIPLARI:
        if kalip.search(duz):
            return ("tanim", ad)
    for kalip, _ in SIRA_KALIPLARI:
        m = kalip.search(duz)
        if m:
            return ("sira", m.group(0))
    return None


def ders_devami(cumle):
    duz = " ".join(x["temiz"] for x in cumle["sozcukler"] if x["temiz"])
    return DEVAM_KALIPLARI.search(duz) is not None


def ders_bloklarini_bul(cumleler):
    """Sözlük ya da ders gibi anlatılan, 5 saniyeden uzun bölümleri bulur."""
    bloklar = []
    i = 0
    while i < len(cumleler):
        t = ders_tetikleyici(cumleler[i])
        if not t:
            i += 1
            continue
        bas, son = cumleler[i]["bas"], cumleler[i]["son"]
        turler, kaliplar = {t[0]}, [t[1]]
        j = i + 1
        while j < len(cumleler) and cumleler[j]["bas"] - son <= 1.5:
            t2 = ders_tetikleyici(cumleler[j])
            if t2:
                turler.add(t2[0])
                if t2[1] not in kaliplar:
                    kaliplar.append(t2[1])
            elif not ders_devami(cumleler[j]):
                break
            son = cumleler[j]["son"]
            j += 1
        if son - bas > DERS_EN_AZ_SN:
            ad = ", ".join('"%s"' % k for k in kaliplar[:3])
            if turler == {"sira"}:
                neden = "Sıralı, adım adım anlatım (%s kalıbı)" % ad
            elif turler == {"tanim"}:
                neden = "Sözcük açıklaması ya da tanım anlatımı (%s kalıbı)" % ad
            else:
                neden = "Tanım ve sıralı anlatım bir arada (%s kalıbı)" % ad
            ilk_cumle = cumleler[i]["yazi"]
            if len(ilk_cumle) > 80:
                ilk_cumle = ilk_cumle[:77].rstrip() + "..."
            bloklar.append({"bas": yuvarla(bas, 1), "son": yuvarla(son, 1),
                            "neden": "%s: %s" % (neden, ilk_cumle)})
        i = j
    return bloklar


def andaki_yazi(sn, cumleler):
    """Verilen saniyede söylenen cümle; boşluğa denk gelirse en yakın cümle (1.5 saniye içinde)."""
    for c in cumleler:
        if c["bas"] - 0.05 <= sn <= c["son"] + 0.05:
            return c["yazi"]
    en_iyi, en_yakin = "", 1.5
    for c in cumleler:
        uzaklik = min(abs(sn - c["bas"]), abs(sn - c["son"]))
        if uzaklik <= en_yakin:
            en_iyi, en_yakin = c["yazi"], uzaklik
    return en_iyi


# ----------------------------------------------------------------------------
# Ana akış
# ----------------------------------------------------------------------------

def anlari_coz(deger):
    if not deger:
        return []
    anlar = []
    for parca in deger.replace(";", ",").split(","):
        parca = parca.strip()
        if not parca:
            continue
        try:
            a = float(parca)
        except ValueError:
            raise Hata(
                "--anlar değeri anlaşılamadı: '%s'. Saniyeleri virgülle ayır, kesir için nokta kullan. "
                "Örnek: --anlar 16,17.5" % parca
            )
        if a < 0 or a != a or a in (float("inf"),):
            raise Hata("--anlar içinde geçersiz saniye var: '%s'. Sıfır ya da daha büyük bir sayı yaz." % parca)
        if a not in anlar:
            anlar.append(a)
    return anlar


def incele(video, altyazi, anlar_metni, cikti):
    if not os.path.isfile(video):
        raise Hata("Video dosyası bulunamadı: %s. Yolu kontrol et." % video)
    if os.path.getsize(video) == 0:
        raise Hata("Video dosyası boş (0 bayt): %s. Videoyu yeniden dışa aktar." % video)
    for arac in ("ffmpeg", "ffprobe"):
        if not shutil.which(arac):
            raise Hata(
                "'%s' bulunamadı. Bu betik ffmpeg ve ffprobe ister. "
                "Kur (ör. 'apt install ffmpeg' ya da 'brew install ffmpeg') ve yeniden dene." % arac
            )
    anlar = anlari_coz(anlar_metni)
    if altyazi and not os.path.isfile(altyazi):
        raise Hata("Altyazı dosyası bulunamadı: %s. Yolu kontrol et ya da --altyazi seçeneğini kaldır." % altyazi)

    uyarilar = []
    bilgi = video_bilgisi(video)
    sure = bilgi["sure"]

    video_adi = os.path.splitext(os.path.basename(video))[0] or "video"
    klasor = os.path.join(cikti, video_adi)
    try:
        os.makedirs(klasor, exist_ok=True)
    except OSError:
        raise Hata("Çıktı klasörü oluşturulamadı: %s. Yazma izni olan bir klasör ver." % klasor)

    if bilgi["ses_var"]:
        ses_baslangic, sessizler = ses_incele(video, sure, uyarilar)
    else:
        ses_baslangic, sessizler = None, []
        uyarilar.append("Videoda ses akışı yok; ses başlangıcı ve sessiz aralıklar boş bırakıldı.")

    kesmeler = [k for k in kesmeleri_bul(video, uyarilar) if 0 <= k <= sure]
    dilim = int(math.ceil(sure / 10.0)) or 1
    siklik = [0] * dilim
    for k in kesmeler:
        siklik[min(dilim - 1, int(k // 10))] += 1

    if len(kesmeler) < sure / 10.0:
        uyarilar.append(
            "Kesme sayısı süreye göre düşük (10 saniyede 1'in altında): yumuşak geçişli video olabilir, "
            "kesme sayısı düşük ölçülmüş olabilir."
        )

    gecerli_anlar = []
    for a in anlar:
        if a > sure:
            uyarilar.append(
                "İstenen an (%s saniye) videonun süresini aşıyor; atlandı."
                % ("%g" % a).replace(".", ",")
            )
        else:
            gecerli_anlar.append(a)

    # Önceki çalıştırmadan kalan kareler karışmasın
    for eski in os.listdir(klasor):
        if re.fullmatch(r"kare_\d+\.\d\.jpg", eski) or eski == "temas_sayfasi.jpg":
            try:
                os.remove(os.path.join(klasor, eski))
            except OSError:
                pass

    zamanlar, an_kareleri = kare_zamanlari(sure, kesmeler, gecerli_anlar, uyarilar)
    kareler = kareleri_cikar(video, zamanlar, klasor, uyarilar)
    var_olan = {k["sn"]: k["dosya"] for k in kareler}
    temas_sayfasi_yap(kareler, set(an_kareleri.values()), klasor, uyarilar)
    benzerlik, degisiyor, ilk_bos, degisim_nedeni = ilk_3sn_gorsel(kareler, klasor, uyarilar)

    # Metin
    parcalar, kaynak, zamanli = [], "yok", False
    if altyazi:
        parcalar, zamanli = altyazi_oku(altyazi, ses_baslangic, sure, uyarilar)
        if parcalar:
            kaynak = "altyazi"
    if not parcalar:
        parcalar = whisper_dene(video, uyarilar)
        if parcalar:
            kaynak = "whisper"
            uyarilar.append("Metin faster-whisper ile otomatik çıkarıldı; sözcük hataları olabilir.")
    if not parcalar:
        uyarilar.append(ALTYAZI_YOK_UYARISI)

    kapsam = None
    if parcalar:
        kapsam_son = max(p["son"] for p in parcalar)
        kapsam = {"bas": yuvarla(parcalar[0]["bas"]), "son": yuvarla(kapsam_son),
                  "eksik_son_sn": yuvarla(max(0.0, sure - kapsam_son))}
        if kaynak == "altyazi" and zamanli:
            if sure - kapsam_son > 2.0:
                uyarilar.append(
                    "Altyazı videonun son %s saniyesini kapsamıyor; kapanıştaki çağrı ve sözler ölçülmemiş "
                    "olabilir. Yayınlanan son halin altyazısını ver."
                    % ("%.1f" % (sure - kapsam_son)).replace(".", ",")
                )
            elif kapsam_son - sure > 2.0:
                uyarilar.append(
                    "Altyazı videodan %s saniye uzun; başka bir sürüme ait olabilir ve saniyeler kaymış "
                    "olabilir. Yayınlanan son halin altyazısını ver."
                    % ("%.1f" % (kapsam_son - sure)).replace(".", ",")
                )

    cumleler = cumlelere_ayir(parcalar, uyarilar)
    sozcukler = [s for c in cumleler for s in c["sozcukler"]]
    kelime_sayisi = sum(1 for s in sozcukler if re.search(r"\w", s["ham"]))
    if parcalar:
        konusma_suresi = parcalar[-1]["son"] - parcalar[0]["bas"]
        dakikada = yuvarla(kelime_sayisi / konusma_suresi * 60.0, 1) if konusma_suresi > 0 else None
    else:
        dakikada = None
    ilk_3sn = " ".join(s["ham"] for s in sozcukler if s["sn"] < 3.0)

    an_listesi = []
    for a in gecerli_anlar:
        an_listesi.append({"sn": a, "yazi": andaki_yazi(a, cumleler),
                           "kare": var_olan.get(an_kareleri[a])})

    sonuc = {
        "dosya": os.path.basename(video),
        "sure_sn": yuvarla(sure),
        "genislik": bilgi["genislik"],
        "yukseklik": bilgi["yukseklik"],
        "dikey": bilgi["yukseklik"] > bilgi["genislik"],
        "ses_baslangic_sn": ses_baslangic,
        "sessiz_araliklar": sessizler,
        "kesmeler_sn": kesmeler,
        "kesme_sikligi_10sn": siklik,
        "ilk_3sn_benzerlik": benzerlik,
        "ilk_3sn_gorsel_degisiyor": degisiyor,
        "ilk_3sn_degisim_nedeni": degisim_nedeni,
        "ilk_kare_bos": ilk_bos,
        "kareler": kareler,
        "metin_kaynagi": kaynak,
        "metin": [{"bas": yuvarla(p["bas"]), "son": yuvarla(p["son"]), "yazi": p["yazi"]} for p in parcalar],
        "altyazi_kapsami": kapsam,
        "kelime_sayisi": kelime_sayisi,
        "dakikada_kelime": dakikada,
        "ilk_soru_sn": ilk_soru(cumleler),
        "ilk_3sn_metin": ilk_3sn,
        "cagrilar": cagrilari_bul(cumleler, sure),
        "ders_bloklari": ders_bloklarini_bul(cumleler),
        "anlar": an_listesi,
        "uyarilar": uyarilar,
    }
    hedef = os.path.join(klasor, "inceleme.json")
    with open(hedef, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return hedef, sonuc


def main():
    ayristirici = argparse.ArgumentParser(
        description="Kısa videoyu inceler: ses, kesmeler, kareler, ilk soru, çağrılar, ders blokları.",
        epilog="Örnek: python3 video_incele.py video.mp4 --altyazi video.srt --anlar 16,17.5 --cikti cikti",
    )
    ayristirici.add_argument("video", help="İncelenecek video dosyası (mp4, mov ...)")
    ayristirici.add_argument("--altyazi", help="Altyazı dosyası: .srt, .vtt ya da düz metin .txt")
    ayristirici.add_argument("--anlar", help="Ayrıca bakılacak saniyeler, virgülle ayrılmış. Örnek: 16,17.5")
    ayristirici.add_argument("--cikti", required=True, help="Çıktı klasörü")
    a = ayristirici.parse_args()
    try:
        hedef, sonuc = incele(a.video, a.altyazi, a.anlar, a.cikti)
    except Hata as e:
        print("HATA: %s" % e, file=sys.stderr)
        return 2
    soru = sonuc["ilk_soru_sn"]
    print("İnceleme bitti: %s" % hedef)
    print("Süre %s saniye, %d kesme, %d kare, metin kaynağı: %s, ilk soru: %s" % (
        ("%.1f" % sonuc["sure_sn"]).replace(".", ","), len(sonuc["kesmeler_sn"]), len(sonuc["kareler"]),
        sonuc["metin_kaynagi"],
        "yok" if soru is None else ("%.1f" % soru).replace(".", ",") + ". saniye"))
    for u in sonuc["uyarilar"]:
        print("UYARI: %s" % u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
