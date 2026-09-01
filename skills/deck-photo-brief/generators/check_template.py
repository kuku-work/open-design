# -*- coding: utf-8 -*-
"""模板化機械閘 — 生成器裡不准有寫死的畫面文案與內容數量。

為什麼要這支：模板的價值在「換一個產品只換資料」。但寫死一句
「MSRP / 建議售價」或一個 `PERSONA = [三個名字]` 不會報錯、畫面也照出，
**沒有任何訊號告訴你模板已經退化成一次性腳本**。這支就是那個訊號。

跑法：python check_template.py [生成器.py ...]
退出碼 0 = PASS；1 = 有寫死的東西。
"""
import ast
import re
import sys
from pathlib import Path

CJK = re.compile(r"[一-鿿]")
# 這些函式的引數是給開發者看的，不會上畫面
DEV_ONLY = {"print", "SystemExit", "assert", "dev"}


def scan(path: Path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    skip = set()          # 要排除的 (lineno, col)
    for node in ast.walk(tree):
        # docstring
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                skip.add((body[0].value.lineno, body[0].value.col_offset))
        # 開發者輸出
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in DEV_ONLY:
                # 開發者輸出裡的東西一律不算——字串、屬性存取都不算
                for sub in ast.walk(node):
                    ln = getattr(sub, "lineno", None)
                    if ln is not None:
                        skip.add((ln, sub.col_offset))

    hard_text, hard_list, fs_leak = [], [], []
    FS_ATTRS = {"name", "stem", "parent", "parts", "suffix"}
    for node in ast.walk(tree):
        # ① 畫面用的中文字串
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if (node.lineno, node.col_offset) in skip:
                continue
            if CJK.search(node.value):
                hard_text.append((node.lineno, node.value.strip()[:56]))
        # ② 模組層寫死的內容清單（換產品就錯的那種）
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
            for el in node.value.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str) and CJK.search(el.value):
                    tgt = node.targets[0]
                    hard_list.append((node.lineno, getattr(tgt, "id", "?")))
                    break
        # ③ 畫面值取自檔案系統（目錄名／檔名當內容用）
        if isinstance(node, ast.Attribute) and node.attr in FS_ATTRS:
            if (node.lineno, node.col_offset) not in skip:
                base = node.value
                nm = getattr(base, "id", None) or getattr(getattr(base, "func", None), "id", None)
                if nm and nm.isupper():        # DATA / OUT / BASE 這類 Path 常數
                    fs_leak.append((node.lineno, f"{nm}.{node.attr}"))
    return hard_text, hard_list, fs_leak


def main(paths):
    fail = False
    for p in paths:
        p = Path(p)
        text, lists, leak = scan(p)
        print(f"── {p.name}")
        if text:
            fail = True
            print(f"  FAIL 畫面文案寫死 {len(text)} 處（應移進 labels）：")
            for ln, s in text[:12]:
                print(f"       L{ln}: {s}")
        else:
            print("  PASS 沒有寫死的畫面文案")
        if lists:
            fail = True
            print(f"  FAIL 模組層寫死內容清單 {len(lists)} 處（數量應由資料決定）：")
            for ln, name in lists:
                print(f"       L{ln}: {name}")
        else:
            print("  PASS 沒有寫死的內容清單")
        if leak:
            fail = True
            print(f"  FAIL 畫面值取自檔案系統 {len(leak)} 處（會把欄位對不上變成靜默錯誤）：")
            for ln, expr in leak:
                print(f"       L{ln}: {expr}")
        else:
            print("  PASS 畫面值沒有取自檔案系統")
    return 1 if fail else 0


if __name__ == "__main__":
    args = sys.argv[1:] or [Path(__file__).with_name("gen_part1.py")]
    raise SystemExit(main(args))
