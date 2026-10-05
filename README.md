# 💰 Harcama Takip

Python ve Streamlit ile geliştirilmiş, kişiye özel hesapları olan harcama takip uygulaması.
Kullanıcılar kendi harcamalarını kaydeder; tarih/kategori filtreleriyle toplamları ve yüzdelik pasta grafiklerini inceler.

![Giriş ekranı](docs/login.jpg)
![Demo harcamaları ve yüzdelik pasta grafikleri](docs/demo.jpg)

## Özellikler

- Kayıt olma, giriş ve çıkış; 8 saatlik oturum süresi.
- Kullanıcıya özel harcama ekleme, listeleme ve onaylı silme.
- Tarih aralığı ve kategori filtreleri; ödeme yöntemine göre toplamlar.
- Kategori ve ödeme yöntemi için yüzdelik pasta grafikler.
- Tek tıklamayla açılan, her oturuma özel örnek verili demo.
- Yerelde SQLite; bulutta `DATABASE_URL` ile PostgreSQL desteği.
- Para tutarları hesaplamalarda tam sayı kuruş olarak saklanır.
- SQLite ve PostgreSQL için otomatik hesap/arayüz testleri.

## Yerelde çalıştırma

Python 3.13 ile doğrulanmıştır. Proje klasöründeki terminalde:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Tarayıcı: http://localhost:8501. PyCharm'da proje yorumlayıcısı olarak `.venv` seçilir.
Streamlit sunucusu açık kaldığı sürece bu adres kullanılabilir.

Linux/macOS: `.venv/bin/python -m pip install -r requirements.txt` ve
`.venv/bin/python -m streamlit run app.py`.

## Mevcut kişisel kayıtları bağlama

Eski veritabanındaki kayıtlara otomatik sahip atanmaz. İlk kayıt olan kişi eski harcamaları alamaz.
Önce veritabanını yedekleyin; ardından **kendi bilgisayarınızda** çalıştırın:

```powershell
.\.venv\Scripts\python.exe setup_owner.py --username Duran
```

Hesap yoksa yeni şifre belirlenir; varsa mevcut şifre doğrulanır. Yalnızca sahipsiz eski kayıtlar aktarılır.
Kullanıcı adları büyük/küçük harfe duyarsızdır: `Duran` ve `duran` aynı hesaptır.
Şifreler 15–128 karakter olmalıdır. Şifreyi sohbet, kaynak kod veya GitHub üzerinden paylaşmayın.

## Ücretsiz yayınlama

Uygulama için **Streamlit Community Cloud**, kalıcı veriler için **Neon Free PostgreSQL** kullanılabilir.
Ücretsiz planların kota ve uyku kuralları sağlayıcılara bağlıdır; ücretli plana geçiş gerekmez.
GitHub hesabı tek başına uygulamayı çalıştırmaz; kaynak kodu saklar.

1. GitHub'da `expense-tracker` deposu oluşturup kaynak dosyalarını yükleyin.
   `.db` dosyaları, `backups`, `.venv`, `.env` ve gerçek `secrets.toml` yüklenmez.
2. Neon'da **Free** planla bir PostgreSQL projesi oluşturun. **Connect** alanından bağlantı adresini alın.
3. Streamlit Community Cloud'a GitHub ile giriş yapın. Depoyu, dalı ve `app.py` dosyasını seçin.
   Python sürümünü **3.13** olarak ayarlayın.
4. Uygulamanın **Secrets** ayarına aşağıdaki anahtarı, Neon'dan aldığınız gerçek değerle ekleyin:

   ```toml
   DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require"
   ```

5. Deploy işlemini başlatın. Tablolar ilk açılışta otomatik oluşur.
6. İki ayrı hesapla kayıt/giriş, veri ayrımı ve silme işlemlerini canlı ortamda doğrulayın.
   Uygulamayı yeniden başlattıktan sonra kayıtların durduğunu kontrol edin.

**Kalıcı veri için `DATABASE_URL` gereklidir.** Community Cloud yerel dosyaların kalıcılığını garanti etmez.
Neon bağlantısını kullanıcıya açık kodda veya README içinde paylaşmayın. SSL seçeneğini koruyun.
Bulut ilk kurulumda boş başlar; kişisel yerel veritabanı otomatik yüklenmez.

## Veri ve güvenlik tasarımı

- Scrypt: rastgele 16 bayt salt, N=131072, r=8, p=1; düz metin şifre saklanmaz.
- Parametreli SQL; kullanıcı kimliği tarayıcı girdisinden değil sunucu oturumundan alınır.
- Bütün harcama sorguları ve silme işlemleri kullanıcı kimliği ile sınırlandırılır.
- Hesap başına 15 dakikada 5 başarısız giriş denemesi; sayaç veritabanında tutulur.
- Demo verileri yalnızca oturum belleğindedir; kişisel kayıtlara yazılmaz.
- Bulut veritabanı bağlantısı yalnızca sunucuda kullanılır. Uygulama HTTPS üzerinden yayınlanmalıdır.
- Şifre sıfırlama, e-posta doğrulaması ve iki aşamalı giriş bu sürümün kapsamı dışındadır.
- Bu sürüm bir portföy uygulamasıdır; yüksek trafik için ek hız sınırlaması, izleme ve yedekleme gerekir.

## Testler

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Yerel testler geçici SQLite veritabanları kullanır; kişisel veritabanını değiştirmez.
`TEST_DATABASE_URL` tanımlanırsa aynı hesap/arayüz testleri PostgreSQL'de ayrı geçici şemalarda çalışır.
GitHub Actions, PostgreSQL 17 servisiyle her push/PR'da iki altyapıyı da test eder.

Testler; şifre saklama, giriş sınırı, farklı hesapların kayıtlarına erişememe/silememe,
eski kayıt geçişi, filtreleme, demo izolasyonu, kayıt/giriş/çıkış, harcama ekleme/silme ve oturum süresini kapsar.

## Docker alternatifi

```sh
docker compose up --build -d
```

SQLite dosyası kalıcı `expense-data` biriminde tutulur. Bu seçenek yerel kullanım veya kendi sunucunuz içindir.
Docker ortamı bu bilgisayarda bulunmadığından imaj derlemesi yerelde doğrulanmamıştır.

## Kaynaklar

- [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)
- [Secrets yönetimi](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Yerel dosya kalıcılığı](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)
- [Neon Free](https://neon.com/blog/neon-free-plan-1-gb-per-project)
- [OWASP şifre saklama önerileri](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
