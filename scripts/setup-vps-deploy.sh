#!/usr/bin/env bash
#
# setup-vps-deploy.sh — Cài deploy tự động (GitHub Actions → VPS) cho NHIỀU repo
# ---------------------------------------------------------------------------
# Chạy TRÊN VPS với quyền root:   sudo bash setup-vps-deploy.sh
# Chạy LẠI cho từng repo (repo #2, #3, ...) — script an toàn khi lặp.
#
# HAI loại SSH key, hành xử KHÁC nhau khi dùng chung 1 VPS:
#   KEY A  — GitHub Actions SSH *VÀO* VPS.
#            ★ DÙNG CHUNG 1 key cho MỌI repo (đều vào cùng VPS/user).
#            → private key dán vào Secret VPS_SSH_KEY của TẤT CẢ repo (giống nhau).
#   KEY B  — VPS `git pull` *RA* GitHub (repo private).
#            ★ MỖI repo 1 key RIÊNG (GitHub cấm 1 deploy key trùng 2 repo).
#            → public key add vào Deploy keys của ĐÚNG repo đó (Read-only).
#            → dùng SSH alias trong ~/.ssh/config để git chọn đúng key theo repo.
# ---------------------------------------------------------------------------
set -euo pipefail

c_info()  { printf '\033[1;36m→ %s\033[0m\n' "$*"; }
c_ok()    { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
c_warn()  { printf '\033[1;33m! %s\033[0m\n' "$*"; }
c_ask()   { printf '\033[1;35m? %s\033[0m'   "$*"; }
pause()   { printf '\033[1;34m\n⏸  %s\033[0m' "${1:-Nhấn Enter để tiếp tục...}"; read -r _; }

[ "$(id -u)" -eq 0 ] || { c_warn "Hãy chạy bằng root:  sudo bash $0"; exit 1; }

echo "======================================================================"
echo "  CÀI DEPLOY TỰ ĐỘNG  (GitHub Actions → VPS)  — hỗ trợ NHIỀU repo"
echo "======================================================================"

# ---------------------------------------------------------------------------
# 1. THU THẬP THÔNG TIN
# ---------------------------------------------------------------------------
c_ask "Tên user deploy [deploy]: ";            read -r DEPLOY_USER;  DEPLOY_USER="${DEPLOY_USER:-deploy}"
c_ask "Thư mục CHA chứa app [/var/www]: ";      read -r PARENT_DIR;   PARENT_DIR="${PARENT_DIR:-/var/www}"
PARENT_DIR="${PARENT_DIR%/}"
c_ask "Git remote SSH của repo [git@github.com:thonglv111/sao-viet-erp.git]: "; read -r GIT_REMOTE
GIT_REMOTE="${GIT_REMOTE:-git@github.com:thonglv111/sao-viet-erp.git}"
c_ask "VPS cần chạy Docker? (bỏ deploy vào group docker) [Y/n]: "; read -r WANT_DOCKER; WANT_DOCKER="${WANT_DOCKER:-Y}"

# Tách thông tin từ remote (dạng scp:  git@HOST:OWNER/REPO.git)
GIT_HOST="$(echo "$GIT_REMOTE" | sed -E 's/^[^@]*@([^:/]+).*/\1/')"     # github.com
REPO_PATH="$(echo "$GIT_REMOTE" | sed -E 's#^[^:]+:##; s#\.git$##')"    # thonglv111/sao-viet-erp
REPO_NAME="$(basename "$REPO_PATH")"                                    # sao-viet-erp

SSH_DIR="/home/${DEPLOY_USER}/.ssh"
KEYA="$SSH_DIR/gha_vps"                       # Key A — DÙNG CHUNG mọi repo
KEYB="$SSH_DIR/deploy_${REPO_NAME}"           # Key B — RIÊNG từng repo
HOST_ALIAS="${GIT_HOST}-${REPO_NAME}"         # vd github.com-sao-viet-erp
CLONE_URL="git@${HOST_ALIAS}:${REPO_PATH}.git"
APP_DIR="${PARENT_DIR}/${REPO_NAME}"

echo
c_info "Tóm tắt:"
echo "    User        : $DEPLOY_USER"
echo "    Git remote  : $GIT_REMOTE"
echo "    Repo path   : $REPO_PATH   (host: $GIT_HOST)"
echo "    Key A (chung): $KEYA"
echo "    Key B (repo) : $KEYB"
echo "    SSH alias   : $HOST_ALIAS"
echo "    Clone URL   : $CLONE_URL"
echo "    → App dir   : $APP_DIR"
echo "    Docker      : $WANT_DOCKER"
pause "Đúng thì Enter, sai thì Ctrl+C để dừng..."

# ---------------------------------------------------------------------------
# 2. USER + GROUP  (idempotent)
# ---------------------------------------------------------------------------
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  c_ok "User '$DEPLOY_USER' đã tồn tại."
else
  c_info "Tạo user '$DEPLOY_USER'..."
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG sudo "$DEPLOY_USER" || true
if [[ "$WANT_DOCKER" =~ ^[Yy] ]]; then
  getent group docker >/dev/null || { c_warn "Tạo group docker (Docker đã cài chưa?)"; groupadd docker; }
  usermod -aG docker "$DEPLOY_USER"
  c_ok "'$DEPLOY_USER' thuộc group docker (hiệu lực ở phiên SSH kế tiếp)."
fi

# ---------------------------------------------------------------------------
# 3. THƯ MỤC .ssh
# ---------------------------------------------------------------------------
c_info "Chuẩn bị $SSH_DIR ..."
mkdir -p "$SSH_DIR"
touch "$SSH_DIR/authorized_keys" "$SSH_DIR/config"

gen_key() {  # $1 = path , $2 = comment  → tạo nếu chưa có, hỏi khi đã tồn tại
  local path="$1" comment="$2"
  if [ -f "$path" ]; then
    c_warn "Đã tồn tại $path"
    c_ask "  Tạo lại (ghi đè)? [y/N]: "; read -r RE
    [[ "$RE" =~ ^[Yy] ]] || { c_ok "  Giữ key cũ."; return 0; }
    rm -f "$path" "$path.pub"
  fi
  sudo -u "$DEPLOY_USER" ssh-keygen -t ed25519 -f "$path" -N "" -C "$comment"
}

# ---------------------------------------------------------------------------
# 4. KEY A — GitHub Actions SSH VÀO VPS  (DÙNG CHUNG mọi repo)
# ---------------------------------------------------------------------------
echo; echo "----- KEY A : GitHub Actions --SSH--> VPS  (chung mọi repo) --------"
if [ -f "$KEYA" ]; then
  c_ok "Key A đã có sẵn ($KEYA) — TÁI DÙNG (không tạo mới)."
else
  c_info "Chưa có Key A → tạo mới (chỉ 1 lần cho cả VPS)."
  sudo -u "$DEPLOY_USER" ssh-keygen -t ed25519 -f "$KEYA" -N "" -C "gha-ssh-into-vps"
fi
# public A → authorized_keys (không nhân đôi)
grep -qF "$(cat "$KEYA.pub")" "$SSH_DIR/authorized_keys" || cat "$KEYA.pub" >> "$SSH_DIR/authorized_keys"
c_ok "Public key A đã nạp vào authorized_keys."

echo
c_warn "PRIVATE KEY A dưới đây → dán vào Secret  VPS_SSH_KEY  của REPO NÀY"
c_warn "(và của MỌI repo khác trên VPS này — GIỐNG NHAU, cả dòng BEGIN/END):"
echo "..................................................................."
cat "$KEYA"
echo "..................................................................."
pause "Đã lưu Secret VPS_SSH_KEY cho repo này? Enter để tiếp..."

# ---------------------------------------------------------------------------
# 5. KEY B — VPS PULL RA GITHUB  (RIÊNG từng repo) + SSH alias
# ---------------------------------------------------------------------------
echo; echo "----- KEY B : VPS --git pull--> GitHub  (riêng repo $REPO_NAME) ----"
gen_key "$KEYB" "deploy-${REPO_NAME}"

echo
c_warn "PUBLIC KEY B dưới đây → GitHub repo  $REPO_PATH  → Settings → Deploy keys"
c_warn "→ Add deploy key (Title tùy ý, CHỈ tick Read, KHÔNG write):"
echo "..................................................................."
cat "$KEYB.pub"
echo "..................................................................."
pause "Đã Add deploy key cho repo $REPO_PATH? Enter để tiếp..."

# ~/.ssh/config: thêm khối alias cho repo này (idempotent theo 'Host <alias>')
if ! grep -qE "^\s*Host\s+${HOST_ALIAS}\s*$" "$SSH_DIR/config"; then
  c_info "Thêm alias '$HOST_ALIAS' vào $SSH_DIR/config"
  {
    echo ""
    echo "# repo: $REPO_PATH"
    echo "Host $HOST_ALIAS"
    echo "    HostName $GIT_HOST"
    echo "    User git"
    echo "    IdentityFile $KEYB"
    echo "    IdentitiesOnly yes"
  } >> "$SSH_DIR/config"
else
  c_ok "Alias '$HOST_ALIAS' đã có trong config."
fi

# host key GitHub (alias trỏ HostName github.com → chỉ cần key của github.com)
sudo -u "$DEPLOY_USER" ssh-keygen -F "$GIT_HOST" >/dev/null 2>&1 \
  || ssh-keyscan "$GIT_HOST" >> "$SSH_DIR/known_hosts" 2>/dev/null

# ---------------------------------------------------------------------------
# 6. PHÂN QUYỀN (sau khi mọi file đã tồn tại)
# ---------------------------------------------------------------------------
c_info "Đặt quyền $SSH_DIR ..."
chmod 700 "$SSH_DIR"
chmod 600 "$SSH_DIR/authorized_keys" "$SSH_DIR/config" "$KEYA" "$KEYB"
chmod 644 "$KEYA.pub" "$KEYB.pub" 2>/dev/null || true
[ -f "$SSH_DIR/known_hosts" ] && chmod 644 "$SSH_DIR/known_hosts"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$SSH_DIR"
c_ok "Quyền OK."

# ---------------------------------------------------------------------------
# 7. TEST AUTH RA GITHUB (qua alias → đúng Key B của repo)
# ---------------------------------------------------------------------------
c_info "Kiểm tra pull được repo qua alias '$HOST_ALIAS'..."
if sudo -u "$DEPLOY_USER" ssh -o StrictHostKeyChecking=accept-new -T "git@${HOST_ALIAS}" 2>&1 | grep -q "successfully authenticated"; then
  c_ok "GitHub xác thực THÀNH CÔNG cho $REPO_PATH."
else
  c_warn "Chưa xác thực được. Đã Add deploy key B cho ĐÚNG repo $REPO_PATH chưa?"
  c_warn "Chạy tay xem lỗi:  sudo -u $DEPLOY_USER ssh -T git@${HOST_ALIAS}"
  pause "Sửa xong rồi Enter để tiếp (hoặc Ctrl+C dừng)..."
fi

# ---------------------------------------------------------------------------
# 8. APP DIR + CLONE (dùng CLONE_URL qua alias → remote origin gắn đúng key)
# ---------------------------------------------------------------------------
c_info "Chuẩn bị thư mục cha: $PARENT_DIR"
mkdir -p "$PARENT_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$PARENT_DIR"

if [ -d "$APP_DIR/.git" ]; then
  c_ok "Đã có repo tại $APP_DIR — cập nhật remote origin về alias."
  ( cd "$APP_DIR" && sudo -u "$DEPLOY_USER" git remote set-url origin "$CLONE_URL" )
elif [ -e "$APP_DIR" ]; then
  c_warn "$APP_DIR đã tồn tại nhưng chưa phải git repo — bỏ qua clone, kiểm tra tay."
else
  c_info "Clone $REPO_PATH vào $APP_DIR (qua alias, quyền $DEPLOY_USER)..."
  ( cd "$PARENT_DIR" && sudo -u "$DEPLOY_USER" git clone "$CLONE_URL" "$REPO_NAME" )
fi
[ -d "$APP_DIR" ] && chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
c_ok "Repo sẵn sàng tại $APP_DIR (origin dùng key riêng của repo)."

# ---------------------------------------------------------------------------
# 9. .env PROD  (dán nội dung, kết thúc bằng dòng EOF hoặc Ctrl-D)
# ---------------------------------------------------------------------------
WRITE_ENV=1
if [ -f "$APP_DIR/.env" ]; then
  c_ok "Đã có $APP_DIR/.env"
  c_ask "  Ghi đè bằng nội dung mới? [y/N]: "; read -r OW
  [[ "$OW" =~ ^[Yy] ]] || WRITE_ENV=0
fi
if [ "$WRITE_ENV" = "1" ] && [ -d "$APP_DIR" ]; then
  echo
  c_warn "DÁN toàn bộ nội dung .env prod. Xong gõ dòng CHỈ có:  EOF  (hoặc Ctrl-D):"
  echo "..................................................................."
  : > "$APP_DIR/.env.tmp"
  while IFS= read -r line; do [ "$line" = "EOF" ] && break; printf '%s\n' "$line" >> "$APP_DIR/.env.tmp"; done
  echo "..................................................................."
  if [ -s "$APP_DIR/.env.tmp" ]; then
    mv "$APP_DIR/.env.tmp" "$APP_DIR/.env"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"; chmod 600 "$APP_DIR/.env"
    c_ok "Đã ghi $APP_DIR/.env ($(wc -l < "$APP_DIR/.env") dòng, quyền 600)."
  else
    rm -f "$APP_DIR/.env.tmp"; c_warn "Không có nội dung → BỎ QUA. Nhớ tạo .env trước khi deploy."
  fi
else
  c_ok "Giữ nguyên .env hiện có."
fi

# ---------------------------------------------------------------------------
# 10. TÓM TẮT + CHECKLIST GITHUB (cho REPO NÀY)
# ---------------------------------------------------------------------------
echo
echo "======================================================================"
c_ok "HOÀN TẤT phần VPS cho repo:  $REPO_PATH"
echo "======================================================================"
echo "Kiểm tra nhanh:"
echo "  groups $DEPLOY_USER  → $(id -nG "$DEPLOY_USER")"
echo "  $(ls -ld "$APP_DIR" 2>/dev/null)"
echo
echo "Đặt trên GitHub — repo  $REPO_PATH  → Settings:"
echo "  • Secrets and variables → Actions:"
echo "      Secret   VPS_SSH_KEY = private KEY A (chung mọi repo — đã in ở trên)"
echo "      Variable VPS_HOST    = $(hostname -I 2>/dev/null | awk '{print $1}')"
echo "      Variable VPS_USER    = $DEPLOY_USER"
echo "      Variable VPS_PORT    = 22"
echo "      Variable APP_DIR     = $APP_DIR"
echo "  • Deploy keys: public KEY B của repo này (Read-only — đã add ở bước 5)"
echo
echo "→ Cấu hình repo tiếp theo: chạy lại script này, nhập git remote của repo đó."
echo "  (Key A giữ nguyên/tái dùng; Key B + alias mới sẽ tự tạo riêng.)"
echo "======================================================================"
