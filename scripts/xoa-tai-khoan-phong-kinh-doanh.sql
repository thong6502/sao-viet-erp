-- =============================================================================
-- XOÁ TÀI KHOẢN ĐĂNG NHẬP GẮN VÀO HỒ SƠ NHÂN SỰ PHÒNG KINH DOANH
-- Postgres 16 (service `db` trong docker-compose trên VPS)
--
-- Chạy trên VPS, từ thư mục có docker-compose.yml + .env:
--
--   docker compose exec -T db psql -v ON_ERROR_STOP=1 \
--       -U "$POSTGRES_USER" -d "$POSTGRES_DB" < scripts/xoa-tai-khoan-phong-kinh-doanh.sql
--
-- SAO LƯU TRƯỚC (bắt buộc — xoá users là không hoàn lại được):
--   docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > svn-$(date +%F-%H%M).sql
--
-- LƯU Ý: app KHÔNG có đường xoá cứng tài khoản (chỉ có khoá/mở), nên mọi bảng
-- đang trỏ vào `users` phải tự dọn tay — phần dưới làm việc đó bằng cách đọc
-- danh sách khoá ngoại từ chính DB (không liệt kê tay 76 cột, không sợ sót).
-- =============================================================================

\set PB '''PB003'''   -- mã phòng Kinh doanh; đổi ở đây nếu chạy cho phòng khác


-- -----------------------------------------------------------------------------
-- BƯỚC 0 — XEM TRƯỚC (chỉ đọc, chạy riêng trước khi xoá)
-- -----------------------------------------------------------------------------
WITH RECURSIVE pb AS (
    SELECT id FROM departments WHERE code = :PB
    UNION ALL
    SELECT d.id FROM departments d JOIN pb ON d.parent_id = pb.id
)
SELECT e.code        AS ma_ho_so,
       e.full_name   AS ho_ten,
       e.position    AS chuc_danh,
       u.id          AS user_id,
       u.code        AS ma_tk,
       u.username    AS ten_dang_nhap,
       u.is_active   AS dang_hoat_dong,
       r.name        AS vai_tro
FROM employees e
JOIN users u ON u.id = e.user_id
LEFT JOIN roles r ON r.id = u.role_id
WHERE e.department_id IN (SELECT id FROM pb)
ORDER BY e.code;


-- -----------------------------------------------------------------------------
-- BƯỚC 1 — XOÁ (một giao dịch; sai ở đâu là rollback sạch, không xoá dở)
-- -----------------------------------------------------------------------------
BEGIN;

CREATE TEMP TABLE tk_xoa ON COMMIT DROP AS
WITH RECURSIVE pb AS (
    SELECT id FROM departments WHERE code = :PB
    UNION ALL
    SELECT d.id FROM departments d JOIN pb ON d.parent_id = pb.id
)
SELECT DISTINCT e.user_id AS user_id
FROM employees e
WHERE e.department_id IN (SELECT id FROM pb)
  AND e.user_id IS NOT NULL;

-- Chốt chặn: không bao giờ xoá tài khoản quản trị, kể cả khi nó bị gán nhầm
-- vào một hồ sơ của phòng Kinh doanh.
DELETE FROM tk_xoa
WHERE user_id IN (SELECT id FROM users WHERE username IN ('admin'));

DO $do$
DECLARE
    r          record;
    n          bigint;
    tong_null  bigint := 0;
    chan       text   := '';
    so_tk      bigint;
BEGIN
    SELECT count(*) INTO so_tk FROM tk_xoa;
    RAISE NOTICE 'Tài khoản trong phạm vi xoá: %', so_tk;
    IF so_tk = 0 THEN
        RAISE EXCEPTION 'Không có tài khoản nào khớp — kiểm lại mã phòng.';
    END IF;

    -- 1) Cắt liên kết hồ sơ ↔ tài khoản (hồ sơ nhân sự GIỮ NGUYÊN, chỉ mất ô đăng nhập).
    UPDATE employees SET user_id = NULL
     WHERE user_id IN (SELECT user_id FROM tk_xoa);
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'employees.user_id -> NULL: % dòng', n;

    -- 2) Trưởng phòng: cột logic, KHÔNG có khoá ngoại nên vòng lặp dưới không thấy.
    --    Bỏ sót ô này thì phòng KD còn trỏ vào tài khoản đã biến mất.
    UPDATE departments SET head_user_id = NULL
     WHERE head_user_id IN (SELECT user_id FROM tk_xoa);
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'departments.head_user_id -> NULL: % dòng', n;

    -- 3) Mọi khoá ngoại trỏ vào users(id), đọc thẳng từ catalog.
    --    Bỏ qua ràng buộc ON DELETE CASCADE/SET NULL — Postgres tự dọn.
    FOR r IN
        SELECT c.conrelid::regclass::text AS tbl,
               a.attname                  AS col,
               a.attnotnull               AS bat_buoc
        FROM pg_constraint c
        JOIN LATERAL unnest(c.conkey) AS k(attnum) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype   = 'f'
          AND c.confrelid = 'users'::regclass
          AND c.confdeltype IN ('a', 'r')
        ORDER BY 1, 2
    LOOP
        IF r.bat_buoc THEN
            -- Cột NOT NULL: không NULL được, chỉ có hai đường — xoá dòng, hoặc dừng.
            EXECUTE format(
                'SELECT count(*) FROM %s WHERE %I IN (SELECT user_id FROM tk_xoa)',
                r.tbl, r.col) INTO n;
            IF n > 0 THEN
                IF r.tbl IN ('refresh_tokens', 'notifications') THEN
                    -- Phiên đăng nhập + thông báo: dữ liệu tạm, xoá theo là đúng.
                    EXECUTE format(
                        'DELETE FROM %s WHERE %I IN (SELECT user_id FROM tk_xoa)',
                        r.tbl, r.col);
                    RAISE NOTICE '%.%: xoá % dòng (dữ liệu tạm)', r.tbl, r.col, n;
                ELSE
                    chan := chan || format(E'\n  - %s.%s : %s dòng', r.tbl, r.col, n);
                END IF;
            END IF;
        ELSE
            EXECUTE format(
                'UPDATE %s SET %I = NULL WHERE %I IN (SELECT user_id FROM tk_xoa)',
                r.tbl, r.col, r.col);
            GET DIAGNOSTICS n = ROW_COUNT;
            IF n > 0 THEN
                tong_null := tong_null + n;
                RAISE NOTICE '%.% -> NULL: % dòng', r.tbl, r.col, n;
            END IF;
        END IF;
    END LOOP;

    IF chan <> '' THEN
        RAISE EXCEPTION E'DỪNG — các tài khoản này còn đứng tên NGƯỜI LẬP trên chứng từ bắt buộc có người lập:%\n\nXoá tài khoản đồng nghĩa phải xoá luôn chứng từ. Hãy KHOÁ tài khoản (BƯỚC 1B) thay vì xoá, hoặc chuyển người lập sang tài khoản khác rồi chạy lại.', chan;
    END IF;

    DELETE FROM users WHERE id IN (SELECT user_id FROM tk_xoa);
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'ĐÃ XOÁ % tài khoản; % ô tham chiếu đã chuyển NULL.', n, tong_null;
END
$do$;

COMMIT;
-- Đọc kỹ dòng NOTICE ở trên. Muốn huỷ thì đổi COMMIT thành ROLLBACK rồi chạy lại.


-- -----------------------------------------------------------------------------
-- BƯỚC 2 — RÀ SÓT: cột int trỏ users nhưng KHÔNG có khoá ngoại (báo cáo, không sửa)
-- -----------------------------------------------------------------------------
DO $do$
DECLARE r record; n bigint; co boolean := false;
BEGIN
    FOR r IN
        SELECT c.table_name AS tbl, c.column_name AS col
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name   = c.table_name
         AND t.table_type   = 'BASE TABLE'
        WHERE c.table_schema = 'public'
          AND c.data_type IN ('integer', 'bigint')
          AND c.column_name LIKE '%user_id'
          AND NOT EXISTS (
                SELECT 1
                FROM pg_constraint fk
                JOIN LATERAL unnest(fk.conkey) AS k(attnum) ON true
                JOIN pg_attribute a ON a.attrelid = fk.conrelid AND a.attnum = k.attnum
                WHERE fk.contype   = 'f'
                  AND fk.confrelid = 'users'::regclass
                  AND fk.conrelid  = format('public.%I', c.table_name)::regclass
                  AND a.attname    = c.column_name)
        ORDER BY 1, 2
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM public.%I x WHERE x.%I IS NOT NULL '
            'AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = x.%I)',
            r.tbl, r.col, r.col) INTO n;
        IF n > 0 THEN
            co := true;
            RAISE NOTICE 'Còn trỏ vào tài khoản đã xoá: %.% — % dòng', r.tbl, r.col, n;
        END IF;
    END LOOP;
    IF NOT co THEN
        RAISE NOTICE 'Sạch: không ô nào còn trỏ vào tài khoản đã xoá.';
    END IF;
END
$do$;


-- =============================================================================
-- BƯỚC 1B (THAY THẾ) — KHOÁ thay vì xoá: người đó hết đăng nhập được ngay lập tức,
-- mọi phiên đang mở bị đá ra (token_version tăng), nhưng chứng từ cũ vẫn còn tên.
-- Đây là cách app đang làm; chạy CÁI NÀY nếu BƯỚC 1 báo DỪNG.
-- =============================================================================
-- BEGIN;
-- WITH RECURSIVE pb AS (
--     SELECT id FROM departments WHERE code = 'PB003'
--     UNION ALL
--     SELECT d.id FROM departments d JOIN pb ON d.parent_id = pb.id
-- ), tk AS (
--     SELECT DISTINCT e.user_id FROM employees e
--     WHERE e.department_id IN (SELECT id FROM pb) AND e.user_id IS NOT NULL
-- )
-- UPDATE users u
--    SET is_active = false, token_version = u.token_version + 1
--  WHERE u.id IN (SELECT user_id FROM tk)
--    AND u.username <> 'admin';
-- DELETE FROM refresh_tokens WHERE user_id IN (
--     SELECT id FROM users WHERE is_active = false);
-- COMMIT;
