# -*- coding: utf-8 -*-
"""Part 2 設計風格提案生成器 — 架構照 gen_part1.py 抄，色票另遵 SKILL.md §色票表。

用法：
    python gen_part2.py                          # 跑空白範本，看版型長什麼樣
    python gen_part2.py <輸入.yaml> <輸出.html>    # 填好資料後出簡報

【固化在本程式，換產品不變】
  版面 960×540｜chrome 五件組（左邊條／頁首線／章名／導覽格／頁碼，位置與 Part 1 完全共用）
  2.1 品牌識別三頁固定結構（因果鏈／命名／LOGOTYPE→IDENTITY→SYSTEM）
  2.2 Mood Board 每方案固定三頁（視覺方向／情境氛圍照 5 張／資訊排版風格 3 張）＋ Recap
  2.4 色彩情緒頁六欄骨架（色號色名→故事標題→MOOD→PLAYLIST→MOMENT→收尾標籤）
  2.5 排版方案比較每頁最多 3 個方案

【全部來自資料，換產品要換】
  章名與節名｜品牌理念/命名/識別描述｜Mood Board 方案內容與張數｜色彩情緒六欄的值
  （沿用 colors[] 既有欄位，不新增欄位）｜排版方案內容與張數

【程式計算，不是寫死】
  頁碼與目錄頁次｜品牌理念因果鏈的格數（steps 長度）｜Mood Board 頁數（方案數 ×3 ＋ 1）
  ｜色彩情緒頁數（len(colors)）｜排版方案頁數（ceil(len(layout_options)/3)）

值為 null／空陣列 ＝ 本案沒有這筆資料 → 畫版型骨架＋空槽，不編值。
空節（mood_boards 全空／colors 全空／layout_options 全空）不出對應的頁。
色票只准用 SKILL.md §色票表（d97d35／262626／f5f5f3／ffffff／6b6b6b／888888／e3e1dc／
c9c6be／9b978e／fbfaf8／efede8），不得新增或挪用 Part 1 生成器裡沒有列在該表的色值。
"""
import math
import sys
import yaml
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
# 沒給參數就跑空白範本 —— 產出的是「版型長什麼樣」，每一格都是空槽。
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else SKILL / "input-template.yaml"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else SKILL / "examples" / "blank-part2.html"

K = 4 / 3
W, H = 960.0, 540.0
BAR_W, RULE_Y = 28.2 * K, 36.2 * K
TXT_L, TITLE_Y = 52.2 * K, 52.1 * K
PAD, BODY_Y, BOT = 52.2 * K, 96 * K, 40 * K
BODY_W, BODY_H = W - TXT_L - PAD, H - BODY_Y - BOT   # the .body content box, in pt
PGN_XY = (686.8 * K, 383.1 * K)
NAV_X = [464.5 * K, 545.2 * K, 627.4 * K]
SEP_X = [546.7 * K, 628.9 * K]

d = yaml.safe_load(DATA.read_text(encoding="utf-8"))
product_spec = d.get("product_spec") or {}
colors = d.get("colors") or []
p1 = d.get("part1") or {}
p2 = d.get("part2") or {}
# product_spec / colors are shared top-level with Part 1 & Part 3. Nested
# under part2 they would be silently ignored -- render empty with no sign
# the input was ever read.
misplaced = [k for k in ("product_spec", "colors") if k in p2]
if misplaced:
    raise SystemExit(
        f"輸入檔錯位：{'／'.join(misplaced)} 放在 part2 底下，但要放在最外層"
        "（與 Part 1／Part 3 共用）。把這幾個區塊往外移一層再跑。")

CH = p2.get("chapter") or {"index": 2, "zh": "Part 2", "en": ""}
NAV = p2.get("nav_sections") or []
L = p2.get("labels") or {}
SEC = L.get("sections") or {}
PH = L.get("placeholders") or {}
BRAND_L = L.get("brand_page") or {}
MB_L = L.get("mood_board_page") or {}
CS_L = L.get("color_story_page") or {}
LO_L = L.get("layout_options_page") or {}

brand = p2.get("brand") or {}
mood_boards = p2.get("mood_boards") or []
layout_options = p2.get("layout_options") or []
color_index_lead = p2.get("color_index_lead")

# Read-only reference back into Part 1's data -- mood_boards.linked_pitch
# resolves against part1.pitches[], and we reuse its own "提案" prefix
# label so the two decks don't invent two different names for one thing.
pitches = p1.get("pitches") or []
PIT_PREFIX = ((p1.get("labels") or {}).get("pitch_page") or {}).get("prefix", "")


def f(v):
    return f"{round(v, 2):g}"


def blank(key=""):
    """空槽的欄位名也是文案 —— 從 labels.placeholders 取，程式不留畫面用中文。"""
    return f'<span class="bk">{PH.get(key, "")}</span>'


def vals(items, key, n=2):
    """有值就印值，沒值就印 n 個空槽——空槽數量是版型的一部分，不是資料。"""
    if items:
        return "".join(f'<span class="vl2">{x}</span>' for x in items)
    return blank(key) * n


def bento_row_h(n, ratio, gap):
    """Row height solved from the available width, not fixed -- same rule
    SKILL.md's bento-box grid uses for H/G: 列高 = (可用寬 − 縫寬總合) ÷
    Σ(寬高比). `height:100%` + `aspect-ratio` alone lets the ratio win and
    silently push the row past the slide when N images don't fit at that
    height; solving for height first guarantees N × width + gaps == BODY_W.
    """
    return (BODY_W - gap * (n - 1)) / (n * ratio)


# 2.2 頁②③固定 5 張／3 張（SKILL.md 規格數字，不是資料驅動的清單長度）。
PHOTO_N, PHOTO_RATIO, PHOTO_GAP = 5, 4 / 5, 10.0
LAYOUT_N, LAYOUT_RATIO, LAYOUT_GAP = 3, 3 / 2, 14.0
PHOTO_ROW_H = bento_row_h(PHOTO_N, PHOTO_RATIO, PHOTO_GAP)
LAYOUT_ROW_H = bento_row_h(LAYOUT_N, LAYOUT_RATIO, LAYOUT_GAP)

# 2.5 每個方案的設計稿尺寸：垂直預算固定（扣掉方案說明文字帶與底部免責聲明），
# 寬度由高度＋比例反推，橫向靠左排（bento 規則：不撐滿，右側留白是正常的）。
LO_RATIO = 4 / 5
LO_META_H, LO_COL_GAP, LO_DISCLAIMER_RESERVE = 48.0, 9.0, 24.0
LOMOCK_H = BODY_H - LO_DISCLAIMER_RESERVE - LO_META_H - LO_COL_GAP
LOMOCK_W = LOMOCK_H * LO_RATIO


def resolve_pitch(v):
    """linked_pitch 可以是 part1.pitches[] 的索引，也可以直接是 headline 字串。"""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        if 0 <= v < len(pitches):
            headline = pitches[v].get("headline") or ""
            tag = f"{PIT_PREFIX} {v + 1:02d}".strip()
            return f"{tag}｜{headline}" if headline else tag
        return None
    return str(v)


def chrome(title, cur, n):
    cells = "".join(
        f'<div class="nv{" on" if i == cur else ""}" style="left:{f(x)}pt">{s}</div>'
        for i, (x, s) in enumerate(zip(NAV_X, NAV))
    )
    seps = "".join(f'<div class="nvsep" style="left:{f(x)}pt"></div>'
                   for x in SEP_X[:max(0, len(NAV) - 1)])
    ttl = (f'<div class="ttl" style="left:{f(TXT_L)}pt;top:{f(TITLE_Y)}pt">{title}</div>'
           if title else "")
    return ('<div class="bar"></div><div class="rule"></div>'
            f'<div class="crumb">{CH["zh"]}</div>{cells}{seps}{ttl}'
            f'<div class="pgn" style="left:{f(PGN_XY[0])}pt;top:{f(PGN_XY[1])}pt">{n:02d}</div>')


# ── 第一趟：組頁面，記錄每節起始頁次（目錄頁碼由此算，不寫死）────────
pages = []          # [(title, nav_idx, inner_html)]
toc = []            # [(節名, 起始頁次)]


def add(title, nav_idx, inner, toc_name=None):
    if toc_name:
        toc.append((toc_name, len(pages) + 1))
    pages.append((title, nav_idx, inner))


# nav 只有 3 格（跟 Part 1 一樣的物理限制）：Mood Board／色彩故事／排版方案。
# 2.1 品牌識別跟 Part 1 的 1.0 產品規格同待遇 -- 框架頁，不進 nav 高亮。
NAV_MB = 0 if len(NAV) > 0 else -1
NAV_CI = 1 if len(NAV) > 1 else -1
NAV_LO = 2 if len(NAV) > 2 else -1

add("", -1, "", None)   # 佔位：分隔頁，內容最後補（要等目錄算完）

# ── 2.1 品牌識別（固定 3 頁，框架頁，資料缺就出空槽）──────────────────
philo = brand.get("philosophy") or {}
steps = philo.get("steps") or []
n_steps = len(steps) or 4   # 步數由資料決定；空資料時用「四段式因果鏈」的預設格數畫骨架


def chain_html():
    parts = []
    for i in range(n_steps):
        val = steps[i] if i < len(steps) else None
        parts.append(
            f'<div class="cbox"><span class="cn">{i + 1:02d}</span>'
            f'<b>{val or blank("brand_step")}</b></div>')
        if i < n_steps - 1:
            parts.append('<div class="carrow">→</div>')
    return "".join(parts)


add(f'{SEC.get("brand", "")} － {BRAND_L.get("philosophy_title", "")}', -1,
    '<div class="brandpage">'
    f'<div class="chain">{chain_html()}</div>'
    f'<div class="bp-tagline"><i>{philo.get("tagline_en") or blank("brand_tagline_en")}</i>'
    f'<b>{philo.get("tagline_zh") or blank("brand_tagline_zh")}</b></div>'
    '</div>', SEC.get("brand"))

naming = brand.get("naming") or {}
metaphors = naming.get("metaphors") or []
add(f'{SEC.get("brand", "")} － {BRAND_L.get("naming_title", "")}', -1,
    '<div class="brandpage">'
    f'<div class="namehead"><b>{naming.get("name") or blank("brand_name")}</b>'
    f'<span>{naming.get("formula") or blank("brand_formula")}</span></div>'
    f'<div class="metaphors">{vals(metaphors, "brand_metaphor", 3)}</div>'
    '<div class="bp-slogan">'
    f'<i>{naming.get("slogan_en") or blank("brand_slogan_en")}</i>'
    f'<b>{naming.get("slogan_zh") or blank("brand_slogan_zh")}</b></div>'
    '</div>')

identity = brand.get("identity") or {}
tiers = [
    (BRAND_L.get("logotype_label", ""), identity.get("logotype")),
    (BRAND_L.get("identity_label", ""), identity.get("identity")),
    (BRAND_L.get("system_label", ""), identity.get("system")),
]
tier_html = "".join(
    f'<div class="tier"><span class="tn">{name}</span><p>{val or blank("brand_tier")}</p></div>'
    for name, val in tiers
)
add(f'{SEC.get("brand", "")} － {BRAND_L.get("identity_title", "")}', -1,
    '<div class="brandpage">'
    f'<div class="tiers">{tier_html}</div>'
    f'<div class="vocab"><label>{BRAND_L.get("vocabulary_label", "")}</label>'
    f'<span>{identity.get("design_vocabulary") or blank("brand_vocabulary")}</span></div>'
    f'<div class="bp-main-tagline">{brand.get("tagline") or blank("brand_tagline_main")}</div>'
    '</div>')

# ── 2.2 Mood Board（每方案固定 3 頁 ＋ Recap；空節不出頁）─────────────
if mood_boards:
    for i, mb in enumerate(mood_boards):
        mb = mb or {}
        keywords = mb.get("keywords") or []
        linked = resolve_pitch(mb.get("linked_pitch"))
        add(f'{SEC.get("mood_board", "")} {i + 1:02d}', NAV_MB,
            '<div class="mbvisual">'
            '<div class="mbl">'
            f'<div class="mbpill">{mb.get("code") or blank("mb_code")}</div>'
            f'<div class="mbname">{mb.get("name") or blank("mb_name")}</div>'
            f'<div class="mbsec"><label>{MB_L.get("concept_label", "")}</label>'
            f'<span>{mb.get("concept") or blank("mb_concept")}</span></div>'
            f'<div class="mbsec"><label>{MB_L.get("keywords_label", "")}</label>'
            f'<div class="mbkw">{vals(keywords, "mb_keyword", 3)}</div></div>'
            f'<div class="mbsec"><label>{MB_L.get("linked_pitch_label", "")}</label>'
            f'<span>{linked or blank("mb_linked_pitch")}</span></div>'
            '</div><div class="mbimg"></div></div>',
            SEC.get("mood_board") if i == 0 else None)

        add(f'{SEC.get("mood_board", "")} {i + 1:02d} － {MB_L.get("photo_style_title", "")}', NAV_MB,
            '<div class="mbphotos">'
            f'<div class="mbsec top"><label>{MB_L.get("photo_style_title", "")}</label>'
            f'<span>{mb.get("photo_style") or blank("mb_photo_style")}</span></div>'
            f'<div class="mbphotorow" style="height:{f(PHOTO_ROW_H)}pt">'
            + '<div class="mbph"></div>' * PHOTO_N + '</div>'
            '</div>')

        add(f'{SEC.get("mood_board", "")} {i + 1:02d} － {MB_L.get("layout_style_title", "")}', NAV_MB,
            '<div class="mblayout">'
            f'<div class="mbsec top"><label>{MB_L.get("layout_style_title", "")}</label>'
            f'<span>{mb.get("layout_style") or blank("mb_layout_style")}</span></div>'
            f'<div class="mblayoutrow" style="height:{f(LAYOUT_ROW_H)}pt">'
            + '<div class="mblo"></div>' * LAYOUT_N + '</div>'
            '</div>')

    rec = "".join(
        f'<tr><td>{(m or {}).get("code") or blank("mb_code")}</td>'
        f'<td>{(m or {}).get("name") or blank("mb_name")}</td>'
        f'<td>{(m or {}).get("concept") or blank("mb_concept")}</td>'
        f'<td>{resolve_pitch((m or {}).get("linked_pitch")) or blank("mb_linked_pitch")}</td></tr>'
        for m in mood_boards)
    add(SEC.get("mood_board_recap", ""), NAV_MB,
        f'<table class="recap"><tr>{"".join(f"<th>{h}</th>" for h in (MB_L.get("recap_head") or []))}</tr>{rec}</table>',
        SEC.get("mood_board_recap"))

# ── 2.3／2.4 色彩故事索引 ＋ 色彩情緒頁（色數由 colors[] 決定，空節不出頁）─
if colors:
    portraits = "".join(
        '<div class="cicard"><div class="ciimg"></div>'
        f'<i style="background:{c.get("hex") or "transparent"}"></i>'
        f'<span>{c.get("name_zh") or c.get("name_en") or blank("color_name")}</span></div>'
        for c in colors)
    add(SEC.get("color_index", ""), NAV_CI,
        f'<div class="cilead">{color_index_lead or blank("color_index_lead")}</div>'
        f'<div class="cigrid">{portraits}</div>', SEC.get("color_index"))

    for c in colors:
        hexv = c.get("hex") or ""
        cname = c.get("name_zh") or c.get("name_en") or ""
        add(f'{SEC.get("color_story", "")} － {cname}', NAV_CI,
            '<div class="cspage"><div class="cshero"></div>'
            '<div class="csbar">'
            '<div class="cshead">'
            f'<i style="background:{hexv or "transparent"}"></i>'
            f'<b>{hexv or blank("color_hex")}</b>'
            f'<span>{c.get("name_zh") or blank("color_name")}</span></div>'
            f'<div class="csttl">{c.get("story_title") or blank("color_story_title")}</div>'
            f'<div class="csrow"><label>{CS_L.get("mood_label", "")}</label>'
            f'<div class="csvals">{vals(c.get("mood"), "color_mood", 3)}</div></div>'
            f'<div class="csrow"><label>{CS_L.get("playlist_label", "")}</label>'
            f'<div class="csvals">{vals(c.get("playlist"), "color_playlist", 3)}</div></div>'
            f'<div class="csrow"><label>{CS_L.get("moment_label", "")}</label>'
            f'<div class="csvals">{vals(c.get("moment"), "color_moment", 3)}</div></div>'
            f'<div class="cstag">{c.get("closing_tag") or blank("color_closing_tag")}</div>'
            '<div class="csphotos"><div class="csph"></div><div class="csph"></div></div>'
            '</div></div>')

# ── 2.5 排版方案比較（每頁最多 3 個方案；方案數決定頁數；空節不出頁）───
if layout_options:
    PER_PAGE = 3
    n_lo_pages = math.ceil(len(layout_options) / PER_PAGE)
    for pi in range(n_lo_pages):
        chunk = layout_options[pi * PER_PAGE:(pi + 1) * PER_PAGE]
        cards = "".join(
            f'<div class="locard"><div class="lomock" style="width:{f(LOMOCK_W)}pt;height:{f(LOMOCK_H)}pt">'
            '<div class="lozone"></div></div>'
            f'<div class="lometa"><b>{lo.get("code") or blank("lo_code")}</b>'
            f'<span>{lo.get("note") or blank("lo_note")}</span>'
            f'<i>{LO_L.get("whitespace_label", "")}：{lo.get("whitespace_ratio") or blank("lo_whitespace")}</i>'
            '</div></div>' for lo in chunk)
        title = SEC.get("layout_options", "") if n_lo_pages == 1 else f'{SEC.get("layout_options", "")} {pi + 1:02d}'
        add(title, NAV_LO,
            f'<div class="lorow">{cards}</div>'
            f'<div class="lonote">{LO_L.get("disclaimer", "")}</div>',
            SEC.get("layout_options") if pi == 0 else None)

# ── 第二趟：分隔頁（目錄頁次此時才算得出來）＋ 渲染 ────────────────
toc_html = "".join(f'<li><span>{a}</span><em>{b:02d}</em></li>' for a, b in toc)
pages[0] = ("", -1,
            f'<div class="bignum">{CH["index"]}</div>'
            f'<div class="chname"><div class="zh">{CH["zh"]}</div>'
            f'<div class="en">{CH["en"]}</div></div>'
            f'<ul class="toc">{toc_html}</ul>')

html = []
for i, (title, nav_idx, inner) in enumerate(pages):
    if i == 0:
        html.append(f'<section class="slide sep">{inner}</section>')
    else:
        html.append(f'<section class="slide">{chrome(title, nav_idx, i + 1)}<div class="body">{inner}</div></section>')

# Palette restricted to SKILL.md's own colour table (§色票 — 不許改 hex):
# d97d35 / 262626 / f5f5f3 / ffffff / 6b6b6b / 888888 / e3e1dc / c9c6be /
# 9b978e / fbfaf8 / efede8. No value outside this set may appear below.
CSS = """
:root{--page:#f5f5f3;--card:#fff;--fg:#262626;--fg2:#6b6b6b;--accent:#d97d35;
--dark:#262626;--dark2:#c9c6be;--dark3:#9b978e;--imgnum:#888;--border:#e3e1dc;
--z1:#fff;--z2:#fbfaf8;--z3:#efede8;
--fd:Cambria,"Songti TC","Noto Serif TC",serif;
--fb:Calibri,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--dark);font-family:var(--fb);color:var(--fg);padding:18pt 0}
.slide{position:relative;width:__W__pt;height:__H__pt;background:var(--page);
overflow:hidden;margin:0 auto 18pt;box-shadow:0 2pt 12pt rgba(0,0,0,.4)}
.bar{position:absolute;left:0;top:0;width:__BAR__pt;height:100%;background:var(--dark)}
.rule{position:absolute;left:0;top:__RULE__pt;width:100%;height:.75pt;background:var(--dark)}
.crumb{position:absolute;left:__CRX__pt;top:__CRY__pt;font-size:11pt;color:var(--fg2)}
.nv{position:absolute;top:__CRY__pt;width:__NVW__pt;text-align:center;font-size:10pt;color:var(--border)}
.nv.on{color:var(--fg);font-weight:600}
.nvsep{position:absolute;top:__CRY__pt;width:.75pt;height:17pt;background:var(--border)}
.ttl{position:absolute;font-size:19pt;font-weight:600;letter-spacing:.02em}
.pgn{position:absolute;font-size:8pt;color:var(--imgnum)}
.body{position:absolute;left:__TXTL__pt;top:__BODY__pt;right:__PAD__pt;bottom:__BOT__pt}
.bk{display:inline-block;min-width:52pt;padding:2pt 8pt;border:.75pt dashed var(--border);
border-radius:3pt;background:var(--z2);color:var(--fg2);font-size:8.5pt;line-height:1.5}
.vl2{display:block;font-size:9.5pt;line-height:1.7;color:var(--fg2)}
.vl2::before{content:"• ";color:var(--accent)}
.sep{background:var(--dark);color:#fff}
.sep .bignum{position:absolute;left:__BIGX__pt;top:__BIGY__pt;font-family:var(--fb);
font-weight:700;font-size:__BIGF__pt;line-height:1;color:#fff}
.sep .chname{position:absolute;left:__SEPL__pt;top:__SEPT__pt}
.sep .zh{font-size:29pt;font-weight:600;letter-spacing:.08em}
.sep .en{font-size:29pt;font-weight:700;margin-top:6pt}
.sep .toc{position:absolute;left:__SEPL__pt;top:__TOCY__pt;list-style:none;width:__TOCW__pt}
.sep .toc li{display:flex;justify-content:space-between;align-items:baseline;
height:__TOCH__pt;border-bottom:.75pt solid rgba(255,255,255,.55);font-size:11pt}
.sep .toc em{font-style:normal;color:var(--accent)}
/* 2.1 Brand Identity */
.brandpage{position:relative;width:100%;height:100%;display:flex;flex-direction:column;
align-items:center;justify-content:center;text-align:center;gap:26pt}
.chain{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:12pt;max-width:100%}
.cbox{border:.75pt solid var(--border);border-radius:4pt;padding:14pt 20pt;min-width:110pt;
background:var(--z1)}
.cbox .cn{display:block;font-size:9pt;color:var(--accent);margin-bottom:6pt}
.cbox b{font-size:15pt;font-weight:600}
.carrow{font-size:16pt;color:var(--border)}
.bp-tagline{display:flex;flex-direction:column;gap:6pt}
.bp-tagline i{font-style:normal;font-family:var(--fd);font-size:14pt;color:var(--fg2)}
.bp-tagline b{font-size:20pt;font-weight:700}
.namehead{display:flex;flex-direction:column;gap:8pt}
.namehead b{font-size:26pt;font-weight:700}
.namehead span{font-size:12pt;color:var(--fg2)}
.metaphors{display:flex;flex-direction:column;gap:4pt;text-align:left;max-width:520pt}
.bp-slogan{display:flex;flex-direction:column;gap:6pt}
.bp-slogan i{font-style:normal;font-family:var(--fd);font-size:13pt;color:var(--fg2)}
.bp-slogan b{font-size:18pt;font-weight:700;color:var(--accent)}
.tiers{display:flex;gap:18pt;width:100%;justify-content:center}
.tier{flex:1;max-width:220pt;border:.75pt solid var(--border);border-radius:4pt;padding:16pt;
background:var(--z1);text-align:left}
.tier .tn{display:block;font-size:11pt;font-weight:700;color:var(--accent);margin-bottom:8pt;
letter-spacing:.1em}
.tier p{font-size:10pt;color:var(--fg2);line-height:1.6}
.vocab{display:flex;gap:10pt;align-items:baseline;justify-content:center}
.vocab label{font-size:9pt;color:var(--fg2);letter-spacing:.15em}
.vocab span{font-size:11pt}
.bp-main-tagline{font-family:var(--fd);font-size:16pt;color:var(--fg)}
/* 2.2 Mood Board */
.mbvisual{display:flex;gap:26pt;height:100%}
.mbl{flex:1;display:flex;flex-direction:column;justify-content:center;gap:11pt;align-items:flex-start}
.mbpill{background:var(--accent);color:#fff;font-size:9pt;padding:3pt 11pt;border-radius:9pt}
.mbname{font-size:20pt;font-weight:600}
.mbsec{margin-top:4pt}
.mbsec.top{margin-top:0}
.mbsec label{display:block;font-size:8pt;letter-spacing:.2em;color:var(--fg2);margin-bottom:5pt}
.mbkw{display:flex;flex-wrap:wrap;gap:8pt 14pt}
.mbimg{flex:0 0 auto;height:100%;background:var(--border);aspect-ratio:3/4}
.mbphotos,.mblayout{width:100%;height:100%;display:flex;flex-direction:column;gap:18pt}
.mbphotorow{display:flex;gap:10pt;align-items:center;justify-content:flex-start}
.mbph{height:100%;aspect-ratio:4/5;background:var(--border);flex:0 0 auto}
.mblayoutrow{display:flex;gap:14pt;align-items:center;justify-content:flex-start}
.mblo{height:100%;aspect-ratio:3/2;background:var(--border);flex:0 0 auto}
.recap{width:100%;border-collapse:collapse;font-size:10pt}
.recap th{background:var(--z3);padding:8pt 11pt;text-align:left;font-weight:600}
.recap td{padding:9pt 11pt;border-bottom:.5pt solid var(--border)}
/* 2.3 Color Story Index */
.cilead{font-size:14pt;font-weight:600;text-align:center;margin-bottom:20pt}
.cigrid{display:flex;flex-wrap:wrap;gap:16pt;justify-content:center}
.cicard{width:110pt;text-align:center}
.ciimg{width:100%;aspect-ratio:3/4;background:var(--border);margin-bottom:8pt}
.cicard i{display:inline-block;width:12pt;height:12pt;border-radius:50%;
border:.5pt solid var(--border);vertical-align:middle;margin-right:5pt}
.cicard span{font-size:9.5pt;color:var(--fg2)}
/* 2.4 Color Emotion Page */
.cspage{display:flex;gap:24pt;height:100%}
.cshero{flex:0 0 auto;height:100%;aspect-ratio:3/4;background:var(--border)}
.csbar{flex:1;display:flex;flex-direction:column;gap:10pt;justify-content:center;min-width:0}
.cshead{display:flex;align-items:center;gap:8pt;font-size:10pt;color:var(--fg2)}
.cshead i{display:inline-block;width:14pt;height:14pt;border-radius:50%;border:.5pt solid var(--border)}
.cshead b{font-weight:700;color:var(--fg)}
.csttl{font-family:var(--fd);font-size:17pt;font-weight:600;line-height:1.4}
.csrow{display:flex;gap:10pt;align-items:baseline}
.csrow label{flex:0 0 70pt;font-size:8pt;letter-spacing:.15em;color:var(--fg2)}
.csvals{display:flex;flex-wrap:wrap;gap:4pt 12pt}
.csvals .vl2{display:inline-block}
.cstag{margin-top:4pt;font-size:10pt;color:var(--accent);border-top:.75pt solid var(--border);
padding-top:10pt}
.csphotos{display:flex;gap:10pt;margin-top:6pt;height:64pt}
.csph{height:100%;aspect-ratio:1/1;background:var(--border);flex:0 0 auto}
/* 2.5 Layout Options Comparison */
.lorow{display:flex;gap:20pt;align-items:flex-start;justify-content:flex-start}
.locard{flex:0 0 auto;display:flex;flex-direction:column;gap:9pt}
.lomock{position:relative;background:var(--border)}
.lozone{position:absolute;left:10%;top:60%;right:10%;bottom:12%;
border:1pt dashed var(--dark3);background:rgba(155,151,142,.12)}
.lometa{display:flex;flex-direction:column;gap:4pt}
.lometa b{font-size:12pt;color:var(--accent)}
.lometa span{font-size:9.5pt;color:var(--fg2)}
.lometa i{font-style:normal;font-size:8.5pt;color:var(--fg2)}
.lonote{position:absolute;left:0;bottom:0;font-size:8pt;color:var(--fg2)}
"""
for k, v in {
    "__W__": f(W), "__H__": f(H), "__BAR__": f(BAR_W), "__RULE__": f(RULE_Y),
    "__PAD__": f(PAD), "__TXTL__": f(TXT_L), "__BODY__": f(BODY_Y), "__BOT__": f(BOT),
    "__CRX__": f(40.2 * K), "__CRY__": f(9.9 * K), "__NVW__": f(83.7 * K),
    "__BIGX__": f(522 * K), "__BIGY__": f(-41.4 * K), "__BIGF__": f(280 * K),
    "__SEPL__": f(28.7 * K), "__SEPT__": f(62.9 * K), "__TOCY__": f(225 * K),
    "__TOCW__": f(190.1 * K), "__TOCH__": f(27.7 * K),
}.items():
    CSS = CSS.replace(k, v)

OUT.write_text(
    '<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
    f'<title>{CH["zh"]}</title>\n<style>' + CSS + '</style>\n</head>\n<body>\n'
    + "\n".join(html) + '\n</body>\n</html>\n', encoding="utf-8")
print(f"{CH['zh']}：{len(pages)} 頁（Mood Board {len(mood_boards)}／色彩 {len(colors)}"
      f"／排版方案 {len(layout_options)}）→ {OUT.name}")
