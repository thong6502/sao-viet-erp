# Triển khai (CI/CD → VPS bằng Docker Compose)

Kiến trúc chạy trên VPS:

```
Internet ─▶ caddy (:80/:443, auto-HTTPS) ─▶ web (nginx) ──/api──▶ backend (uvicorn :8000) ──▶ db (Postgres)
                                             └ phục vụ frontend build (Vite → dist)
```

Caddy tự xin & gia hạn chứng chỉ Let's Encrypt cho `SITE_DOMAIN`, tự chuyển http → https.

Mỗi lần push lên `main`, workflow [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml):
1. **CI gate** — build frontend (`tsc + vite`) và chạy `pytest` (SQLite in-memory). Gãy ⇒ dừng, KHÔNG deploy.
2. **Deploy** — SSH vào VPS: `git reset --hard origin/main` → `docker compose -f docker-compose.prod.yml up -d --build`.

---

## 1. Biến & bí mật trên GitHub (Settings → Secrets and variables → Actions)

**Variables** (đã tạo):

| Tên | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `VPS_HOST` | `103.245.237.54` | IP/host VPS |
| `VPS_USER` | `deploy` | user SSH triển khai |
| `VPS_PORT` | `22` | cổng SSH |
| `APP_DIR` | `/var/www/erp-svn` | thư mục chứa repo trên VPS |

**Secrets** (đã tạo):

| Tên | Ý nghĩa |
| --- | --- |
| `VPS_SSH_KEY` | **private key** để Actions SSH vào VPS. Public key tương ứng phải nằm trong `~deploy/.ssh/authorized_keys` trên VPS. |

---

## 2. Chuẩn bị VPS (làm 1 lần)

```bash
# a) Cài Docker + Compose plugin (Ubuntu)
curl -fsSL https://get.docker.com | sh

# b) Cho user deploy chạy docker không cần sudo
sudo usermod -aG docker deploy      # đăng xuất/đăng nhập lại để có hiệu lực

# c) Cho phép GitHub Actions SSH vào: dán public key (cặp với VPS_SSH_KEY) vào authorized_keys
sudo -u deploy mkdir -p /home/deploy/.ssh
echo "ssh-ed25519 AAAA...public-key-cua-VPS_SSH_KEY... actions" \
  | sudo -u deploy tee -a /home/deploy/.ssh/authorized_keys
sudo -u deploy chmod 600 /home/deploy/.ssh/authorized_keys
```

### Clone repo (private) vào APP_DIR

Repo private ⇒ VPS cần quyền đọc. Dùng **Deploy key (read-only)**:

```bash
# Trên VPS, tạo key cho việc git pull (KHÁC với VPS_SSH_KEY ở trên)
sudo -u deploy ssh-keygen -t ed25519 -f /home/deploy/.ssh/id_ed25519 -N ""
cat /home/deploy/.ssh/id_ed25519.pub
```
Copy nội dung `.pub` → GitHub repo **Settings → Deploy keys → Add deploy key** (KHÔNG cần quyền ghi).

```bash
sudo mkdir -p /var/www && sudo chown deploy:deploy /var/www
sudo -u deploy git clone git@github.com:thonglv111/sao-viet-erp.git /var/www/erp-svn
```

### DNS & tường lửa (cho HTTPS)

- Trỏ bản ghi **A** của subdomain (vd `erp.saovietnhat.vn`) → IP VPS `103.245.237.54`. Chờ DNS phân giải đúng **trước khi** chạy Caddy (Let's Encrypt cần điều này).
- Mở cổng **80** và **443**:

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```

### Tạo file `.env` production

```bash
cd /var/www/erp-svn
cp .env.prod.example .env
nano .env   # điền POSTGRES_PASSWORD, JWT_SECRET (openssl rand -hex 32), SEED_ADMIN_PASSWORD,
            # SITE_DOMAIN=subdomain, CORS_ORIGINS=https://subdomain
```

### Chạy lần đầu (kiểm tra)

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend    # thấy "seeded admin" là OK
```
Mở `http://<VPS_HOST>` → đăng nhập bằng `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD`.

---

## 3. Vận hành

- **Deploy tự động**: push lên `main`. Xem tiến trình ở tab **Actions**.
- **Deploy tay**: Actions → *Deploy (production)* → *Run workflow*.
- **Log**: `docker compose -f docker-compose.prod.yml logs -f backend`
- **Backup DB**:
  ```bash
  docker compose -f docker-compose.prod.yml exec db \
    pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
  ```
- **Dữ liệu Postgres** nằm ở volume `pgdata` — deploy KHÔNG xóa dữ liệu.

## 4. Lưu ý
- `git reset --hard origin/main` **ghi đè mọi thay đổi local** trên VPS (trừ file gitignore như `.env`). Đừng sửa code trực tiếp trên server.
- Guard bảo mật: `APP_ENV=production` bắt buộc `JWT_SECRET` ≥ 32 ký tự, khác default — nếu không backend sẽ từ chối khởi động.
- Chưa có TLS/HTTPS: production thật nên đặt sau reverse-proxy (Caddy/Traefik) hoặc thêm certbot cho nginx — đổi `CORS_ORIGINS`/domain tương ứng.
