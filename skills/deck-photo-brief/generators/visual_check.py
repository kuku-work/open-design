# -*- coding: utf-8 -*-
"""視覺產出驗收 — 把「看圖」從自律變成一個指令。

為什麼要這支：產出 HTML 之後我會直接報告「做好了」，因為 grep 沒殘留、頁數對、
程式沒報錯。但需求方每次都是**看畫面**發現問題——內部術語印上客戶頁、
圖表做成空白加說明、元素溢出版面。**文字方法驗不出視覺問題。**

這支做兩件事：
  1. 機械抓五類畫面問題（抓得到的就不要靠眼睛）
  2. 逐頁截圖並列出路徑，逼人真的去看（抓不到的靠眼睛，但要有圖可看）

跑法：
    python visual_check.py <頁面.html> [--ref <參考.html>] [--out <截圖目錄>]

退出碼 0 = 機械檢查全過（**不代表設計沒問題，那要人看圖**）。
"""
import argparse
import re
import sys
from pathlib import Path

# 不該出現在交付頁面上的東西：路徑、檔名、內部代號、來源標記、盤點術語
LEAK_PATTERNS = [
    (r"[A-Za-z]:\\\\|[A-Za-z]:/|\.\./|/tmp/", "檔案路徑"),
    (r"\.(?:yaml|yml|json|py|md|pdf)\b", "檔名副檔名"),
    (r"\[(?:SP|ST|SR)\]", "evidence 來源標記"),
    # 代號後常隔著名稱才接「型／版式」（M4 象限矩陣型），\s* 抓不到；
    # 用「非字母 + M/S + 數字 + 中文 2-8 字 + 型/版式」定位，避開產品名（MUCAPSO M1）
    (r"(?<![A-Za-z])[MS]\d{1,2}\s*[一-鿿]{2,8}(?:型|版式)", "版型代號"),
    (r"evidence|fixture|placeholder|TODO|_todo|待確認|盤點", "內部術語"),
]


def analyse(html: Path, ref: Path | None, out_dir: Path):
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    findings, shots = [], []

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1440, "height": 840}, device_scale_factor=1.5)
        pg.goto(html.resolve().as_uri())
        pg.wait_for_timeout(400)

        # Part 1 renders section.slide, Part 3 renders section.sheet.
        # Hard-coding one makes the other report "0 pages + PASS" --
        # finding nothing is not the same as finding nothing wrong.
        slides = pg.locator("section.slide, section.sheet")
        n = slides.count()
        for i in range(n):
            s = slides.nth(i)
            box = s.bounding_box()
            text = s.inner_text()

            # ① 內部資訊洩漏
            for pat, kind in LEAK_PATTERNS:
                for mt in re.finditer(pat, text, re.I):
                    findings.append((i + 1, "洩漏", f"{kind}：{mt.group()[:40]}"))

            # ② 元素溢出版面（會被 overflow:hidden 切掉，畫面上看是「缺一角」）
            over = s.evaluate(
                """el => {
                  const r = el.getBoundingClientRect();
                  return [...el.querySelectorAll('*')].filter(c => {
                    const b = c.getBoundingClientRect();
                    if (!b.width || !b.height) return false;
                    return b.right > r.right + 1 || b.left < r.left - 1
                        || b.bottom > r.bottom + 1 || b.top < r.top - 1;
                  }).map(c => (c.className || c.tagName) + '')
                    .filter(cn => !/bignum/.test(cn)).slice(0, 4);
                }"""
            )
            for cn in over:
                findings.append((i + 1, "溢出", f"元素超出版面：{cn[:40]}"))

            # ③ 內容佔比過低（大片留白＝多半是該放的資訊沒放，不是排版風格）
            ink = s.evaluate(
                """el => {
                  const r = el.getBoundingClientRect(); let a = 0;
                  el.querySelectorAll('*').forEach(c => {
                    const b = c.getBoundingClientRect();
                    if (b.width > 2 && b.height > 2 &&
                        (c.innerText?.trim() || getComputedStyle(c).backgroundColor !== 'rgba(0, 0, 0, 0)'))
                      a += Math.min(b.width, r.width) * Math.min(b.height, r.height);
                  });
                  return a / (r.width * r.height);
                }"""
            )
            if ink < 0.12:
                findings.append((i + 1, "留白", f"內容佔比僅 {ink:.0%}——先確認是不是該放的資訊沒放"))

            # ④ 空槽比例（完成度，不是錯誤，但要看得見）
            blanks = s.locator(".bk").count()
            if blanks:
                findings.append((i + 1, "空槽", f"{blanks} 格待填"))

            # ⑤ 截圖
            p = out_dir / f"p{i+1:02d}.png"
            s.screenshot(path=str(p))
            shots.append(p)

        if ref and ref.exists():
            rp = br.new_page(viewport={"width": 1440, "height": 840}, device_scale_factor=1.5)
            rp.goto(ref.resolve().as_uri())
            rp.wait_for_timeout(300)
            rs = rp.locator("section.slide")
            for i in range(min(rs.count(), 4)):
                rs.nth(i).screenshot(path=str(out_dir / f"ref-p{i+1:02d}.png"))
        br.close()
    return n, findings, shots


CHECKLIST = """
機械抓不到的，自己開圖看這五項（一頁一頁看，不要只看第一頁）：
  1. 這頁上有沒有只有我看得懂的字？（代號、來源標記、給自己的說明）
  2. 圖表是「畫出來了」還是「一塊空白加一段說明」？
  3. 資訊層級對嗎——最大的字是不是這頁最重要的訊息？
  4. 留白是設計還是缺內容？（算得出主體尺寸被鎖死＝設計；算不出＝缺內容）
  5. 跟參考檔並排看，哪裡是我自己加的？（自己加的東西要說得出理由）
"""


SELFTEST_INJECT = """
<section class="slide"><div class="body"><div class="slot">
<b>M4 象限矩陣型：雙軸象限</b>
<span>本案 evidence 無競品分析。[ST] 只到品牌與 TA</span>
<span>資料在 03-deck-data.yaml 的 _todo</span>
</div></div></section>
<section class="slide"><div class="body">
<div style="position:absolute;left:900pt;top:20pt;width:200pt">溢出版面的元素</div>
</div></section>
"""


def selftest(base: Path) -> int:
    """把已知問題注進一份乾淨樣本，確認檢查器真的抓得到。

    ⚠️ 為什麼要這個模式：用乾淨樣本跑出 PASS，證明的只是「不會誤報」，
    不是「抓得到」。這支的版型代號規則就是靠這個模式才發現從沒生效過——
    正規式假設代號後直接接「型」，實際是「M4 象限矩陣型」隔了四個字。
    驗證樣本必須真的含有被驗的東西。
    """
    import tempfile, shutil
    src = base.read_text(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="vcheck-"))
    try:
        sample = tmp / "dirty.html"
        sample.write_text(src.replace("</body>", SELFTEST_INJECT + "</body>"), encoding="utf-8")
        _, findings, _ = analyse(sample, None, tmp / "shots")
        kinds = {msg.split("：")[0] for _, k, msg in findings if k == "洩漏"}
        kinds |= {"元素溢出" for _, k, _ in findings if k == "溢出"}
        expect = {"版型代號", "evidence 來源標記", "內部術語", "檔名副檔名", "元素溢出"}
        miss = expect - kinds
        print("selftest 應抓到：", "、".join(sorted(expect)))
        print("selftest 實抓到：", "、".join(sorted(kinds)) or "（無）")
        if miss:
            print("  FAIL 漏掉：", "、".join(sorted(miss)))
            return 1
        print("  PASS 五類全部抓到")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path)
    ap.add_argument("--selftest", action="store_true",
                    help="注入已知問題驗證檢查器本身（不改動原檔）")
    ap.add_argument("--ref", type=Path, default=None, help="參考檔，會一併截前四頁供並排")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    out = a.out or a.html.parent / (a.html.stem + "-shots")

    if a.selftest:
        return selftest(a.html)

    n, findings, shots = analyse(a.html, a.ref, out)
    if n == 0:
        print(f"── {a.html.name}：FAIL 找不到任何頁面")
        print("     選擇器 section.slide / section.sheet 都沒命中。"
              "掃不到東西不等於乾淨——先確認頁面容器的 class 名。")
        return 1
    print(f"── {a.html.name}：{n} 頁，截圖在 {out}")

    hard = [f for f in findings if f[1] in ("洩漏", "溢出")]
    soft = [f for f in findings if f[1] == "留白"]
    slots = [f for f in findings if f[1] == "空槽"]

    for label, items in (("FAIL", hard), ("WARN", soft)):
        if items:
            print(f"  {label} {len(items)} 項")
            for pgno, kind, msg in items[:15]:
                print(f"       p{pgno:02d} [{kind}] {msg}")
    if not hard:
        print("  PASS 沒有內部資訊洩漏、沒有元素溢出版面")
    if slots:
        total = sum(int(m.split(" ")[0]) for _, _, m in slots)
        print(f"  INFO 空槽 {total} 格，分佈在 {len(slots)} 頁（完成度，不是錯誤）")

    print(CHECKLIST)
    print(f"截圖：{shots[0].parent}\\p01.png … p{n:02d}.png")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
