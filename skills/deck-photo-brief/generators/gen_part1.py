# -*- coding: utf-8 -*-
"""Part 1 行銷 Brief 生成器 — 版型固化、內容全部來自資料。

用法：
    python gen_part1.py                          # 跑空白範本，看版型長什麼樣
    python gen_part1.py <輸入.yaml> <輸出.html>    # 填好資料後出簡報

【固化在本程式，換產品不變】
  版面 960×540｜chrome 五件組（左邊條／頁首線／章名／導覽格／頁碼）
  分隔頁結構｜置中極簡頁的排法｜矩陣十字軸幾何｜SWOT 2×2｜文氏圖排列演算法
  人物誌的橫幅＋雙欄位表結構｜提案頁左文右圖｜Recap 表格

【全部來自資料，換產品要換】
  章名與節名｜產品名／定價／賣點／色票｜矩陣軸定義與四象限｜競品座標
  SWOT 四類條目｜persona（數量決定頁數）｜核心概念（數量決定圓數）
  提案（數量決定頁數與 Recap 行數）

【程式計算，不是寫死】
  頁碼與目錄頁次（依實際頁序）｜文氏圖圓心位置（依概念數）
  競品在矩陣裡的版面座標（由 -1..1 換算）｜每頁該不該出現（空節不出頁）

值為 null／空陣列 ＝ 本案沒有這筆資料 → 畫版型骨架＋空槽，不編值。
座標依據 00-evidence-analysis 的實測值；原檔 720×405 → 960×540，×4/3。
"""
import sys
import yaml
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
# 沒給參數就跑空白範本 —— 產出的是「版型長什麼樣」，每一格都是空槽。
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else SKILL / "input-template.yaml"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else SKILL / "examples" / "blank-template.html"

K = 4 / 3
W, H = 960.0, 540.0
BAR_W, RULE_Y = 28.2 * K, 36.2 * K
TXT_L, TITLE_Y = 52.2 * K, 52.1 * K
PGN_XY = (686.8 * K, 383.1 * K)
NAV_X = [464.5 * K, 545.2 * K, 627.4 * K]
SEP_X = [546.7 * K, 628.9 * K]

d = yaml.safe_load(DATA.read_text(encoding="utf-8"))
spec = d.get("product_spec") or {}
colors = d.get("colors") or []
p1 = d.get("part1") or {}
# Both are read from the top level and shared with Part 3. Nested under
# part1 they would be silently ignored -- the deck would render with empty
# slots and give no sign the input was ever read.
misplaced = [k for k in ("product_spec", "colors") if k in p1]
if misplaced:
    raise SystemExit(
        f"輸入檔錯位：{'／'.join(misplaced)} 放在 part1 底下，但要放在最外層"
        "（與 Part 3 共用）。把這幾個區塊往外移一層再跑。")
CH = p1.get("chapter") or {"index": 1, "zh": "Part 1", "en": ""}
# ⚠️ key 用 index 不用 no —— YAML 1.1 會把 no 解析成布林 False（Norway problem）
NAV = p1.get("nav_sections") or []
L = p1.get("labels") or {}
SEC = L.get("sections") or {}
PH = L.get("placeholders") or {}
SPEC_L = L.get("spec_page") or {}
PER_L = L.get("persona_page") or {}
PIT_L = L.get("pitch_page") or {}
SWOT_L = L.get("swot_quadrants") or []
# ⚠️ 不設 fallback。資料沒有產品名就顯示空槽——拿目錄名／檔名湊會把
#    「欄位對不上」這種錯誤變成靜默的（graceful ≠ silent）。
PRODUCT_NAME = p1.get("product_name")   # part1 自己的；不吃 project（那是拍攝計畫的專案欄位）


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


ORDER = p1.get("sections_order") or ["spec", "matrix", "swot", "audience", "comms", "pitch"]

add("", -1, "", None)   # 佔位：分隔頁，內容最後補（要等目錄算完）

# 產品規格：定價／定位（置中極簡，一頁一訊息）
if "spec" in ORDER:
  add("", -1,
      '<div class="center">'
      f'<div class="c-name">{PRODUCT_NAME or blank("product")}</div>'
      f'<div class="c-main">{SPEC_L.get("price_title","")}　{spec.get("price") or blank("price")}</div>'
      f'<div class="c-sub">{spec.get("price_positioning") or blank("price_positioning")}</div>'
      + (f'<div class="c-quote">{spec["positioning_statement"]}</div>'
         if spec.get("positioning_statement") else "")
      + '</div>', SEC.get("spec"))

# 產品規格：賣點＋色票（賣點數與色數都由資料決定）
feats = spec.get("features") or []
feat_html = "".join(
    ('<span class="fx">｜</span>' if i else "")
      + f'<div class="fw"><b>{x["keyword"]}</b><span>{x.get("spec") or ""}</span></div>'
      for i, x in enumerate(feats)
) or blank("features")
# Headline size is computed, not fixed: more items -- or one long keyword --
# would otherwise push the row past the safe area.
feat_widest = max((len(x.get("keyword") or "") for x in feats), default=0)
# Floor at 14pt: below that, let word-break wrap the text rather than
# shrinking it into something nobody can read.
feat_size = max(14.0, min(38.0, 300.0 / max(len(feats), 1), 260.0 / max(feat_widest, 1)))
sw_html = "".join(
      f'<div class="sw"><i style="background:{c["hex"]}"></i>'
      f'<span>{c.get("name_zh") or c.get("name_en")}</span></div>' for c in colors
)
if "spec" in ORDER:
  add("", -1,
      '<div class="center">'
      f'<div class="c-lead">{SPEC_L.get("features_lead","").replace("{n}", str(len(feats)))}</div>'
      f'<div class="frow" style="--fsz:{f(feat_size)}pt">{feat_html}</div>'
      + (f'<div class="c-lead sp">{SPEC_L.get("colors_lead","").replace("{n}", str(len(colors)))}</div><div class="swrow">{sw_html}</div>'
       if colors else "")
        + '</div>')

# 定位矩陣：軸定義、四象限、競品座標全部資料驅動
m = p1.get("positioning_matrix") or {}
av, ah = m.get("axis_v") or {}, m.get("axis_h") or {}
qd = m.get("quadrants") or {}
quad_html = "".join(
    f'<div class="qd {k}">{vals(qd.get(k), "quadrant")}</div>'
    for k in ("tl", "tr", "bl", "br")
)
comp_html = "".join(
    f'<div class="cmp" style="left:{f(50 + c["x"] * 40)}%;top:{f(50 - c["y"] * 40)}%">{c["name"]}</div>'
    for c in (m.get("competitors") or [])
)
own = m.get("own")
own_html = (f'<div class="ownmark" style="left:{f(50 + own["x"] * 40)}%;'
            f'top:{f(50 - own["y"] * 40)}%">{PRODUCT_NAME or blank("product")}</div>'
            ) if own else ''
add(SEC.get("matrix",""), 0 if NAV else -1,
    '<div class="matrix">'
    '<div class="ax-h"></div><div class="ax-v"></div>'
    '<div class="ah-tip"></div><div class="av-tip"></div>'
    f'<div class="ax-lb top">{av.get("top") or blank("axis")}</div>'
    f'<div class="ax-lb bottom">{av.get("bottom") or blank("axis")}</div>'
    f'<div class="ax-lb left">{ah.get("left") or blank("axis")}</div>'
    f'<div class="ax-lb right">{ah.get("right") or blank("axis")}</div>'
    f'<div class="ax-tag t">{av.get("tag") or blank("axis_tag")}</div>'
    f'<div class="ax-tag l">{ah.get("tag") or blank("axis_tag")}</div>'
    f'{quad_html}{comp_html}{own_html}</div>', SEC.get("matrix"))

# SWOT：四類固定（框架本身就是四格），條目由資料決定
sw = p1.get("swot") or {}
SW = [(q.get("zh", ""), q.get("en", ""), q.get("key")) for q in SWOT_L]
sc = "".join(
    f'<div class="sc"><div class="sh">{zh}<em>{en}</em></div>'
    f'<div class="sb">{vals(sw.get(key), "swot_item", 3)}</div></div>'
    for zh, en, key in SW
)
add(SEC.get("swot",""), 1 if len(NAV) > 1 else -1, f'<div class="swot">{sc}</div>', SEC.get("swot"))

# 受眾輪廓：persona 數量決定頁數
personas = p1.get("personas") or []
if personas:
    cards = "".join(
        f'<div class="pcard"><div class="pimg"></div>'
        f'<b>{p.get("name") or blank("persona_name")}</b>'
        f'<span>{p.get("narrative") or blank("persona_narrative")}</span></div>' for p in personas
    )
    add(SEC.get("audience",""), 2 if len(NAV) > 2 else -1,
        f'<div class="prow">{cards}</div>', SEC.get("audience"))
    for i, p in enumerate(personas):
        def tbl(rows):
            # [{label, value}] rather than {label: value}: the row label is
            # display text like any other, so it lives in the data and can be
            # renamed without touching every persona.
            return "".join(
                f'<tr><th>{r.get("label") or ""}</th>'
                f'<td>{r.get("value") or blank("")}</td></tr>'
                for r in (rows or [])
            )
        add(f'{SEC.get("persona","")} {i+1:02d} － {p.get("name") or ""}', 2 if len(NAV) > 2 else -1,
            '<div class="phero"><div class="pimg lg"></div><div class="pmeta">'
            f'<b>{p.get("title") or blank("persona_title")}</b>'
            f'<i>{p.get("person") or blank("persona_person")}</i>'
            f'<p>{p.get("narrative") or blank("persona_story")}</p></div></div>'
            '<div class="ptables">'
            f'<div class="pt"><div class="ptag">{PER_L.get("background","")}</div><table>{tbl(p.get("background"))}</table></div>'
            f'<div class="pt"><div class="ptag">{PER_L.get("consumer","")}</div><table>{tbl(p.get("consumer"))}</table></div>'
            '</div>')

# 市場溝通主軸：圓的數量與位置由概念數計算
axes = p1.get("communication_axes") or []
n = len(axes) or 3
POS = {1: [(50, 50)], 2: [(33, 50), (67, 50)],
       3: [(50, 30), (34, 62), (66, 62)],
       4: [(35, 32), (65, 32), (35, 66), (65, 66)]}
pos = POS.get(n, [(50 + 30 * __import__("math").cos(2 * 3.14159 * i / n - 1.5708),
                   50 + 30 * __import__("math").sin(2 * 3.14159 * i / n - 1.5708))
                  for i in range(n)])
circles = "".join(
    f'<div class="vc" style="left:{f(x)}%;top:{f(y)}%"></div>' for x, y in pos)
labels = "".join(
    f'<div class="vl" style="left:{f(x)}%;top:{f(y)}%">'
    f'{(axes[i] if i < len(axes) else None) or blank("comms_axis")}</div>'
    for i, (x, y) in enumerate(pos))
add(SEC.get("comms",""), -1, f'<div class="venn">{circles}{labels}</div>', SEC.get("comms"))

# 產品切角：提案數決定頁數；沒有提案就出一頁版型示意
pitches = p1.get("pitches") or [None]
for i, p in enumerate(pitches):
    p = p or {}
    add(SEC.get("pitch",""), -1,
        '<div class="pitch"><div class="pl">'
        f'<div class="pill">{PIT_L.get("prefix","")} {i+1:02d}</div>'
        f'<div class="ph">{p.get("headline") or blank("pitch_headline")}</div>'
        f'<div class="pn">{p.get("product_name") or blank("pitch_product")}</div>'
        f'<div class="ps">{p.get("subtitle") or blank("pitch_subtitle")}</div>'
        f'<div class="pc"><label>{PIT_L.get("concept_label","")}</label>'
        f'{p.get("concept") or blank("pitch_concept")}</div></div>'
        '<div class="pr"></div></div>',
        SEC.get("pitch") if i == 0 else None)
rec = "".join(
    f'<tr><td>{PIT_L.get("prefix","")} {i+1:02d}</td>'
    f'<td>{(x or {}).get("headline") or blank("recap_headline")}</td>'
    f'<td>{(x or {}).get("subtitle") or blank("recap_subtitle")}</td></tr>'
    for i, x in enumerate(pitches))
add(SEC.get("pitch_recap",""), -1,
    f'<table class="recap"><tr>{"".join(f"<th>{h}</th>" for h in (PIT_L.get("recap_head") or []))}</tr>{rec}</table>')

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
        wrap = inner if inner.startswith('<div class="center"') else f'<div class="body">{inner}</div>'
        html.append(f'<section class="slide">{chrome(title, nav_idx, i + 1)}{wrap}</section>')

CSS = """
:root{--bg:#fff;--fg:#262626;--fg2:#6b6b6b;--muted:#9a9a9a;--accent:#d97d35;
--dark:#2f3a38;--line:#d9d9d9;--soft:#f2f0ec;
--fd:Cambria,"Songti TC","Noto Serif TC",serif;
--fb:Calibri,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#4a4a48;font-family:var(--fb);color:var(--fg);padding:18pt 0}
.slide{position:relative;width:__W__pt;height:__H__pt;background:var(--bg);
overflow:hidden;margin:0 auto 18pt;box-shadow:0 2pt 12pt rgba(0,0,0,.4)}
.bar{position:absolute;left:0;top:0;width:__BAR__pt;height:100%;background:var(--dark)}
.rule{position:absolute;left:0;top:__RULE__pt;width:100%;height:.75pt;background:var(--dark)}
.crumb{position:absolute;left:__CRX__pt;top:__CRY__pt;font-size:11pt;color:#595959}
.nv{position:absolute;top:__CRY__pt;width:__NVW__pt;text-align:center;font-size:10pt;color:var(--line)}
.nv.on{color:#5e5e5e;font-weight:600}
.nvsep{position:absolute;top:__CRY__pt;width:.75pt;height:17pt;background:var(--line)}
.ttl{position:absolute;font-size:19pt;font-weight:600;letter-spacing:.02em}
.pgn{position:absolute;font-size:8pt;color:var(--muted)}
.body{position:absolute;left:__TXTL__pt;top:__BODY__pt;right:__PAD__pt;bottom:__BOT__pt}
.bk{display:inline-block;min-width:52pt;padding:2pt 8pt;border:.75pt dashed #c9c5bd;
border-radius:3pt;background:#fbfaf8;color:#b3aea4;font-size:8.5pt;line-height:1.5}
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
.center{position:absolute;inset:0;display:flex;flex-direction:column;
align-items:center;justify-content:center;text-align:center}
.c-name{font-size:10pt;letter-spacing:.34em;color:var(--muted);margin-bottom:20pt}
.c-main{font-size:26pt;font-weight:700}
.c-sub{font-size:14pt;color:var(--accent);margin-top:10pt}
.c-quote{margin-top:52pt;font-family:var(--fd);font-size:17pt;color:var(--dark)}
.c-lead{font-size:13pt;font-weight:600}
.c-lead.sp{margin-top:56pt}
.frow{display:flex;flex-wrap:wrap;justify-content:center;align-items:baseline;gap:14pt 26pt;margin-top:22pt;max-width:100%}
.fx{font-size:34pt;color:var(--line);font-weight:200}
.fw b{display:block;font-size:var(--fsz,38pt);font-weight:400;color:var(--accent);letter-spacing:.06em;word-break:break-word}
.fw span{display:block;font-size:11pt;color:var(--fg2);margin-top:8pt}
.swrow{display:flex;gap:20pt;margin-top:18pt}
.sw{text-align:center;font-size:9pt;color:var(--fg2)}
.sw i{display:block;width:26pt;height:26pt;border-radius:50%;margin:0 auto 6pt;
border:.5pt solid var(--line)}
.matrix{position:relative;width:100%;height:100%}
.ax-h{position:absolute;left:8%;right:8%;top:50%;height:.9pt;background:#4a4a48}
.ax-v{position:absolute;top:6%;bottom:6%;left:50%;width:.9pt;background:#4a4a48}
.ah-tip{position:absolute;right:8%;top:50%;transform:translate(50%,-50%);
border-left:6pt solid #4a4a48;border-top:3.5pt solid transparent;border-bottom:3.5pt solid transparent}
.av-tip{position:absolute;left:50%;top:6%;transform:translate(-50%,-50%);
border-bottom:6pt solid #4a4a48;border-left:3.5pt solid transparent;border-right:3.5pt solid transparent}
.ax-lb{position:absolute;font-size:12pt;font-weight:600}
.ax-lb.top{left:50%;top:0;transform:translate(-50%,-130%)}
.ax-lb.bottom{left:50%;bottom:0;transform:translate(-50%,130%)}
.ax-lb.left{left:0;top:50%;transform:translateY(-50%)}
.ax-lb.right{right:0;top:50%;transform:translateY(-50%)}
.ax-tag{position:absolute;background:#7f7f7f;color:#fff;font-size:9pt;
padding:4pt 9pt;line-height:1.3;text-align:center}
.ax-tag.t{left:50%;top:-11%;transform:translateX(-50%)}
.ax-tag.l{left:-3%;top:37%}
.qd{position:absolute;width:31%;display:flex;flex-direction:column;gap:4pt}
.qd.tl{left:11%;top:2%}.qd.tr{right:1%;top:2%}
.qd.bl{left:11%;bottom:2%}.qd.br{right:1%;bottom:2%}
.cmp{position:absolute;transform:translate(-50%,-50%);font-size:10pt;font-weight:600;color:#4a4a48}
.ownmark{position:absolute;transform:translate(-50%,-50%);border:1pt solid var(--accent);
color:var(--accent);font-size:9pt;padding:5pt 11pt;border-radius:2pt;white-space:nowrap}
.swot{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;
gap:14pt;width:100%;height:100%}
.sc{border:.75pt solid var(--line);display:flex;flex-direction:column}
.sh{background:var(--soft);padding:7pt 11pt;font-size:11pt;font-weight:600}
.sh em{font-style:normal;font-size:8.5pt;color:var(--muted);margin-left:7pt}
.sb{padding:11pt;display:flex;flex-direction:column;gap:5pt;align-items:flex-start}
.prow{display:flex;gap:21pt;height:100%;align-items:center}
.pcard{flex:1;border:.75pt solid var(--line);padding:18pt;text-align:center}
.pimg{width:84pt;height:84pt;border-radius:50%;background:var(--soft);margin:0 auto 12pt}
.pimg.lg{width:96pt;height:96pt;margin:0 16pt 0 0;flex:0 0 auto}
.pcard b{display:block;font-size:14pt;margin-bottom:9pt}
.phero{display:flex;align-items:center;background:#f6f8fa;padding:14pt 16pt;border-radius:6pt}
.pmeta b{display:block;font-size:12pt}
.pmeta i{display:block;font-style:normal;margin:5pt 0 8pt}
.ptables{display:flex;gap:26pt;margin-top:16pt}
.pt{flex:1;display:flex;align-items:flex-start;gap:8pt}
.ptag{writing-mode:vertical-rl;background:var(--soft);color:var(--fg2);
font-size:9pt;padding:9pt 4pt;border-radius:3pt;letter-spacing:.15em}
.pt table{flex:1;border-collapse:collapse;font-size:9pt}
.pt th{background:#e8eef3;font-weight:600;padding:5pt 9pt;white-space:nowrap;
border:.5pt solid #fff;text-align:center}
.pt td{padding:4pt 9pt;border-bottom:.5pt solid var(--line)}
.venn{position:relative;width:100%;height:100%}
.vc{position:absolute;transform:translate(-50%,-50%);border:1pt solid var(--accent);
border-radius:50%;width:172pt;height:172pt;opacity:.55}
.vl{position:absolute;transform:translate(-50%,-50%);font-size:9.5pt;text-align:center}
.pitch{display:flex;gap:26pt;height:100%}
.pl{flex:1;display:flex;flex-direction:column;justify-content:center;gap:9pt;align-items:flex-start}
.pill{background:var(--accent);color:#fff;font-size:9pt;padding:3pt 11pt;border-radius:9pt}
.ph{font-size:20pt;font-weight:600}
.pn{border-bottom:1.5pt solid var(--accent);padding-bottom:3pt}
.pc{margin-top:9pt}
.pc label{display:block;font-size:8pt;letter-spacing:.2em;color:var(--muted);margin-bottom:5pt}
.pr{width:38%;background:var(--soft);border-radius:4pt}
.recap{width:100%;border-collapse:collapse;font-size:10pt}
.recap th{background:var(--soft);padding:8pt 11pt;text-align:left;font-weight:600}
.recap td{padding:9pt 11pt;border-bottom:.5pt solid var(--line)}
"""
for k, v in {
    "__W__": f(W), "__H__": f(H), "__BAR__": f(BAR_W), "__RULE__": f(RULE_Y),
    "__PAD__": f(52.2 * K), "__TXTL__": f(TXT_L), "__BODY__": f(96 * K), "__BOT__": f(40 * K),
    "__CRX__": f(40.2 * K), "__CRY__": f(9.9 * K), "__NVW__": f(83.7 * K),
    "__BIGX__": f(522 * K), "__BIGY__": f(-41.4 * K), "__BIGF__": f(280 * K),
    "__SEPL__": f(28.7 * K), "__SEPT__": f(62.9 * K), "__TOCY__": f(225 * K),
    "__TOCW__": f(190.1 * K), "__TOCH__": f(27.7 * K),
}.items():
    CSS = CSS.replace(k, v)

OUT.write_text(
    '<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
    f'<title>{PRODUCT_NAME or ""} · {CH["zh"]}</title>\n<style>' + CSS + '</style>\n</head>\n<body>\n'
    + "\n".join(html) + '\n</body>\n</html>\n', encoding="utf-8")
print(f"{PRODUCT_NAME or DATA.stem}：{len(pages)} 頁（persona {len(personas)}／提案 {len(p1.get('pitches') or [])}"
      f"／概念 {len(axes)}／競品 {len(m.get('competitors') or [])}）→ {OUT.name}")
