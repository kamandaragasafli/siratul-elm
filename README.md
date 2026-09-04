# Sirac Backend (Django)

Mobil tətbiq üçün REST API. Şəbəkə / internet üzərindən işləyir.

## Qurulum

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_sample
```

## İşə salma (mobil üçün vacib)

`0.0.0.0` — telefon eyni Wi‑Fi-dən qoşula bilsin:

```powershell
python manage.py runserver 0.0.0.0:8000
```

## Endpoint-lər

| Method | URL | Təsvir |
|--------|-----|--------|
| GET | `/api/health/` | Əlaqə yoxlaması |
| GET | `/api/books/` | Kitab siyahısı |
| GET | `/api/books/<id>/` | Kitab + fəsillər |
| GET | `/api/channels/` | Video kanallar (ad + link) |
| POST | `/api/support/` | Dəstək mesajı |
| — | `/admin/` | Admin panel |

### Video kanallar (admin)

1. `http://127.0.0.1:8000/admin/` → giriş: `admin` / `admin123`
2. **Video kanallar** → Əlavə et
3. **Kanal adı** (mobildə görünür) + **Kanal linki** (sonrakı mərhələ)

Mobil tərəfdə ünvan: `Sirac/src/api/config.ts` → `API_BASE_URL`
