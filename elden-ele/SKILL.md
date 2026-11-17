---
name: elden-ele
description: Reels, Shorts ve TikTok videolarını inceler. Veriyi hesaptan kendisi çeker ya da ekran görüntüsü ve CSV'den okur; videoyu izleyip hangi videonun hangi saniyede neden kaybettiğini ve neden gönderilmediğini kanıtla bulur. Tetikleyici: videom neden tutmadı, reels analiz, kısa video incele, elden ele.
---

# Elden Ele

Kısa videonun dağıtımını büyük ölçüde izleyicinin onu birine göndermesi belirler. Bu skill kullanıcının hesap verisini çeker ya da okur, videoyu betiklerle ölçer, Türkçe sıra dışı videolarla karşılaştırır ve her video için kanıtlı bir sonuç verir: hangi saniyede kaybetti, neden, sonraki videoda ne değişmeli.

Claude'da kod çalıştırma açık olmalı. Hazırlayan: Serhat Kaya (Instagram @imzabirturk).

## Çalışma sırası

### 1. Bağlantıyı seç
Bu skill hiçbir ücretli çağrı yapmaz. Bütün veri ya kullanıcının kendi hesabından ücretsiz çekilir ya da kullanıcının indirdiği dosyadan ve ekran görüntüsünden okunur.

Önce oturumda `vidiq_` ile başlayan araçlar var mı bak.

**Varsa:** Instagram sayılarını kendin çek (2. adım). Bu çağrı kullanıcının kendi vidIQ hesabıyla yapılır ve kredi harcamaz.

**Yoksa:** Instagram kullanıcısına bir kez şunu öner: "Claude'un bağlayıcılarından vidIQ'yu kendi ücretsiz hesabınla eklersen ve orada Instagram hesabını bağlarsan Reels sayılarını ben çekerim; kredi harcanmaz." Kabul etmezse 3. adıma geç. Israr etme.

YouTube ve TikTok için her zaman 3. adım: Studio'dan indirilen CSV ve ekran görüntüsü.

Neden bağlayıcı: Claude'un kod ortamı Instagram ve Google adreslerine çoğu planda doğrudan bağlanamaz. Bağlayıcı bu engele takılmaz.

### 2. Instagram verisini bağlayıcıdan çek (kredisiz)
Yalnız şu iki aracı kullan; ikisi de 0 kredi:
1. `vidiq_social_account_list`, `platform: INSTAGRAM`: hesabın `platformAccountId` değerini al.
2. `vidiq_instagram_owner_insights`, `platformAccountId`, `mode: reels`, `limit: 25`, `since` (daha eski Reels için dönen `nextUntil` değerini `until` olarak ver). Çıktının tamamını `ig.json` dosyasına yaz; `thumbnailUrl` gibi uzun bağlantıları çıkarabilirsin.

**Kredi harcayan hiçbir vidIQ aracını çağırma** (YouTube analizi, video izleme, rakip profili, sıra dışı video araması dahil). Kullanıcı açıkça istese bile önce bunun skill'in dışında olduğunu ve kredi harcayacağını söyle.

- Çıktıda `isPossibleTrial` olan deneme Reels'leri betik hesap ortalamasına katmaz.
- Instagram'da tutma grafiği bağlayıcıdan gelmez; en zayıf 1-3 video için kullanıcıdan telefondaki istatistik ekranının görüntüsünü iste (3. adım).
- Bağlantı süresi dolmuşsa araç bunu söyler; kullanıcıdan vidIQ'da Instagram'ı yeniden bağlamasını iste.

### 3. Dosya ve ekran görüntüsü (YouTube, TikTok, bağlayıcısız Instagram, tutma grafikleri)
Kullanıcıya `references/veri-toplama.md`'deki yolu göster. Gelen ekran görüntülerini kendin incele, değerleri `elle.csv` dosyasına yaz:
`video_id,baslik,platform,yayin_tarihi,sure_sn,goruntuleme,erisim,begeni,yorum,paylasim,kaydetme,ort_izleme_sn,kaydirma_orani,link,etiket`
- Okuyamadığın değeri boş bırak, tahmin etme.
- "Paylaşım", "Gönderim", "Shares", "Sends" aynı alandır: `paylasim`.
- Okuduğun tabloyu kullanıcıya göster ve onaylat. Onay gelmeden betik çalıştırma.

**Tutma grafiği** ekran görüntüsünden `tutma.json`:
`{"VIDEO_ID":[{"sn":0,"yuzde":100},{"sn":3,"yuzde":..}, ...]}`
Noktaları 0, 1, 2, 3, 5, 8, 10. saniyelerde, sonra her %10'luk süre diliminde ve son saniyede oku; belirgin kırılmaları ekle. Bu değerler ±5 puan yaklaşıktır.

**Rakip ızgarası** ekran görüntüsünden `rakip.csv`: `hesap,video,goruntuleme`.

### 4. Etiketle
Konu türüne göre desen (ör. "gündem videoları daha çok gönderiliyor") için her videoya bir etiket gerekir. Video başlıklarını kullanıcıya listele, etiketleri birlikte koy (ör. gündem, tarih, eğitim, eğlence) ve `etiket.csv` olarak yaz: `video_id,etiket`. Kullanıcı istemezse atla; rapor konu deseni çıkarmadığını söyler.

### 5. Betikleri çalıştır
Çalışma klasörünü skill klasöründen ayrı tut. `SKILL` yerine bu skill'in kurulu olduğu klasörün tam yolunu yaz. Kullanıcıya komut gösterirsen köşeli parantez kullanma, yalnız kullanılan argümanları yaz.

**a. Sayıları birleştir** (elindeki bütün dosyalar; olmayanı yazma):
```bash
python3 SKILL/scripts/veri_birlestir.py ig.json youtube-studio.csv tiktok-studio.csv elle.csv etiket.csv --rakip rakip.csv --cikti calisma
```

**b. Her videoyu incele** (her video için ayrı komut):
```bash
python3 SKILL/scripts/video_incele.py reels1.mp4 --altyazi reels1.srt --anlar 17 --cikti calisma/videolar
```
- Çıktı klasörünün adı dosya adından gelir: `reels1.mp4` için `calisma/videolar/reels1/`.
- `--anlar`: tutma grafiği varsa düşüş saniyeleri, yoksa ortalama izleme saniyesi. Virgülle birden çok: `--anlar 3,17,30`.
- Konuşma metne dökülemezse betik söyler; kullanıcıdan srt iste (CapCut otomatik altyazı, YouTube Studio altyazı indirme) ya da konuşma metnini yapıştırmasını iste.
- "Altyazı videonun sonunu kapsamıyor" uyarısında yayınlanan son halin altyazısını iste.

**c. Raporu üret** (her incelenen video için bir `--inceleme` ve `--video-id` çifti):
```bash
python3 SKILL/scripts/rapor.py --ozet calisma/ozet.json --tablo calisma/tablo.csv \
  --inceleme calisma/videolar/reels1/inceleme.json --video-id REELS1_ID \
  --tutma tutma.json --cikti calisma/rapor
```
`video-id`: Instagram'da bağlantıdaki kısa kod (ör. `DfsnVrysiXm`), YouTube'da video kimliği, TikTok'ta video numarası.

### 6. Videoya ve metne kendin bak
Betik sayıları ölçer, anlamı sen okursun. `references/turkce-ornekler.md`'yi oku; karşılaştırma zemini orada.

**Kare sayfası** (`calisma/videolar/reels1/temas_sayfasi.jpg`):
- İlk kare: konuyu gösteren görsel ve ekranda okunur bir yazı var mı?
- İlk karede dikkati konudan alan bir şey var mı (logo, maskot, alakasız süs, küçük yazı)?
- Düşüş anlarındaki karelerde ne oluyor?

**Metin** (`inceleme.json` içindeki `metin`):
- İlk 3 saniye hangi türde: iddia, soru, çerçeve ya da oyun, sahnenin ortası, tanıyor musunuz, gündelik nesneden tarihe? Hiçbiri değilse (yalnız bilgi, yalnız istatistik) bunu yaz.
- En güçlü cümle (izleyicinin birine aktarmak isteyeceği cümle) ve saniyesi.
- Ders anlatır gibi giden bölümler. Bunları ancak tutma grafiğinde orada düşüş varsa ya da kaydırma yüksekse sorun diye yaz; bir sonuca hızla akan liste izlenir.
- Gönderme sebebi ne: duygu (gurur, öfke, şaşkınlık), kimlik, işe yarar bilgi, birine söylenecek bir şey? Videonun neresinde kuruluyor?

Bulduklarını `okuma.md` dosyasına yaz (video başına başlık, maddeler, her maddede saniye) ve 5c komutunu sonuna `--okuma okuma.md` ekleyerek yeniden çalıştır. Okuman raporun en üstüne girer.

### 7. Sonucu ver
`calisma/rapor/rapor.md` dosyasını okuyarak kontrol et. Kullanıcıya `rapor.html` dosyasını ver (görseller içinde, tek dosya). Sohbette en fazla 5 satır yaz:
- Hesabın gönderme oranı ortancası ve videoların bantları.
- En zayıf videonun bir cümlelik nedeni, saniyesiyle.
- Hesap genelindeki en güçlü desen.
- Sonraki video için en fazla 3 değişiklik.

Hüküm kuralları:
- Her hüküm bir sayıya ya da saniyeye dayanır.
- Bir desen 3 videoda tekrarlanmadan "hesabın deseni" deme.
- Ekran görüntüsünden okunanı "yaklaşık" diye işaretle; gönderme sayısı 10'un altındaysa oranı kesin hüküm gibi yazma.
- Türkçe sıra dışı örneklerle çelişen katı kural koyma (süre, soru saniyesi, kapanış çağrısı); kararı hesabın kendi verisi verir.
- Konu seçimini kötüleme; gönderilmeyen konuda gönderme sebebinin videonun içinde nasıl kurulacağını öner.

### 8. Sonraki video: uyarlama kartı ve metin kapısı
Raporu verdikten sonra kullanıcıya bir kez sor: "Sıra dışı videondaki kalıbı bir sonraki konuna uyarlayayım mı?" Kabul ederse `references/uyarlama-karti.md`'yi uygula: kaynak videonun kartını doldur, kullanıcının sonraki konusu için 2 açılış seçeneği, ilk kare ve gönderme sebebi öner.

Kullanıcı yeni bir metin getirirse `references/metin-kapisi.md`'den geçir. Eşikleri hesabın kendi raporundan al.

## Bilmen gerekenler (kullanıcıya açıkça söyle)
- **Ücretsiz:** skill hiçbir ücretli çağrı yapmaz. vidIQ kullanılıyorsa kullanıcının kendi ücretsiz hesabıyla, vidIQ'nun 0 kredi olarak tanımladığı iki çağrıyla çalışır; kredi düşmez. Bağlayıcı herhangi bir sebeple çalışmazsa araç ekran görüntüsü ve dosyayla devam eder.
- **Tutma grafiği** Instagram, YouTube ve TikTok'ta uygulamanın ya da Studio'nun istatistik ekranında görünür, dışa aktarılan dosyaya girmez. Araç en zayıf 1-3 video için ekran görüntüsünü ister ve okur; okuma ±5 puan yaklaşıktır.
- **Erişim:** Instagram bağlayıcı çıktısında erişim yoktur; gönderme oranı görüntüleme üzerinden hesaplanır ve raporda belirtilir. Ekran görüntüsünde erişim varsa onunla düzeltilir.
- **Rakip videolar:** profil ızgarasının ekran görüntüsünden herkese açık izlenmeler okunur; rakip yalnız kendi ortalamasına göre değerlendirilir.
- **Konuşma metni:** Claude'un ortamı konuşmayı her zaman metne dökemeyebilir; o durumda srt ya da düz metin istenir. Claude Code'da konuşma modeli kuruluysa kendisi döker.
- **Yeni videolar:** yayından 48 saat geçmemiş videolar "yeni" diye işaretlenir ve hesap ortalamasına katılmaz.
- **Az gönderme:** bir platformda gönderme sayıları çok küçükse (ör. YouTube Shorts'ta 0-3) o platformda bant çıkarılmaz; izlemeye devam oranı ve izleme yüzdesi kullanılır.
