# Sirac Backend (Django)

Mobil tətbiq üçün REST API. Şəbəkə / internet üzərindən işləyir.

## Render (Neon Postgres) — Shell lazım deyil

**Root Directory:** `backend`

**Build Command:**
```text
bash scripts/build.sh
```

**Start Command:**
```text
bash scripts/start.sh
```

Skriptlər özləri edir: `pip install` → `migrate` → admin (`Kamandar`) → `collectstatic` → gunicorn.

Yalnız Environment: `DATABASE_URL` (Neon).

Admin: `/admin/` → `Kamandar` / `20012001Kamandar`

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
