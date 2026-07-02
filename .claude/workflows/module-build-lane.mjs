export const meta = {
  name: 'module-build-lane',
  description: 'Lane worktree: build 1 phân hệ SVN trong git worktree RIÊNG (args.workdir) với backend/frontend/db cổng RIÊNG; eval TĨNH code+API (không Playwright). TUẦN TỰ tuyệt đối (1 agent/lần, không pipeline/song song). Resolve → spec → plan → build+nâng-chất → wire nội-bộ → back-fill.',
  phases: [
    { title: 'Resolve',   detail: 'đọc §41 → màn + thứ tự + số spec (từ specBase); Context Map → seam mở khóa' },
    { title: 'Spec',      detail: 'từng màn một: research → reconcile → verify độc lập → ghi spec MÀN ERP THẬT' },
    { title: 'Plan',      detail: 'spec → feature_list.json; tách làm-ngay vs treo' },
    { title: 'Build',     detail: 'BE+FE theo BAR → init → nâng-chất: verifier TĨNH code+API chấm (MAX_FIX 2)' },
    { title: 'Wire',      detail: 'đóng seam NỘI-BỘ: màn cùng phân hệ nối bằng picker + dữ liệu thật' },
    { title: 'Back-fill', detail: 'đóng seam phân hệ này mở khóa cho phân hệ trước' },
  ],
}

// ── LANE PARAMS (từ args) ──
let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
const MODULE  = A.module
const WORKDIR = A.workdir            // vd D:/jobs/SVN-dm — git worktree riêng của lane
const BE_PORT = A.bePort || 8000
const FE_PORT = A.fePort || 5173
const DB      = A.db || 'dev.db'
const SPEC_BASE = A.specBase || null // số spec bắt đầu (tránh trùng giữa lane); null = đọc index max+1
if (!MODULE || !WORKDIR) return { error: 'Cần args {module, workdir, bePort, fePort, db, specBase}' }

// ── Hạ model+effort toàn lane để đỡ session-limit: Sonnet 5 + medium (mọi agent) ──
const __rawAgent = agent
agent = (p, o = {}) => __rawAgent(p, { model: 'sonnet', effort: 'medium', ...o })

const DOMAIN = 'docs/DOMAIN_NHA_MAY_IN.md'
const LEDGER = 'docs/CROSS_MODULE_LINKS.md'

const LANE = `BỐI CẢNH LANE (BẮT BUỘC): làm việc HOÀN TOÀN trong git worktree "${WORKDIR}" — mọi đường dẫn file & lệnh chạy đều TRONG thư mục đó (dùng đường dẫn TUYỆT ĐỐI bắt đầu bằng "${WORKDIR}/", hoặc cd vào đó ở đầu mỗi lệnh bash vì cwd reset mỗi call). TUYỆT ĐỐI KHÔNG sửa file ở D:/jobs/SVN hay worktree khác. TUYỆT ĐỐI KHÔNG chạy git clean/checkout/reset/stash (sẽ xoá file người khác). Backend lane = cổng ${BE_PORT} (DATABASE_URL=sqlite:///./${DB} đã ở ${WORKDIR}/backend/.env); frontend lane = cổng ${FE_PORT}.`

const CONTRACT = 'CONTRACT: bám đúng mục tiêu được giao; KHÔNG lấn việc màn/bước khác; chỉ đụng file trong phạm vi nêu; trả đúng format yêu cầu.'
const GROUNDING = `Đọc ${DOMAIN} (§ liên quan + §41) làm nguồn chuẩn; web chỉ bù chỗ thiếu; đánh dấu suy luận "chưa xác nhận". Tôn trọng P0 invariant (snapshot giá copy-on-write, Order 1─n Job, DeliveryLine.job_item_id, PrintForm ẩn khỏi Sale) và docs/DB_SCHEMA.md.`
const SEAM = `Nếu gặp liên đới tới phân hệ CHƯA build: KHÔNG làm bừa — dựng SEAM theo ${LEDGER}: (1) cấp ID SEAM-NN; (2) marker "# SEAM-NN: chờ <phân hệ>"; (3) placeholder = Stub raise NotImplementedError("SEAM-NN chưa back-fill"), KHÔNG trả số giả im lặng; (4) 1 test pytest skip/xfail mang đúng ID; (5) hướng phụ thuộc theo DIP — bên CẦN sở hữu port; (6) ghi 1 dòng 8-trường vào ${LEDGER} (⏳). Nguồn sự thật = marker+test.`
const CHECKPOINT = 'CHECKPOINT: cập nhật feature_list.json + progress.md (TRONG worktree lane) sau mỗi feature để resume. KHÔNG git commit trừ khi được yêu cầu.'
const BAR = `BẮT BUỘC đọc trước khi build (TRONG worktree lane): docs/PRODUCT_SENSE.md (6 nguyên tắc "done" + 10 no-go) · docs/UI_DESIGN.md (List→Object-page, panel liên quan chéo module, KPI/biểu đồ/toolbar/tab, states, PDF letterhead) · docs/EVALUATION.md (AUTO-FAIL). Mức chất lượng: docs/design-assets/. Màn ERP THẬT cho công việc thật — KHÔNG form CRUD tối thiểu.`
const WIRE = `NỐI NỘI-BỘ: tham chiếu tới màn CÙNG PHÂN HỆ đã build (xem DANH SÁCH ĐÃ BUILD) → WIRE THẲNG bằng PICKER + kéo dữ liệu thật, KHÔNG ô gõ ID tay, KHÔNG seam. Chỉ seam khi liên đới PHÂN HỆ KHÁC chưa build.`

// Verifier lane: KIỂM TĨNH code + API (KHÔNG Playwright → rẻ + nhanh). Bỏ kiểm thị giác/tương-tác runtime
// (người dùng tự mắt xem 1 lần mỗi phân hệ). Không boot vite, không screenshot, không snapshot.
const EVAL_STATIC = (screen) => `MỤC TIÊU (Verifier ĐỘC LẬP + ĐỐI KHÁNG — KHÔNG thấy lý luận builder): thẩm định màn "${screen}" theo docs/EVALUATION.md BẰNG KIỂM TĨNH CODE + API (KHÔNG dùng Playwright/browser — tiết kiệm token). ${LANE}
CÁCH THẨM ĐỊNH (rẻ, không browser):
1) Chạy ${WORKDIR}/init.ps1 (từ ${WORKDIR}) → pytest+compile PHẢI XANH; không xanh → FAIL (kèm lỗi).
2) ĐỌC code màn (BE router/schema/service + FE page/component) rồi GREP bắt AUTO-FAIL CẤU TRÚC theo EVALUATION.md:
   • Ô gõ ID/tên tự do cho tham chiếu (input/placeholder chứa "ID"/"mã ...(tạm thời)"/nhập tay) thay vì PICKER/combobox trả bản ghi thật.
   • Thiếu PANEL liên quan chéo-module / tab lịch sử / drill-through mà spec đòi (đối chiếu acceptance criteria trong spec màn này).
   • Link/nút CHẾT: <a href="#..."> hoặc onClick rỗng không thật sự điều hướng/hành động.
   • Thiếu TRƯỜNG bắt buộc theo spec; validation server-side vắng; sai luật VN (MST/thuế/đơn vị) nếu áp dụng.
   • Chứng từ gửi ra: PDF builder KHÔNG có letterhead SVN (grep chỗ sinh PDF).
   • BỊA SỐ: giá trị hard-code thay cho seam "chờ phân hệ X" (đáng ra stub RAISE).
3) XÁC MINH DỮ LIỆU THẬT qua API (chỉ backend, KHÔNG browser): cd ${WORKDIR}/backend && python -m uvicorn app.main:app --host 127.0.0.1 --port ${BE_PORT} (nếu curl :${BE_PORT}/api/health='ok' thì dùng lại; ghi ${WORKDIR}/_uv.log). Lấy token: curl -s -XPOST :${BE_PORT}/api/auth/login (admin/admin123). curl các endpoint chính của màn (list/detail/dashboard) → kiểm trả DỮ LIỆU THẬT, FK-linked, KHÔNG số bịa; endpoint seam trả 501/NotImplemented (không giả 0).
4) CHẤM: mọi AUTO-FAIL cấu trúc ⇒ FAIL. Không dính + init xanh + API trả data thật ⇒ PASS. NGHI NGỜ THÌ FAIL. Kèm bằng chứng (đường dẫn:dòng code / đoạn JSON API).
5) init không xanh không sửa nổi / backend không bật → SKIP (KHÔNG giả vờ PASS). ${CONTRACT}`

const VERDICT_SCHEMA = { type:'object', required:['verdict'], properties:{
  verdict:{enum:['PASS','FAIL','SKIP']}, autoFail:{type:'array',items:{type:'string'}},
  weakest:{type:'string'}, evidence:{type:'string'} } }
const SCREENS_SCHEMA = { type:'object', required:['screens'], properties:{ screens:{ type:'array', items:{
  type:'object', required:['key','name','spec','depth','deps'], properties:{
    key:{type:'string'}, name:{type:'string'}, spec:{type:'integer'},
    depth:{enum:['light','medium','heavy']}, deps:{type:'array',items:{type:'string'}} } } },
  backfill:{ type:'array', items:{ type:'object', properties:{ id:{type:'string'}, from:{type:'string'}, need:{type:'string'} } } } } }
const SPEC_SCHEMA  = { type:'object', required:['screen','specPath','featCount'], properties:{
  screen:{type:'string'}, specPath:{type:'string'}, featCount:{type:'integer'},
  crossLinks:{type:'array',items:{type:'string'}}, p0Flags:{type:'array',items:{type:'string'}} } }
const BUILD_SCHEMA = { type:'object', required:['screen','done','initGreen','validated'], properties:{
  screen:{type:'string'}, done:{type:'boolean'}, initGreen:{type:'boolean'},
  validated:{type:'boolean'}, evidence:{type:'string'}, blockers:{type:'array',items:{type:'string'}} } }

// ── PHASE 0 — RESOLVE ──
phase('Resolve')
const r = await agent(
  `MỤC TIÊU: cho phân hệ "${MODULE}", (1) đọc ${WORKDIR}/${DOMAIN} §41 → liệt kê MÀN + thứ tự phụ thuộc dữ liệu + độ sâu in (light/medium/heavy). `
  + (SPEC_BASE ? `Gán số spec BẮT ĐẦU TỪ ${SPEC_BASE} tăng dần (để tránh trùng số với lane khác). `
              : `Gán số spec = đọc ${WORKDIR}/docs/product-specs/index.md lấy max+1 tăng dần. `)
  + `(2) đọc Context Map ${WORKDIR}/${LEDGER} → mọi entry "⏳ ... Tới=${MODULE}" (seam phân hệ NÀY mở khóa) → trả danh sách backfill {id,from,need}. `
  + `Không có trong §41 → screens rỗng. ${LANE} ${CONTRACT}`,
  { label:`resolve:${MODULE}`, phase:'Resolve', schema: SCREENS_SCHEMA })
const SCREENS = (r && r.screens) || []
if (!SCREENS.length) return { error:`Không tìm thấy màn cho phân hệ "${MODULE}" trong §41` }
log(`[${MODULE}] Resolve: ${SCREENS.length} màn; ${((r&&r.backfill)||[]).length} seam back-fill`)

// ── PHASE 1 — SPEC (TUẦN TỰ TỪNG MÀN — 1 agent/lần, KHÔNG pipeline/song song) ──
phase('Spec')
const _sResearch = (s) => agent(`MỤC TIÊU: giải phẫu màn "${s.name}" (${MODULE}, in offset SVN), depth=${s.depth}. `+
    (s.depth==='heavy'?'Tra phần mềm in thật (Label Traxx, PrintVis, Tharstern, Optimus, EFI Pace, PrintSmith, Avanti) qua WebSearch/WebFetch. ':
     s.depth==='medium'?'Chủ yếu domain doc + DB schema; web bù phần đặc thù in. ':'CRUD phổ thông — domain doc + DB schema, không web. ')+
    `FORMAT: bản ghi giải phẫu + nguồn. ${LANE} ${CONTRACT} ${GROUNDING}`, { label:`research:${s.key}`, phase:'Spec' })
const _sReconcile = (research,s) => agent(`MỤC TIÊU: đối chiếu giải phẫu màn "${s.name}" với ${WORKDIR}/${DOMAIN} — bỏ field không hợp SVN, thêm field đặc thù in còn thiếu. ${LANE} ${CONTRACT} ${GROUNDING}\nINPUT:\n${research}`,
    { label:`reconcile:${s.key}`, phase:'Spec' })
const _sVerify = (draft,s) => agent(`MỤC TIÊU (đối kháng): tự ĐỌC LẠI ${WORKDIR}/${DOMAIN} rồi PHẢN BÁC bản nháp màn "${s.name}" — field thừa/thiếu? luồng sai? phá P0/DB schema? Chỉ giữ điều tự kiểm chứng. ${LANE} ${CONTRACT} ${GROUNDING}\nBẢN NHÁP:\n${draft}`,
    { label:`verify:${s.key}`, phase:'Spec' })
const _sWrite = (v,s) => agent(`MỤC TIÊU: viết SPEC màn "${s.name}" như MỘT MÀN ERP THẬT (không CRUD tối thiểu) theo ${WORKDIR}/docs/product-specs/_TEMPLATE.md, bám ${BAR} `+
    `Spec PHẢI nêu: (a) List→Object-page; (b) ĐỦ TRƯỜNG THẬT + luật VN (MST/thuế/đơn vị) — không cắt còn 3 ô; (c) mọi tham chiếu là PICKER (không gõ ID); `+
    `(d) PANEL LIÊN QUAN chéo module + drill-through (seam nếu module đích chưa có); (e) toolbar hành động + tab lịch sử + KPI/biểu đồ khi dữ liệu cho phép; (f) đủ states; (g) PDF letterhead nếu là chứng từ gửi ra. `+
    `Acceptance criteria quan sát được. GHI ${WORKDIR}/docs/product-specs/spec-${String(s.spec).padStart(2,'0')}-${s.key}.md + thêm dòng index.md. ${SEAM} ${LANE} ${CONTRACT} ${GROUNDING}\nĐÃ VERIFY:\n${v}`,
    { label:`spec:${s.key}`, phase:'Spec', schema: SPEC_SCHEMA })
const specs = []
for (const s of SCREENS) {
  const research = await _sResearch(s)
  const draft = await _sReconcile(research, s)
  const v = await _sVerify(draft, s)
  const spec = await _sWrite(v, s)
  if (spec) specs.push(spec)
}
log(`[${MODULE}] Spec: ${specs.length}/${SCREENS.length} màn (tuần tự)`)

// ── PHASE 2 — PLAN ──
phase('Plan')
const plan = await agent(
  `MỤC TIÊU (Planner "${MODULE}"): đọc các spec vừa tạo (${WORKDIR}/docs/product-specs/) + ${WORKDIR}/feature_list.json (nếu có). Sinh feat mới (GIỮ feat done + evidence), đúng thứ tự phụ thuộc, `+
  `acceptance criteria + dependencies, mức "Full per-screen". TÁCH mỗi feat: "làm ngay" hoặc "TREO: cần phân hệ <X>". Feat treo: KHÔNG build, ghi seam vào ${WORKDIR}/${LEDGER}. `+
  `Ghi ${WORKDIR}/feature_list.json. FORMAT: tổng feat, số làm-ngay, số treo, feat đầu buildable. ${LANE} ${CONTRACT}`,
  { label:`plan:${MODULE}`, phase:'Plan' })
log(`[${MODULE}] Plan: ${(plan||'(null)').slice(0,160)}`)

// ── PHASE 3 — BUILD + NÂNG-CHẤT (TUẦN TỰ từng màn; verifier TĨNH code+API) ──
phase('Build')
const order = [...SCREENS].sort((a,b)=>a.deps.length-b.deps.length).map(s=>s.key)
const MAX_FIX = 2
const builds = []
const BUILT = []
for (const key of order) {
  const s = SCREENS.find(x=>x.key===key)
  const builtList = BUILT.length ? BUILT.join(', ') : '(chưa màn nào trong phân hệ này xong)'
  let res = await agent(`MỤC TIÊU (Builder màn "${s.name}", ${MODULE}): xây feat "làm ngay" (BE FastAPI + FE React/Vite) theo ${WORKDIR}/docs/product-specs/spec-${String(s.spec).padStart(2,'0')}-${s.key}.md. ${BAR} ${WIRE}\n`+
    `DANH SÁCH ĐÃ BUILD (cùng phân hệ — WIRE thẳng bằng picker, KHÔNG seam): ${builtList}.\n`+
    `RANH GIỚI: file màn này + đấu nối tới màn đã build. ${SEAM} Chạy ${WORKDIR}/init.ps1 (từ ${WORKDIR}) — chỉ done khi XANH (pytest+compile). ${LANE} ${CHECKPOINT} ${GROUNDING}`,
    { label:`build:${s.key}`, phase:'Build', schema: BUILD_SCHEMA })
  let fixes = 0
  while (res && res.initGreen && fixes < MAX_FIX) {
    const v = await agent(EVAL_STATIC(s.name), { label:`validate:${s.key}`, phase:'Build', schema: VERDICT_SCHEMA })
    if (!v || v.verdict !== 'FAIL') break
    fixes++
    res = await agent(`MỤC TIÊU: sửa màn "${s.name}" đúng chỗ verifier chê (lần ${fixes}/${MAX_FIX}) rồi chạy lại ${WORKDIR}/init.ps1. ${BAR} ${WIRE} ${LANE} ${CHECKPOINT}\n`+
      `AUTO-FAIL: ${(v.autoFail||[]).join(' · ')||'—'}\nĐIỂM YẾU: ${v.weakest||'—'}\nBẰNG CHỨNG: ${v.evidence||'—'}`,
      { label:`rebuild:${s.key}`, phase:'Build', schema: BUILD_SCHEMA }) || res
  }
  if (fixes >= MAX_FIX && res) (res.blockers = res.blockers || []).push(`chưa đạt bar sau ${MAX_FIX} lần sửa — cần người xem`)
  if (res && res.done) BUILT.push(s.name)
  builds.push(res); log(`[${MODULE}] Build ${s.name}: ${res&&res.done?'DONE':'CHƯA'}${res&&res.blockers&&res.blockers.length?' (blocker)':''}`)
}

// ── PHASE 3.5 — WIRE nội-bộ ──
phase('Wire')
const wired = await agent(
  `MỤC TIÊU (Nối nội-bộ "${MODULE}"): quét spec + Context Map ${WORKDIR}/${LEDGER} tìm SEAM mà CẢ HAI đầu thuộc "${MODULE}" và cả hai màn đã build. Đóng từng seam: thay stub/ô-gõ-ID bằng PICKER + kéo dữ liệu thật. `+
  `Sau đó: KHÔNG còn ô gõ ID tay giữa màn cùng phân hệ; test skip→XANH; xoá stub; entry ⏳→✅. Chạy ${WORKDIR}/init.ps1 — chỉ done khi xanh. ${LANE} ${CHECKPOINT} ${CONTRACT} ${GROUNDING}`,
  { label:`wire:${MODULE}`, phase:'Wire', schema: BUILD_SCHEMA })
log(`[${MODULE}] Wire nội-bộ: ${wired&&wired.done?'DONE ✅':'CHƯA'}`)

// ── PHASE 4 — BACK-FILL ──
phase('Back-fill')
const backfilled = []
for (const item of ((r && r.backfill) || [])) {
  const b = await agent(
    `MỤC TIÊU (Back-fill seam ${item.id}): phân hệ "${MODULE}" đã có → hoàn thiện phần TREO ở "${item.from}" (${item.need}). `+
    `Đấu vào seam đã dựng (port/interface). PHA CONTRACT: (a) test ${item.id} skip→XANH, (b) XOÁ stub NotImplementedError, (c) entry ${item.id} trong ${WORKDIR}/${LEDGER} ⏳→✅. `+
    `Chạy ${WORKDIR}/init.ps1 — chỉ done khi xanh. ${LANE} ${CHECKPOINT} ${CONTRACT} ${GROUNDING}`,
    { label:`backfill:${item.id}`, phase:'Back-fill', schema: BUILD_SCHEMA })
  backfilled.push({ id:item.id, ...(b||{}) })
  log(`[${MODULE}] Back-fill ${item.id}: ${b&&b.done?'ĐÓNG ✅':'CHƯA'}`)
}

return {
  module: MODULE, workdir: WORKDIR, ports:{be:BE_PORT, fe:FE_PORT}, db: DB,
  specs: specs.map(x=>({screen:x.screen, specPath:x.specPath, featCount:x.featCount, crossLinks:x.crossLinks||[], p0Flags:x.p0Flags||[]})),
  plan: (plan||'').slice(0,400),
  builds: builds.filter(Boolean).map(b=>({screen:b.screen, done:b.done, initGreen:b.initGreen, validated:b.validated, blockers:b.blockers||[]})),
  wiredInternal: !!(wired && wired.done),
  backfilled,
}
