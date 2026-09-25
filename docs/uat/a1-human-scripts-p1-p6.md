# GP · UAT scripts người thật × 6 chân dung (P1–P6)

> **Đối tác quan sát:** Học viện Tài chính (HVTC) · Viettel Money  
> **Staging shell (GP):** https://welora-staging.onrender.com  
> **Repo:** `thangnc2u/welora-staging` · ticket GP A  
> **Parity:** CP A1 Notion-readable (25/09) — adapted cho GP OS paths + seed aliases Done #227  
> **Luật chạy:** DNA ≤7 · **không số tiền trong DNA** · OS goals chỉ `emergency_fund` | `debt_payoff` · UI **không** lộ khóa CORE-/SAFE-/DEBT- · không đụng Hard Deny / `gate_months` / `TARGET_MONTHS` · mọi số tiền mẫu gắn `[Inf]`

---

## Header chung (đọc trước khi chạy)

### Seed aliases (Done #227) — mật khẩu chung `WeloraDemo1!`

| Px | label_vi | household | alias |
|----|----------|-----------|-------|
| P1 | Độc thân đô thị 18+ | `solo` | `demo-p1@welora.demo` |
| P2 | 25–34 Gia đình trẻ khởi đầu | `young_family` | `partner@welora.demo` |
| P3 | 35–59 Nâng đỡ hai đầu (không con nhỏ) | `couple_no_kids` | `demo-p3@welora.demo` |
| P4 | 35–59 Ba đời trên một take-home | `sandwich_3gen` | `demo-p4@welora.demo` |
| P5 | 55–64 Cửa sổ 10 năm trước hưu | `pre_retire` | `demo-p5@welora.demo` |
| P6 | 65+ Tuổi vàng và hộ đồng hành | `retire_companion` | `demo-p6@welora.demo` |

- Nếu account trống trên staging: `POST /auth/demo/seed` rồi login lại.
- **Primary path:** seed-login (đối tác survey sẵn demo).  
- **Alternate:** register mới tại `/app/register` (Email hoặc SĐT) — ghi rõ trong Notes nếu dùng.

### Đường dẫn OS GP (đã verify trên `welora-staging`)

| Màn | Path |
|-----|------|
| Login | `/app/login` (1 ô: Email hoặc SĐT) |
| Home | `/app` |
| Onboarding / DNA | `/app/onboarding` · `/app/dna` |
| Accounts | `/app/accounts` |
| Transactions | `/app/transactions` |
| Budget | `/app/budget` |
| Goals | `/app/goals` (+ Học thêm / Pedia inline — scrubbed keys) |
| Cổng An Toàn | `/app/safety` |
| Welorademy | `/app/academy` (lesson titles WA-02-xx; soft order theo PRD) |
| Content | `/app/content` `[Inf]` nếu deep-link lesson cụ thể |

### Map soft Academy (PRD `academy_emphasis` → tiêu đề GP)

Không bắt buộc URL node `02.x` (CP). Trên GP dùng **tiêu đề bài** trong `/app/academy`; thứ tự soft:

| Soft id (PRD) | Tiêu đề GP (WA) |
|---------------|-----------------|
| 02.1 | Xây dựng quỹ khẩn cấp (`WA-02-01`) |
| 02.2 | Nguyên tắc sử dụng quỹ (`WA-02-02`) |
| 02.3 | Nơi giữ quỹ (`WA-02-03`) |
| 02.4 | Chọn phương pháp trả nợ (`WA-02-04`) |
| 02.5 | Nhận diện nợ tốt/xấu (`WA-02-05`) |
| 02.6 | Lập kế hoạch trả nợ (`WA-02-06`) |
| 02.7 | Ưu tiên trả nợ vs đầu tư (`WA-02-07`) |
| 02.8 | `[Inf]` — nếu chưa có bài GP, mở bài gần nhất / ghi Notes |

### Mục lục

1. [P1 · Độc thân đô thị 18+](#p1--độc-thân-đô-thị-18)
2. [P2 · 25–34 Gia đình trẻ khởi đầu](#p2--2534-gia-đình-trẻ-khởi-đầu)
3. [P3 · 35–59 Nâng đỡ hai đầu](#p3--3559-nâng-đỡ-hai-đầu-không-con-nhỏ)
4. [P4 · 35–59 Ba đời trên một take-home](#p4--3559-ba-đời-trên-một-take-home)
5. [P5 · 55–64 Cửa sổ 10 năm trước hưu](#p5--5564-cửa-sổ-10-năm-trước-hưu)
6. [P6 · 65+ Tuổi vàng và hộ đồng hành](#p6--65-tuổi-vàng-và-hộ-đồng-hành)
7. [Phụ lục A — PASS/FAIL tổng](#phụ-lục-a--bảng-tổng-passfail)
8. [Phụ lục B — `[Inf]` cần Founder](#phụ-lục-b--inf-cần-founder-chốt)

---

## P1 · Độc thân đô thị 18+

**household:** `solo` · **alias:** `demo-p1@welora.demo` · **~18 phút**

### 1. Intro / partner observe

- **HVTC:** thấy người 18–24 bắt đầu từ quỹ / chi tiêu dễ hiểu trên staging GP.  
- **Viettel Money:** thấy flow mobile dựng quỹ đầu + optional nợ thẻ — không nhảy đầu tư.

### 2. Prep

- Thiết bị: iPhone Safari ưu tiên (hoặc Android Chrome).  
- **Login primary:** `/app/login` → `demo-p1@welora.demo` / `WeloraDemo1!`  
  - Nếu trống: `POST /auth/demo/seed` rồi login lại.  
- **Alternate:** `/app/register` email `ten+p1@...` — không dùng mật khẩu seed.  
- Giả định `[Inf]`: thu nhập ~15tr/tháng · nợ thẻ tuỳ chọn ~5tr · EF mục tiêu ~36tr.

### 3. Steps (≥4 nhập liệu)

1. **Login / Home** — mở https://welora-staging.onrender.com/app/login → vào `/app`. Ghi PASS nếu shell load, không lỗi token.  
2. **DNA ≤7 (không số tiền)** — `/app/onboarding` hoặc `/app/dna`. Skeleton: quỹ 3 tháng · hay hết lương · chưa lưới an toàn · lo mất việc · cắt chi · chưa ngân sách · hối tiếc mua sắm. **Không** nhập số dư / lương.  
3. **Accounts** — `/app/accounts`: tạo Chi tiêu hàng ngày + Quỹ dự phòng (+ thẻ nợ tuỳ chọn `[Inf]` −5tr).  
4. **Transactions** — `/app/transactions`: ≥5 giao dịch tay (lương `[Inf]` 15tr, ăn uống, di chuyển, giải trí, chuyển vào quỹ).  
5. **Goals** — `/app/goals`: tạo `emergency_fund` target `[Inf]` 36tr; optional `debt_payoff` nếu có thẻ. Chỉ 2 loại goal.  
6. **Cổng / DNA / Học thêm** — mở `/app/safety`, `/app/dna`, khối Học thêm trên `/app/goals`. **Assert:** UI copy **không** hiện `CORE-` / `SAFE-` / `DEBT-`.  
7. **Academy soft** — `/app/academy`: thứ tự soft *Nguyên tắc sử dụng quỹ → Xây dựng quỹ → Nơi giữ quỹ → Lập kế hoạch trả nợ → Ưu tiên trả nợ vs đầu tư*; hoàn thành ít nhất *Nguyên tắc sử dụng quỹ*. Path deep-link `[Inf]`.

### 4. Checklist PASS/FAIL

- [ ] Login seed (hoặc register alternate) OK  
- [ ] DNA ≤7 lưu; không hỏi / không nhập số tiền; không gắn KUAT từ DNA  
- [ ] Tạo ≥2 account đúng type  
- [ ] Nhập ≥5 giao dịch; số dư hợp lý `[Inf]`  
- [ ] Goal `emergency_fund` ~36tr `[Inf]`; không goal loại khác  
- [ ] `/app/safety` mở được (không sửa cổng)  
- [ ] Học thêm / goals / academy: **không** lộ CORE-/SAFE-/DEBT-  
- [ ] Soft academy hoàn thành ≥1 bài đầu lộ trình  
- [ ] Firewall: không gợi ý sản phẩm đầu tư / vay cụ thể trên UI user-facing  

### 5. Partner observe questions

1. DNA có cảm giác “hiểu mình” không, hay như form bank?  
2. Nhập tay 5 giao dịch trên mobile — nản ở bước nào?  
3. Mục tiêu EF `[Inf]` 36tr — hứng khởi hay nản?  

---

## P2 · 25–34 Gia đình trẻ khởi đầu

**household:** `young_family` · **alias:** `partner@welora.demo` · **~22 phút**

### 1. Intro / partner observe

- **HVTC:** hộ có con nhỏ — ngân sách hộ → bảo vệ; soft Academy bắt đầu *Xây dựng quỹ*.  
- **Viettel Money:** 2 thu nhập ghi chi tiêu hộ không rối; EF rồi mới `debt_payoff`.

### 2. Prep

- Thiết bị: mobile-first.  
- **Login primary:** `partner@welora.demo` / `WeloraDemo1!` (seed P2 Done).  
- Alternate: register `ten+p2@...`.  
- Giả định `[Inf]`: thu hộ ~28tr · chi thiết yếu ~20tr · nợ thẻ ~12tr · EF ~120tr.

### 3. Steps (≥4 nhập liệu)

1. **Login** `/app/login` → `/app`.  
2. **DNA ≤7:** an toàn 12 tháng cho con · chi tăng khi có con · lưới an toàn · lo ốm/mất TN · ưu tiên BH+quỹ · khó theo dõi 2 người chi · nợ tiêu dùng. Không số tiền.  
3. **Accounts** `/app/accounts`: Chi tiêu hộ · Quỹ DP · Nợ thẻ `[Inf]`.  
4. **Transactions** `/app/transactions`: ≥7 giao dịch (2 lương, nhà, nhà trẻ, BH, sữa/bỉm, trả thẻ) `[Inf]`.  
5. **Budget** `/app/budget`: tag Học phí con, Bảo hiểm, Nhà ở.  
6. **Goals** `/app/goals`: `emergency_fund` `[Inf]` 120tr **rồi** `debt_payoff` `[Inf]` 12tr. Thử tìm goal giáo dục → **không có** (MVP đúng).  
7. **Cổng / Học thêm:** `/app/safety` + Học thêm trên goals — assert không CORE-/SAFE-/DEBT-.  
8. **Academy soft:** *Xây dựng quỹ → Nguyên tắc sử dụng quỹ → Nơi giữ quỹ → Chọn phương pháp trả nợ* (+ soft 02.8 `[Inf]`).

### 4. Checklist PASS/FAIL

- [ ] Login / DNA OK (không số tiền)  
- [ ] 3 account; nợ hiển thị đúng nghĩa nợ  
- [ ] ≥7 giao dịch + budget tags hộ  
- [ ] EF rồi `debt_payoff` (đúng thứ tự)  
- [ ] Không có goal giáo dục / loại goal thứ 3  
- [ ] Không lộ CORE-/SAFE-/DEBT- trên UI  
- [ ] Soft academy mở ≥1 bài đầu  
- [ ] Firewall + Cổng mở được (không đụng cấu hình)  

### 5. Partner observe questions

1. Hộ muốn chung 1 TK hay 2 TK trên app?  
2. Thiếu goal giáo dục — chấp nhận hay bối rối?  
3. Bài *Xây dựng quỹ* giúp thấy tiền hộ đi đâu không?

---

## P3 · 35–59 Nâng đỡ hai đầu (không con nhỏ)

**household:** `couple_no_kids` · **alias:** `demo-p3@welora.demo` · **~20 phút**

### 1. Intro / partner observe

- **HVTC:** hỗ trợ cha mẹ hai bên — Academy cân bằng, không phán xét.  
- **Viettel Money:** tag `ho-tro-gia-dinh` theo dõi riêng dòng hỗ trợ GM.

### 2. Prep

- **Login primary:** `demo-p3@welora.demo` / `WeloraDemo1!`  
- Alternate: `ten+p3@...`  
- Giả định `[Inf]`: thu ~38tr · hỗ trợ GM ~6tr · EF ~108tr · **không nợ** (ưu tiên).

### 3. Steps (≥4 nhập liệu)

1. **Login** → `/app`.  
2. **DNA ≤7:** cân bằng hỗ trợ GM vs bản thân · xung đột ưu tiên · quỹ riêng vợ chồng · lo cha mẹ bệnh · cắt mong muốn · áp lực gia đình · từng cho mượn quá nhiều. Không số.  
3. **Accounts** `/app/accounts`: Chi tiêu · Tiết kiệm hỗ trợ GM · Quỹ DP.  
4. **Transactions** `/app/transactions`: ≥6 giao dịch gồm ≥2 lần gửi GM gắn tag `ho-tro-gia-dinh` `[Inf]`.  
5. **Budget** `/app/budget`: tag `ho-tro-gia-dinh`, Bảo hiểm, Nhà ở — lọc tag kiểm tra tổng.  
6. **Goals** `/app/goals`: chỉ `emergency_fund` `[Inf]` 108tr — **không** tạo `debt_payoff`.  
7. **Cổng / DNA / Học thêm:** assert không CORE-/SAFE-/DEBT-.  
8. **Academy soft:** *Xây dựng quỹ → Lập kế hoạch trả nợ → Nguyên tắc sử dụng quỹ → Chọn phương pháp trả nợ → Nhận diện nợ tốt/xấu*.

### 4. Checklist PASS/FAIL

- [ ] DNA không số tiền  
- [ ] 3 account phân biệt bằng tên  
- [ ] Tag `ho-tro-gia-dinh` tạo + lọc đúng tổng `[Inf]`  
- [ ] EF ~108tr; không debt_payoff  
- [ ] Giọng UI không phán xét “nên/không nên cho bố mẹ tiền”  
- [ ] Không lộ CORE-/SAFE-/DEBT-  
- [ ] Soft academy ≥1 bài hoàn thành  
- [ ] Cổng `/app/safety` mở được  

### 5. Partner observe questions

1. Tách số hỗ trợ GM — nhẹ nhõm hay áp lực?  
2. Bài về kế hoạch / nợ có sát tình huống “hai đầu”?  
3. Muốn share với vợ/chồng trên cùng tài khoản?

---

## P4 · 35–59 Ba đời trên một take-home

**household:** `sandwich_3gen` · **alias:** `demo-p4@welora.demo` · **~22 phút**

### 1. Intro / partner observe

- **HVTC:** một lương nuôi 3 thế hệ + nợ — Academy **phòng thủ**, bắt đầu bài trả nợ, **không** đẩy đầu tư.  
- **Viettel Money:** thứ tự **`debt_payoff` trước**, EF mỏng sau — đúng stress take-home.

### 2. Prep

- **Login primary:** `demo-p4@welora.demo` / `WeloraDemo1!` (seed P4 Done).  
- Alternate: `ten+p4@...`  
- Giả định `[Inf]`: take-home ~22tr · nợ ~40tr · EF mỏng ~60tr.

### 3. Steps (≥4 nhập liệu)

1. **Login** → `/app`.  
2. **DNA ≤7:** hết nợ lãi cao · một lương ba đời · không cháy túi · lo mất việc · ưu tiên nhu cầu · nhiều miệng · từng vay tiêu dùng. Không số.  
3. **Accounts** `/app/accounts`: Chi tiêu duy nhất · Quỹ DP mỏng · Khoản vay/nợ.  
4. **Transactions** `/app/transactions`: ≥6 giao dịch (lương, nhà, học phí, hỗ trợ GM, trả nợ, thiết yếu) `[Inf]`.  
5. **Budget** `/app/budget`: Học phí + hỗ trợ GM + Trả nợ; **Giải trí = 0** chấp nhận.  
6. **Goals — thứ tự bắt buộc:** tạo **`debt_payoff` `[Inf]` 40tr trước**, rồi `emergency_fund` mỏng `[Inf]` 60tr.  
7. **Cổng / Học thêm:** assert không CORE-/SAFE-/DEBT-; không gợi ý đảo nợ / vay mới.  
8. **Academy soft:** *Chọn phương pháp trả nợ → Xây dựng quỹ → Nguyên tắc sử dụng quỹ → Nơi giữ quỹ* (+ soft 02.8 `[Inf]`).

### 4. Checklist PASS/FAIL

- [ ] Bài trả nợ mở đầu soft lộ trình  
- [ ] Nợ hiển thị là nợ (không như tài sản)  
- [ ] Budget Giải trí = 0 chấp nhận  
- [ ] `debt_payoff` **trước** `emergency_fund`  
- [ ] ≥6 giao dịch nhập tay  
- [ ] Không gợi ý đầu tư / sản phẩm vay cụ thể  
- [ ] Không lộ CORE-/SAFE-/DEBT-  
- [ ] Cổng mở được (không đụng cấu hình)  

### 5. Partner observe questions

1. Nợ cạnh goal trả nợ — động lực hay nặng nề?  
2. Giải trí = 0 có thực tế với hộ 3 đời?  
3. Bài phương pháp trả nợ có ví dụ gần “một lương ba đời”?

---

## P5 · 55–64 Cửa sổ 10 năm trước hưu

**household:** `pre_retire` · **alias:** `demo-p5@welora.demo` · **~22 phút**

### 1. Intro / partner observe

- **HVTC:** hưu trí = **thông tin**, không tư vấn đầu tư M03 trên MVP.  
- **Viettel Money:** người 55–64 tự tin nhập quỹ lớn trên mobile; EF dày rồi mới debt.

### 2. Prep

- **Login primary:** `demo-p5@welora.demo` / `WeloraDemo1!`  
- Alternate: `ten+p5@...` · cỡ chữ lớn nếu có.  
- Giả định `[Inf]`: thu ~30tr · vay sửa nhà / home loan ~50tr · EF ~135tr.

### 3. Steps (≥4 nhập liệu)

1. **Login** → `/app`.  
2. **DNA ≤7:** đệm trước hưu · sợ trễ · kế hoạch 10 năm · lo lạm phát/y tế · thận trọng · không biết bắt đầu · từng đầu tư cảm xúc. Không số.  
3. **Accounts** `/app/accounts`: Chi tiêu · Tiết kiệm (`tiet_kiem`) · optional nợ — **không** account đầu tư / `dau_tu`.  
4. **Transactions** `/app/transactions`: ≥5 giao dịch `[Inf]`.  
5. **Goals:** `emergency_fund` `[Inf]` 135tr **trước**, rồi `debt_payoff` `[Inf]` 50tr.  
6. **Cổng / Học thêm / Academy:** assert không CORE-/SAFE-/DEBT-; Academy không khuyên mua kênh đầu tư. Soft: *Lập kế hoạch trả nợ → Nhận diện nợ → Nguyên tắc sử dụng quỹ → Ưu tiên trả nợ vs đầu tư*.  
7. Kiểm tra **không** có Investments UI (danh mục / giá CK).

### 4. Checklist PASS/FAIL

- [ ] Không bắt tạo account đầu tư  
- [ ] EF trước `debt_payoff`  
- [ ] Không Investments UI  
- [ ] DNA không số tiền  
- [ ] ≥5 giao dịch + ≥2 account  
- [ ] Không lộ CORE-/SAFE-/DEBT-  
- [ ] Chữ/nút đủ rõ trên mobile  
- [ ] Academy không khuyên sản phẩm đầu tư cụ thể  

### 5. Partner observe questions

1. Chữ / nút đủ lớn cho 55–64?  
2. Mong app “nên gửi/đầu tư gì”? (ghi nếu có — MVP không trả lời sản phẩm)  
3. Soft bài kế hoạch giúp hình dung 10 năm?

---

## P6 · 65+ Tuổi vàng và hộ đồng hành

**household:** `retire_companion` · **alias:** `demo-p6@welora.demo` · **~25 phút**

### 1. Intro / partner observe

- **HVTC:** cấu trúc **tối giản đúng 2 account**; giọng Academy chậm.  
- **Viettel Money:** người 65+ tự gõ; người đồng hành chỉ nhắc (ghi số lần chạm máy).

### 2. Prep

- **Login primary:** `demo-p6@welora.demo` / `WeloraDemo1!`  
- Alternate: người 65+ tự register `ten+p6@...` · cỡ chữ lớn.  
- Giả định `[Inf]`: thu ~12tr · **không nợ** · EF y tế ~54tr · **đúng 2 accounts**.

### 3. Steps (≥4 nhập liệu)

1. **Login / Register** — ưu tiên người 65+ tự thao tác ≥80% bước.  
2. **DNA ≤7:** yên tâm chi tháng · sợ tốn y tế · con không phải gánh · lo bệnh dài ngày · thích tiền mặt · phụ thuộc con một phần · từng quyết định vội. Không số.  
3. **Accounts** `/app/accounts`: **đúng 2** — Chi tiêu + Tiết kiệm thanh khoản. App không bắt thêm.  
4. **Transactions** `/app/transactions`: ≥4 giao dịch (lương hưu/tiền gửi, ăn uống, thuốc/y tế, chuyển quỹ) `[Inf]`.  
5. **Goals:** chỉ `emergency_fund` `[Inf]` 54tr — **hiếm / không** `debt_payoff`.  
6. **Cổng / Học thêm:** assert không CORE-/SAFE-/DEBT-; không pop-up giống chuyển tiền; không gợi ý BH/tiền gửi cụ thể.  
7. **Academy soft:** *Nguyên tắc sử dụng quỹ → Nơi giữ quỹ → Nhận diện nợ → Xây dựng quỹ* (giọng chậm). Soft 02.8 `[Inf]`.

### 4. Checklist PASS/FAIL

- [ ] Người 65+ tự login/register (đồng hành ≤2 bước thay)  
- [ ] Đúng 2 account; app không bắt thêm  
- [ ] User tự bấm ≥80% bước  
- [ ] EF ~54tr; không cần debt_payoff  
- [ ] DNA không số tiền  
- [ ] Không lộ CORE-/SAFE-/DEBT-  
- [ ] Không gợi ý BH/tiền gửi cụ thể; không pop-up giống chuyển tiền  
- [ ] Soft academy ≥1 bài hoàn thành  

### 5. Partner observe questions

1. Bước khó nhất với người 65+?  
2. Yên tâm ghi tiết kiệm vào điện thoại?  
3. Bài *Nguyên tắc sử dụng quỹ* dễ hiểu không?

---

## Phụ lục A — Bảng tổng PASS/FAIL

| Persona | label_vi | Alias | Partner (HVTC/VM) | Surveyor | Ngày | PASS x/tổng | Dòng FAIL | Notes |
|---------|----------|-------|-------------------|----------|------|-------------|-----------|-------|
| P1 | Độc thân đô thị 18+ | demo-p1@welora.demo | | | | __ / 9 | | |
| P2 | 25–34 Gia đình trẻ khởi đầu | partner@welora.demo | | | | __ / 8 | | |
| P3 | 35–59 Nâng đỡ hai đầu | demo-p3@welora.demo | | | | __ / 8 | | |
| P4 | 35–59 Ba đời trên một take-home | demo-p4@welora.demo | | | | __ / 8 | | |
| P5 | 55–64 Cửa sổ 10 năm trước hưu | demo-p5@welora.demo | | | | __ / 8 | | |
| P6 | 65+ Tuổi vàng và hộ đồng hành | demo-p6@welora.demo | | | | __ / 8 | | |

**Quy tắc:** PASS khi không FAIL dòng bắt buộc (login, DNA không số tiền, account, giao dịch, goal đúng thứ tự/loại, không lộ CORE-/SAFE-/DEBT-, firewall). FAIL UX quan sát → PASS có Notes → backlog.

---

## Phụ lục B — `[Inf]` cần Founder chốt

1. Thu nhập mẫu (triệu/tháng): P1 15 · P2 28 · P3 38 · P4 22 · P5 30 · P6 12  
2. Chi thiết yếu: P1 ~12 · P2 20 · P3 ~18 · P4 ~20 · P5 ~15 · P6 ~9  
3. Target EF: P1 36 · P2 120 · P3 108 · P4 60 · P5 135 · P6 54  
4. Nợ mẫu: P1 5 (tuỳ) · P2 12 · P4 40 · P5 50 · P3/P6 không  
5. Số dư mở từng account / persona  
6. Mức budget từng danh mục  
7. Thành phần hộ P2 (1 con?) · P4 (2 con + 1 ông/bà?)  
8. 4 trụ đời sống P6 — tên gọi chính thức  
9. Danh mục “Y tế” có trong DEFAULT_CATEGORIES staging?  
10. Soft node `02.8` / deep-link Academy lesson URL trên GP (nếu khác `/app/academy`)  
11. CSV header · dấu thu/chi · chuyển account · wake Render cold start  

---

**DoD GP A (docs):** 6 script đủ template · ≥4 bước nhập liệu / persona · partner HVTC + Viettel Money trong intro/observe · `[Inf]` đánh dấu · path GP staging · không Hard Deny / mail Quen / Production cutover · PR-only không merge.
