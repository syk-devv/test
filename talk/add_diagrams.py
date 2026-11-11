"""v1 해설 페이지에 다이어그램(SVG)을 넣어 v2를 만든다.

사용법: python talk/add_diagrams.py
입력: talk/v1/*.html  출력: talk/v2/*.html
그림의 수치는 모두 페이지 본문(= fusion_select.json)에 이미 적힌 값만 쓴다.
'예시'라고 적힌 그림만 설명용 가상 값이다.
"""
import math
import re
from pathlib import Path

ROOT = Path(__file__).parent
SRC, OUT = ROOT / "v1", ROOT / "v2"
PAGES = {"eli5": "eli5_v1.html", "eli15": "eli15_v1.html",
         "eli20": "eli20_v1.html", "ai": "eli_ai신입_v1.html"}

EXTRA_CSS = """
:root{--c-bm:#0066cc;--c-vec:#e8710a;--c-gain:#1e8e3e;--c-tie:#aeaeb2;--c-loss:#d70015;--c-fuse:#5856d6;--hl:#fff4d6;--hl-line:#d4a017;--box:#e8f0fb}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--c-bm:#4da3ff;--c-vec:#ff9f45;--c-gain:#30d158;--c-tie:#636366;--c-loss:#ff453a;--c-fuse:#8e8cff;--hl:#4a3b10;--hl-line:#e0b23a;--box:#1d3150}}
:root[data-theme="dark"]{--c-bm:#4da3ff;--c-vec:#ff9f45;--c-gain:#30d158;--c-tie:#636366;--c-loss:#ff453a;--c-fuse:#8e8cff;--hl:#4a3b10;--hl-line:#e0b23a;--box:#1d3150}
figure{margin:14px 0 8px}figcaption{font-size:13px;color:var(--mut);margin-top:2px}
.f-bm{fill:var(--c-bm)}.f-vec{fill:var(--c-vec)}.f-gain{fill:var(--c-gain)}.f-tie{fill:var(--c-tie)}.f-loss{fill:var(--c-loss)}.f-fuse{fill:var(--c-fuse)}
.f-card{fill:var(--card)}.f-soft{fill:var(--soft)}.f-box{fill:var(--box)}.f-hl{fill:var(--hl)}.f-ink{fill:var(--ink)}.f-hair{fill:var(--hair)}
.s-ink{stroke:var(--ink)}.s-hair{stroke:var(--hair)}.s-mut{stroke:var(--mut)}.s-bm{stroke:var(--c-bm)}.s-vec{stroke:var(--c-vec)}.s-fuse{stroke:var(--c-fuse)}.s-tie{stroke:var(--c-tie)}.s-loss{stroke:var(--c-loss)}.s-gain{stroke:var(--c-gain)}.s-hl{stroke:var(--hl-line)}
.t.m{font-size:13px}.t.l{font-size:16px}.t.xl{font-size:22px;font-weight:700}
"""

GAIN, TIE, LOSS = "g", "t", "l"
CLS = {GAIN: "f-gain", TIE: "f-tie", LOSS: "f-loss"}
SYM = {GAIN: "▲", TIE: "–", LOSS: "▼"}

# 6개 조합 판정(덱 2장 그림과 같은 순서). ⑤ = 위키 · e5-small
VERDICT = {
    "RRF k=60": [GAIN, TIE, TIE, GAIN, LOSS, TIE],
    "RRF k 변경": [GAIN, TIE, TIE, GAIN, TIE, GAIN],
    "가중 RRF": [GAIN, TIE, GAIN, GAIN, TIE, GAIN],
    "점수 결합": [GAIN, GAIN, GAIN, GAIN, TIE, GAIN],
}
CIRC = "①②③④⑤⑥"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def T(x, y, s, cls="t", anchor="start", extra=""):
    a = "" if anchor == "start" else f' text-anchor="{anchor}"'
    return f'<text x="{x:.1f}" y="{y:.1f}"{a} class="{cls}"{extra}>{esc(s)}</text>'


def R(x, y, w, h, cls, rx=6, extra=""):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w,0):.1f}" height="{h:.1f}" rx="{rx}" class="{cls}"{extra}/>'


def L(x1, y1, x2, y2, cls="s-ink", w=2, extra=""):
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}" stroke-width="{w}"{extra}/>'


def arrow(x1, y1, x2, y2, cls="s-ink", fcls="f-ink", w=2):
    a = math.atan2(y2 - y1, x2 - x1)
    h = 8
    p1 = (x2 - h * math.cos(a - 0.45), y2 - h * math.sin(a - 0.45))
    p2 = (x2 - h * math.cos(a + 0.45), y2 - h * math.sin(a + 0.45))
    bx, by = x2 - h * 0.8 * math.cos(a), y2 - h * 0.8 * math.sin(a)
    return (L(x1, y1, bx, by, cls, w) +
            f'<path d="M{x2:.1f},{y2:.1f} L{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f} z" class="{fcls}"/>')


def svg(w, h, body, label):
    return f'<svg viewBox="0 0 {w} {h}" class="pic" role="img" aria-label="{esc(label)}">{body}</svg>'


def fig(s, cap):
    return f'<figure>{s}<figcaption>{esc(cap)}</figcaption></figure>'


def legend(x, y, items):
    out = ""
    for cls, lab in items:
        out += R(x, y - 11, 12, 12, cls, 3) + T(x + 17, y, lab, "t m")
        x += 34 + len(lab) * 12
    return out


# ---------- 그림 모음 ----------

def pipeline(labels=("질문", "BM25", "단어가 겹치는 문서", "벡터 검색", "뜻이 비슷한 문서",
                     "결합", "RRF · 가중 RRF", "· 점수 결합", "top-10", "→ 언어 모델")):
    q, b1, b2, v1, v2, f1, f2, f3, o1, o2 = labels
    b = R(6, 88, 70, 48, "f-soft", 10) + T(41, 117, q, "t b", "middle")
    b += R(112, 22, 150, 64, "f-bm", 10) + T(187, 48, b1 + " top-100", "t b w", "middle") + T(187, 70, b2, "t w m", "middle")
    b += R(112, 138, 150, 64, "f-vec", 10) + T(187, 164, v1 + " top-100", "t b w", "middle") + T(187, 186, v2, "t w m", "middle")
    b += R(300, 74, 132, 76, "f-fuse", 10) + T(366, 100, f1, "t b w", "middle") + T(366, 120, f2, "t w m", "middle") + T(366, 138, f3, "t w m", "middle")
    b += R(462, 88, 92, 48, "f-soft", 10) + T(508, 108, o1, "t b", "middle") + T(508, 127, o2, "t m", "middle")
    b += arrow(76, 106, 110, 60) + arrow(76, 118, 110, 165)
    b += arrow(262, 54, 298, 96) + arrow(262, 170, 298, 128) + arrow(432, 112, 460, 112)
    return svg(560, 214, b, "질문이 두 검색기를 거쳐 결합된 뒤 top-10이 언어 모델로 가는 흐름")


def verdict_grid(methods, names=None, params=None, note=True):
    names = names or methods
    cw, x0, top = 52, 140, 50
    rows = len(methods) + (len(params) if params else 0)
    h = top + rows * 42 + (34 if note else 8)
    b = legend(0, 16, [("f-gain", "이득 ▲"), ("f-tie", "구분 안 됨 –"), ("f-loss", "손해 ▼")])
    for j in range(6):
        b += T(x0 + j * cw + cw / 2 - 2, top - 8, CIRC[j], "t b", "middle")
    b += T(462, top - 8, "이득·구분·손해", "t s")
    y = top
    for m, nm in zip(methods, names):
        v = VERDICT[m]
        b += T(0, y + 25, nm, "t b")
        for j, s in enumerate(v):
            b += R(x0 + j * cw, y, cw - 6, 34, CLS[s], 6) + T(x0 + j * cw + cw / 2 - 3, y + 23, SYM[s], "t b w", "middle")
        b += T(470, y + 23, f"{v.count(GAIN)} · {v.count(TIE)} · {v.count(LOSS)}", "t b")
        y += 42
    for lab, vals in (params or []):
        b += T(0, y + 22, lab, "t m")
        for j, s in enumerate(vals):
            b += T(x0 + j * cw + cw / 2 - 3, y + 22, s, "t", "middle")
        y += 42
    if note:
        b += T(0, y + 14, "⑤ = 위키 · e5-small (RRF k=60이 유일하게 손해였던 조합)", "t s")
    return svg(560, h, b, "결합 방식별 6개 조합 판정")


def stacked(rows, total, legend_items=None, cap_total=None):
    """rows: (label, [(value, cls), ...])"""
    x0, W = 150, 390
    top = 34 if legend_items else 8
    b = legend(0, 16, legend_items) if legend_items else ""
    y = top
    for lab, segs in rows:
        b += T(0, y + 23, lab, "t b")
        x = x0
        for v, cls in segs:
            w = W * v / total
            if v:
                b += R(x, y, w - 2, 34, cls, 4)
                if w > 22:
                    b += T(x + w / 2 - 1, y + 23, str(v), "t b w", "middle")
            x += w
        y += 44
    if cap_total:
        b += T(x0, y + 8, cap_total, "t s")
        y += 14
    return svg(560, y + 4, b, "누적 막대")


def ranges(rows, lo, hi, ticks, unit_fmt="{:+.3f}", zero=True, tick_fmt=None):
    """rows: (label, a, b, cls) — 구간 a~b를 막대로."""
    x0, x1 = 170, 540
    X = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    tick_fmt = tick_fmt or unit_fmt
    h = 20 + len(rows) * 52 + 30
    b = ""
    for t in ticks:
        b += L(X(t), 12, X(t), h - 26, "s-hair", 1) + T(X(t), h - 8, tick_fmt.format(t) if t else "0", "t s", "middle")
    if zero and lo < 0 < hi or lo == 0:
        b += L(X(0), 10, X(0), h - 24, "s-ink", 2)
    y = 20
    for lab, a, c, cls in rows:
        b += T(0, y + 20, lab, "t b")
        b += R(X(a), y + 4, X(c) - X(a), 22, cls, 11)
        b += T(X(a) - 4, y + 40, unit_fmt.format(a), "t s", "middle") + T(X(c) + 4, y + 40, unit_fmt.format(c), "t s", "middle")
        y += 52
    return svg(560, h, b, "범위 막대")


def hbars(rows, vmax, fmt="{}", tick_note=None):
    """rows: (label, value, cls, text)"""
    x0, W = 170, 330
    b, y = "", 6
    for lab, v, cls, txt in rows:
        b += T(0, y + 22, lab, "t b")
        b += R(x0, y + 4, W, 26, "f-soft", 5)
        b += R(x0, y + 4, W * v / vmax, 26, cls, 5)
        b += T(x0 + W * v / vmax + 6, y + 23, txt, "t b")
        y += 40
    if tick_note:
        b += T(x0, y + 10, tick_note, "t s")
        y += 16
    return svg(560, y + 4, b, "막대 그래프")


def crossover():
    x0, x1, y0, y1 = 70, 540, 230, 20
    rmax, smin, smax = 100, 0.010, 0.034
    X = lambda r: x0 + (r - 1) / (rmax - 1) * (x1 - x0)
    Y = lambda s: y0 - (s - smin) / (smax - smin) * (y0 - y1)
    b = ""
    # 양쪽 문서가 이기는 구간 음영
    b += R(X(1), y1, X(62) - X(1), y0 - y1, "f-soft", 0)
    for s in (0.015, 0.020, 0.025, 0.030):
        b += L(x0, Y(s), x1, Y(s), "s-hair", 1) + T(x0 - 6, Y(s) + 4, f"{s:.3f}", "t s", "end")
    for r in (1, 20, 40, 62, 80, 100):
        b += T(X(r), y0 + 18, str(r), "t s" if r != 62 else "t b", "middle")
    b += L(x0, y0, x1, y0, "s-ink", 1.5)
    pts = " ".join(f"{X(r):.1f},{Y(2/(60+r)):.1f}" for r in range(1, 101))
    b += f'<polyline points="{pts}" fill="none" class="s-fuse" stroke-width="3"/>'
    b += L(x0, Y(1 / 61), x1, Y(1 / 61), "s-bm", 3)
    b += L(X(62), y1, X(62), y0, "s-ink", 1.5, ' stroke-dasharray="4 4"')
    b += f'<circle cx="{X(62):.1f}" cy="{Y(1/61):.1f}" r="5" class="f-ink"/>'
    b += T(X(4), Y(0.0315), "양쪽 모두 r위 = 2/(60+r)", "t b", extra=' style="fill:var(--c-fuse)"')
    b += T(X(64), Y(1 / 61) - 10, "한쪽만 1위 = 1/61 ≈ 0.0164", "t b", extra=' style="fill:var(--c-bm)"')
    b += T(X(30), Y(0.0125), "이 구간(r < 62)에선", "t m", "middle") + T(X(30), Y(0.0125) + 17, "양쪽 문서가 정답을 앞선다", "t m", "middle")
    b += T((x0 + x1) / 2, y0 + 38, "두 검색기에서 모두 r위인 문서의 r", "t s", "middle")
    return svg(560, 276, b, "RRF k=60에서 한쪽 1위와 양쪽 r위 점수 비교")


def rrf_example():
    """k=60 식으로 계산한 예시: 한쪽 1위 정답 vs 양쪽 중간 순위 문서들"""
    docs = [("문서 A", 3, 4), ("문서 B", 6, 2), ("문서 C", 8, 6), ("문서 D", 10, 12), ("★ 정답", 1, None)]
    sc = [(n, (1 / (60 + a) if a else 0) + (1 / (60 + c) if c else 0), a, c) for n, a, c in docs]
    sc.sort(key=lambda t: -t[1])
    b = T(0, 16, "예시 (k=60 식으로 계산)", "t s")
    b += T(150, 40, "BM25", "t b", "middle", ' style="fill:var(--c-bm)"') + T(220, 40, "벡터", "t b", "middle", ' style="fill:var(--c-vec)"')
    b += T(330, 40, "RRF 점수", "t b", "middle") + T(470, 40, "결합 순위", "t b", "middle")
    y = 52
    for i, (n, s, a, c) in enumerate(sc, 1):
        star = n.startswith("★")
        b += R(0, y, 556, 32, "f-hl" if star else "f-soft", 6, ' style="stroke:var(--hl-line)"' if star else "")
        b += T(12, y + 21, n, "t b")
        b += T(150, y + 21, f"{a}위" if a else "밖", "t", "middle") + T(220, y + 21, f"{c}위" if c else "100위 밖", "t", "middle")
        b += T(330, y + 21, f"{s:.5f}", "t", "middle") + T(470, y + 21, f"{i}위", "t b", "middle")
        y += 38
    return svg(560, y + 2, b, "RRF k=60 예시 계산")


def k_curves():
    x0, x1, y0, y1 = 70, 470, 220, 20
    X = lambda r: x0 + (r - 1) / 9 * (x1 - x0)
    Y = lambda v: y0 - v * (y0 - y1)
    b = ""
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        b += L(x0, Y(v), x1, Y(v), "s-hair", 1) + T(x0 - 6, Y(v) + 4, f"{int(v*100)}%", "t s", "end")
    for r in range(1, 11):
        b += T(X(r), y0 + 18, str(r), "t s", "middle")
    b += T((x0 + x1) / 2, y0 + 38, "순위 r  (세로: 1위 점수 대비 r위 점수)", "t s", "middle")
    for k, cls, dash in ((0, "s-loss", ""), (2, "s-vec", ""), (10, "s-fuse", ""), (60, "s-bm", ""), (500, "s-tie", ' stroke-dasharray="5 4"')):
        pts = " ".join(f"{X(r):.1f},{Y((k+1)/(k+r)):.1f}" for r in range(1, 11))
        b += f'<polyline points="{pts}" fill="none" class="{cls}" stroke-width="3"{dash}/>'
        v10 = (k + 1) / (k + 10)
        yy = Y(v10) + 4
        if k == 500:
            yy -= 12
        b += T(x1 + 8, yy, f"k={k}  {v10*100:.0f}%", "t m b")
    return svg(560, 266, b, "k값별 순위에 따른 RRF 점수 감소")


def split_design(sel="선택용 2,107개", val="검증용 2,108개"):
    b = R(170, 6, 220, 46, "f-soft", 10) + T(280, 27, "질문 4,215개", "t b", "middle") + T(280, 45, "문서별로 반씩 나눔 (seed 고정)", "t s", "middle")
    b += arrow(240, 52, 140, 78) + arrow(320, 52, 420, 78)
    b += R(4, 80, 266, 150, "f-box", 12) + T(137, 104, sel, "t b", "middle")
    for i, s in enumerate(["후보: k 5개 · w 9개 · α 9개", "더 나은 검색기 하나 고르기", "MRR@10 최고 설정 고르기", "→ 설정을 하나로 고정"]):
        b += T(20, 132 + i * 24, s, "t m")
    b += R(290, 80, 266, 150, "f-hl", 12) + T(423, 104, val, "t b", "middle")
    for i, s in enumerate(["고른 설정 그대로 실행", "질문 단위 paired bootstrap", "2,000회 → 95% 구간", "→ 이득 / 구분 안 됨 / 손해"]):
        b += T(306, 132 + i * 24, s, "t m")
    b += arrow(270, 200, 288, 200)
    return svg(560, 236, b, "선택용과 검증용 분리 설계")


def ci_schematic():
    x0, x1 = 150, 540
    X = lambda v: x0 + (v + 1) / 2 * (x1 - x0)
    b = L(X(0), 4, X(0), 150, "s-ink", 2) + T(X(0), 168, "차이 0", "t s", "middle")
    rows = [("이득", 0.15, 0.75, 0.45, "f-gain", "s-gain"), ("구분 안 됨", -0.35, 0.4, 0.05, "f-tie", "s-tie"), ("손해", -0.8, -0.2, -0.5, "f-loss", "s-loss")]
    y = 14
    for lab, a, c, m, f, s in rows:
        b += T(0, y + 24, lab, "t b")
        b += R(X(a), y + 10, X(c) - X(a), 20, f, 10, ' opacity="0.85"')
        b += f'<circle cx="{X(m):.1f}" cy="{y+20}" r="6" class="f-ink"/>'
        y += 46
    b += T(x0, 186, "막대 = 95% 구간, 점 = 차이 추정값 (모양은 예시)", "t s")
    return svg(560, 194, b, "95% 구간과 판정의 관계")


def mrr_bars():
    b, x0 = "", 40
    for r in range(1, 11):
        v = 1 / r
        x = x0 + (r - 1) * 50
        b += R(x, 20 + 130 * (1 - v), 38, 130 * v, "f-bm", 4)
        b += T(x + 19, 14 + 130 * (1 - v), f"{v:.2f}".rstrip("0").rstrip("."), "t m b", "middle")
        b += T(x + 19, 170, f"{r}위", "t s", "middle")
    b += T(0, 196, "11위부터는 0점. 질문마다 이 점수를 매기고 평균을 낸다.", "t s")
    return svg(560, 204, b, "정답 순위별 MRR 점수")


def minmax():
    b = T(0, 18, "예시: 한 질문의 top-100 점수", "t s")
    b += T(0, 50, "BM25 원점수", "t b") + T(0, 104, "벡터(코사인)", "t b")
    raw_b = [(23.1, "1위"), (11.4, "2위"), (10.9, "3위"), (4.2, "100위")]
    raw_v = [(0.86, "1위"), (0.84, "2위"), (0.83, "3위"), (0.71, "100위")]
    for i, (v, lab) in enumerate(raw_b):
        b += R(130 + i * 62, 30, 56, 30, "f-soft", 6) + T(158 + i * 62, 50, f"{v}", "t", "middle")
    for i, (v, lab) in enumerate(raw_v):
        b += R(130 + i * 62, 84, 56, 30, "f-soft", 6) + T(158 + i * 62, 104, f"{v:.2f}", "t", "middle")
    b += arrow(380, 72, 410, 72) + T(395, 140, "min-max", "t s", "middle")
    nb = [(v - 4.2) / (23.1 - 4.2) for v, _ in raw_b]
    nv = [(v - 0.71) / (0.86 - 0.71) for v, _ in raw_v]
    for i in range(4):
        b += R(420, 30 + 0, 0, 0, "f-soft")
    b += T(416, 50, " ".join(f"{v:.2f}" for v in nb[:3]) + "…0", "t b", extra=' style="fill:var(--c-bm)"')
    b += T(416, 104, " ".join(f"{v:.2f}" for v in nv[:3]) + "…0", "t b", extra=' style="fill:var(--c-vec)"')
    b += T(0, 168, "→ 두 점수가 모두 0~1이 된 뒤 (1−α)·BM25 + α·벡터", "t m b")
    return svg(560, 178, b, "min-max 정규화 예시")


def rank_vs_score():
    x0, x1 = 120, 540
    X = lambda v: x1 - v * (x1 - x0)
    b = T(0, 16, "예시: 한 검색기의 1~5위", "t s")
    b += T(0, 58, "순위만", "t b") + T(0, 76, "(RRF)", "t s")
    for i in range(5):
        x = x0 + i * 100
        b += f'<circle cx="{x}" cy="58" r="15" class="f-tie"/>' + T(x, 63, f"{i+1}", "t b w", "middle")
        if i:
            b += T(x - 50, 40, "1칸", "t s", "middle")
    b += T(0, 140, "점수", "t b") + T(0, 158, "(점수 결합)", "t s")
    vals = [1.0, 0.52, 0.44, 0.36, 0.28]
    b += L(X(0.52) + 16, 116, X(1.0) - 16, 116, "s-bm", 2) + T((X(0.52) + X(1.0)) / 2, 108, "1위가 크게 앞섬", "t m b", "middle", ' style="fill:var(--c-bm)"')
    for i, v in enumerate(vals):
        b += f'<circle cx="{X(v):.1f}" cy="140" r="15" class="f-bm" opacity="{0.95 if i==0 else 0.6}"/>' + T(X(v), 145, f"{i+1}", "t b w", "middle")
    b += T(x0, 184, "← 낮음", "t s") + T(x1, 184, "정규화 점수 높음 →", "t s", "end")
    return svg(560, 192, b, "순위와 점수가 담는 정보의 차이")


def alpha_strip(vals=(0.5, 0.6, 0.4, 0.4, 0.4, 0.5)):
    x0, x1 = 40, 520
    X = lambda v: x0 + v * (x1 - x0)
    b = L(x0, 110, x1, 110, "s-ink", 2)
    for v in [i / 10 for i in range(11)]:
        b += L(X(v), 104, X(v), 116, "s-ink", 1.5) + T(X(v), 134, f"{v:.1f}", "t s", "middle")
    cnt = {}
    for j, v in enumerate(vals):
        n = cnt.get(v, 0)
        cnt[v] = n + 1
        b += f'<circle cx="{X(v):.1f}" cy="{92 - n*26}" r="12" class="f-fuse"/>' + T(X(v), 97 - n * 26, CIRC[j], "t b w", "middle")
    b += T(x0, 158, "← BM25 쪽 비중", "t s", extra=' style="fill:var(--c-bm)"') + T(x1, 158, "벡터 쪽 비중 →", "t s", "end", ' style="fill:var(--c-vec)"')
    return svg(560, 166, b, "조합별로 고른 α")


def flow(steps):
    """steps: (title, sub, cls)"""
    b, y = "", 4
    for i, (t, s, cls) in enumerate(steps):
        b += R(0, y, 556, 50, cls, 10) + T(16, y + 22, t, "t b w") + T(16, y + 41, s, "t w m")
        if i < len(steps) - 1:
            b += arrow(40, y + 50, 40, y + 64)
        y += 66
    return svg(560, y - 12, b, "실무 절차")


def leftover():
    return stacked([("top-10 밖 99개", [(45, "f-fuse"), (34, "f-vec"), (20, "f-loss")])], 99,
                   [("f-fuse", "둘 다 top-100 안 → rerank"), ("f-vec", "한쪽만"), ("f-loss", "둘 다 밖")])


def funnel():
    W = 540
    b = ""
    rows = [("검증용 질문", 2108, "2,108", "f-tie"), ("한 검색기만 top-10", 208, "208 (BM25만 102 · 벡터만 106)", "f-fuse"),
            ("그중 그 검색기 1위", 107, "107 = '혼자 1위'", "f-loss")]
    y = 4
    for lab, v, txt, cls in rows:
        w = W * v / 2108
        b += T(0, y + 16, lab, "t b") + R(0, y + 24, w, 24, cls, 4)
        b += T(w - 10, y + 42, txt, "t m b w", "end") if w > 300 else T(w + 8, y + 42, txt, "t m b")
        y += 60
    return svg(560, y, b, "혼자 1위인 정답이 몇 개인지")


def waffle_pair(a, b_, la, lb):
    out = ""
    for g, (n, lab) in enumerate(((a, la), (b_, lb))):
        ox = g * 290
        for i in range(100):
            r, c = divmod(i, 10)
            out += f'<circle cx="{ox+14+c*22}" cy="{14+r*22}" r="8" class="{"f-gain" if i < n else "f-hair"}"/>'
        out += T(ox + 110, 248, lab, "t b", "middle")
    return svg(560, 258, out, "100번 중 1등을 지킨 횟수")


def sad_count(n_before, n_after):
    b = T(0, 30, "순서만 합치기", "t b") + T(0, 100, "무게를 주면", "t b")
    for i in range(n_before):
        b += f'<text x="{150 + i * 42}" y="40" style="font-size:30px">😢</text>'
    b += T(150, 108, "0번! 😊", "t xl")
    b += T(0, 140, "더 많은 조합(38개)에서 손해 본 횟수", "t s")
    return svg(560, 150, b, "손해 횟수 9번에서 0번")


def merge_kids():
    b = T(70, 20, "글자 친구 줄", "t b", "middle", ' style="fill:var(--c-bm)"') + T(70, 160, "뜻 친구 줄", "t b", "middle", ' style="fill:var(--c-vec)"')
    for i in range(4):
        b += R(10 + i * 32, 32, 26, 34, "f-bm", 4) + R(10 + i * 32, 104, 26, 34, "f-vec", 4)
    b += arrow(150, 50, 250, 80) + arrow(150, 120, 250, 92)
    b += T(400, 52, "하나의 줄", "t b", "middle")
    cl = ["f-bm", "f-vec", "f-bm", "f-vec", "f-bm", "f-vec"]
    for i, c in enumerate(cl):
        b += R(270 + i * 44, 68, 36, 40, c, 5)
    b += R(270, 68, 36, 40, "f-hl", 5, ' style="stroke:var(--hl-line);stroke-width:3"') + T(288, 94, "★", "t b", "middle")
    return svg(560, 168, b, "두 줄을 하나로 합치기")


def method_bars(vals, names, pct=True, vmax=100, note=None):
    cl = ["f-tie", "f-vec", "f-fuse", "f-bm"]
    rows = [(n, v, cl[i % 4], (f"{v}%" if pct else str(v))) for i, (n, v) in enumerate(zip(names, vals)) if v is not None]
    return hbars(rows, vmax, tick_note=note)


M4 = ["RRF k=60", "RRF k 변경", "가중 RRF", "점수 결합"]
M4_15 = ["순서만 합치기", "순서 + 다이얼", "순서 + 친구별 무게", "점수로 합치기"]


def figs_for(page):
    """{위치: [figure html, ...]}  위치: 'intro', 'gloss', 1..10"""
    F = {}
    add = lambda k, s, c: F.setdefault(k, []).append(fig(s, c))
    if page in ("eli20", "ai"):
        add("intro", pipeline(), "RAG 검색 단계. 이 발표가 다루는 것은 가운데 '결합' 상자 하나다.")
        if page == "eli20":
            add("gloss", mrr_bars(), "MRR@10: 정답이 1위면 1점, 2위면 0.5점, 5위면 0.2점.")
            add("gloss", minmax(), "min-max 정규화 (값은 예시). 단위가 다른 두 점수를 0~1로 맞춘다.")
        add("gloss", ci_schematic(), "판정 규칙: 95% 구간이 0보다 위면 이득, 0을 걸치면 구분 안 됨, 아래면 손해.")
        add(1, verdict_grid(["RRF k=60"]), "RRF k=60 · 6개 조합 판정 (더 나은 검색기 하나 대비).")
        add(1, ranges([("RRF k=60 − 단일", -0.055, 0.036, "f-tie")], -0.06, 0.06, [-0.06, -0.03, 0, 0.03, 0.06]),
            "6개 조합의 MRR@10 차이 범위. 0을 사이에 두고 양쪽으로 갈린다.")
        add(1, stacked([("38개 조합", [(11, "f-gain"), (18, "f-tie"), (9, "f-loss")])], 38,
                       [("f-gain", "이득"), ("f-tie", "구분 안 됨"), ("f-loss", "손해")]),
            "청킹 방식까지 넓힌 38개 조합에서도 이득 11 · 손해 9.")
        add(2, verdict_grid(M4, params=[("고른 k (k 변경)", ["2", "0", "0", "2", "0", "10"]),
                                        ("고른 α (점수 결합)", [".5", ".6", ".4", ".4", ".4", ".5"])]),
            "네 결합 방식 × 6개 조합. 아래로 갈수록 초록(이득)이 늘고 빨강(손해)이 사라진다.")
        add(2, ranges([("점수 결합 − RRF k=60", 0.023, 0.068, "f-bm")], 0, 0.08, [0, 0.02, 0.04, 0.06, 0.08]),
            "점수 결합 − RRF k=60: 6개 조합 모두 +0.023 ~ +0.068.")
        add(3, funnel(), "'혼자 1위'인 정답의 정의와 개수 (검증용, Qwen3-0.6B).")
        add(3, crossover(), "RRF k=60 식. 두 검색기 모두 61위 안에만 들면 한쪽 1위 문서를 이긴다.")
        add(3, rrf_example(), "예시: 양쪽에서 중간 순위로 겹친 문서들이 정답 앞에 끼어든다.")
        add(3, method_bars([8, 32, 44, 51], M4, note="중앙값 순위: RRF k=60 5위 · k 변경 2위 · 점수 결합 1위"),
            "혼자 1위였던 정답 107개 중 결합 후에도 1위를 지킨 비율.")
        if page == "ai":
            add(3, method_bars([8, 0, None, 3], M4, vmax=20),
                "반대 방향: 둘 다 top-10 밖이던 정답 76개 중 top-10에 오른 비율 (가중 RRF는 미보고).")
        add(4, k_curves(), "k가 작을수록 1위와 뒤 순위의 점수 차가 커진다. k=500은 사실상 평평하다.")
        add(4, ranges([("k=60 대비 고른 k", 0.008, 0.050, "f-fuse")], 0, 0.06, [0, 0.02, 0.04, 0.06]),
            "고른 k(2 · 0 · 0 · 2 · 0 · 10)의 MRR@10 향상. 6개 중 5개는 구간 > 0.")
        add(4, ranges([("k=60", 3, 13, "f-tie"), ("고른 k", 8, 27, "f-vec")], 0, 30, [0, 10, 20, 30], "{:.0f}%"),
            "대가: top-10 안 동점 비율이 늘어 동점 규칙(BM25 우선)의 영향이 커진다.")
        add(5, split_design(), "후보 공간과 판정 기준은 실행 전에 고정. 검증용은 판정에만 쓴다. 결합 방식 사이에는 식만 다르다.")
        add(6, stacked([("RRF k=60", [(11, "f-gain"), (18, "f-tie"), (9, "f-loss")]),
                        ("가중 RRF", [(27, "f-gain"), (11, "f-tie"), (0, "f-loss")])], 38,
                       [("f-gain", "이득"), ("f-tie", "구분 안 됨"), ("f-loss", "손해")]),
            "38개 조합: 가중치를 주면 이득 11 → 27, 손해 9 → 0.")
        add(7, rank_vs_score(), "순위는 간격을 늘 '1칸'으로 본다. 점수는 1위가 얼마나 앞서는지까지 담는다 (값은 예시).")
        add(7, alpha_strip(), "조합별로 고른 α. 0.4~0.6에 모여 있지만 조합마다 다르다.")
        add(7, ranges([("점수 결합 − 가중 RRF", 0.011, 0.027, "f-bm")], 0, 0.03, [0, 0.01, 0.02, 0.03]),
            "6개 조합 모두 구간 > 0.")
        add(8, hbars([("격차 규칙 (선택용)", 37, "f-gain", "37/38"), ("격차 규칙 (검증용)", 27, "f-vec", "27/38"),
                      ("RRF k=60 판정 일치", 20, "f-tie", "20/38")], 38),
            "선택용에서 맞던 '격차 0.029 이하면 RRF 이득' 규칙이 검증용에서 크게 떨어졌다.")
        add(8, hbars([("점수 결합", 5, "f-bm", "5개"), ("가중 RRF", 3, "f-fuse", "3개"), ("RRF k=60", 1, "f-tie", "1개")], 6),
            "질문 분할을 20번 바꿔도 20번 모두 이득이었던 조합 수 (6개 중).")
        if page == "ai":
            add(8, ranges([("최대 regret", 0, 0.019, "f-gain"), ("95% 구간 반폭", 0.014, 0.032, "f-tie")], 0, 0.04,
                          [0, 0.01, 0.02, 0.03, 0.04], "{:.3f}", tick_fmt="{:.2f}"),
                "고른 설정의 손실(regret)은 판정 구간 폭보다 작다.")
        add(9, flow([("① 정답 달린 질문 모으기", "선택용 / 검증용으로 나눈다", "f-fuse"),
                     ("② 검색기 하나씩 재기", "BM25 · 벡터 각각 MRR@10", "f-vec"),
                     ("③ 점수 결합 먼저", "α는 선택용에서 고른다", "f-bm"),
                     ("④ 점수를 못 쓰면 가중 RRF", "k는 10 이하부터", "f-gain"),
                     ("⑤ 차이가 안 나면 검색기 하나", "결합하지 않는다", "f-tie")]),
            "실무 절차.")
        add(9, hbars([("RRF k=60", 9, "f-loss", "9개"), ("RRF k=2", 5, "f-loss", "5개"), ("점수 결합 α=0.5", 3, "f-loss", "3개")], 38),
            "값을 고정해서 쓰면 38개 조합 중 손해가 나는 조합 수. 세 방식 모두 0이 아니다.")
        add(10, leftover(), "점수 결합 후에도 top-10 밖 99개. 20개는 결합 방식으로는 못 고친다.")
    elif page == "eli15":
        add("gloss", mrr_bars(), "MRR@10 점수표: 정답이 앞에 있을수록 점수가 크다.")
        add("gloss", ci_schematic(), "'구분 안 됨'은 범위가 0을 걸친 경우다.")
        add(1, stacked([("38개 조합", [(11, "f-gain"), (18, "f-tie"), (9, "f-loss")])], 38,
                       [("f-gain", "좋아짐"), ("f-tie", "가릴 수 없음"), ("f-loss", "나빠짐")]),
            "청킹 방식까지 넓힌 38개 조합에서도 나빠진 게 9개다.")
        add(3, rrf_example(), "예시: 양쪽 다 그럭저럭 앞에 둔 문서들이 점수를 두 번 받아 정답을 앞지른다.")
        add(3, method_bars([8, 32, 44, 51], M4_15), "혼자 1위였던 정답 107개 중 합친 뒤에도 1등을 지킨 비율.")
        add(4, k_curves(), "k(다이얼)를 바꾸면 10등의 점수가 1등 대비 얼마나 줄어드는지.")
        add(6, stacked([("순서만", [(11, "f-gain"), (18, "f-tie"), (9, "f-loss")]),
                        ("순서 + 무게", [(27, "f-gain"), (11, "f-tie"), (0, "f-loss")])], 38,
                       [("f-gain", "좋아짐"), ("f-tie", "가릴 수 없음"), ("f-loss", "나빠짐")]),
            "38개 조합: 무게를 주면 나빠진 조합이 9 → 0.")
        add(7, rank_vs_score(), "순서는 간격을 늘 한 칸으로 본다 (값은 예시).")
        add(8, hbars([("연습 문제", 37, "f-gain", "37/38"), ("시험 문제", 27, "f-vec", "27/38")], 38),
            "'성적 차이가 0.029 이하면 RRF가 이득' 규칙이 맞은 조합 수.")
        add(9, hbars([("RRF k=60", 9, "f-loss", "9개"), ("RRF k=2", 5, "f-loss", "5개"), ("점수 결합 α=0.5", 3, "f-loss", "3개")], 38),
            "질문 없이 값을 정해 두면 38개 중 나빠지는 조합 수.")
        add(10, leftover(), "못 찾은 99개를 이유별로 나누면.")
    elif page == "eli5":
        add("gloss", merge_kids(), "두 친구의 줄을 하나로 다시 세워요. ★ 정답이 맨 앞이면 좋아요.")
        add(3, waffle_pair(8, 51, "순서만: 8번", "점수로: 51번"), "친구 하나가 1등으로 찾은 정답, 100번 중 몇 번 1등을 지켰을까요?")
        add(6, sad_count(9, 0), "손해 본 횟수가 9번 → 0번.")
    return F


def fix_existing(html):
    # 예전 그림의 고정 밝은색 → 다크 모드에서도 보이게 변수로
    html = html.replace('fill="#fff4d6" stroke="#d4a017"', 'style="fill:var(--hl);stroke:var(--hl-line)"')
    html = html.replace('fill="#fff4d6"', 'style="fill:var(--hl)"').replace('fill="#e8f0fb"', 'style="fill:var(--box)"')
    html = re.sub(r'(fill|stroke)="(var\(--[a-z-]+\))"', r'style="\1:\2"', html)
    # 한 요소에 style이 두 번 생기면 합친다
    html = re.sub(r'style="([^"]*)" style="([^"]*)"', r'style="\1;\2"', html)
    return html


def inject(html, F):
    html = html.replace("</style>", EXTRA_CSS + "</style>", 1)
    html = fix_existing(html)
    if "intro" in F:
        i = html.index("</div>", html.index('<div class="one">')) + 6
        html = html[:i] + "".join(F["intro"]) + html[i:]
    if "gloss" in F:
        i = html.index("</dl>", html.index("먼저 알아 둘 말")) + 5
        html = html[:i] + "".join(F["gloss"]) + html[i:]
    for n in range(1, 11):
        if n not in F:
            continue
        s = html.index(f'<span class="no">{n}장</span>')
        e = html.find('<div class="card">', s)
        if e < 0:
            e = html.index("</main>", s)
        end = html.rindex("</div>", s, e)
        d = html.find("<details>", s, end)
        i = d if d >= 0 else end
        html = html[:i] + "".join(F[n]) + html[i:]
    return html


def main():
    OUT.mkdir(exist_ok=True)
    for key, name in PAGES.items():
        html = (SRC / name).read_text(encoding="utf-8")
        html = inject(html, figs_for(key))
        html = re.sub(r'href="(eli[^"]*)_v1\.html"', r'href="\1_v2.html"', html)
        (OUT / name.replace("_v1", "_v2")).write_text(html, encoding="utf-8")
        print(name, html.count("<svg"), "svg")


if __name__ == "__main__":
    main()
