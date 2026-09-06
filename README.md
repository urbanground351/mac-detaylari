# Flashscore Haftalık Maç Summary Kazıyıcı

Bu proje, Flashscore üzerindeki Türkiye ligleri fikstürlerinden haftalık maçları otomatik olarak bulur ve maçların Flashscore üzerindeki uzun **özet / önizleme metinlerini (Summary / Preview)** çeker.

İstenmeyen veriler (oranlar, sakat oyuncular, stadyum, hakem, maç istatistikleri vb.) **çekilmez**, yalnızca maç bilgisi ve uzun analiz yazısı kaydedilir.

## Kurulum

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m playwright install chromium
```

## Çalıştırma Seçenekleri

### 1. Bu Haftanın Tüm Maçlarının Summary Yazılarını Çekme (Varsayılan)
`config.json` dosyasındaki Türkiye liglerinin (Süper Lig, 1. Lig vb.) bu haftaki tüm maçlarını çeker:

```powershell
py scraper.py
```

### 2. Sadece Summary Metni Yayınlanmış Maçları Kaydetme
Henüz editör/AI özeti yazılmamış ileri tarihli maçları filtreleyip sadece uzun metni olan maçları kaydetmek için:

```powershell
py scraper.py --only-with-summary
```

### 3. Belirli Gün Sayısına Göre Çekme (Ör: 3 gün)
```powershell
py scraper.py --days 3
```

### 4. Belirli Bir Ligi Çekme
```powershell
py scraper.py --league super-lig
py scraper.py --league 1-lig
```

### 5. Tek Bir Maç URL'si Çekme
```powershell
py scraper.py "https://www.flashscore.com/match/football/amedspor-EHdgkFvm/kasimpasa-dOlaIG4l/?mid=SdbNHpFE"
```

## Çıktı Formatı (`data/matches.json`)
Her maç sadece temel kimlik bilgileri ve uzun özet metni ile kaydedilir:

```json
[
  {
    "match_id": "SdbNHpFE",
    "url": "https://www.flashscore.com/match/football/kasimpasa-dOlaIG4l/amedspor-EHdgkFvm/?mid=SdbNHpFE",
    "scraped_at": "2026-09-06T00:06:04.103780+00:00",
    "tournament": "Super Lig",
    "round": "Round 4",
    "match_time": "2026-09-06 17:00",
    "home_team": "Kasimpasa",
    "away_team": "Amedspor",
    "summary": "Amedspor travel to face Kasimpasa in round four of the Super Lig. Amedspor enters this match as the outsider with a 31% chance of victory...\n\nKasimpasa are eighth in the league with five points...\n\nAmedspor are fifth in the league with six points...\n\nKey Players to Watch and Missing Players...\n\nKey Numbers...\n\nBetting Insights..."
  }
]
```

## GitHub Actions Otomasyonu (8 Saatte Bir Otomatik Güncelleme)

Proje içerisinde hazır bir GitHub Actions iş akışı bulunmaktadır (`.github/workflows/scraper.yml`).

- **Zamanlama**: Her 8 saatte bir (00:00, 08:00, 16:00 UTC) otomatik çalışır (`cron: '0 */8 * * *'`).
- **Manuel Çalıştırma**: GitHub repo sayfasında **Actions** sekmesi -> **Update Matches Data** -> **Run workflow** butonu ile istenildiği an tetiklenebilir.
- **Otomatik Commit**: Yeni maç ve özet verilerini çekip `data/matches.json` dosyasına commit edip depoya geri pushlar.

### Projeyi GitHub'a Yükleme:

```powershell
git remote add origin https://github.com/urbanground351/mac-detaylari.git
git push -u origin main
```
3. **Önemli İzin Ayarı**: GitHub Actions'ın `data/matches.json` dosyasını depoya geri kaydedebilmesi için:
   - GitHub deponuzda: **Settings** -> **Actions** -> **General**
   - Aşağı kaydırıp **Workflow permissions** bölümünü bulun.
   - **"Read and write permissions"** seçeneğini seçin ve **Save** butonuna tıklayın.
