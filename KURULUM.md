# Kurulum Adımları

## 1. Docker Desktop ve VS Code kur (terminalde çalıştır)
```bash
brew install --cask docker visual-studio-code
```
Kurulduktan sonra Docker Desktop'ı Applications'dan aç ve tamamen başlamasını bekle.

## 2. Sanal ortam oluştur ve Python paketlerini kur
```bash
cd ~/Desktop/digital_twin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. .env dosyasını oluştur
```bash
cp .env.example .env
```

## 4. Tüm servisleri başlat
```bash
docker compose up -d
```

## Servis Adresleri
| Servis      | Adres                    | Kullanıcı | Şifre    |
|-------------|--------------------------|-----------|----------|
| TimescaleDB | localhost:5432           | postgres  | postgres |
| Qdrant UI   | http://localhost:6333/dashboard | -   | -        |
| Redis       | localhost:6379           | -         | -        |
| n8n         | http://localhost:5678    | admin     | admin123 |
| Grafana     | http://localhost:3000    | admin     | admin123 |
| FastAPI     | http://localhost:8000    | -         | -        |

## Servisleri durdur
```bash
docker compose down
```

## Servisleri durdur ve verileri sil (sıfırdan başlamak için)
```bash
docker compose down -v
```
