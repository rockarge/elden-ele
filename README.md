# Elden Ele

Reels, Shorts ve TikTok videolarını inceleyen ücretsiz bir Claude skill'i. Videonu kendisi izler, hesabının sayılarıyla eşleştirir ve hangi videonun hangi saniyede, neden kaybettiğini, neden kimseye gönderilmediğini kanıtıyla söyler.

Kredi, abonelik ya da ücretli araç gerektirmez.

## Neden yaptım
Instagram'ın başı Adam Mosseri, takip etmeyen insanlara ulaşmada en ağır basan sinyallerden birinin gönderme oranı olduğunu söylüyor: videoyu görenlerin kaçı onu birine gönderiyor.

Bir tarih videom 1.654 kez izlendi, 3 kişi gönderdi. Aynı hafta başka bir videom 32 bin kez izlendi, 198 kez gönderildi. Farkı ancak videoyu saniye saniye açınca gördüm: asıl soruyu 15. saniyede soruyordum, izleyicinin yarısından fazlası ilk 3 saniyede geçmişti.

Bunu her video için elle yapmamak için bu aracı kurdum.

## Analiz araçlarından farkı
Kısa video analiz araçları (vidIQ gibi) çoğunlukla izlenme sayısına ve kredili işlemlere dayanır. Elden Ele farklı bir soruya bakar: video neden gönderilmedi?

- **Ölçüsü gönderme oranı.** Her videoyu, görenlerin kaçının onu birine gönderdiğiyle ve hesabının kendi ortalamasıyla kıyaslar.
- **Düşüşü cümleye bağlar.** Tutma grafiğinde izleyicinin gittiği her aralığın karşısına o anda söylediğin cümleyi ve ekrandaki kareyi koyar. Genel bir video yorumu değil, senin grafiğinle senin videonun eşleşmesi.
- **Instagram tutma grafiğini okur.** Bu grafik dışa aktarılan dosyaya girmiyor, vidIQ'nun Instagram verisinde de yok; telefondaki istatistik ekranında görünüyor. Elden Ele o ekranın görüntüsünden okur.
- **Videoyu sınırsız izler.** Sesin başladığı anı, ilk sorunun saniyesini, çağrıların yerini, ilk karenin boş olup olmadığını ölçer. Video başına kredi yok.
- **Türkçe sıra dışı videolarla karşılaştırır.** Kendi hesabının ortalamasının 3 ile 100 katı izlenmiş 19 Türkçe kısa videonun ortak noktalarını bilir; ama kuralı onlardan değil, senin hesabının verisinden koyar.
- **Sıra dışı videoyu senin videona uyarlar.** Kendi en çok izlenen videonun ya da verdiğin bir rakip videonun ilk 3 saniyesini, ilk karesini ve gönderme sebebini çıkarır; bir sonraki konun için iki açılış seçeneği ve ilk kare önerir. Kalıbı taşır, cümleyi kopyalamaz.
- **Emin olmadığı yerde hüküm yazmaz.** Yeni, deneme ve az gönderilmiş videoları ayırır; bir desen 3 videoda tekrar etmeden "hesabının deseni" demez.

## Ne yapar
1. **Sayıları toplar.** Claude'a kendi ücretsiz vidIQ hesabınla vidIQ bağlayıcısını eklediysen Instagram Reels sayılarını kredisiz çeker. Yoksa Meta Business Suite, YouTube Studio ya da TikTok Studio'dan indirdiğin dosyayı ve ekran görüntülerini okur.
2. **Videoyu izler** ve kareleri tek sayfada önüne koyar.
3. **Düşüşü sebebiyle eşleştirir.**
4. **Rakipte sıra dışı videoyu bulur.** Bir hesabın video ızgarasının ekran görüntüsünden, o hesabın ortalamasının kaç katı izlenen videoları çıkarır.
5. **Rapor verir.** Hesabının sıra dışı videoları ayrı bölümde, video başına kanıtlı hükümler, hesap genelindeki desenler, sonraki video için en fazla 3 değişiklik. Telefonda açılan tek bir dosya.
6. **Uyarlar.** Sıra dışı videonun kalıbını bir sonraki konuna taşır.

## Kurulum
**Claude (web ve masaüstü):** Bu sayfadaki `elden-ele.zip` dosyasını indir, Claude ayarlarındaki Skills bölümünden yükle. Kod çalıştırma açık olmalı.

**Claude Code:** `elden-ele` klasörünü `~/.claude/skills/` altına kopyala.

**İsteğe bağlı:** Instagram sayılarını elle getirmemek için Claude'un bağlayıcılarından vidIQ'yu kendi ücretsiz hesabınla ekle ve orada Instagram hesabını bağla. Araç yalnız kredisiz çağrıları kullanır.

Sonra Claude'a "Reels'lerimi Elden Ele ile incele" de. Elindekileri tek tek sorarak başlar.

## Bilmen gerekenler
- **Tutma grafiği** Instagram, YouTube ve TikTok'ta istatistik ekranında görünür, indirilen dosyaya girmez. Araç en zayıf 1-3 videon için o ekranın görüntüsünü ister ve okur.
- **Konuşma metni:** Claude'un ortamı konuşmayı her zaman metne dökemeyebilir; o durumda videonun altyazısını (srt) ister. CapCut'ta otomatik altyazıyı srt olarak dışa aktarabilirsin.
- **Yeni videolar:** yayından 48 saat geçmemiş videolar "yeni" diye işaretlenir ve hesap ortalamasına katılmaz; sayıları henüz oturmamıştır.
- **Rakip videolar:** herkese açık izlenmelerle ve rakibin kendi ortalamasına göre değerlendirilir.

Hazırlayan: Serhat Kaya · Instagram [@imzabirturk](https://www.instagram.com/imzabirturk/)
