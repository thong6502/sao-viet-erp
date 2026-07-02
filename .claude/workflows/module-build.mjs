export const meta = {
  name: 'module-build',
  description: 'Build BẤT KỲ phân hệ SVN (args.module): resolve màn → spec (tuần tự) → plan → build+validate (tuần tự) → back-fill mối nối chéo. One-shot, 1 agent/lần. Đọc/ghi Context Map CROSS_MODULE_LINKS.md; seam = SEAM-id + marker + test skip.',
  phases: [
    { title: 'Resolve',   detail: 'đọc §41 → màn + thứ tự + số spec; đọc Context Map → seam mà phân hệ này mở khóa' },
    { title: 'Spec',      detail: 'tuần tự mỗi màn: research → reconcile → verify độc lập → ghi spec MÀN ERP THẬT (đủ trường/panel liên quan/hành động/states)' },
    { title: 'Plan',      detail: 'spec → feature_list.json; tách feat làm-ngay vs treo → ghi Context Map' },
    { title: 'Build',     detail: 'tuần tự: BE+FE theo BAR (chọn-đừng-gõ, panel liên quan, PDF letterhead) → init → VÒNG NÂNG-CHẤT: evaluator độc lập đối kháng chấm tới khi đạt bar' },
    { title: 'Wire',      detail: 'đóng seam NỘI-BỘ: màn cùng phân hệ tự nối bằng picker + kéo dữ liệu thật (hết gõ ID tay)' },
    { title: 'Back-fill', detail: 'Parallel Change: đóng seam phân hệ này mở khóa cho phân hệ trước (test skip→xanh, xoá stub, đóng entry)' },
  ],
}

const MODULE = (args && args.module) || (typeof args === 'string' ? args : null)
if (!MODULE) return { error: 'Thiếu args.module — gọi qua skill svn-build-module với {module:"<tên phân hệ>"}' }

const DOMAIN = 'docs/DOMAIN_NHA_MAY_IN.md'
const LEDGER = 'docs/CROSS_MODULE_LINKS.md'

// Delegation contract (Anthropic): mọi subagent phải có mục tiêu / format / tool+nguồn / ranh giới.
const CONTRACT = 'CONTRACT: bám đúng mục tiêu được giao; KHÔNG lấn việc màn/bước khác; chỉ đụng file trong phạm vi nêu; trả đúng format yêu cầu.'
const GROUNDING = `Đọc ${DOMAIN} (§ liên quan + §41) làm nguồn chuẩn; web chỉ bù chỗ thiếu; đánh dấu suy luận "chưa xác nhận". Tôn trọng P0 invariant (snapshot giá copy-on-write, Order 1─n Job, DeliveryLine.job_item_id, PrintForm ẩn khỏi Sale) và docs/DB_SCHEMA.md.`
// Seam (Feathers/Branch-by-Abstraction) + Context Map ghi bằng máy, không bằng trí nhớ.
const SEAM = `Nếu gặp liên đới tới phân hệ CHƯA build: KHÔNG làm bừa — dựng SEAM theo quy ước ${LEDGER}: `
  + `(1) cấp ID ổn định SEAM-NN; (2) đặt marker "# SEAM-NN: chờ <phân hệ>" tại chỗ nối; `
  + `(3) placeholder = Stub tường minh raise NotImplementedError("SEAM-NN chưa back-fill"), KHÔNG trả giá trị giả im lặng; `
  + `(4) tạo 1 test pytest skip/xfail mang đúng ID (reason="SEAM-NN ...") làm enabling point; `
  + `(5) hướng phụ thuộc theo DIP — bên CẦN sở hữu interface/port, bên cung cấp implement sau; tránh vòng lặp; `
  + `(6) ghi 1 dòng 8-trường vào ${LEDGER} (⏳). Nguồn sự thật = marker+test, sổ chỉ là index.`
const CHECKPOINT = 'CHECKPOINT: cập nhật status/passes trong feature_list.json + progress.md sau mỗi feature (để resume, không restart). KHÔNG git commit trừ khi người dùng yêu cầu.'
// BAR chất lượng — ép mọi build đọc trước; mục tiêu ERP THẬT xuất sắc + dễ dùng, không CRUD tối thiểu.
const BAR = `BẮT BUỘC đọc trước khi build: docs/PRODUCT_SENSE.md (6 nguyên tắc "done" + 10 no-go) · docs/UI_DESIGN.md (kiến trúc List→Object-page, panel liên quan chéo module, KPI/biểu đồ/toolbar/tab, states, PDF letterhead) · docs/EVALUATION.md (AUTO-FAIL). Mức chất lượng cần chạm: docs/design-assets/. Làm màn ERP THẬT cho công việc thật — KHÔNG form CRUD tối thiểu.`
// Nội-bộ = WIRE thẳng; chéo phân hệ chưa build = seam.
const WIRE = `NỐI NỘI-BỘ: tham chiếu tới màn CÙNG PHÂN HỆ đã build (xem DANH SÁCH ĐÃ BUILD) → WIRE THẲNG bằng PICKER + kéo dữ liệu thật, TUYỆT ĐỐI không ô gõ ID tay, không seam. Chỉ seam khi liên đới PHÂN HỆ KHÁC chưa build (hoặc màn cùng phân hệ chưa tới lượt).`
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

// ── PHASE 0 — RESOLVE (1 subagent) ──
phase('Resolve')
const r = await agent(
  `MỤC TIÊU: cho phân hệ "${MODULE}", (1) đọc ${DOMAIN} §41 → liệt kê MÀN + thứ tự phụ thuộc dữ liệu + độ sâu in (light/medium/heavy, để hiệu chỉnh công sức research); `
  + `gán số spec kế tiếp = đọc docs/product-specs/index.md lấy max+1 tăng dần. `
  + `(2) đọc Context Map ${LEDGER} → mọi entry "⏳ ... Tới=${MODULE}" (seam phân hệ NÀY mở khóa) → trả danh sách backfill {id,from,need}. `
  + `Không có trong §41 → screens rỗng. ${CONTRACT}`,
  { label:`resolve:${MODULE}`, phase:'Resolve', schema: SCREENS_SCHEMA })
const SCREENS = (r && r.screens) || []
if (!SCREENS.length) return { error:`Không tìm thấy màn cho phân hệ "${MODULE}" trong §41` }
log(`Resolve: ${SCREENS.length} màn; ${((r&&r.backfill)||[]).length} seam cần back-fill`)

// ── PHASE 1 — SPEC (TUẦN TỰ: mỗi màn lần lượt research → reconcile → verify độc lập → ghi spec; 1 agent/lần, KHÔNG pipeline/song song) ──
phase('Spec')
const specs = []
for (const s of SCREENS) {
  // ① research (effort theo depth)
  const research = await agent(`MỤC TIÊU: giải phẫu màn "${s.name}" (${MODULE}, in offset SVN), depth=${s.depth}. `+
    (s.depth==='heavy'?'Tra phần mềm in thật (Label Traxx, PrintVis, Tharstern, Optimus, EFI Pace, PrintSmith, Avanti) qua WebSearch/WebFetch: dữ liệu hiển thị/input/nút/luồng. ':
     s.depth==='medium'?'Chủ yếu domain doc + DB schema; web bù phần đặc thù in. ':'CRUD phổ thông — domain doc + DB schema, không web. ')+
    `FORMAT: bản ghi giải phẫu + nguồn. ${CONTRACT} ${GROUNDING}`, { label:`research:${s.key}`, phase:'Spec' })
  // ② reconcile với domain
  const draft = await agent(`MỤC TIÊU: đối chiếu giải phẫu màn "${s.name}" với ${DOMAIN} — bỏ field không hợp SVN, thêm field đặc thù in còn thiếu. ${CONTRACT} ${GROUNDING}\nINPUT:\n${research}`,
    { label:`reconcile:${s.key}`, phase:'Spec' })
  // ③ adversarial verify ĐỘC LẬP: tự đọc lại domain, KHÔNG tin lý luận của bước trước
  const v = await agent(`MỤC TIÊU (đối kháng): tự ĐỌC LẠI ${DOMAIN} rồi PHẢN BÁC bản nháp màn "${s.name}" — field thừa/thiếu? luồng sai nghiệp vụ in? phá P0/DB schema? Đừng mặc nhiên tin bản nháp; chỉ giữ điều tự kiểm chứng được. ${CONTRACT} ${GROUNDING}\nBẢN NHÁP CẦN SOI:\n${draft}`,
    { label:`verify:${s.key}`, phase:'Spec' })
  // ④ ghi spec MÀN ERP THẬT (đủ trường/panel liên quan/hành động/states) + seam nếu chạm phân hệ chưa có
  const spec = await agent(`MỤC TIÊU: viết SPEC màn "${s.name}" như MỘT MÀN ERP THẬT (không CRUD tối thiểu) theo docs/product-specs/_TEMPLATE.md, bám ${BAR} `+
    `Spec PHẢI nêu rõ: (a) kiến trúc List→Object-page; (b) ĐỦ TRƯỜNG THẬT theo nghiệp vụ + luật VN (MST, thuế, đơn vị) — không cắt còn 3 ô; (c) mọi tham chiếu là PICKER (không gõ ID); `+
    `(d) các PANEL LIÊN QUAN chéo module + drill-through (seam nếu module đích chưa có); (e) toolbar hành động ngữ cảnh + tab lịch sử + KPI/biểu đồ khi dữ liệu cho phép; (f) đủ states (rỗng/tải/lỗi); (g) PDF letterhead nếu là chứng từ gửi ra. `+
    `Acceptance criteria viết dạng quan sát được (Playwright). GHI docs/product-specs/spec-${String(s.spec).padStart(2,'0')}-${s.key}.md + thêm dòng index.md. ${SEAM} ${CONTRACT} ${GROUNDING}\nĐÃ VERIFY:\n${v}`,
    { label:`spec:${s.key}`, phase:'Spec', schema: SPEC_SCHEMA })
  if (spec) specs.push(spec)
}
log(`Spec: ${specs.length}/${SCREENS.length} màn`)

// ── PHASE 2 — PLAN (barrier: cần đủ spec; tách làm-ngay vs treo) ──
phase('Plan')
const plan = await agent(
  `MỤC TIÊU (Planner "${MODULE}"): đọc các spec vừa tạo + feature_list.json hiện có. Sinh feat mới (GIỮ feat done + evidence), đúng thứ tự phụ thuộc, `+
  `acceptance criteria + dependencies, mức "Full per-screen". TÁCH mỗi feat: "làm ngay" hoặc "TREO: cần phân hệ <X>". `+
  `Feat treo: KHÔNG đưa vào build, ghi seam vào ${LEDGER}. FORMAT: tổng feat, số làm-ngay, số treo, feat đầu buildable. ${CONTRACT}`,
  { label:`plan:${MODULE}`, phase:'Plan' })
log(`Plan: ${(plan||'(null — agent lỗi/limit)').slice(0,180)}`)

// ── PHASE 3 — BUILD + VÒNG NÂNG-CHẤT (tuần tự; build → evaluator độc lập đối kháng → sửa tới khi đạt bar) ──
phase('Build')
const order = [...SCREENS].sort((a,b)=>a.deps.length-b.deps.length).map(s=>s.key)
const MAX_FIX = 4 // nâng-chất: sửa tới khi đạt bar, có trần chống doom-loop
const builds = []
const BUILT = [] // màn cùng phân hệ đã xong → build sau WIRE thẳng vào, không seam
for (const key of order) {
  const s = SCREENS.find(x=>x.key===key)
  const builtList = BUILT.length ? BUILT.join(', ') : '(chưa màn nào trong phân hệ này xong)'
  let res = await agent(`MỤC TIÊU (Builder màn "${s.name}", ${MODULE}): xây feat "làm ngay" (BE FastAPI + FE React/Vite) theo spec-${String(s.spec).padStart(2,'0')}-${s.key}.md. ${BAR} ${WIRE}\n`+
    `DANH SÁCH ĐÃ BUILD (cùng phân hệ — WIRE thẳng bằng picker + kéo dữ liệu, KHÔNG seam): ${builtList}.\n`+
    `RANH GIỚI: file màn này + đấu nối tới màn đã build. ${SEAM} Chạy ./init.ps1 — chỉ done khi XANH (pytest+compile). ${CHECKPOINT} ${GROUNDING}`,
    { label:`build:${s.key}`, phase:'Build', schema: BUILD_SCHEMA })
  let fixes = 0
  while (res && res.initGreen && fixes < MAX_FIX) {
    const v = await agent(`MỤC TIÊU (Evaluator ĐỘC LẬP + ĐỐI KHÁNG — KHÔNG thấy lý luận builder): tự khởi động app (backend :8000 + Vite :5173) rồi Playwright MCP mở màn "${s.name}" và thao tác NHƯ NHÂN VIÊN NHÀ IN THẬT. Chấm nghiêm theo docs/EVALUATION.md: quét AUTO-FAIL (gõ ID tay · thiếu panel liên quan · bịa số · thiếu trường · PDF không letterhead · thiếu state/console lỗi · không làm nổi việc), 4 tiêu chí ≥4, và 2 lăng kính Liền-mạch/Dễ-dùng; hiệu chỉnh theo mức docs/design-assets/. NGHI NGỜ THÌ FAIL. Mọi kết luận kèm bằng chứng (screenshot/thao tác/network). Không mở được app → verdict SKIP (KHÔNG giả vờ PASS). ${CONTRACT}`,
      { label:`validate:${s.key}`, phase:'Build', schema: VERDICT_SCHEMA })
    if (!v || v.verdict !== 'FAIL') break
    fixes++
    res = await agent(`MỤC TIÊU: sửa màn "${s.name}" đúng chỗ evaluator chê (lần ${fixes}/${MAX_FIX}) rồi chạy lại ./init.ps1. ${BAR} ${WIRE} ${CHECKPOINT}\n`+
      `AUTO-FAIL: ${(v.autoFail||[]).join(' · ')||'—'}\nĐIỂM YẾU: ${v.weakest||'—'}\nBẰNG CHỨNG: ${v.evidence||'—'}`,
      { label:`rebuild:${s.key}`, phase:'Build', schema: BUILD_SCHEMA }) || res
  }
  if (fixes >= MAX_FIX && res) (res.blockers = res.blockers || []).push(`chưa đạt bar sau ${MAX_FIX} lần sửa — cần người xem`)
  if (res && res.done) BUILT.push(s.name)
  builds.push(res); log(`Build ${s.name}: ${res&&res.done?'DONE':'CHƯA'}${res&&res.blockers&&res.blockers.length?' (blocker)':''}`)
}

// ── PHASE 3.5 — WIRE (đóng seam NỘI-BỘ: màn cùng phân hệ tự nối, hết gõ ID tay) ──
phase('Wire')
const wired = await agent(
  `MỤC TIÊU (Nối nội-bộ "${MODULE}"): quét spec + Context Map ${LEDGER} tìm SEAM mà CẢ HAI đầu thuộc phân hệ "${MODULE}" và cả hai màn đã build. Đóng từng seam đó: thay stub/ô-gõ-ID bằng PICKER + kéo dữ liệu thật giữa 2 màn `+
  `(vd Báo giá CHỌN Khách hàng thật + NẠP giá vốn thật từ Tính giá; Tính giá đọc cấu phần Sản phẩm thật). Sau khi xong: KHÔNG còn ô gõ ID tay giữa các màn cùng phân hệ; test skip→XANH; xoá stub; entry ⏳→✅. `+
  `Chạy ./init.ps1 — chỉ done khi xanh. ${CHECKPOINT} ${CONTRACT} ${GROUNDING}`,
  { label:`wire:${MODULE}`, phase:'Wire', schema: BUILD_SCHEMA })
log(`Wire nội-bộ: ${wired&&wired.done?'DONE ✅':'CHƯA'}`)

// ── PHASE 4 — BACK-FILL (Parallel Change: expand→migrate→CONTRACT/đóng seam) ──
phase('Back-fill')
const backfilled = []
for (const item of ((r && r.backfill) || [])) {
  const b = await agent(
    `MỤC TIÊU (Back-fill seam ${item.id}): phân hệ "${MODULE}" đã có → hoàn thiện phần TREO ở "${item.from}" (${item.need}). `+
    `Đấu vào seam đã dựng (port/interface). PHA CONTRACT bắt buộc: (a) test ${item.id} skip→XANH, (b) XOÁ stub NotImplementedError, (c) đổi entry ${item.id} trong ${LEDGER} ⏳→✅. `+
    `Chạy ./init.ps1 — chỉ done khi xanh. ${CHECKPOINT} ${CONTRACT} ${GROUNDING}`,
    { label:`backfill:${item.id}`, phase:'Back-fill', schema: BUILD_SCHEMA })
  backfilled.push({ id:item.id, ...(b||{}) })
  log(`Back-fill ${item.id}: ${b&&b.done?'ĐÓNG ✅':'CHƯA'}`)
}

return {
  module: MODULE,
  specs: specs.map(x=>({screen:x.screen, specPath:x.specPath, featCount:x.featCount, crossLinks:x.crossLinks||[], p0Flags:x.p0Flags||[]})),
  plan: (plan||'').slice(0,400),
  builds: builds.filter(Boolean).map(b=>({screen:b.screen, done:b.done, initGreen:b.initGreen, validated:b.validated, blockers:b.blockers||[]})),
  wiredInternal: !!(wired && wired.done),
  backfilled,
}
