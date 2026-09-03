# Bổ sung "Các tình huống thường gặp" cho 12 chương còn lại — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mỗi chương 2–13 của "Sổ tay sử dụng phân hệ Kinh doanh" (`docs/user-manual-kinh-doanh/`) có thêm một mục `\subsubsection*{Các tình huống thường gặp}` — bảng 2 cột Vấn đề/Cách xử lý — đúng format đã có ở Chương 1, để cả cuốn nhất quán (hiện chỉ Chương 1 có mục này).

**Architecture:** Không viết nội dung mới từ đầu — mỗi chương đã có sẵn 3–15 khung `\begin{luuy}` (đã live+source-verify lúc viết chương gốc). Mỗi Task đọc lại các khung đó, chọn ra 3–4 cái mang dáng "vấn đề người dùng thật gặp → cách xử lý", viết lại súc tích hơn thành một dòng bảng, chèn `\subsubsection*{Các tình huống thường gặp}` + `\begin{longtable}` vào cuối chương (không đụng nội dung đã có), biên dịch + xem lại bằng ảnh render.

**Tech Stack:** LaTeX (xelatex, MiKTeX), PyMuPDF (`python`, không phải `python3`) để render trang ra PNG kiểm bằng mắt.

**Spec:** Không có spec riêng — bối cảnh đầy đủ nằm trong phần "Bối cảnh" dưới đây và trong chính plan gốc đã hoàn tất `docs/superpowers/plans/2026-09-02-huong-dan-su-dung-kinh-doanh.md`.

## Bối cảnh

Cuốn sổ tay đã viết xong 100% qua nhiều phiên, dựng từ môi trường cô lập (backend port 8010, frontend port 5174, DB Postgres `svn_erp_manual_demo`) qua live browser + đọc mã nguồn — **KHÔNG cần mở lại môi trường đó cho plan này**, vì mọi nội dung dùng lại đều đã verify khi viết chương gốc. Chỉ Chương 1 (Đơn vị đo & Quy đổi) có mục "Các tình huống thường gặp" (bảng `Vấn đề`/`Cách xử lý`, xem `chuong-01-don-vi-quy-doi.tex:143-175`); 12 chương còn lại thiếu hẳn — người dùng phát hiện và yêu cầu bổ sung đủ.

Riêng Chương 10 đã có sẵn hai lớp liên quan đến "cảnh báo/tình huống" (không phải trùng lặp, giữ nguyên cả hai):
- `\subsection{Những cảnh báo mềm bạn có thể gặp khi tính giá}` cuối chương (dòng 383–406) — liệt kê các cảnh báo HỆ THỐNG tự hiện (nhãn đỏ thiếu khổ/giấy, băng cảnh báo dữ liệu nền đổi, khổ tờ in vượt máy không cảnh báo, công đoạn thiếu công thức).
- Một khung `\begin{luuy}` mới thêm ở Khối 4 (dòng 202–211) về rủi ro xếp sai thứ tự chuỗi công đoạn.

Mục "Các tình huống thường gặp" mới của Chương 10 phải né trùng với "cảnh báo mềm" — chỉ chứa những tình huống do NGƯỜI DÙNG tự gây ra rồi tự khắc phục (routing sai thứ tự, ghi đè chuỗi tay, nhét cả cuốn sách vào 1 dòng), không lặp lại 4 mục cảnh báo hệ thống đã liệt kê ở đó. Task 9 xử lý riêng phần rút gọn khung `\luuy` cũ ở Khối 4 để tránh chép hai lần cùng ví dụ số.

## Global Constraints

- Format bảng bắt buộc giống hệt Chương 1: `\subsubsection*{Các tình huống thường gặp}` (không đánh số, không vào mục lục) rồi `\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}` với dòng đầu `\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\` + `\midrule` + `\endhead`, mỗi dòng nội dung cách nhau `\hline`, kết bằng `\bottomrule` + `\end{longtable}`.
- KHÔNG chép nguyên văn khung `\luuy` gốc vào bảng — bảng phải súc tích hơn (2–4 câu mỗi ô), giữ lại ví dụ số nếu có.
- Không cần mở lại môi trường cô lập, không cần ảnh chụp mới — chỉ dùng lại nội dung đã verify.
- KHÔNG có bước git commit — `docs/user-manual-kinh-doanh/` đã nằm trong `.gitignore`, không track.
- KHÔNG cần TDD/pytest — "test" của mỗi Task là: biên dịch 2 lần bằng `xelatex -interaction=nonstopmode main.tex`, PATH thêm bằng
  `export PATH="$PATH:/c/Users/Windows10 Pro/AppData/Local/Programs/MiKTeX/miktex/bin/x64"` (bash) trong `docs/user-manual-kinh-doanh/`,
  grep log kiểm không có `error:`/`undefined`/`missing character` mới (bỏ qua các dòng `ignored error: Infinite glue shrinkage` — đã biết vô hại, có từ trước), rồi render đúng trang vừa sửa ra PNG bằng script Python (PyMuPDF, gọi bằng `python` — KHÔNG phải `python3`) ghi vào thư mục scratchpad, Read lại ảnh để xác nhận bảng không tràn lề/không vỡ chữ. Xoá `compile1.log`/`compile2.log` sau khi xong mỗi Task.
- Không đổi bất kỳ nội dung nào khác đã có trong 12 file — chỉ CHÈN THÊM đúng một khối mới vào cuối mỗi file (trừ Task 9 có thêm bước rút gọn một khung `\luuy` đã có).

---

### Task 1: Chương 2 — Máy & Thiết bị

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-02-may-thiet-bi.tex` (chèn sau dòng 303, cuối file — sau `\end{luuy}` của mục "Lưu ý vận hành cần nhớ")

- [ ] **Bước 1: Đọc lại 20 dòng cuối file để xác nhận vị trí chèn**

Xác nhận file kết thúc đúng ở `\end{luuy}` (dòng 303), không còn nội dung nào sau đó.

- [ ] **Bước 2: Chèn khối mới bằng Edit — old_string là 3 dòng cuối file, new_string thêm mục mới sau đó**

```latex
  \item Khi lập phiếu tính giá, chọn Máy chỉ cần gán đúng máy — không cần tự tay chép khổ/chừa lề
  của máy vào phiếu, hệ tự đọc thẳng từ danh mục này mỗi lần tính lại.
\end{enumerate}
\end{luuy}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Đặt tên Nhóm máy dài hơn 24 ký tự lúc tạo máy mới.
&
Hệ vẫn cho chọn tên đó ở ô ``Nhóm máy'' khi tạo, nhưng lúc lưu máy báo lỗi kỹ thuật tiếng Anh
\textit{``loai\_may: String should have at most 24 characters''}. Đặt tên Nhóm máy ngắn gọn dưới
24 ký tự ngay từ đầu. \\
\hline
Cần đổi tên một Nhóm máy đã tạo (vd gõ sai chính tả).
&
Không sửa được tên tại chỗ — tạo nhóm mới đúng tên, chuyển từng máy đang thuộc nhóm cũ sang nhóm
mới, rồi xoá nhóm cũ (chỉ xoá được khi không còn máy nào dùng). \\
\hline
Đổi Nhóm máy của một máy in từ ``Máy in'' sang tên khác (vd ``Cán màng / UV''), hai khối ô ``Khổ
kẽm \& Vùng in'' và ``Thông số chừa lề tờ in'' biến mất khỏi form.
&
Đúng hành vi — 7 ô này chỉ hiện khi tên Nhóm máy chứa chữ ``in''. Số liệu cũ vẫn còn trong dữ
liệu, chỉ không sửa được qua form nữa; đổi lại đúng nhóm có chữ ``in'' để thấy lại. \\
\hline
Bình bài ra số con thành phẩm hụt 14–19\% so với thực tế.
&
Kiểm lại ô ``Nhíp giấy'' trên màn Máy — đây CHỈ là phần giấy bị kẹp khi chạy máy (8–12mm), không
phải mép nhíp trên bản kẽm (khoảng 44mm, không có ô riêng). Gõ nhầm mép nhíp kẽm vào ô Nhíp giấy
là nguyên nhân phổ biến nhất gây hụt số con. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**

```bash
cd "D:/jobs/SVN/docs/user-manual-kinh-doanh" && export PATH="$PATH:/c/Users/Windows10 Pro/AppData/Local/Programs/MiKTeX/miktex/bin/x64" && xelatex -interaction=nonstopmode main.tex > compile1.log 2>&1; xelatex -interaction=nonstopmode main.tex > compile2.log 2>&1; grep -iE "^!|error:|undefined|missing character" compile2.log
```

Expected: chỉ còn các dòng `ignored error: Infinite glue shrinkage` đã biết, không có gì khác.

- [ ] **Bước 4: Render trang vừa sửa ra PNG rồi Read lại kiểm bằng mắt**

Viết script Python (KHÔNG heredoc, dùng Write tool) tìm trang chứa chữ ``Bình bài ra số con thành phẩm hụt'' bằng PyMuPDF, `get_pixmap(dpi=150).save(...)` vào thư mục scratchpad, rồi Read ảnh đó — xác nhận bảng đủ 4 dòng, không tràn lề phải, chữ không vỡ dấu.

- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 2: Chương 3 — Công đoạn

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-03-cong-doan.tex` (chèn sau dòng 310, cuối file — sau `\end{figure}`)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn** (kết thúc ở `\end{figure}` dòng 310)

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\begin{figure}[H]
\centering
\includegraphics[width=0.95\textwidth]{06-tab1-cd0002-may-rang-buoc.png}
\caption{CD-0002 — khối ``Máy làm được công đoạn này'' với 2 nhóm máy đã tick.}
\end{figure}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Cột ``Ràng buộc'' trên danh sách để trống, tưởng công đoạn không ràng buộc máy nào.
&
Đừng tin cột danh sách — mở form sửa của đúng công đoạn đó để xem thật, cột danh sách có thể
trống dù bản ghi đã tick máy ràng buộc (lỗi hiển thị đã ghi nhận, dữ liệu vẫn đúng). \\
\hline
Lưu một công đoạn khai NGOÀI dòng giấy (ghi kẽm, ép nhũ, khung lụa…) báo lỗi E-CD-DONVI.
&
Sửa cả hai ô đơn vị đầu vào và đầu ra sang đúng loại đơn vị thật của bước đó — đừng để một đầu
giữ nguyên \texttt{tờ} theo mặc định của form. \\
\hline
Tìm ô ``Đơn giá'' hay ``Cách tính giá'' riêng cho công đoạn.
&
Không có ô riêng — toàn bộ tiền của công đoạn gõ vào đúng MỘT ô ``Công thức tính giá'', đơn giá
nằm ngay trong công thức (vd \texttt{so\_kem * 95000}). \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log** (lệnh giống Task 1 Bước 3)
- [ ] **Bước 4: Render trang chứa ``E-CD-DONVI'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 3: Chương 4 — Khuôn/Bế

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-04-khuon-be.tex` (chèn sau dòng 136, cuối file — sau `\end{luuy}`)

- [ ] **Bước 1: Đọc lại 20 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
  \item Bản kẽm (\texttt{kem}) KHÔNG tính vào phí khuôn — kẽm là vật tư tiêu hao phải phơi mới cho
  từng bài in, tiền của nó đã nằm sẵn trong công thức của công đoạn Ghi kẽm (\texttt{so\_kem × đơn
  giá}, xem mục \ref{chuong:cong-doan}). Cộng thêm vào phí khuôn là tính trùng.
\end{itemize}
\end{luuy}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Muốn nhân bản một khuôn có sẵn để tạo dòng tương tự.
&
Không có nút ``Nhân bản'' ở danh mục này (chỉ có Xóa) — mỗi khuôn là một con dao vật lý cụ thể,
phải tự khai dòng mới. \\
\hline
Lập Lệnh sản xuất mà quên gán Khuôn ở bước liên quan.
&
Hệ vẫn cho phát hành lệnh bình thường (gán khuôn không bắt buộc) — nhưng thợ tới bước đó có thể
không biết lấy đúng dao nào. Với hàng lặp lại nhiều lần (hộp, tem quen), tập thói quen gán ngay
lúc lập lệnh. \\
\hline
Đơn lặp lại dùng đúng khuôn cũ vẫn bị tính thêm phí khuôn mới.
&
Chọn ``Dùng khuôn có sẵn'' và để 0 hoặc bỏ trống ô Phí khuôn trên phiếu tính giá — đúng thông lệ
ngành, phí khuôn chỉ thu ở đơn đặt lần đầu. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``Dùng khuôn có sẵn'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 4: Chương 5 — Giấy

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-05-giay.tex` (chèn sau dòng 171, cuối file — sau `\end{luuy}`)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\begin{luuy}
Đừng nhầm hai ô công thức: ``Công thức tính giá'' phục vụ phiếu tính giá (ra tiền), ``Công thức tính
lượng'' phục vụ kế hoạch vật tư (ra lượng) — sửa nhầm ô sẽ làm sai một trong hai module mà không báo
lỗi gì, vì cả hai công thức đều hợp lệ về mặt cú pháp.
\end{luuy}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Cần sửa giá của một loại Giấy đang dùng.
&
Chỉ có một cách — sửa thẳng ô ``Đơn giá'' trong form Giấy. Đừng đi tìm màn ``phiên bản giá''/lịch
sử giá — API còn sống ở backend nhưng không còn nút nào gọi tới trên giao diện. Sửa xong, phiếu
tính giá lập MỚI tự lấy giá mới; phiếu đã chốt/gửi khách giữ nguyên số cũ. \\
\hline
Đọc nhãn ``Đơn giá (đ/kg)'' trên danh sách Giấy dù ĐVT của dòng đó là tờ/ram/cái.
&
Nhãn luôn in cứng ``đ/kg'' bất kể ĐVT thật — đây là khoảng hiển thị chưa cập nhật, không phải sai
dữ liệu; số gõ vào thực chất là đ/tờ, đ/ram... theo đúng ĐVT đã chọn, engine tính giá vẫn đọc
đúng. \\
\hline
Sửa công thức của một loại Giấy mà không rõ tại sao Tính giá hoặc Kế hoạch vật tư ra số sai.
&
Kiểm đúng ô đã sửa — ``Công thức tính giá'' phục vụ phiếu tính giá (ra tiền), ``Công thức tính
lượng'' phục vụ kế hoạch vật tư (ra lượng); sửa nhầm ô không báo lỗi vì cả hai đều hợp lệ cú
pháp. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``phiên bản giá'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 5: Chương 6 — Vật tư khác

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-06-vat-tu-khac.tex` (chèn sau dòng 118, cuối file — sau `\end{luuy}`)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\begin{luuy}
Menu Cấu hình danh mục còn một mục tên ``Thành phẩm'' đứng ngay sau Vật tư khác, dùng CHUNG một bảng
dữ liệu với danh mục này nhưng phục vụ mục đích khác hẳn (khai sản phẩm đặt riêng theo từng đơn hàng,
không tạo/xoá tay được) — xem chi tiết ở phần Thành phẩm phía sau tài liệu này, đừng nhầm hai màn.
\end{luuy}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Mở danh mục Vật tư khác trên hệ thống mới thấy rỗng, tưởng lỗi tải dữ liệu.
&
Đúng hành vi — hệ thống trắng không có sẵn bộ vật tư mẫu nào. Tự khai từng mực/keo/màng cần dùng
qua nút ``Thêm vật tư khác''. \\
\hline
Tìm tab ``Công thức tính giá'' trên màn Vật tư khác để gắn tiền vào phiếu tính giá.
&
Tab này bị ẩn có chủ đích — xưởng không thêm dòng mực/màng/keo rời vào phiếu tính giá; tiền của
chúng đã nằm sẵn trong đơn giá khoán của công đoạn dùng tới (xem chương Công đoạn). \\
\hline
Nhầm màn Vật tư khác với màn Thành phẩm (dùng chung một bảng dữ liệu).
&
Vật tư khác là kho nguyên liệu dùng chung (mực, keo, màng); Thành phẩm là sản phẩm đặt riêng theo
từng đơn hàng, không tạo/xoá tay được — xem chương Thành phẩm. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``hệ thống trắng không có sẵn'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 6: Chương 7 — Thành phẩm

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-07-thanh-pham.tex` (chèn sau dòng 127, cuối file)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
Việc chốt một đơn hàng thật để xem dòng Thành phẩm tự sinh ra sao cần đủ Khách hàng
(mục \ref{chuong:khach-hang}), một phiếu Tính giá (mục \ref{chuong:tinh-gia}) và Đơn hàng bán đã chốt
— trình tự này thuộc các chương phía sau, sẽ có ảnh chụp luồng tự sinh thật khi tới chương
\ref{chuong:don-hang-ban}.

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Không rõ khác gì giữa danh mục Thành phẩm và Loại sản phẩm.
&
Loại sản phẩm là khuôn mẫu kỹ thuật (name card/sách/hộp — trả lời ``in kiểu gì''), dùng để bình
bài/tính giá. Thành phẩm trả lời câu khác: ``hàng nào của đơn nào'', chỉ xuất hiện SAU khi đơn đã
chốt. \\
\hline
Muốn xoá một dòng Thành phẩm không dùng nữa.
&
Cột Hành động không có nút Xóa hay Nhân bản — tắt cờ ``Đang dùng'' trên bảng lọc để ngừng dùng,
không xoá hẳn (xoá sẽ làm mồ côi dữ liệu kho nếu dòng đó còn lô tồn/phiếu đã ghi sổ). \\
\hline
Đặt cùng một tên hàng ở hai đơn khác nhau nhưng hệ tạo ra hai dòng Thành phẩm tách biệt thay vì
gộp tồn kho.
&
Hệ so tên đã chuẩn hoá (bỏ hoa/thường, gộp khoảng trắng/gạch ngang, KHÔNG bỏ dấu) — gõ tên hơi
khác (thiếu dấu, thừa khoảng trắng kiểu khác) vẫn đẻ dòng mới. Sửa lại Tên trên dòng thừa cho khớp
đúng dòng cũ. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``mồ côi dữ liệu kho'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 7: Chương 8 — Loại sản phẩm

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-08-loai-san-pham.tex` (chèn sau dòng 175, cuối file — sau `\end{figure}`)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\begin{figure}[H]
\centering
\includegraphics[width=0.95\textwidth]{09-nhap-excel-loai-san-pham.png}
\caption{Hộp thoại Nhập Excel của Loại sản phẩm — cùng cơ chế MỘT LƯỢT với các danh mục khác: mã đã
có thì cập nhật, ô trống trong file xoá giá trị cột đó, mã chưa có thì tạo mới.}
\label{fig:lsp-excel}
\end{figure}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Cần khai các thuộc tính kỹ thuật (Kiểu cấu trúc, Kiểu hộp, Có bìa, Kiểu đóng mặc định…) cho một
Loại sản phẩm.
&
Form web không có ô cho sáu cột này (tạo/sửa qua web luôn ép ngầm về mặc định) — chỉ khai được
qua xuất Excel danh mục, sửa trên file rồi nhập lại. \\
\hline
Đã tự tay sửa chuỗi công đoạn của một sản phẩm (xoá bớt/thêm bước), sau đó chọn lại đúng Loại sản
phẩm đó (hoặc chọn lần đầu) — các bước đã xoá tay bất ngờ quay lại.
&
Đúng hành vi — chọn một Loại sản phẩm CÓ chuỗi mặc định luôn bung lại ĐỦ các bước mặc định, không
hỏi xác nhận, không hoàn tác. Đã chỉnh tay chuỗi thì tránh chọn lại Loại sản phẩm của chính sản
phẩm đó, trừ khi cố ý muốn nạp lại đúng bộ mặc định. \\
\hline
Xoá một Loại sản phẩm đang được một phiếu tính giá tham chiếu.
&
Không bị chặn thao tác — máy tự chuyển dòng đó thành ngừng dùng thay vì xoá hẳn (khác Thành phẩm,
không có nút nào). Xem lại các dòng đã ngừng dùng bằng công tắc trên dải lọc. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``bung lại ĐỦ các bước mặc định'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 8: Chương 9 — Khách hàng

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-09-khach-hang.tex` (chèn sau dòng 209, cuối file — sau `\end{viDu}`)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\begin{viDu}
Khách hàng thật tạo trong phiên soạn tài liệu này: \textbf{KH001 — Công ty TNHH Bao bì Sao Việt}.
Email hoá đơn \texttt{hoadon@saoviet-baobi.vn}. Chính sách tài chính: hạn mức công nợ 50 triệu đồng,
30 ngày kể từ ngày xuất hoá đơn, chiết khấu 0\%–10\%, markup 15\%–35\% (trên giá vốn). Một liên hệ
chính: Nguyễn Văn An — Trưởng phòng mua hàng — 0909123456. Một điểm giao mặc định: Nhà máy Bao bì
Sao Việt, Lô CN-12 KCN Quang Minh, Mê Linh, Hà Nội. Nhãn: VIP. Một ghi chú, một lịch hẹn chăm sóc
ngày 13/9/2026 (đã tích xong), một tài liệu loại GPKD.
\end{viDu}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Lưu hồ sơ khách mới trùng MST/tên/email với một khách đã có.
&
Hệ chỉ hiện banner cảnh báo, KHÔNG chặn lưu — tự quyết định vẫn tạo mới (hai khách trùng thông tin
thật) hay huỷ để dùng lại khách cũ. \\
\hline
Sale muốn biết chiết khấu/markup đã thoả thuận với một khách có vượt rào công ty cho phép không.
&
Mở hồ sơ khách, xem 4 ô Chiết khấu min/max, Markup min/max — đây là nơi DUY NHẤT khai rào giá
riêng cho khách đó; Báo giá tự đọc 4 số này để cảnh báo/chặn khi lập. \\
\hline
Đã tạo lịch hẹn chăm sóc và tích ``Đánh dấu đã xong'', nhưng tab Nhật ký lọc ``Chăm sóc'' vẫn đứng
ở 0.
&
Đúng hành vi hiện tại — Nhật ký chỉ ghi 4 loại thao tác (tạo khách, sửa chính sách tài chính, gán
nhãn, đính kèm tài liệu); lịch hẹn/chăm sóc chưa lên Nhật ký dù màn có hiển thị bộ lọc. Muốn xem
đã hẹn/chăm sóc gì, vào thẳng tab Chăm sóc. \\
\hline
Định gõ một nhãn mới cho khách (vd ``Khách VIP'') mà không để ý đã có nhãn gần giống.
&
Mở kho nhãn xem trước — hệ đã mồi sẵn 13 nhãn thường dùng (VIP, Ưu tiên, Đối tác lâu năm…), chọn
thẳng từ đó để tránh tạo trùng ý khác chữ. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``kho nhãn xem trước'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 9: Chương 10 — Tính giá (kèm rút gọn khung `\luuy` cũ ở Khối 4)

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-10-tinh-gia.tex` (rút gọn khối dòng 202–211; chèn mới sau dòng 406, cuối file)

**Interfaces:**
- Produces: label `\label{sec:tg-tinh-huong}` trên mục mới — dùng để khung `\luuy` ở Khối 4 (đã rút gọn) trỏ ngược qua `\ref{sec:tg-tinh-huong}`.

- [ ] **Bước 1: Đọc lại dòng 189–211 (khung `\luuy` ở Khối 4) và 15 dòng cuối file (383–406)**

- [ ] **Bước 2: Rút gọn khung `\luuy` ở Khối 4 bằng Edit — bỏ ví dụ số cụ thể (chuyển xuống bảng mới), giữ phần giải thích CƠ CHẾ**

old_string:
```latex
\begin{luuy}
Thứ tự chip KHÔNG chỉ để hiển thị — hệ tính ``Bù hao công đoạn'' và ``Tờ vào máy'' bằng cách đi
NGƯỢC từ chip CUỐI lên chip ĐẦU (bước cuối hỏi trước ``để ra đủ hàng tốt thì phải nhận vào bao
nhiêu'', dội ngược dần lên đầu chuỗi). Xếp sai thứ tự — đã từng xảy ra thật: bước ``In'' bị đẩy
xuống cuối chuỗi thay vì đứng đầu (đúng quy trình phải in xong mới cán màng/bế/dán được) — khiến cả
hai số này tính sai hoàn toàn (báo 10.310 tờ thay vì đúng phải 20.619 tờ). Hệ có cảnh báo ``chuỗi
đứt đơn vị'' khi đơn vị RA của một bước không khớp đơn vị VÀO của bước liền sau, nhưng đây chỉ là
gợi ý — hệ KHÔNG tự chặn tính giá. Trước khi tin số Bù hao/Tờ vào máy, luôn tự soát lại chuỗi chip
đúng theo trình tự chạy thật ngoài xưởng.
\end{luuy}
```

new_string:
```latex
\begin{luuy}
Thứ tự chip KHÔNG chỉ để hiển thị — hệ tính ``Bù hao công đoạn'' và ``Tờ vào máy'' bằng cách đi
NGƯỢC từ chip CUỐI lên chip ĐẦU (bước cuối hỏi trước ``để ra đủ hàng tốt thì phải nhận vào bao
nhiêu'', dội ngược dần lên đầu chuỗi) — xếp sai thứ tự làm cả hai số này tính sai hoàn toàn, xem ca
thật đã xảy ra ở mục ``Các tình huống thường gặp'' cuối chương (\ref{sec:tg-tinh-huong}). Hệ có
cảnh báo ``chuỗi đứt đơn vị'' khi đơn vị RA của một bước không khớp đơn vị VÀO của bước liền sau,
nhưng đây chỉ là gợi ý — hệ KHÔNG tự chặn tính giá.
\end{luuy}
```

- [ ] **Bước 3: Chèn mục mới ở cuối file bằng Edit**

old_string (3 dòng cuối file hiện tại):
```latex
\item \textbf{Công đoạn báo ``thiếu công thức — 0đ''} — không phải lỗi nhập liệu, xem ví dụ và lưu
ý ở mục \ref{sec:tg-vidu-tronven}: công đoạn được chọn đúng nhưng bản thân công đoạn đó chưa khai
công thức tính giá ở danh mục thì phần giá vốn Công đoạn luôn ra 0đ một cách im lặng.
\end{enumerate}
\end{luuy}
```

new_string:
```latex
\item \textbf{Công đoạn báo ``thiếu công thức — 0đ''} — không phải lỗi nhập liệu, xem ví dụ và lưu
ý ở mục \ref{sec:tg-vidu-tronven}: công đoạn được chọn đúng nhưng bản thân công đoạn đó chưa khai
công thức tính giá ở danh mục thì phần giá vốn Công đoạn luôn ra 0đ một cách im lặng.
\end{enumerate}
\end{luuy}

\subsubsection*{Các tình huống thường gặp}
\label{sec:tg-tinh-huong}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Chuỗi công đoạn (Khối 4) xếp sai thứ tự so với quy trình chạy thật ngoài xưởng — vd bước ``In'' bị
đẩy xuống cuối chuỗi thay vì đứng đầu.
&
Xếp lại đúng thứ tự chạy thật trước khi tin số — hệ tính ``Bù hao công đoạn''/``Tờ vào máy'' bằng
cách đi ngược từ bước cuối lên bước đầu (mục \ref{sec:tg-congdoan-block}), xếp sai thứ tự làm hai
số này sai hoàn toàn. Ca thật đã xảy ra: chuỗi đúng phải là In → Cán màng → Bế TP → Dán TP → KCS →
Đóng gói → Giao hàng; xếp nhầm In xuống cuối khiến ``Tờ vào máy'' báo 10.310 tờ thay vì đúng phải
20.619 tờ. \\
\hline
Đã tự sửa tay chuỗi công đoạn của một sản phẩm trong phiếu, sau đó bấm lại/đổi lại đúng Loại sản
phẩm gắn với nó — chuỗi bất ngờ trở lại y hệt mặc định, mất hết chỗ vừa sửa.
&
Đúng hành vi hệ thống (xem chương Loại sản phẩm) — tránh chọn lại Loại sản phẩm của chính sản phẩm
đó sau khi đã chỉnh tay chuỗi, trừ khi cố ý muốn nạp lại bộ mặc định. \\
\hline
Định khai một cuốn sách (bìa + ruột) chỉ bằng một dòng ``Sản phẩm'' duy nhất trong phiếu.
&
Tách thành hai dòng riêng (``Ruột'' và ``Bìa'' — khác giấy, khác số màu, khác công đoạn), rồi dùng
``Nhóm khi báo giá'' để gộp lại thành một dòng trên bản in gửi khách nếu cần. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 4: Biên dịch 2 lần, grep log**
- [ ] **Bước 5: Render CẢ trang chứa khung `\luuy` đã rút gọn (Khối 4) LẪN trang chứa bảng mới cuối chương ra PNG, Read lại cả hai kiểm bằng mắt — xác nhận `\ref{sec:tg-tinh-huong}` resolve ra đúng số mục, không phải ``??''**
- [ ] **Bước 6: Xoá `compile1.log`, `compile2.log`**

---

### Task 10: Chương 11 — Báo giá

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-11-bao-gia.tex` (chèn sau dòng 252, cuối file — sau `\end{luuy}`)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\begin{luuy}
Một báo giá chỉ sinh được ĐÚNG MỘT đơn hàng — đã có đơn thì nút đổi thành ``Xem đơn hàng'', không
tạo thêm đơn thứ hai từ cùng báo giá đó được nữa.
\end{luuy}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Cần sửa một báo giá đã gửi (đổi giá/điều khoản) — bấm nhầm ``Báo giá →'' trên Phiếu tính giá lại
ra một mã báo giá MỚI.
&
``Báo giá →'' trên phiếu LUÔN tạo báo giá mới, không mở lại bản cũ. Muốn sửa bản đã có, mở đúng
báo giá đó và dùng ``Tạo phiên bản mới'' bên trong nó. \\
\hline
Đọc ô ``Markup'' trên Báo giá rồi so trực tiếp với ``Biên lợi nhuận'' hiển thị bên Đơn hàng bán,
thấy hai số lệch nhau dù cùng một đơn.
&
Không phải lỗi nhập liệu hai nơi — Markup ở Báo giá tính trên GIÁ VỐN, Biên lợi nhuận ở Đơn hàng
bán tính trên GIÁ BÁN; hai công thức khác nhau, chênh rõ khi tỷ lệ lớn (vd markup 10\% ứng với
biên lợi nhuận chỉ 9,1\%). \\
\hline
Báo giá đã được duyệt, sửa lại giá/markup/chiết khấu xong mà hệ bắt trình duyệt lại từ đầu.
&
Đúng hành vi khi mức sửa mới NẶNG hơn mức đã duyệt trước — sửa nhẹ hơn hoặc bằng mức cũ (vd hạ giá
bán, giảm markup nhưng vẫn trong rào cũ) thì không cần duyệt lại. \\
\hline
Báo giá đang chạy (Nháp/Chờ duyệt/Đã duyệt/Đã gửi/Khách đồng ý) mà không tìm thấy nút ``Tạo phiên
bản mới''.
&
Đúng thiết kế — chỉ báo giá đã đi hết vòng đời (khách chốt/từ chối) mới tạo phiên bản mới được;
còn Nháp thì sửa thẳng tại chỗ, các trạng thái giữa chừng phải đợi khách trả lời trước. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``biên lợi nhuận chỉ 9,1\%'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 11: Chương 12 — Đơn hàng bán

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-12-don-hang-ban.tex` (chèn sau dòng 277, cuối file — sau `\end{luuy}`)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\begin{luuy}
Đơn đã chốt rồi mới huỷ — ô Lý do hủy nên kể luôn tình trạng lúc huỷ (vd ``đã ra kẽm'', ``khách đổi
ý sau khi ký'') vì đây là bằng chứng duy nhất còn lại để tra cứu sau này, không có ô nào khác ghi
lại chi tiết đó.
\end{luuy}

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Bấm ``Chốt đơn'' mà khách chưa đóng đủ tiền cọc, sợ thao tác bị chặn.
&
Không bị chặn — ``Chốt'' chỉ khoá cứng thông tin đơn (giá/PO/ngày giao), thu cọc là bước riêng;
chỉ tới bước ``Chuyển xuống sản xuất'' mới thật sự bị chặn nếu cọc chưa đủ. \\
\hline
Cần sửa địa chỉ giao hàng riêng cho một đơn đã tạo.
&
Màn Đơn hàng không có ô sửa địa chỉ/người nhận — hai ô này chỉ đọc, kế thừa từ Báo giá. Phải quay
lại sửa ở Báo giá TRƯỚC khi tạo đơn; tạo đơn xong thì chịu. \\
\hline
Huỷ một đơn đã chốt nhưng nút Huỷ bị khoá/báo lỗi.
&
Kiểm đơn còn hoá đơn đang hiệu lực không (bước Hóa đơn \& công nợ) — có thì phải huỷ hoá đơn trước
rồi mới huỷ được đơn. \\
\hline
So ``Biên lợi nhuận'' hiển thị ở Đơn hàng bán với ``Markup'' đã gõ bên Báo giá cho cùng một đơn,
thấy hai số khác nhau.
&
Không phải lỗi — hai chỉ số đo hai thứ khác nhau (Biên lợi nhuận chia giá bán, Markup chia giá
vốn), chỉ trùng nhau ở mức thấp do làm tròn. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``bước Chuyển xuống sản xuất'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 12: Chương 13 — Giao hàng

**Files:**
- Modify: `docs/user-manual-kinh-doanh/chuong-13-giao-hang.tex` (chèn sau dòng 270, cuối file)

- [ ] **Bước 1: Đọc lại 15 dòng cuối file xác nhận vị trí chèn**

- [ ] **Bước 2: Chèn khối mới bằng Edit**

```latex
\subsection{Cầu nối sang Kế toán — ``Đã giao đủ'' là cờ được phép xuất hoá đơn}

Nhãn hệ tự tính ``Đã giao đủ'' ở tầng Yêu cầu (mục đầu chương) không chỉ để Bán hàng đọc — Kế toán
dựa đúng vào cờ này để biết đơn đã đủ điều kiện xuất hoá đơn hay chưa, trước khi ghi nhận ở panel
Hóa đơn của Đơn hàng bán (mục \ref{sec:dhb-hoadon}). Vì vậy một đơn giao dở dang, dù khách đã ép
xuất hoá đơn trước, vẫn nên đợi đủ hàng rồi mới ghi — tránh lệch sổ giữa số đã giao thật và số đã
xuất hoá đơn.

\subsubsection*{Các tình huống thường gặp}

\begin{longtable}{>{\raggedright\arraybackslash}p{5cm} p{9.8cm}}
\rowcolor{tblhead}\textbf{Vấn đề} & \textbf{Cách xử lý} \\
\midrule
\endhead
Số ``Còn phải giao'' của một đơn không khớp phép tính Đặt trừ Đã giao trừ số đang có trong yêu cầu
mở, thấp hơn thực tế.
&
Đừng vội nghĩ do gõ sai số lượng — kiểm có yêu cầu nào đã ``lên kế hoạch rồi bị huỷ kế hoạch''
không (mục \ref{sec:gh-huy-yeu-cau}), số giữ chỗ của yêu cầu đó không tự trả lại. Đây là lỗi phần
mềm đã xác nhận qua mã nguồn — cách xử lý thực tế là lập một yêu cầu giao MỚI cho phần hàng còn
lại. \\
\hline
NV Sales không thấy nút ``Huỷ yêu cầu'' trên một yêu cầu mình vừa gửi nhầm.
&
Đúng phân quyền mặc định — NV Sales chỉ có Xem + Sửa, không có quyền Huỷ; nhờ Trưởng phòng/Giám
đốc Kinh doanh hoặc Quản lý giao hàng huỷ giúp. \\
\hline
Bấm ``Xem bản in'' ở Đơn hàng bán, tưởng đây là nơi theo dõi Yêu cầu/Chuyến giao hàng.
&
Hai thứ không liên quan — ``Xem bản in'' chỉ là phiếu giao hàng in nhanh, mượn số của đơn hàng,
không đọc dữ liệu YCGH; theo dõi giao hàng thật nằm ở mục đầu chương này. \\
\hline
Huỷ một Đơn hàng bán đã chốt trong khi đơn đó còn Yêu cầu/Chuyến giao hàng đang mở.
&
Hệ không tự kiểm tra hay cảnh báo việc này — phải tự nhớ báo điều phối huỷ kế hoạch/huỷ yêu cầu
(nếu còn huỷ được) ngay sau khi huỷ đơn. \\
\bottomrule
\end{longtable}
```

- [ ] **Bước 3: Biên dịch 2 lần, grep log**
- [ ] **Bước 4: Render trang chứa ``lên kế hoạch rồi bị huỷ kế hoạch'' ra PNG, Read lại kiểm bằng mắt**
- [ ] **Bước 5: Xoá `compile1.log`, `compile2.log`**

---

### Task 13: Rà soát cuối + gửi lại PDF

**Files:** không sửa file nào — chỉ kiểm tổng và gửi.

- [ ] **Bước 1: Biên dịch main.tex 2 lần từ đầu, xác nhận tổng số trang tăng hợp lý (91 trang cũ + phần thêm của 12 chương) và không có undefined ref nào còn sót (grep `Label(s) may have changed` không xuất hiện ở log lần 2)**

- [ ] **Bước 2: Grep toàn bộ 13 file chương xác nhận đủ 13/13 chương có `Các tình huống thường gặp`**

```bash
cd "D:/jobs/SVN/docs/user-manual-kinh-doanh" && grep -l "Các tình huống thường gặp" chuong-*.tex | wc -l
```

Expected: `13`.

- [ ] **Bước 3: Xoá `compile1.log`, `compile2.log`**

- [ ] **Bước 4: Gửi `main.pdf` qua SendUserFile với caption ngắn nêu đã thêm đủ 12 chương + đổi gì ở chương 10**

---

## Self-Review (đã chạy khi viết plan)

**1. Spec coverage:** 12/12 chương trong yêu cầu đều có Task riêng (Task 1–12), cộng Task 13 rà soát tổng — đủ. Riêng yêu cầu phụ "routing công đoạn đã nhắc chưa, thêm ảnh 2 chưa" được Task 9 xử lý bằng dữ liệu số đầy đủ rút ra từ ảnh 2 (không nhúng ảnh Slack gốc — không phù hợp một cuốn sổ tay gửi khách nội bộ chuyên nghiệp).

**2. Placeholder scan:** Không còn "TBD"/"tương tự Task N"/mô tả chung chung — mọi Task đều có nguyên văn khối LaTeX sẽ chèn.

**3. Type/format consistency:** Cả 12 bảng dùng đúng một khai báo cột `>{\raggedright\arraybackslash}p{5cm} p{9.8cm}` và cùng chuỗi `\rowcolor{tblhead}...\midrule...\endhead...\hline...\bottomrule` như Chương 1 — khớp tuyệt đối, không có chương nào lệch cấu trúc cột.
