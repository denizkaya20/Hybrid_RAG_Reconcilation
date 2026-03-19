# 🏦 IPARD II - LLM & RAG Hibrit Eşleştirme Sistemi

Banka işlemleri ile başvuru sahiplerini otomatik eşleştiren akıllı mutabakat sistemi.

## 📋 İçindekiler

- [Özellikler](#özellikler)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Ayarlar](#ayarlar)
- [Çıktılar](#çıktılar)
- [Sorun Giderme](#sorun-giderme)

---

## ✨ Özellikler

### 🤖 4 Aşamalı Akıllı Eşleştirme

1. **Phase 1: TC/VKN Eşleştirme** (En Güvenilir)
   - Kimlik numarası veya vergi numarası ile otomatik eşleştirme
   - %99 güvenilirlik

2. **Phase 2: Başvuru No Eşleştirme** (Çok Güvenilir)
   - Başvuru numarası ile otomatik eşleştirme
   - %97 güvenilirlik

3. **Phase 3: Güvenli İsim/Şirket Eşleştirme** (Güvenilir)
   - Token bazlı akıllı isim eşleştirme
   - Nadir kelime analizi ile doğrulama
   - %88-90 güvenilirlik

4. **Phase 4: LLM + RAG Eşleştirme** (Akıllı)
   - Vektör tabanlı semantic search (RAG)
   - LLM ile karar verme (DeepSeek, Qwen, GPT-OSS)
   - Karmaşık durumlar için

### 🎯 Otomatik Özellikler

- ✅ Excel header ve kolon pozisyonlarını **otomatik** bulur
- ✅ Türkçe karakter normalizasyonu
- ✅ İşlem filtresi (virement, faiz tahakkuk vb.)
- ✅ 3 farklı LLM modeliyle karşılaştırmalı sonuç
- ✅ Detaylı Excel raporları

---

## 🚀 Kurulum

### 1. Gereksinimler

```bash
Python 3.8+
```

### 2. Sanal Ortam Oluşturma

```bash
cd C:\Users\deniz\Desktop\MUTABAKAT\Hybrid_Approach
python -m venv myenv
myenv\Scripts\activate
```

### 3. Kütüphaneleri Yükleme

```bash
pip install pandas openpyxl xlrd chromadb sentence-transformers requests python-dotenv
```

### 4. API Anahtarlarını Ayarlama

`.env` dosyasını oluşturun (veya düzenleyin):

```dotenv
# LLM API'ları
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-chat

GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_API_KEY=your-groq-api-key

QWEN_MODEL=qwen/qwen3-32b
GPTOSS_MODEL=openai/gpt-oss-20b

# RAG ayarları
EMBED_MODEL=intfloat/multilingual-e5-base
RAG_TOPK=12
```

⚠️ **ÖNEMLİ:** API anahtarlarınızı asla GitHub'a yüklemeyin!

---

## 📝 Kullanım

### 1. Dosya Yollarını Ayarlama

`src/config.py` dosyasını açın ve **en üstteki** dosya yollarını düzenleyin:

```python
# =========================================================================
# 📁 DOSYA YOLLARI - Buradan kolayca değiştirin!
# =========================================================================

APPLICANTS_XLS = r"C:\Users\deniz\Desktop\MUTABAKAT\6-HAZİRAN\IPARD II\6406 Borçlu Def.Borç Kayıt.Arası Mutabakat- HAZİRAN 2023-IPARD II..xls"
IPARD2_XLS = r"C:\Users\deniz\Desktop\MUTABAKAT\6-HAZİRAN\IPARD II\IPARD2.xls"

# =========================================================================
```

💡 **İpucu:** Farklı ay için sadece bu 2 satırı değiştirin (örn: `6-HAZİRAN` → `7-TEMMUZ`)

### 2. Başvuru Satır Aralığını Ayarlama

Aynı `src/config.py` dosyasında:

```python
# Sheet ayarları
APPLICANTS_SHEET = "6406"
APPLICANTS_START_ROW = 81    # 👈 Başlangıç satırı
APPLICANTS_END_ROW = 113      # 👈 Bitiş satırı
```

📌 **Not:** Excel'deki gerçek satır numaralarını kullanın (1'den başlar)

### 3. Programı Çalıştırma

```bash
cd src
python runner.py
```

### 4. İlerlemeyi İzleme

Terminal'de şu şekilde loglar göreceksiniz:

```
✅ Applicants loaded: 33 | rows=81-113
🔍 ES_FINANSMAN: Otomatik header ve kolonlar aranıyor...
✅ ES_FINANSMAN: Header bulundu: satır 7
✅ ES_FINANSMAN: 40 işlem
✅ TRANSFER: 38 işlem
✅ Total txns loaded: 78

✅ [deepseek] Phase1 TC/VKN matches: 5
✅ [deepseek] Phase2 BasvuruNo matches: 3
✅ [deepseek] Phase3a Person safe matches: 1
✅ [deepseek] Phase3b Company safe matches: 1
✅ [deepseek] Phase4 LLM+RAG matches: 21
✅ Excel written: C:\...\llm_rag_output_hybrid_deepseek.xlsx
```

---

## ⚙️ Ayarlar

### 📂 Dosya Yapısı

```
Hybrid_Approach/
├── src/
│   ├── runner.py              # Ana program
│   ├── config.py              # 👈 AYARLARIN HEPSİ BURADA
│   ├── io_applicants.py       # Başvuru okuma
│   ├── io_ipard2.py           # Banka ekstresi okuma
│   ├── rule_candidates.py     # Kural tabanlı eşleştirme
│   ├── rag_store.py           # Vektör veritabanı
│   ├── llm_client.py          # LLM istemcisi
│   ├── hybrid_matcher.py      # LLM karar verme
│   ├── excel_out.py           # Excel çıktı
│   ├── text_norm.py           # Metin normalizasyonu
│   ├── token_stats.py         # Token istatistikleri
│   └── filters.py             # İşlem filtreleri
├── .env                       # 👈 API ANAHTARLARI BURADA
├── indexes/                   # RAG vektör index'leri (otomatik)
└── llm_rag_hybrid/           # 👈 ÇIKTI DOSYALARI BURADA
    ├── llm_rag_output_hybrid_deepseek.xlsx
    ├── llm_rag_output_hybrid_qwen_groq.xlsx
    └── llm_rag_output_hybrid_gptoss_groq.xlsx
```

### 🎛️ config.py - Tüm Ayarlar

```python
# 📁 Dosya Yolları
APPLICANTS_XLS = r"C:\path\to\applicants.xls"
IPARD2_XLS = r"C:\path\to\ipard2.xls"

# 📊 Sheet Ayarları
APPLICANTS_SHEET = "6406"
APPLICANTS_START_ROW = 81
APPLICANTS_END_ROW = 113

ES_SHEET = "EŞ-FİNANSMAN HESABI"
TR_SHEET = "TRANSFER HESABI"

# 🚫 Filtrelenecek İşlemler
FILTERED_TRANSACTION_NAMES = [
    "Remittance Buying Foreign Currency",
    "EFT to Account",
    "Virement",
    "Deposit Interest Accrual",
    "Virement Cancel",
]

# 🤖 RAG Ayarları
EMBED_MODEL = "intfloat/multilingual-e5-base"
RAG_TOPK = 12  # Kaç aday işlem getirilecek

# 📤 Çıktı Ayarları
OUTPUT_DIR = "llm_rag_hybrid"
OUTPUT_PREFIX = "llm_rag_output_hybrid"
```

---

## 📊 Çıktılar

### 📁 Çıktı Konumu

```
C:\Users\deniz\Desktop\MUTABAKAT\Hybrid_Approach\llm_rag_hybrid\
```

### 📋 Excel Dosyaları

Her model için ayrı Excel dosyası oluşturulur:

- `llm_rag_output_hybrid_deepseek.xlsx`
- `llm_rag_output_hybrid_qwen_groq.xlsx`
- `llm_rag_output_hybrid_gptoss_groq.xlsx`

### 📑 Excel Sheet'leri

Her dosyada 5 sheet bulunur:

1. **MATCHED** 
   - Başarıyla eşleşen tüm kayıtlar
   - Kolonlar: model, name, tc_vkn, basvuru_no, decision, confidence, txn_id, amount, narrative, vb.

2. **REVIEW**
   - İnceleme gereken kayıtlar
   - REVIEW, CONFLICT, NO_MATCH durumları

3. **UNMATCHED_APPLICANTS**
   - Hiçbir işlemle eşleşmeyen başvuru sahipleri

4. **UNMATCHED_TXNS**
   - Hiçbir başvuru sahibiyle eşleşmeyen işlemler
   - (Opsiyonel: best_candidate_name ve score)

5. **STATS**
   - Özet istatistikler
   - Toplam başvuru, eşleşme, review sayıları

### 📈 İstatistik Örneği

```
applicants_total: 33
matched_applicants: 31
matched_rows: 31
review_rows: 2
unmatched_applicants: 0
txns_total: 78
used_txns_in_matches: 31
unmatched_txns: 47
```

---

## 🔧 Sorun Giderme

### ❌ "Header bulunamadı" Hatası

**Sorun:** Excel dosyasındaki header satırı bulunamıyor.

**Çözüm:**
- Excel dosyasını açıp header satırını kontrol edin
- Şu kolonlar **mutlaka** olmalı:
  - `TRANSACTION DATE`
  - `AMOUNT`
  - `NARRATIVE`
  - `TRANSACTION NAME`

### ❌ "Kolonlar bulunamadı" Hatası

**Sorun:** Gerekli kolonlar tespit edilemiyor.

**Çözüm:**
- Kolon isimleri yukarıdaki gibi olmalı
- Farklı isimlerse `io_ipard2.py`'deki `_find_column_indices()` fonksiyonunu güncelleyin

### ❌ API Hatası (429, 500, vb.)

**Sorun:** LLM API'si hata veriyor.

**Çözüm:**
- `.env` dosyasında API anahtarlarını kontrol edin
- API limitinizi kontrol edin (özellikle Groq için)
- `llm_client.py` otomatik retry yapıyor, bekleyin

### ❌ ChromaDB Hatası

**Sorun:** Vektör veritabanı hatası.

**Çözüm:**
- `indexes/chroma_txns` klasörünü silin, tekrar oluşacak
- Disk alanınızı kontrol edin

### ⚠️ Tarih Parse Uyarısı

```
UserWarning: Parsing dates in %d.%m.%Y %H:%M format when dayfirst=False
```

**Sorun:** Pandas tarih formatı uyarısı.

**Çözüm:**
- Sadece uyarı, sorun değil
- Türkçe tarih formatı (%d.%m.%Y) doğru çalışıyor

---

## 🎓 Nasıl Çalışır?

### 1️⃣ Excel Okuma
- Başvuru sahiplerini okur (isim, TC/VKN, başvuru no)
- Banka işlemlerini okur (2 sheet: EŞ-FİNANSMAN, TRANSFER)
- Header ve kolonları **otomatik** bulur

### 2️⃣ Normalizasyon
- Türkçe karakterleri dönüştürür (ş→s, ğ→g, vb.)
- Boşlukları temizler
- Token'lara böler

### 3️⃣ Eşleştirme (4 Aşama)

**Phase 1: TC/VKN**
```python
TC: 12345678901 → narrative'de ara
```

**Phase 2: Başvuru No**
```python
Başvuru: 2023/18/1 → narrative'de ara
```

**Phase 3: Akıllı İsim**
```python
"Ahmet Yılmaz" → tokens: [AHMET, YILMAZ]
Narrative: "AHMET YILMAZ tarafından..." → MATCH ✅
```

**Phase 4: LLM + RAG**
```python
1. Query oluştur: "Ahmet Yılmaz 2023/18/1 12345678901"
2. RAG: En yakın 12 işlemi bul (vektör similarity)
3. LLM: Karar ver (MATCH/REVIEW/NO_MATCH)
```

### 4️⃣ Excel Çıktı
- Her model için ayrı dosya
- 5 sheet (MATCHED, REVIEW, vb.)
- Detaylı istatistikler

---

## 📞 Destek

Sorun yaşarsanız:

1. Terminal log'larını kontrol edin
2. Excel dosyalarının formatını kontrol edin
3. `.env` ve `config.py` ayarlarını gözden geçirin
4. `indexes` klasörünü silip tekrar deneyin

---

## 📄 Lisans

Bu proje dahili kullanım içindir.

---

## 🔄 Versiyon

**v1.0** - Ocak 2025
- İlk stabil sürüm
- Otomatik header/kolon bulma
- 3 LLM modeli desteği
- 4 aşamalı hibrit eşleştirme
