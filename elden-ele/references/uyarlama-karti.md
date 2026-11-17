# Uyarlama kartı: sıra dışı videodan sonraki videona

Bir videonun neden tuttuğunu anlatmak yetmez; kalıbı kullanıcının bir sonraki konusuna taşımak gerekir. Kart ücretsizdir, Claude doldurur.

## Kaynak video
Öncelik sırası:
1. Kullanıcının kendi sıra dışı videosu (raporda "Hesabın sıra dışı videoları"). Elde ölçümü ve dosyası olduğu için en güvenilir kaynak budur.
2. Kullanıcının verdiği bir rakip ya da ilham videosu: bağlantı, ekran görüntüsü ya da video dosyası. Dosya varsa `video_incele.py` ile ölç; yoksa kullanıcıdan videonun ilk 3 saniyesini ve kapanışını anlatmasını iste.
3. `turkce-ornekler.md`'deki örnekler.

## Kart (kaynak video için doldur)
| Alan | Kaynak videoda | Kanıt |
|---|---|---|
| İlk 3 saniye türü | iddia / soru / çerçeve / sahnenin ortası / kanıt | ilk 3 saniyede söylenen ve ilk kare |
| İlk kare | ne görünüyor, yazı var mı | kare sayfası |
| İzleyiciyi tutan şey | merak, zaman baskısı, tehlike, kimlik, şaşkınlık | metin |
| Gönderme sebebi | kime, neden gönderilir | metin ve kapanış |
| Süre ve tempo | saniye, dakikada kelime | inceleme |
| Ölçülen sonuç | kaç kat, gönderme sayısı, kaydırma | rapor |

## Uyarlama (kullanıcının sonraki konusu için)
Kullanıcıdan sonraki videonun konusunu iste. Sonra:
1. Kaynak videonun ilk 3 saniye türünü bu konuya uygula; **2 açılış seçeneği** yaz (her biri en fazla iki cümle, ekranda yazacak tek satırla birlikte).
2. İlk kare için ne gösterileceğini öner: konunun en somut, gerçek görüntüsü.
3. Gönderme sebebini bu konuda kim için, nerede kurulacağıyla yaz.
4. Süreyi hesabın kendi süre deseninden al; desen yoksa kaynak videonun süresini önerme, "hesabında süre deseni çıkmadı" de.
5. Metin yazılırsa `metin-kapisi.md`'den geçir.

Kopyalama yok: kalıp taşınır, cümle taşınmaz. Kaynak videodan cümle, görsel ya da başlık aynen alınmaz.

## Örnek (bu skill'in geliştirildiği hesaptan)
Kaynak: 161 saniyelik bir Kapadokya Reels'i, hesap ortancasının yaklaşık 63 katı izlendi, 2.895 kez gönderildi, kaydırma %30 (hesabın en düşüğü).
- İlk 3 saniye: kanıt ve zaman farkı. "Bu fotoğraf 3 Ekim'de çekildi. Kaya 26 gün sonra çöktü." İlk karede bir izleyicinin çektiği gerçek fotoğraf, çatlak görünüyor.
- İlk soru 27. saniyede; buna rağmen kaydırma düşük. İzleyiciyi tutan, açılıştaki zaman farkı.
- Gönderme sebebi: "Kapadokya'yı seven birine gönder, bir de ona sor: bir çatlak görse kime haber verirdi?"

Uyarlama (konu: kaybolan bir meslek), kalıp örneği: açılış "Bu dilekçe [yıl] yılında yazıldı. Yazan adam okuma bilmiyordu." İlk kare: gerçek bir dilekçe fotoğrafı. Köşeli parantezli yer ve iddia, kullanıcının kaynağındaki gerçek bilgiyle doldurulur; doğrulanmamış tarih ya da olay yazılmaz.
