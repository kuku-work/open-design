# -*- coding: utf-8 -*-
"""Part 3 拍攝計畫生成器 — 架構照 gen_part1.py／gen_part2.py 抄。

Reads a data yaml and emits the Part 3 deck HTML. Every geometric number is
computed from the data + the fixed skeleton in SKILL.md / DESIGN.md. Nothing
is hand-typed per page.

用法：
    python gen_part3.py                                # 沒給參數 → 跑空白範本，看版型長什麼樣
    python gen_part3.py <輸入.yaml> <輸出.html>          # 換資料檔／輸出檔
    python gen_part3.py <輸入.yaml> <輸出.html> --review  # 額外印出審閱鷹架
                                                           # （sheet-label ＋ deck-head 說明段）

2026-08-25 版面區塊化：全部版式改走「Header / Content / Meta / Footer」
四段垂直骨架（DESIGN.md §5-0）。空間先切區塊、每區有職責，原本無主的留白
改成有欄位的補充資訊帶（Meta）。

2026-09-01 資料驅動化：畫面文案全部搬進 yaml 的 part3.labels（不設
fallback，資料沒有就顯示空槽／空白，不編值）；審閱鷹架（sheet-label／
deck-head）改走 dev() 標記 ＋ --review 旗標，預設關閉、交付 HTML 乾淨。
DATA／OUT 改吃 sys.argv，沒給參數才落回本案路徑（照 gen_part1.py 的形狀）。

2026-09-02 併入 deck-photo-brief skill：頂層資料節（project／colors／
zones／standard_shots／themes／key_visual／schedule）缺了 → 該節相關頁面
不出，不是出一頁錯的；節內的個別欄位缺了 → 走 blank() 顯示空槽，不拿
別的欄位或檔名／目錄名湊（同 gen_part1.py 的「graceful ≠ silent」）。
DATA／OUT 沒給參數就落回 skill 自己的 input-template.yaml / blank-part3.html。
"""
import sys
import math
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
_argv = [a for a in sys.argv[1:] if a != "--review"]
REVIEW = "--review" in sys.argv[1:]
# 沒給參數就跑空白範本 —— 產出的是「版型長什麼樣」，每一格都是空槽。
DATA = Path(_argv[0]) if len(_argv) > 0 else SKILL / "input-template.yaml"
OUT = Path(_argv[1]) if len(_argv) > 1 else SKILL / "examples" / "blank-part3.html"


def dev(s):
    """Mark a review-only scaffolding string (sheet-label / deck-head).

    Identity function at runtime — it only exists so check_template.py can
    recognize "this text is developer metadata about the template, not
    something that ever reaches a delivered page" and skip it. Never wrap
    real deck content (page body) in this; only add_page()'s label/layout/
    detail arguments and the deck-head blurb qualify.
    """
    return s


# ── 共用骨架（DESIGN.md §4-1，固定值，不許漂移）────────────────────────
PAGE_W, PAGE_H = 960.0, 540.0
SAFE_L, SAFE_W = 43.2, 873.6          # 安全邊界 / 滿版線寬（右緣 916.8）
SAFE_R = SAFE_L + SAFE_W              # 916.8
TEXT_L = 50.4                          # 文字左緣
HEAD_BASE = 40.3                       # 頁首標題塊上緣
DIVIDER_Y = 493.2                      # 底部分隔線
PNO_X, PNO_Y = 933.1, 516.0            # 頁碼（10pt 基線）

# ── 頁面區塊骨架（DESIGN.md §5-0）─────────────────────────────────────
# 四個切點全部落在 3.6 pt 底格上：108 = 30×3.6／432 = 120×3.6／
# 493.2 = 137×3.6／540 = 150×3.6。實測依據見 04-generation-report.md〈版面區塊化〉。
HEADER_TOP = 0.0
HEADER_BOT = 108.0                     # 30 × 3.6
META_TOP = 432.0                       # 120 × 3.6
FOOTER_TOP = DIVIDER_Y                 # 493.2 = 137 × 3.6
CONTENT_TOP = HEADER_BOT
META_H = FOOTER_TOP - META_TOP         # 61.2 = 17 × 3.6
HEADER_PAD = 10.8                      # Header 區內的上下呼吸（--space-3）


def content_box(has_meta):
    """Content 區的 (top, height)。沒有 Meta 內容就把 Meta 的高度吃掉。"""
    bot = META_TOP if has_meta else FOOTER_TOP
    return CONTENT_TOP, bot - CONTENT_TOP      # 324.0 / 385.2


# ── 便當盒 grid 參數 ────────────────────────────────────────────────
GAP = 7.2                # 同頁單一常數：列內圖片間縫（--space-2）
ROW_GAP_H = 24.0         # H 版式兩列之間（要吃下 9pt 編號：+8 偏移 + 字高）
ROW_GAP_G = 18.0         # G 版式兩列之間（無編號，沿用 components.html 的 --space-5）
HERO_GAP = 10.8          # hero 與側欄之間（components.html --space-3）
IDX_BAND = 25.2          # 圖片底下留給 9pt 編號的帶狀空間（7 × 3.6；偏移 8 ＋ 字盒 11.25 ＋ 呼吸 6）

# ── G 氣氛參考的排法（SKILL.md〈G 的排法〉）─────────────────────────
# G 預設「單列大圖」；列高低於下限就折成兩小疊。下限訂在 H 的實測上限
# 201.5 之上 —— G 的列高不許掉進 H 的區間，那正是「圖太小」的病灶。
G_ROW_MIN = 210.0
# 產品去背窗：區塊化之後它是 Header 區的右側輔助元件，四個變體共用同一個錨點。
# 高度由 Header 區推導（108 − 2×10.8 = 86.4），寬度由鎖死的 151.3:111.4 比例推導。
CUT_AR = 151.3 / 111.4                 # 1.3582，比例鎖死不許變形
CUT_H = HEADER_BOT - 2 * HEADER_PAD    # 86.4
CUT_W = CUT_H * CUT_AR                 # 117.34
CUT_X = SAFE_R - CUT_W                 # 右對齊 916.8
CUT_Y = HEADER_PAD                     # 10.8
G4_BLEED_W = 360.0                     # 出血變體：貼右頁緣，垂直方向守 Content 區

RATIO = {"4:5": 0.8, "3:2": 1.5, "2:3": 2 / 3, "16:9": 16 / 9, "1:1": 1.0}
RCLASS = {"4:5": "r45", "3:2": "r32", "2:3": "r23", "16:9": "r169", "1:1": "r11"}

# ── 產品色（由輸入決定，不沿用範例值）────────────────────────────────
# ⚠️ 不設 fallback：頂層資料節缺了就是這案沒有這節 → 該節相關頁面不出
#    （見各 add_page 前的 if 判斷），不是拿別的欄位湊出一頁。
data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
project = data.get("project") or {}
colors = data.get("colors") or []
zones = data.get("zones") or []
std = data.get("standard_shots") or []
themes = data.get("themes") or []
kv = data.get("key_visual") or {}
schedule = data.get("schedule") or []
theme_by_color = {t["color"]: t for t in themes}   # color name -> its theme entry, if any

# ── 畫面文案層（part3.labels，換產品只換這裡，程式不留畫面用中文）──
# 不設 fallback：labels 用 .get(key, "") 空字串退化（版型骨架照出，字串空
# 白）；project 的資料欄位一律直接索引，缺了就是資料本身沒填，直接報錯，
# 不拿別的欄位湊（同 gen_part1.py 的「graceful ≠ silent」原則）。
p3 = data.get("part3") or {}
DECK_TITLE_SUFFIX = p3.get("deck_title_suffix") or ""
L = p3.get("labels") or {}
_SEC_RAW = L.get("sections") or {}
SECTION = {k: (v.get("title") or "", v.get("sub")) for k, v in _SEC_RAW.items()}

ZONE_SUFFIX = L.get("zone_suffix", "")
SCENE_PREFIX = L.get("scene_prefix", "")
COVER_SUBTITLE = L.get("cover_subtitle", "")
BANNER_PLACEHOLDER = L.get("banner_placeholder", "")
OVERVIEW_FIELDS = L.get("overview_fields") or []
INFOCARD_EYEBROW_PREFIX = L.get("infocard_eyebrow_prefix", "")
CARD_FIELDS = L.get("card_fields") or []
TIMELINE_HEADERS = L.get("timeline_headers") or []
TIMELINE_FOCUS_DEFAULT = L.get("timeline_focus_default", "")
TIMELINE_FOCUS_THEME = L.get("timeline_focus_theme", "")
SCHEDULE_LUNCH_MARKER = L.get("schedule_lunch_marker", "")
SCHEDULE_KV_MARKER = L.get("schedule_kv_marker", "")
ZONE_PHOTO_CAPTION = L.get("zone_photo_caption", "")
ZONE_SESSIONS_LABEL = L.get("zone_sessions_label", "")
SHOTLIST_SCENES_LABEL = L.get("shotlist_scenes_label", "")
SHOTLIST_COMPOSITION_LABEL = L.get("shotlist_composition_label", "")
SHOTLIST_APPLIES_SUFFIX = L.get("shotlist_applies_suffix", "")
SHOTLIST_COMPOSE_TMPL = L.get("shotlist_compose", "")
GENERIC_FEATURE_MARKER = L.get("generic_feature_marker", "")
KV_PRIMARY_LABEL = L.get("kv_primary_label", "")
KV_SECONDARY_LABEL = L.get("kv_secondary_label", "")
MOOD_REF_CAPTION = L.get("mood_ref_caption", "")
MOOD_PAGE_TITLE = L.get("mood_page_title", "")
MOOD_BLEED_CAPTION = L.get("mood_bleed_caption", "")
CUTOUT_CAPTION = L.get("cutout_caption", "")
MOOD_META = L.get("mood_meta") or {}
THEME_EYEBROW_SUFFIX = L.get("theme_eyebrow_suffix", "")
THEME_SHOTLIST_LABEL = L.get("theme_shotlist_label", "")
THEME_META = L.get("theme_meta") or {}
H_COUNT_TMPL = L.get("h_count_template", "")
BLANK_SLOT = L.get("blank_slot", "")


def f(v):
    """pt 值轉字串，最多兩位小數。"""
    return f"{round(v, 2):g}"


def blank():
    """個別欄位缺值的畫面空槽 —— 沿用 Meta 帶已有的 BLANK_SLOT 文案，不拿別的
    欄位或檔名／目錄名湊（同 gen_part1.py／gen_part2.py 的 blank()：欄位對不上
    要看得見，不能悄悄補別的字）。
    """
    return f'<span class="bk">{BLANK_SLOT}</span>'


def val(x):
    """None（真的沒填）才顯示空槽；空字串是資料本身給的值，原樣印出，不是缺。

    踩過的坑：schedule 午休列的 scene/focus 本來就是空字串 ''（沒有場景是
    事實，不是漏填），若用 `x or blank()` 會把它誤判成「待補」，把完整資料
    改成看起來缺資料的假象——那是把 graceful 做成 silent 的反面案例。
    """
    return blank() if x is None else x


def slug(name_en):
    return (name_en or "").upper().replace(" ", "")


def head_label(c):
    return f'{val(c.get("name_en"))} {val(c.get("name_zh"))} ｜ {val(c.get("scene"))}'


def session_line(c, model=True):
    """Header 區的情境資訊行。三格都來自 colors[]，不重打。"""
    tail = f'MODEL {val(c.get("model"))}' if model else val(c.get("scene"))
    return f'{val(c.get("time_slot"))} ｜ {val(c.get("studio_zone"))} {ZONE_SUFFIX} ｜ {tail}'


# ── 頁面切片：ceil(n/10)，平均分，餘數給前面的頁 ──────────────────────
def split_pages(n, per=10):
    pages = math.ceil(n / per)
    base, rem = divmod(n, pages)
    return [base + (1 if i < rem else 0) for i in range(pages)]


# ── 版型選擇（SKILL.md 機械規則，不憑感覺）────────────────────────────
def pick_layout(items):
    """items: list of dicts with 'ratio' and optional 'hero'."""
    n = len(items)
    hero_i = next((i for i, s in enumerate(items) if s.get("hero")), None)
    if hero_i is not None:
        # hero 落在哪一側：資料沒有 side 欄位，用「是否為該頁第一格」判定
        side = "left" if hero_i == 0 else "right"
        return f"hero-{side}-two-rows", hero_i
    ratios = {s["ratio"] for s in items}
    if len(ratios) == 1 and n == 8:
        return "uniform-4x2", None
    if len(ratios) == 1 and n == 4:
        return "uniform-2x2", None
    return "mixed-2rows", None


def two_row_split(items):
    """張數為奇數時上列多一張。"""
    up = math.ceil(len(items) / 2)
    return items[:up], items[up:]


def row_h_by_width(items, avail_w=SAFE_W):
    s = sum(RATIO[i["ratio"]] for i in items)
    return (avail_w - GAP * (len(items) - 1)) / s


def solve_two_rows(upper, lower, row_gap, vbudget):
    """兩列等高：列高 = min(兩列各自的寬度上限, 垂直預算)。"""
    h = min(row_h_by_width(upper), row_h_by_width(lower) if lower else 1e9)
    h = min(h, (vbudget - row_gap) / 2)
    return h


# ── G 排法求解（SKILL.md〈G 的排法〉四變體）─────────────────────────
def g_col_terms(col):
    """一個直欄在列高公式裡的線性項：欄寬 = a * 列高 + c。

    單格：寬 = 比例 × 列高。
    上下疊的直欄：寬 = (列高 − 縫) × k，k = 1 ÷ Σ(1/比例)。
    """
    if len(col) == 1:
        return RATIO[col[0]["ratio"]], 0.0
    k = 1.0 / sum(1.0 / RATIO[r["ratio"]] for r in col)
    return k, -GAP * (len(col) - 1) * k


def g_row_height(cols, avail_w):
    """列高 = (可用寬 − 縫總寬 − Σc) ÷ Σa。"""
    terms = [g_col_terms(c) for c in cols]
    a = sum(t[0] for t in terms)
    c = sum(t[1] for t in terms)
    return (avail_w - GAP * (len(cols) - 1) - c) / a


def g_single_row(refs, vbudget):
    """G-1 單列；列高不足下限就折最寬的兩張成一個上下疊的直欄（G-2）。"""
    cols = [[r] for r in refs]
    h = g_row_height(cols, SAFE_W)
    if h >= G_ROW_MIN or len(refs) < 3:
        return dev("G-1 單列"), cols, min(h, vbudget)
    # 最寬的兩張；同寬時取排序在後的（[SP] p10 折的就是末兩張 16:9）
    order = sorted(range(len(refs)), key=lambda i: (-RATIO[refs[i]["ratio"]], -i))
    a, b = sorted(order[:2])
    # a 之前的格子一個都沒被抽走，所以疊欄就插在 rest 的第 a 個位置
    rest = [r for i, r in enumerate(refs) if i not in (a, b)]
    cols = ([[r] for r in rest[:a]] + [[refs[a], refs[b]]]
            + [[r] for r in rest[a:]])
    return dev("G-2 兩小疊"), cols, min(g_row_height(cols, SAFE_W), vbudget)


def g_span_solve(span_ratio, upper, lower, hb_max, row_gap):
    """跨列圖在右側跨滿兩列；兩列寬度由跨列圖寬度決定 → 迭代收斂。"""
    hb = hb_max
    uh = lh = 0.0
    for _ in range(200):
        left_w = SAFE_W - hb * span_ratio - HERO_GAP
        uh_nat = g_row_height([[r] for r in upper], left_w) if upper else 0.0
        lh_nat = g_row_height([[r] for r in lower], left_w) if lower else 0.0
        nat = uh_nat + row_gap + lh_nat
        if nat <= hb_max:
            uh, lh, hb_new = uh_nat, lh_nat, nat
        else:
            scale = (hb_max - row_gap) / (uh_nat + lh_nat)
            uh, lh, hb_new = uh_nat * scale, lh_nat * scale, hb_max
        if abs(hb_new - hb) < 0.001:
            return hb_new, uh, lh
        hb = hb_new
    return hb, uh, lh


def solve_hero(hero_ratio, upper, lower, hb_max, row_gap=ROW_GAP_H):
    """hero 跨兩列；hero 寬度由 hb 決定，側欄寬度由 hero 寬度決定 → 迭代收斂。"""
    hb = hb_max
    uh = lh = 0.0
    for _ in range(200):
        hero_w = hb * hero_ratio
        right_w = SAFE_W - hero_w - HERO_GAP
        uh_nat = row_h_by_width(upper, right_w)
        lh_nat = row_h_by_width(lower, right_w)
        nat = uh_nat + row_gap + lh_nat
        if nat <= hb_max:
            uh, lh, hb_new = uh_nat, lh_nat, nat
        else:
            scale = (hb_max - row_gap) / (uh_nat + lh_nat)
            uh, lh, hb_new = uh_nat * scale, lh_nat * scale, hb_max
        if abs(hb_new - hb) < 0.001:
            hb = hb_new
            break
        hb = hb_new
    return hb, uh, lh


# ── HTML 片段 ──────────────────────────────────────────────────────
def ph(ratio, text, extra_cls=""):
    return (f'<div class="ph {RCLASS[ratio]} {extra_cls}">'
            f'<span>{text}</span></div>')


def cell(ratio, text, index=None):
    idx = f'<span class="idx">{index}</span>' if index else ""
    return f'<div class="cell">{ph(ratio, text)}{idx}</div>'


def prow(items, height, render):
    inner = "".join(render(s) for s in items)
    return f'<div class="prow" style="height:{f(height)}pt">{inner}</div>'


def shot_text(c, s):
    t = f'{slug(c.get("name_en"))}-{s["no"]:02d} · {s["ratio"]}'
    if s.get("desc"):
        t += f' · {s["desc"]}'
    return t


# ── Header 區 ──────────────────────────────────────────────────────
def header_block(eyebrow_text=None, title=None, sub=None,
                 right_top=None, right_sub=None):
    """Header 區（0–108）的標題群 ＋ 右側輔助元件。

    高度固定不塌：不論裡面填幾行，下一區一律從 108 起算。
    """
    h = ""
    if eyebrow_text:
        h += f'<div class="hd-eyebrow">{eyebrow_text}</div>'
    if title:
        h += f'<div class="hd-title">{title}</div>'
    if sub:
        h += f'<div class="hd-sub">{sub}</div>'
    if right_top:
        h += f'<div class="hd-right">{right_top}</div>'
    if right_sub:
        h += f'<div class="hd-right2">{right_sub}</div>'
    return f'<div class="band-head">{h}</div>'


# ── Meta 區 ────────────────────────────────────────────────────────
def meta_block(cols, gap=14.4, plain=False):
    """Meta 區（432–493.2）：N 欄並排的補充資訊帶。

    cols: [(label, value)]，value 給 None 代表「標好的空槽」——資料沒有就
    留空槽並標示待補，不編值（SKILL.md〈輸出〉不許編造）。
    plain=True 時不畫標籤，只排一行值（封面品牌行用）。
    """
    inner = ""
    for lab, val in cols:
        if plain:
            inner += f'<div class="mcol"><div class="mval plain">{val}</div></div>'
            continue
        if val is None:
            body = f'<div class="mslot">{BLANK_SLOT}</div>'
        else:
            body = f'<div class="mval">{val}</div>'
        inner += f'<div class="mcol"><div class="mlab">{lab}</div>{body}</div>'
    return (f'<div class="band-meta" style="gap:{f(gap)}pt">{inner}</div>')


PAGES = []          # (layout_letter, title, html)


def add_page(letter, label, body, bg="", pno_dark=False, layout="", detail="",
             has_meta=False):
    PAGES.append(dict(letter=letter, label=label, body=body, bg=bg,
                      pno_dark=pno_dark, layout=layout, detail=detail,
                      has_meta=has_meta))


# ════════════════════════════════════════════════════════════════════
# 3.1 封面（A）
# ════════════════════════════════════════════════════════════════════
DOT_D, DOT_PITCH = 22.1, 28.8
dots = "".join(
    f'<span class="dot" style="left:{f(TEXT_L + i * DOT_PITCH)}pt;background:{c.get("hex") or "transparent"}"></span>'
    for i, c in enumerate(colors))

# Header：色點列在區內垂直置中；Content：產品名 → 副標 → 橘線資訊組；
# Meta：品牌行；Footer：分隔線 ＋ 頁碼（與其餘 24 頁同一條 y）。
# project 整節缺了就沒有封面可畫（連產品名都沒有）—— 這頁不出，不是出一頁全空槽。
if project:
    A_DOT_TOP = (HEADER_BOT - DOT_D) / 2                 # 42.95
    _a_top, _a_h = content_box(True)
    A_NAME_TOP = _a_top + 21.6                            # 129.6
    A_SUB_TOP = A_NAME_TOP + 66 + 14.4                    # 210.0
    A_BAR_H = 50.4
    A_BAR_TOP = _a_top + _a_h - A_BAR_H                   # 381.6，貼齊 Content 區下緣
    cover = f"""
<div class="cover-dots" style="top:{f(A_DOT_TOP)}pt">{dots}</div>
<div class="cover-name" style="top:{f(A_NAME_TOP)}pt">{val(project.get('product_name'))}</div>
<div class="cover-sub" style="top:{f(A_SUB_TOP)}pt">{COVER_SUBTITLE}</div>
<div class="cover-bar" style="top:{f(A_BAR_TOP)}pt;height:{f(A_BAR_H)}pt"></div>
<div class="cover-meta" style="top:{f(A_BAR_TOP)}pt">
  <div class="cm1">{val(project.get('shoot_date'))}　{val(project.get('shoot_time'))}</div>
  <div class="cm2">{val(project.get('venue'))}</div>
</div>
{meta_block([(None, f"{val(project.get('brand'))}　｜　{val(project.get('product_line'))}")], plain=True)}
"""
    add_page("A", dev("封面 Cover"), cover, bg="dark", pno_dark=True, has_meta=True,
             layout=dev("A 封面"),
             detail=dev(f'Header 色點 {len(colors)} 顆 ｜ Content 產品名 66pt ｜ Meta 品牌行'))

# ════════════════════════════════════════════════════════════════════
# 3.2 總覽資訊卡（B）
# ════════════════════════════════════════════════════════════════════
# Header：滿版產品橫幅（960 × 108，Header 區的滿版圖）
# Content：左側 4 組欄位列撐滿整區 ＋ 右側 284.4 見方深色卡垂直置中
# Meta：無（Content 區向下延伸吃掉 Meta 的高度）
# project 整節缺了就沒有欄位可填 —— 這頁不出。
if project:
    B_TOP, B_H = content_box(False)                       # 108 / 385.2
    CARD_SIDE = 284.4
    B_EYE_TOP = B_TOP + HEADER_PAD                        # 118.8
    B_ROWS_TOP = B_EYE_TOP + 21.6                         # 140.4
    B_ROWS_BOT = B_TOP + B_H - 21.6                       # 471.6，與 Footer 分隔線留 21.6
    info_rows = [(fld["label"], val(project.get(fld["key"]))) for fld in OVERVIEW_FIELDS]
    B_PITCH = (B_ROWS_BOT - B_ROWS_TOP) / len(info_rows)  # 86.4
    rows_html = ""
    for i, (k, v) in enumerate(info_rows):
        top = B_ROWS_TOP + i * B_PITCH
        rows_html += (
            f'<div class="inf-row" style="top:{f(top)}pt;height:{f(B_PITCH)}pt">'
            f'<span class="inf-k">{k}</span><span class="inf-v">{v}</span>'
            f'<span class="inf-line"></span></div>')

    card_fields = [(fld["label"], val(project.get(fld["key"]))) for fld in CARD_FIELDS]
    fields_html = "".join(
        f'<div class="cf-row"><span class="cf-k">{k}</span><span class="cf-v">{v}</span></div>'
        for k, v in card_fields)
    B_CARD_TOP = B_TOP + (B_H - CARD_SIDE) / 2            # 158.4

    overview = f"""
<div class="banner" style="height:{f(HEADER_BOT)}pt">{ph('16:9', f"{BANNER_PLACEHOLDER} · 960 × {f(HEADER_BOT)} pt", "banner-ph")}</div>
<div class="b-eyebrow" style="top:{f(B_EYE_TOP)}pt">{SECTION['B'][0]}</div>
{rows_html}
<div class="infocard" style="top:{f(B_CARD_TOP)}pt">
  <span class="ic-eyebrow">{INFOCARD_EYEBROW_PREFIX} ｜ {val(project.get('product_line'))}</span>
  <span class="ic-name">{val(project.get('product_name'))}</span>
  <span class="ic-sub">{val(project.get('brand'))}</span>
  <div class="ic-fields">{fields_html}</div>
</div>
"""
    add_page("B", SECTION['B'][0], overview, layout=dev("B 總覽資訊卡"),
             detail=dev(f'Header 滿版橫幅 960×{f(HEADER_BOT)} ｜ Content 欄位列 4 組（列距 {f(B_PITCH)}）＋ 資訊卡 284.4 見方 ｜ Meta 無'))

# ════════════════════════════════════════════════════════════════════
# 3.3 時間軸表格（C）
# ════════════════════════════════════════════════════════════════════
by_en = {c.get("name_en"): c for c in colors}


def match_color(session):
    for c in colors:
        name_en = c.get("name_en")
        if name_en and session.startswith(name_en):
            return c
    return None


trs = ""
for i, r in enumerate(schedule):
    session_key = r.get("color_session")
    c = match_color(session_key or "")
    if session_key == SCHEDULE_LUNCH_MARKER:
        zeb = "z3"
    else:
        zeb = "z1" if i % 2 == 0 else "z2"
    if c:
        # color.scene / 項數 一律由正本推導，不抄表格上的手寫值
        session = f'{val(c.get("name_en"))} {val(c.get("name_zh"))}'
        scene = val(c.get("scene"))
        n_shots = len(c.get("shots") or [])
        focus = TIMELINE_FOCUS_DEFAULT.replace("{n}", str(n_shots))
        if theme_by_color.get(c.get("name_en")):
            focus = TIMELINE_FOCUS_THEME.replace("{n}", str(n_shots))
        dot = f'<span class="rdot" style="background:{c.get("hex") or "transparent"}"></span>'
        zone = val(c.get("studio_zone"))
        time = val(c.get("time_slot"))
    else:
        session = val(session_key)
        scene, focus = val(r.get("scene")), val(r.get("focus"))
        dot, zone, time = "", val(r.get("zone")), val(r.get("time"))
        if session_key == SCHEDULE_KV_MARKER:
            scene = val(kv.get("scene"))
            zone = val(kv.get("studio_zone"))
            time = val(kv.get("time_slot"))
    trs += (f'<tr class="{zeb}"><td>{time}</td>'
            f'<td>{dot}<span class="sess">{session}</span></td>'
            f'<td>{scene}</td><td>{zone}</td><td>{focus}</td></tr>')

# Content：表格上緣切齊 Content 區上緣，列高守 DESIGN.md §6-1 的 38.2
# schedule 整節缺了就沒有列可畫 —— 這頁不出。
if schedule:
    C_TOP, C_H = content_box(False)
    C_HEAD_H, C_ROW_H = 30.2, 38.2
    C_TBL_H = C_HEAD_H + C_ROW_H * len(schedule)
    _timeline_thead = "".join(f"<th>{h}</th>" for h in TIMELINE_HEADERS)
    timeline = f"""
{header_block(SECTION['C'][0], SECTION['C'][1])}
<div class="tbl-wrap" style="top:{f(C_TOP)}pt">
<table class="timeline">
  <colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"><col class="c5"></colgroup>
  <thead><tr>{_timeline_thead}</tr></thead>
  <tbody>{trs}</tbody>
</table>
</div>
"""
    add_page("C", SECTION['C'][0], timeline, layout=dev("C 時間軸表格"),
             detail=dev(f'Content 表格 {len(schedule)} 列 ｜ 表頭 {f(C_HEAD_H)} ＋ 列高 {f(C_ROW_H)} = {f(C_TBL_H)} ｜ Meta 無'))

# ════════════════════════════════════════════════════════════════════
# 3.4 棚區卡片（D）
# ════════════════════════════════════════════════════════════════════
# Content：卡片高度 = Content 區高度（撐滿，不用原檔那個超出區塊的 407.0）
# Meta：每一區的場次分配（zones[].scenes，原本沒被用到的資料）
# zones 整節缺了就沒有棚區卡可畫 —— 這頁不出。
if zones:
    D_TOP, D_H = content_box(True)
    CARD_W = 278.8
    n_cards = len(zones)
    card_gap = (SAFE_W - CARD_W * n_cards) / (n_cards - 1) if n_cards > 1 else 0.0
    CARD_PAD = 14.4
    CARD_FILL = "#a5a5a5"        # 三張卡統一成一個灰（禁則）：取三值的中位數
    D_CODE_H = 38.4              # 24pt 棚區代號一行 ＋ 下方間距
    D_PH_H = (D_H - 2 * CARD_PAD - D_CODE_H - 2 * GAP) / 2   # 代號 ＋ 兩張照片 ＝ 2 道縫
    cards = ""
    for i, z in enumerate(zones):
        left = SAFE_L + i * (CARD_W + card_gap)
        photos = ""
        for j, p in enumerate(z.get("photos") or []):
            cap = f'{val(z.get("code"))} {ZONE_PHOTO_CAPTION} {j + 1} · {p.get("ratio")}'
            photos += f'<div class="zph" style="height:{f(D_PH_H)}pt">{ph(p.get("ratio"), cap)}</div>'
        cards += (f'<div class="zcard" style="left:{f(left)}pt;top:{f(D_TOP)}pt;'
                  f'width:{f(CARD_W)}pt;height:{f(D_H)}pt;background:{CARD_FILL};'
                  f'padding:{f(CARD_PAD)}pt;gap:{f(GAP)}pt">'
                  f'<span class="zcode" style="height:{f(D_CODE_H)}pt">{val(z.get("label"))}</span>'
                  f'{photos}</div>')

    area = (header_block(SECTION['D'][0], SECTION['D'][1]) + cards
            + meta_block([(f'{val(z.get("label"))} {ZONE_SESSIONS_LABEL}',
                           "、".join(z.get("scenes") or []) or None)
                          for z in zones], gap=card_gap))
    add_page("D", SECTION['D'][0], area, bg="white", has_meta=True,
             layout=dev("D 棚區卡片"),
             detail=dev(f'Content 卡 {n_cards} 張 {f(CARD_W)}×{f(D_H)}（實景照 {f(D_PH_H)} 高）｜ Meta 棚區場次 {n_cards} 欄'))

# ════════════════════════════════════════════════════════════════════
# 3.5 標準鏡位清單（E）
# ════════════════════════════════════════════════════════════════════
# Content：16 條分兩欄，列距由 Content 區高度推導（撐滿，不用原檔的 31.67）
# Meta：適用場景 ＋ 顆數組成（兩條原本擠在頁首下方的說明行）
# standard_shots 整節缺了就沒有清單可列 —— 這頁不出。
if std:
    E_TOP, E_H = content_box(True)
    half = math.ceil(len(std) / 2)
    cols = [std[:half], std[half:]]
    E_PITCH = E_H / half
    items = ""
    for ci, col in enumerate(cols):
        x = TEXT_L + ci * (SAFE_W / 2)
        for ri, t in enumerate(col):
            top = E_TOP + ri * E_PITCH
            items += (f'<div class="li" style="left:{f(x)}pt;top:{f(top)}pt;'
                      f'height:{f(E_PITCH)}pt"><span class="bul"></span>'
                      f'<span class="lt">{t.get("label") if isinstance(t, dict) else t}</span></div>')

    # 「適用於」一行由 color.scene 推導，不抄原檔那句（原句列 5 個場景卻寫 6 個）
    applies = (" · ".join(val(c.get("scene")) for c in colors)
               + SHOTLIST_APPLIES_SUFFIX.replace("{n}", str(len(colors))))
    generic_n = sum(1 for s in std
                     if (s.get("feature") if isinstance(s, dict) else None) == GENERIC_FEATURE_MARKER)
    compose = (SHOTLIST_COMPOSE_TMPL
               .replace("{generic}", str(generic_n))
               .replace("{specific}", str(len(std) - generic_n))
               .replace("{total}", str(len(std))))
    shotlist = (header_block(SECTION['E'][0], SECTION['E'][1]) + items
                + meta_block([(SHOTLIST_SCENES_LABEL, applies),
                              (SHOTLIST_COMPOSITION_LABEL, compose)]))
    add_page("E", SECTION['E'][0], shotlist, has_meta=True,
             layout=dev("E 雙欄清單"),
             detail=dev(f'Content {len(std)} 條 × 2 欄（列距 {f(E_PITCH)}）｜ Meta 適用場景 ＋ 清單組成'))

# ════════════════════════════════════════════════════════════════════
# 3.6 主視覺 KV（F）
# ════════════════════════════════════════════════════════════════════
# Header：深色標題帶佔滿 Header 區（0–108），右側一排產品色環
# Content：主次雙圖，共用高度由可用寬求解，在 Content 區垂直置中
# Meta：無
# key_visual 整節缺了就沒有 KV 可畫 —— 這頁不出。
if kv:
    BAND_H = HEADER_BOT
    RING_D, RING_PITCH = 43.5, 48.95
    rings = ""
    BAND_PAD_X = 28.8
    ring_total = (RING_PITCH * (len(colors) - 1) + RING_D) if colors else 0.0
    ring_x0 = SAFE_W - BAND_PAD_X - ring_total
    kv_text_w = ring_x0 - BAND_PAD_X - 14.4
    for i, c in enumerate(colors):
        rings += (f'<span class="ring" style="left:{f(ring_x0 + i * RING_PITCH)}pt;'
                  f'top:{f((BAND_H - RING_D) / 2)}pt;background:{c.get("hex") or "transparent"}"></span>')

    KV_GAP = 6.5
    F_TOP, F_H = content_box(False)
    kv_images = kv.get("images") or []
    kv_ratios = [RATIO[i["ratio"]] for i in kv_images]
    kv_h = min((SAFE_W - KV_GAP) / sum(kv_ratios), F_H) if kv_ratios else 0.0
    kv_top = F_TOP + (F_H - kv_h) / 2
    kv_imgs = ""
    for i, im in enumerate(kv_images):
        kv_label = KV_PRIMARY_LABEL if i else KV_SECONDARY_LABEL
        kv_imgs += ph(im["ratio"], f'KV {kv_label} · {im["ratio"]}')

    keyvis = f"""
<div class="kvband" style="height:{f(BAND_H)}pt;--kv-text-w:{f(kv_text_w)}pt">
  <span class="kv-slot">{val(kv.get('time_slot'))} ｜ {val(kv.get('studio_zone'))} {ZONE_SUFFIX} ｜ {SCENE_PREFIX}{val(kv.get('scene'))}</span>
  <span class="kv-title">{val(kv.get('title'))} KEY VISUAL</span>
  <span class="kv-desc">{val(kv.get('description'))}</span>
  {rings}
</div>
<div class="prow kv-row" style="left:{f(SAFE_L)}pt;top:{f(kv_top)}pt;height:{f(kv_h)}pt;gap:{f(KV_GAP)}pt">{kv_imgs}</div>
"""
    add_page("F", f'{val(kv.get("title"))} KEY VISUAL', keyvis, bg="white", layout=dev("F KV 標題帶"),
             detail=dev(f'Header 深色帶 {f(SAFE_W)}×{f(BAND_H)} ＋ 色環 {len(colors)} 顆 ｜ Content 雙圖共用高 {f(kv_h)} ｜ Meta 無'))

# ════════════════════════════════════════════════════════════════════
# 3.7 / 3.8 / 3.9 每色：G 氣氛參考 → (I 獨立主題) → H 鏡位網格
# ════════════════════════════════════════════════════════════════════
for c in colors:
    name_en = c.get("name_en")
    name_zh = c.get("name_zh")

    # ── G 氣氛參考（SKILL.md〈G 的排法〉四變體）──────────────────
    # Header：22pt 固定標題 ＋ 色名場景 ＋ MODEL ＋ 右側產品去背窗
    # Content：參考圖列（四變體共用同一個垂直預算）
    # Meta：MOOD / PLAYLIST / MOMENT 三欄 ＋ PROPS 空槽
    # mood_refs 這個色缺了就沒有參考圖可排 —— 這色的 G 頁不出。
    refs = c.get("mood_refs") or []
    if refs:
        G_TOP, G_H = content_box(True)
        gtext = lambda s: f'{MOOD_REF_CAPTION} · {s["ratio"]}'          # noqa: E731
        span_i = next((i for i, r in enumerate(refs) if r.get("span")), None)
        bleed_i = next((i for i, r in enumerate(refs) if r.get("bleed")), None)
        bleed_html = ""

        if span_i is not None:
            # G-3 跨列：標記那張在右側跨滿兩列；之前的進上列、之後的進下列
            variant = dev("G-3 跨列")
            sp = refs[span_i]
            up, lo = refs[:span_i], refs[span_i + 1:]
            hb, uh, lh = g_span_solve(RATIO[sp["ratio"]], up, lo, G_H, ROW_GAP_G)
            span_cell = (f'<div class="cell hero-cell" style="height:{f(hb)}pt">'
                         f'{ph(sp["ratio"], gtext(sp))}</div>')
            side = (f'<div class="hero-side" style="gap:{f(ROW_GAP_G)}pt">'
                    f'{prow(up, uh, lambda s: cell(s["ratio"], gtext(s)))}'
                    f'{prow(lo, lh, lambda s: cell(s["ratio"], gtext(s)))}</div>')
            gtop = G_TOP + (G_H - hb) / 2          # 在 Content 區裡置中
            grid = (f'<div class="grid" style="top:{f(gtop)}pt">'
                    f'<div class="hero-block" style="gap:{f(HERO_GAP)}pt;'
                    f'height:{f(hb)}pt">{side}{span_cell}</div></div>')
            body_h = hb
            detail = dev(f'{len(refs)} 張參考圖 ｜ 跨列圖 {f(hb * RATIO[sp["ratio"]])}×{f(hb)} ｜ '
                         f'上列 {f(uh)} / 下列 {f(lh)}')

        elif bleed_i is not None:
            # G-4 出血：標記那張貼右頁緣；水平出血、垂直守 Content 區。
            # 其餘分兩列，奇數時下列多一張。
            variant = dev("G-4 出血")
            bl = refs[bleed_i]
            rest = refs[:bleed_i] + refs[bleed_i + 1:]
            up, lo = rest[:len(rest) // 2], rest[len(rest) // 2:]
            bleed_left = PAGE_W - G4_BLEED_W
            right_lim = bleed_left - GAP
            uh = g_row_height([[r] for r in up], right_lim - SAFE_L)
            lh = g_row_height([[r] for r in lo], right_lim - SAFE_L)
            if uh + ROW_GAP_G + lh > G_H:
                scale = (G_H - ROW_GAP_G) / (uh + lh)
                uh, lh = uh * scale, lh * scale
            body_h = uh + ROW_GAP_G + lh
            gtop = G_TOP + (G_H - body_h) / 2
            bleed_html = (f'<div class="ph g-bleed" style="left:{f(bleed_left)}pt;'
                          f'top:{f(G_TOP)}pt;width:{f(G4_BLEED_W)}pt;height:{f(G_H)}pt">'
                          f'<span>{gtext(bl)}<br>{MOOD_BLEED_CAPTION}</span></div>')
            grid = (f'<div class="prow g-abs" style="left:{f(SAFE_L)}pt;top:{f(gtop)}pt;'
                    f'height:{f(uh)}pt">'
                    + "".join(cell(s["ratio"], gtext(s)) for s in up) + '</div>'
                    + f'<div class="prow g-abs" style="left:{f(SAFE_L)}pt;'
                    f'top:{f(gtop + uh + ROW_GAP_G)}pt;height:{f(lh)}pt">'
                    + "".join(cell(s["ratio"], gtext(s)) for s in lo) + '</div>')
            detail = dev(f'{len(refs)} 張參考圖 ｜ 出血圖 {f(G4_BLEED_W)}×{f(G_H)} ｜ '
                         f'上列 {f(uh)} / 下列 {f(lh)}')

        else:
            # G-1 單列（預設）／列高不足下限 → G-2 兩小疊
            variant, gcols, gh = g_single_row(refs, G_H)
            inner = ""
            for col in gcols:
                if len(col) == 1:
                    inner += cell(col[0]["ratio"], gtext(col[0]))
                else:
                    cw = g_col_terms(col)[0] * gh + g_col_terms(col)[1]
                    inner += (f'<div class="cell gstack" style="width:{f(cw)}pt;gap:{f(GAP)}pt">'
                              + "".join(ph(r["ratio"], gtext(r)) for r in col) + '</div>')
            gtop = G_TOP + (G_H - gh) / 2        # 在 Content 區裡置中
            grid = (f'<div class="grid" style="top:{f(gtop)}pt">'
                    f'<div class="prow" style="height:{f(gh)}pt">{inner}</div></div>')
            body_h = gh
            detail = dev(f'{len(refs)} 張參考圖 ｜ {len(gcols)} 欄單列 ｜ 列高 {f(gh)}')

        mood = (
            f'<div class="band-head">'
            f'<div class="g-title">{MOOD_PAGE_TITLE}</div>'
            f'<div class="g-scene">{head_label(c)}</div>'
            f'<div class="g-model">{session_line(c)}</div>'
            f'<div class="cutout" style="left:{f(CUT_X)}pt;top:{f(CUT_Y)}pt;'
            f'width:{f(CUT_W)}pt;height:{f(CUT_H)}pt">'
            f'<span>{CUTOUT_CAPTION}<br>{val(name_en)} {val(name_zh)}</span></div>'
            f'</div>'
            + bleed_html + grid
            + meta_block([(MOOD_META.get("mood", ""), " · ".join(c.get("mood") or []) or None),
                          (MOOD_META.get("playlist", ""), " · ".join(c.get("playlist") or []) or None),
                          (MOOD_META.get("moment", ""), " · ".join(c.get("moment") or []) or None),
                          (MOOD_META.get("props", ""), None)]))
        add_page("G", f'{val(name_en)} {MOOD_REF_CAPTION}', mood, layout=variant,
                 has_meta=True,
                 detail=dev(f'{detail} ｜ Meta 情緒/歌單/時刻 3 欄 ＋ 道具空槽'))

    # ── I 獨立主題企劃（可選，插在該色氣氛參考之後）──────────────
    th = theme_by_color.get(name_en)
    # reference_board／shot_list 是版面幾何要靠的結構資料，缺了這頁就沒得排 —— 不出。
    if th and th.get("shot_list") and th.get("reference_board"):
        # Header：色名前導 ＋ 30pt 主題名；Content：左欄五段 ＋ 右欄 Reference Board
        # Meta：MODEL 規格 ＋ 場次
        I_TOP, I_H = content_box(True)
        I_BOARD_L = 480.0
        rb = th["reference_board"]
        rb_w = SAFE_R - I_BOARD_L
        rb_h = rb_w / RATIO[rb["ratio"]]
        I_CAP_H = 20.7
        i_board_top = I_TOP + (I_H - rb_h - I_CAP_H) / 2

        # 左欄五段：副標 / 敘述 / MOOD / KEYWORDS / PALETTE / SHOT LIST
        n = len(th["shot_list"])
        rows_n = math.ceil(n / 2)
        seg_h = [19.0,                       # 14pt 副標
                 36.0,                       # 12pt 敘述兩行
                 30.0,                       # MOOD 標籤 ＋ 值
                 30.0,                       # KEYWORDS 標籤 ＋ 值
                 12.0 + 46.8,                # PALETTE 標籤 ＋ 色票
                 12.0 + rows_n * 21.0]       # SHOT LIST 標籤 ＋ 勾號列
        seg_gap = (I_H - sum(seg_h)) / (len(seg_h) - 1)
        ytop, ys = I_TOP, []
        for h in seg_h:
            ys.append(ytop)
            ytop += h + seg_gap

        sw = "".join(
            f'<span class="sw" style="left:{f(TEXT_L + i * 70.55)}pt;background:{hexv}"></span>'
            for i, hexv in enumerate(th.get("palette") or []))
        sl = ""
        for ci2, colitems in enumerate([th["shot_list"][:rows_n], th["shot_list"][rows_n:]]):
            for ri2, t in enumerate(colitems):
                sl += (f'<div class="ck" style="left:{f(TEXT_L + ci2 * 208)}pt;'
                       f'top:{f(ys[5] + 12.0 + ri2 * 21.0)}pt">'
                       f'<span class="ckm">✓</span>{t}</div>')

        theme_html = (
            header_block(f'{val(name_zh)} {slug(name_en)} ｜ {THEME_EYEBROW_SUFFIX}',
                         val(th.get("title")))
            + f'<div class="i-sub" style="top:{f(ys[0])}pt">{val(th.get("subtitle"))}</div>'
            + f'<div class="i-desc" style="top:{f(ys[1])}pt">{val(th.get("description"))}</div>'
            + f'<div class="i-lab" style="top:{f(ys[2])}pt">MOOD</div>'
            + f'<div class="i-val" style="top:{f(ys[2] + 13)}pt">{val(th.get("mood"))}</div>'
            + f'<div class="i-lab" style="top:{f(ys[3])}pt">KEYWORDS</div>'
            + f'<div class="i-val" style="top:{f(ys[3] + 13)}pt">{" ｜ ".join(th.get("keywords") or []) or blank()}</div>'
            + f'<div class="i-lab" style="top:{f(ys[4])}pt">PALETTE</div>'
            + f'<div class="sw-row" style="top:{f(ys[4] + 12)}pt">{sw}</div>'
            + f'<div class="i-lab" style="top:{f(ys[5])}pt">{THEME_SHOTLIST_LABEL.replace("{n}", str(n))}</div>'
            + sl
            + f'<div class="i-board" style="left:{f(I_BOARD_L)}pt;top:{f(i_board_top)}pt;'
              f'width:{f(rb_w)}pt">{ph(rb["ratio"], f"Reference Board · {rb['ratio']}")}'
              f'<div class="i-cap">Reference Board ｜ {val(th.get("title"))} {val(th.get("mood"))}</div></div>'
            + meta_block([(THEME_META.get("model", ""), th.get("model_spec") or None),
                          (THEME_META.get("session", ""), session_line(c, model=False))]))
        add_page("I", dev(f'{name_en or "?"} 獨立主題企劃'), theme_html,
                 layout=dev("I（可選版式）"), has_meta=True,
                 detail=dev(f'Content 左欄六段（段距 {f(seg_gap)}）＋ Reference Board '
                            f'{f(rb_w)}×{f(rb_h)} ｜ Meta MODEL ＋ 場次'))

    # ── H 鏡位網格 ────────────────────────────────────────────────
    # Header：色名場景 ＋ 情境資訊行；右側 Shot 範圍 ＋ 張數
    # Content：便當盒 grid（撐滿 Content 區）；Meta：無
    # shots 這個色缺了就沒有鏡位可排 —— 這色的 H 頁不出。
    shots = c.get("shots") or []
    if shots:
        shot_count = c.get("shot_count")
        if shot_count is not None:
            assert len(shots) == shot_count, (name_en, len(shots), shot_count)
        sizes = split_pages(len(shots), 10)
        cur = 0
        H_TOP, H_H = content_box(False)
        H_VBUDGET = H_H - IDX_BAND
        for pi, size in enumerate(sizes):
            page_shots = shots[cur:cur + size]
            cur += size
            lo_no, hi_no = page_shots[0]["no"], page_shots[-1]["no"]
            layout, hero_i = pick_layout(page_shots)

            if hero_i is None:
                up, lo = two_row_split(page_shots)
                h = solve_two_rows(up, lo, ROW_GAP_H, H_VBUDGET)
                rows = prow(up, h, lambda s: cell(s["ratio"], shot_text(c, s), f'{s["no"]:02d}'))
                if lo:
                    rows += prow(lo, h, lambda s: cell(s["ratio"], shot_text(c, s), f'{s["no"]:02d}'))
                body_h = h * (2 if lo else 1) + (ROW_GAP_H if lo else 0) + IDX_BAND
                gtop = H_TOP + (H_H - body_h) / 2
                grid = (f'<div class="grid" style="top:{f(gtop)}pt;gap:{f(ROW_GAP_H)}pt">'
                        f'{rows}</div>')
                detail = dev(f'{layout} {len(up)}+{len(lo)} ｜ 列高 {f(h)}')
            else:
                hero = page_shots[hero_i]
                rest = [s for i, s in enumerate(page_shots) if i != hero_i]
                up, lo = two_row_split(rest)
                hb, uh, lh = solve_hero(RATIO[hero["ratio"]], up, lo, H_VBUDGET)
                hero_cell = (f'<div class="cell hero-cell" style="height:{f(hb)}pt">'
                             f'{ph(hero["ratio"], shot_text(c, hero))}'
                             f'<span class="idx">{hero["no"]:02d}</span></div>')
                side = (f'<div class="hero-side" style="gap:{f(ROW_GAP_H)}pt">'
                        f'{prow(up, uh, lambda s: cell(s["ratio"], shot_text(c, s), f"{s["no"]:02d}"))}'
                        f'{prow(lo, lh, lambda s: cell(s["ratio"], shot_text(c, s), f"{s["no"]:02d}"))}'
                        f'</div>')
                inner = hero_cell + side if layout.startswith("hero-left") else side + hero_cell
                body_h = hb + IDX_BAND
                gtop = H_TOP + (H_H - body_h) / 2
                grid = (f'<div class="grid" style="top:{f(gtop)}pt">'
                        f'<div class="hero-block" style="gap:{f(HERO_GAP)}pt;height:{f(hb)}pt">{inner}</div></div>')
                detail = dev(f'{layout} hero={hero["no"]:02d} ｜ 側欄 {len(up)}+{len(lo)} ｜ '
                             f'hero 高 {f(hb)} / 上列 {f(uh)} / 下列 {f(lh)}')

            h_count = (H_COUNT_TMPL.replace("{size}", str(size))
                                    .replace("{name}", name_en or "")
                                    .replace("{total}", str(len(shots))))
            body = (
                f'<div class="band-head">'
                f'<div class="h-scene">{head_label(c)}</div>'
                f'<div class="h-model">{session_line(c)}</div>'
                f'<div class="h-range">Shot {lo_no:02d}–{hi_no:02d}</div>'
                f'<div class="h-count">{h_count}</div>'
                f'</div>') + grid
            add_page("H", dev(f'{name_en or "?"} 鏡位網格 {pi + 1}/{len(sizes)}（Shot {lo_no:02d}–{hi_no:02d}）'),
                     body, layout=layout,
                     detail=dev(f'{size} 張 ｜ {detail.split("｜", 1)[1].strip() if "｜" in detail else detail} ｜ Meta 無'))

# ════════════════════════════════════════════════════════════════════
# 組檔
# ════════════════════════════════════════════════════════════════════
TOKENS = """
    /* ─── design-systems/photo-brief/tokens.css: all 56 variables carried over ─── */
    --bg: #f5f5f3;
    --surface: #ffffff;
    --surface-warm: #fbfaf8;
    --fg: #262626;
    --fg-2: #6b6b6b;
    --muted: #888888;
    --meta: var(--muted);
    --border: #e3e1dc;
    --border-soft: var(--border);
    --accent: #d97d35;
    --accent-on: #262626;
    --accent-hover: color-mix(in oklab, var(--accent), black 8%);
    --accent-active: color-mix(in oklab, var(--accent), black 14%);
    --success: #16a34a;
    --warn: #eab308;
    --danger: #dc2626;
    --font-display: Cambria, "STSongti TC", "Songti TC", "Noto Serif TC", serif;
    --font-body: Calibri, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
    --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    --text-xs: 9pt;
    --text-sm: 11pt;
    --text-base: 12pt;
    --text-lg: 14pt;
    --text-xl: 18pt;
    --text-2xl: 24pt;
    --text-3xl: 30pt;
    --text-4xl: 66pt;
    --leading-body: 1.5;
    --leading-tight: 1.15;
    --tracking-display: 0em;
    --space-1: 3.6pt;
    --space-2: 7.2pt;
    --space-3: 10.8pt;
    --space-4: 14.4pt;
    --space-5: 18pt;
    --space-6: 21.6pt;
    --space-8: 28.8pt;
    --space-12: 43.2pt;
    --section-y-desktop: 40.3pt;
    --section-y-tablet: 40.3pt;
    --section-y-phone: 40.3pt;
    --radius-sm: 6pt;
    --radius-md: 9pt;
    --radius-lg: 12pt;
    --radius-pill: 9999pt;
    --elev-flat: none;
    --elev-ring: 0 0 0 1px var(--border);
    --elev-raised: var(--elev-ring);
    --focus-ring: 0 0 0 3px color-mix(in oklab, var(--accent), transparent 70%);
    --motion-fast: 150ms;
    --motion-base: 200ms;
    --ease-standard: cubic-bezier(0.2, 0, 0, 1);
    --container-max: 873.6pt;
    --container-gutter-desktop: 43.2pt;
    --container-gutter-tablet: 43.2pt;
    --container-gutter-phone: 43.2pt;

    /* ─── page band skeleton (DESIGN.md §5-0), four cut points ─── */
    --band-header-h: 108pt;     /*  0     – 108     = 30 × 3.6  */
    --band-meta-top: 432pt;     /*  432   – 493.2   = 120 × 3.6 */
    --band-meta-h: 61.2pt;      /*  61.2            = 17 × 3.6  */
    --band-footer-top: 493.2pt; /*  493.2 – 540     = 137 × 3.6 */
"""

CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: #cfccc4;
  font-family: var(--font-body);
  color: var(--fg);
  padding: 36pt 0 72pt;
}
.deck { width: 960pt; margin-inline: auto; }
.sheet { margin-bottom: 54pt; }

/* ── Page frame ─────────────────────────────────────────────────────── */
.pg {
  position: relative; width: 960pt; height: 540pt;
  background: var(--bg); overflow: hidden;
  outline: 1px solid #b6b2a8;
}
.pg.dark { background: var(--fg); color: var(--surface); }
.pg.white { background: var(--surface); }

/* ── Four-band skeleton ─────────────────────────────────────────────── */
.band-head {
  position: absolute; left: 0; top: 0; width: 960pt; height: var(--band-header-h);
}
.band-meta {
  position: absolute; left: 43.2pt; top: var(--band-meta-top);
  width: 873.6pt; height: var(--band-meta-h);
  display: flex; align-items: flex-start;
}
.band-meta .mcol { flex: 1 1 0; min-width: 0; }
.band-meta .mlab {
  font-size: 10pt; font-weight: 700; color: var(--accent);
  letter-spacing: .1em; line-height: 1.2;
}
.band-meta .mval {
  margin-top: 5.4pt; font-size: var(--text-sm); color: var(--fg); line-height: 1.35;
}
.band-meta .mval.plain {
  /* No label, single line (cover brand line): vertically centered in the 61.2 band */
  margin-top: 25.2pt; font-size: 10pt; color: var(--fg-2); letter-spacing: .06em;
}
.band-meta .mslot {
  margin-top: 5.4pt; height: 29.7pt; border: 1px dashed var(--border);
  display: flex; align-items: center; padding-left: 7.2pt;
  font-size: var(--text-xs); color: var(--muted);
}
.pg.dark .band-meta .mval.plain { color: #9b978e; }

/* Inline empty-slot marker for a missing field (blank()); dark-page / KV-band variant below. */
.bk {
  display: inline-block; padding: 1pt 6pt; border: 1px dashed var(--border);
  border-radius: 3pt; font-size: var(--text-xs); color: var(--muted);
}
.pg.dark .bk, .kvband .bk { border-color: #9b978e; color: #c9c6be; }

.rule { position: absolute; left: 43.2pt; top: var(--band-footer-top); width: 873.6pt; height: 1px; background: var(--border); }
.pg.dark .rule { background: #9b978e; }
.pno { position: absolute; left: 933.1pt; top: 508pt; font-size: 10pt; color: var(--fg-2); line-height: 1; }
.pno.on-dark { color: #9b978e; }

/* ── Header band title group (shared) ───────────────────────────────────── */
.hd-eyebrow {
  position: absolute; left: 50.4pt; top: 30.7pt;
  font-size: var(--text-base); font-weight: 700; color: var(--accent); line-height: 1;
}
.hd-title {
  position: absolute; left: 50.4pt; top: 55.8pt;
  font-family: var(--font-display); font-weight: 700; font-size: var(--text-3xl);
  line-height: 1.15;
}
.hd-sub { position: absolute; left: 50.4pt; top: 90pt; font-size: var(--text-lg); color: var(--fg-2); line-height: 1; }
.hd-right { position: absolute; right: 43.2pt; top: 29pt; font-size: var(--text-lg); font-weight: 700; color: var(--accent); line-height: 1; text-align: right; }
.hd-right2 { position: absolute; right: 43.2pt; top: 50pt; font-size: 10pt; color: var(--fg-2); line-height: 1; text-align: right; }

/* ── A Cover ───────────────────────────────────────────────────── */
.cover-dots { position: absolute; left: 0; height: 22.1pt; width: 100%; }
.cover-dots .dot { position: absolute; top: 0; width: 22.1pt; height: 22.1pt; border-radius: 50%; }
.cover-name {
  position: absolute; left: 50.4pt;
  font-family: var(--font-display); font-weight: 700; font-size: var(--text-4xl);
  line-height: 1; color: var(--surface);
}
.cover-sub { position: absolute; left: 50.4pt; font-size: var(--text-xl); color: #c9c6be; line-height: 1; }
.cover-bar { position: absolute; left: 43.2pt; width: 2pt; background: var(--accent); }
.cover-meta { position: absolute; left: 61.2pt; }
.cover-meta .cm1 { font-size: 16pt; font-weight: 700; color: var(--surface); line-height: 1.35; }
.cover-meta .cm2 { margin-top: 5pt; font-size: 13pt; color: #c9c6be; line-height: 1.35; }

/* ── B Overview info card ─────────────────────────────────────────────── */
.banner { position: absolute; left: 0; top: 0; width: 960pt; overflow: hidden; }
.banner .ph.banner-ph { width: 960pt; height: 100%; aspect-ratio: auto; }
.b-eyebrow { position: absolute; left: 50.4pt; font-size: var(--text-base); font-weight: 700; color: var(--accent); line-height: 1; }
.inf-row { position: absolute; left: 50.4pt; width: 554.4pt; }
.inf-row .inf-k { position: absolute; left: 0; top: 6pt; font-size: var(--text-sm); color: var(--fg-2); }
.inf-row .inf-v { position: absolute; left: 215.6pt; top: 4.5pt; font-size: 13pt; color: var(--fg); }
.inf-row .inf-line { position: absolute; left: 0; bottom: 0; width: 554.4pt; height: 1px; background: var(--border-soft); }
.infocard {
  position: absolute; left: 632.4pt; width: 284.4pt; height: 284.4pt;
  background: var(--fg); color: var(--surface);
  padding: 28.8pt 21.6pt 28.8pt 32.4pt; display: flex; flex-direction: column;
}
.infocard .ic-eyebrow { font-size: var(--text-base); font-weight: 700; color: var(--accent); }
.infocard .ic-name {
  margin-top: 10.8pt; font-family: var(--font-display); font-weight: 700;
  font-size: var(--text-2xl); line-height: 1.15;
}
.infocard .ic-sub { margin-top: 3.6pt; font-size: var(--text-sm); color: #c9c6be; }
.infocard .ic-fields { margin-top: auto; display: grid; gap: 7.2pt; }
.cf-row { display: flex; justify-content: space-between; gap: 14.4pt; }
.cf-row .cf-k { font-size: var(--text-sm); color: #9b978e; }
.cf-row .cf-v { font-size: var(--text-sm); }

/* ── C Timeline table ─────────────────────────────────────────────── */
.tbl-wrap { position: absolute; left: 43.2pt; }
table.timeline { border-collapse: collapse; width: 856.8pt; table-layout: fixed; }
table.timeline col.c1 { width: 122.4pt; }
table.timeline col.c2 { width: 194.4pt; }
table.timeline col.c3 { width: 136.8pt; }
table.timeline col.c4 { width: 64.8pt; }
table.timeline col.c5 { width: 338.4pt; }
table.timeline thead tr { height: 30.2pt; background: var(--fg); color: var(--surface); }
table.timeline thead th { padding: 0 10.8pt; text-align: left; font-weight: 700; font-size: var(--text-sm); }
table.timeline tbody tr { height: 38.2pt; }
table.timeline tbody tr.z1 { background: var(--surface); }
table.timeline tbody tr.z2 { background: var(--surface-warm); }
table.timeline tbody tr.z3 { background: #efede8; }
table.timeline tbody td { padding: 0 10.8pt; font-size: var(--text-sm); color: var(--fg); vertical-align: middle; }
.rdot { display: inline-block; width: 14.2pt; height: 14.2pt; border-radius: 50%; vertical-align: -3pt; margin-right: 7.2pt; }

/* ── D Studio zone cards ───────────────────────────────────────────────── */
.zcard {
  position: absolute; border-radius: 9pt; box-shadow: 0 0 0 1px #ffffff inset;
  display: flex; flex-direction: column; align-items: center; overflow: hidden;
}
.zcard .zcode {
  align-self: flex-start; font-family: var(--font-display); font-weight: 700;
  font-size: var(--text-2xl); color: var(--surface); line-height: 1.1;
}
.zcard .zph { flex: 0 0 auto; }
.zcard .zph .ph { height: 100%; width: auto; }

/* ── E Two-column list ───────────────────────────────────────────────── */
.li { position: absolute; width: 410pt; display: flex; align-items: center; }
.li .bul { flex: 0 0 auto; width: 7.1pt; height: 7.1pt; border-radius: 50%; background: var(--accent); }
.li .lt { display: block; padding-left: 9pt; font-size: var(--text-base); line-height: 1.2; }

/* ── F KV title band ──────────────────────────────────────────────── */
.kvband {
  position: absolute; left: 43.2pt; top: 0; width: 873.6pt;
  background: var(--fg); color: var(--surface); padding: 15.4pt 28.8pt;
}
.kvband .kv-slot { display: block; width: var(--kv-text-w); font-size: var(--text-base); font-weight: 700; color: var(--accent); line-height: 1; }
.kvband .kv-title {
  display: block; width: var(--kv-text-w); margin-top: 8pt; font-family: var(--font-display);
  font-weight: 700; font-size: 26pt; line-height: 1.1;
}
.kvband .kv-desc { display: block; width: var(--kv-text-w); margin-top: 6pt; font-size: 13pt; color: #c9c6be; }
.kvband .ring { position: absolute; width: 43.5pt; height: 43.5pt; border-radius: 50%; border: 1.5pt solid var(--surface); }
.kv-row { position: absolute; }

/* ── G Mood references ───────────────────────────────────────────────── */
.g-title { position: absolute; left: 50.4pt; top: 22.7pt; font-size: 22pt; font-weight: 600; line-height: 1; }
.g-scene { position: absolute; left: 50.4pt; top: 57pt; font-size: var(--text-base); font-weight: 700; color: var(--accent); line-height: 1; }
.g-model { position: absolute; left: 50.4pt; top: 78pt; font-size: var(--text-sm); color: var(--fg-2); line-height: 1; }
.cutout {
  position: absolute; background: var(--border); display: flex;
  align-items: center; justify-content: center; text-align: center;
  font-size: var(--text-xs); color: var(--fg-2); line-height: 1.4;
}

/* ── H Shot grid ───────────────────────────────────────────────── */
.h-scene { position: absolute; left: 50.4pt; top: 30.7pt; font-size: var(--text-base); font-weight: 700; color: var(--accent); line-height: 1; }
.h-model { position: absolute; left: 50.4pt; top: 52pt; font-size: var(--text-sm); color: var(--fg-2); line-height: 1; }
.h-range { position: absolute; right: 43.2pt; top: 29pt; font-size: var(--text-lg); font-weight: 700; color: var(--accent); line-height: 1; }
.h-count { position: absolute; right: 43.2pt; top: 52pt; font-size: 10pt; color: var(--fg-2); line-height: 1; }

/* ── I Special theme spread ───────────────────────────────────────────── */
.i-sub { position: absolute; left: 50.4pt; font-size: var(--text-lg); color: var(--fg); line-height: 1.2; }
.i-desc { position: absolute; left: 50.4pt; width: 400pt; font-size: var(--text-base); color: var(--fg-2); line-height: 1.45; }
.i-lab { position: absolute; left: 50.4pt; font-size: 10pt; font-weight: 700; color: var(--accent); letter-spacing: .1em; line-height: 1; }
.i-val { position: absolute; left: 50.4pt; font-size: 13pt; color: var(--fg); line-height: 1.3; }
.sw-row { position: absolute; left: 0; height: 46.8pt; width: 100%; }
.sw-row .sw { position: absolute; top: 0; width: 61.2pt; height: 46.8pt; border: 1px solid var(--border); }
.ck { position: absolute; font-size: var(--text-sm); color: var(--fg); line-height: 1.2; width: 200pt; }
.ck .ckm { color: var(--accent); font-weight: 700; margin-right: 5pt; }
.i-board { position: absolute; }
.i-board .ph { width: 100%; height: auto; }
.i-cap { margin-top: 7.2pt; font-size: 10pt; font-style: italic; color: var(--fg-2); line-height: 1.2; }

/* ── Bento-box grid (DESIGN.md §5-1, three rules) ────────────────────── */
.grid { position: absolute; left: 43.2pt; width: 873.6pt; display: flex; flex-direction: column; }
.prow { display: flex; justify-content: flex-start; gap: 7.2pt; }
.cell { position: relative; height: 100%; flex: 0 0 auto; }
.ph {
  height: 100%; width: auto; background: var(--border);
  display: flex; align-items: center; justify-content: center; text-align: center;
  color: var(--fg-2); font-size: var(--text-xs); line-height: 1.35; padding: 3pt;
}
.idx { position: absolute; left: 3.5pt; top: calc(100% + 8pt); font-size: var(--text-xs); color: var(--muted); line-height: 1; }
.hero-block { display: flex; align-items: flex-start; }
.hero-side { display: flex; flex-direction: column; flex: 0 0 auto; }
.hero-cell { flex: 0 0 auto; }
/* G layout variants: stacked column (G-2) / absolutely positioned row (G-4) / bleed image (G-4) */
.gstack { display: flex; flex-direction: column; }
.gstack > .ph { width: 100%; height: auto; }
.prow.g-abs { position: absolute; }
.ph.g-bleed { position: absolute; width: auto; height: auto; flex-direction: column; }
.r45 { aspect-ratio: 4 / 5; }
.r32 { aspect-ratio: 3 / 2; }
.r23 { aspect-ratio: 2 / 3; }
.r169 { aspect-ratio: 16 / 9; }
.r11 { aspect-ratio: 1 / 1; }
"""

# ── Review-only scaffolding CSS (only emitted with --review) ──────────
# The matching HTML (.sheet-label / .deck-head) is only ever built when
# REVIEW is true, so this stylesheet fragment stays out of the delivered
# page too — a delivered HTML must not contain the strings "sheet-label"
# or "deck-head" anywhere, CSS included.
CSS_REVIEW = """
.deck-head { margin-bottom: 24pt; }
.deck-head h1 { margin: 0; font-family: var(--font-display); font-size: var(--text-3xl); }
.deck-head p { margin: 6pt 0 0; font-size: var(--text-sm); color: #4a4842; }
.sheet-label {
  display: flex; align-items: baseline; gap: 10.8pt;
  margin-bottom: 7.2pt; font-size: var(--text-sm); color: #3d3b36;
}
.sheet-label .no { font-weight: 700; font-variant-numeric: tabular-nums; }
.sheet-label .lay {
  padding: 1pt 7.2pt; background: var(--fg); color: var(--surface);
  font-weight: 700; font-size: var(--text-xs); letter-spacing: .08em;
}
.sheet-label .det { color: #5f5c55; font-size: var(--text-xs); }
"""

sheets = []
for i, p in enumerate(PAGES, start=1):
    lay, det = p["layout"], p["detail"]
    detail = f'{lay} ｜ {det}' if lay and det else (lay or det)
    cls = "pg" + (f' {p["bg"]}' if p["bg"] else "")
    pno_cls = "pno on-dark" if p["pno_dark"] else "pno"
    sheet_label_html = ""
    if REVIEW:
        sheet_label_html = f"""
  <div class="sheet-label">
    <span class="no">P{i:02d}</span>
    <span class="lay">{dev("版式")} {p['letter']}</span>
    <span>{p['label']}</span>
    <span class="det">{detail}</span>
  </div>"""
    sheets.append(f"""
<section class="sheet" id="p{i:02d}">{sheet_label_html}
  <div class="{cls}">{p['body']}<div class="rule"></div><div class="{pno_cls}">{i:02d}</div></div>
</section>""")

total_shots = sum(len(c.get("shots") or []) for c in colors)
DECK_TITLE = f'{project.get("product_name") or ""} · {DECK_TITLE_SUFFIX}'
deck_head_html = ""
if REVIEW:
    deck_head_html = f"""
  <div class="deck-head">
    <h1>{DECK_TITLE}</h1>
    <p>
      {dev(f'共 {len(PAGES)} 頁 · 960 × 540 pt（16:9）· 六色 {total_shots} 顆鏡位 ·'
           f'版式池 A/B/C/D/E/F/G/H/I（本輪不含 Part 2.5 的 J）。'
           f'全部版式走同一套四段垂直骨架：Header 0–108 ／ Content 108–432（沒有 Meta 就到 493.2）／'
           f'Meta 432–493.2 ／ Footer 493.2–540。'
           f'圖片全部是佔位塊：<code>background: var(--border)</code> ＋ <code>aspect-ratio</code>，'
           f'零外連圖片／字型網址。頁框上方那行標籤是審閱鷹架，不屬於 deck 內容。')}
    </p>
  </div>"""

html_out = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{DECK_TITLE}</title>
<style>
:root {{{TOKENS}}}
{CSS}
{CSS_REVIEW if REVIEW else ""}
</style>
</head>
<body>
<div class="deck">{deck_head_html}
{''.join(sheets)}
</div>
</body>
</html>
"""

# Zero pages means the input has no Part 3 data at all. Writing an empty deck
# and exiting 0 would look like success -- say which sections are missing instead.
if not PAGES:
    need = {"project": project, "schedule": schedule, "zones": zones,
            "standard_shots": std, "key_visual": kv, "colors": colors}
    missing = [k for k, v in need.items() if not v]
    raise SystemExit(
        "這份輸入沒有 Part 3 的資料，一頁都產不出來。\n"
        "     缺的節：" + ("／".join(missing) if missing else "（節都在，但每一節的內容都是空的）") +
        "\n     Part 3 需要拍攝計畫的資料（專案資訊／棚區／標準鏡位／時間軸／每色的鏡位與氣氛參考）。")

OUT.write_text(html_out, encoding="utf-8")

print(f"pages   = {len(PAGES)}")
print(f"lines   = {html_out.count(chr(10)) + 1}")
print(f"bytes   = {len(html_out.encode('utf-8'))}")
print(f"shots   = {total_shots}")
print()
print("── 版式對照表 ──")
for i, p in enumerate(PAGES, start=1):
    meta = "Meta" if p["has_meta"] else "  — "
    print(f'P{i:02d} | {p["letter"]} | {meta} | {p["label"]} | {p["layout"]} | {p["detail"]}')
counts = {}
for p in PAGES:
    counts[p["letter"]] = counts.get(p["letter"], 0) + 1
print()
print("版式頁數：" + " / ".join(f"{k}×{v}" for k, v in sorted(counts.items())))
print("有 Meta 內容的頁：" + str(sum(1 for p in PAGES if p["has_meta"])) + " / " + str(len(PAGES)))
print("每色鏡位：" + " / ".join(f'{c.get("name_en") or "?"} {len(c.get("shots") or [])}' for c in colors)
      + f" = {total_shots}")
