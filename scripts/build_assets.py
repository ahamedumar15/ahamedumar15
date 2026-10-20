#!/usr/bin/env python3
"""Generate every SVG used by the profile README.

Standard library only. Text is drawn from glyph outlines in assets/src/kit.json
(Inter and JetBrains Mono, OFL-1.1), so the images render identically on every
platform: GitHub cannot load web fonts inside an SVG served as an image.

    python scripts/build_assets.py              # all assets, live stats included
    python scripts/build_assets.py --offline    # all assets except stats
    python scripts/build_assets.py --only stats # what the daily workflow runs

If the GitHub fetch fails, the existing stats.svg is left untouched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
KIT = json.loads((ASSETS / "src" / "kit.json").read_text(encoding="utf-8"))
USER = "ahamedumar15"
W = 1200

# Design tokens: OBSIDIAN / AI SYSTEMS
BG = "#060914"
PANEL = "#0A1024"
CHIP = "#0C1430"
LINE = "#1C2650"
LINE2 = "#28346A"
BLUE = "#4F8CFF"
SKY = "#8FB3FF"
VIOLET = "#8B5CF6"
LILAC = "#A78BFA"
CYAN = "#5EEAD4"
ROSE = "#F28BAA"
TEXT = "#EEF2FF"
SOFT = "#C9D2EE"
MUTE = "#94A0C6"
DIM = "#5B6690"

REDUCED = (
    "@media (prefers-reduced-motion: reduce){*{animation:none!important}"
    ".motion{display:none}.rm-show{opacity:1!important}.rm-hide{opacity:0!important}}"
)


class Svg:
    """Collects glyph and gradient defs so each glyph outline is stored once per file."""

    def __init__(self, w: int, h: int, label: str):
        self.w, self.h, self.label = w, h, label
        self.defs: dict[str, str] = {}
        self.css: list[str] = []
        self.body: list[str] = []
        self.n = 0

    def uid(self, p: str) -> str:
        self.n += 1
        return f"{p}{self.n}"

    def add(self, *parts: str) -> None:
        self.body.extend(parts)

    def gradient(self, stops, x1=0, y1=0, x2=1, y2=0, user=None) -> str:
        gid = self.uid("g")
        units = ""
        if user:
            x1, y1, x2, y2 = user
            units = ' gradientUnits="userSpaceOnUse"'
        s = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>' for o, c, a in stops)
        self.defs[gid] = f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{units}>{s}</linearGradient>'
        return f"url(#{gid})"

    def radial(self, stops, cx=0.5, cy=0.5, r=0.5) -> str:
        gid = self.uid("r")
        s = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>' for o, c, a in stops)
        self.defs[gid] = f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}">{s}</radialGradient>'
        return f"url(#{gid})"

    def blur(self, sd: float) -> str:
        fid = f"blur{str(sd).replace('.', '_')}"
        self.defs[fid] = (f'<filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%">'
                          f'<feGaussianBlur stdDeviation="{sd}"/></filter>')
        return f"url(#{fid})"

    def glyph_runs(self, s: str, font: str, size: float, x: float, y: float, track: float = 0, anchor="start"):
        glyphs = KIT["fonts"][font]
        width = text_width(s, font, size, track)
        if anchor == "middle":
            x -= width / 2
        elif anchor == "end":
            x -= width
        k = size / 1000
        uses, cx = [], 0.0
        for ch in s:
            adv, d = glyphs.get(ch, glyphs["?"])
            if d:
                gid = f"{font}{ord(ch):x}"
                self.defs[gid] = f'<path id="{gid}" d="{d}"/>'
                uses.append(f'<use href="#{gid}" x="{cx:.0f}"/>')
            cx += adv + track * 1000 / size if size else adv
        return f'<g transform="translate({x:.2f} {y:.2f}) scale({k:.5f})">{"".join(uses)}</g>', width

    def text(self, s, x, y, size, font="r", fill=TEXT, track=0, anchor="start", cls="", opacity=1) -> float:
        run, width = self.glyph_runs(s, font, size, x, y, track, anchor)
        c = f' class="{cls}"' if cls else ""
        o = f' opacity="{opacity}"' if opacity != 1 else ""
        self.add(f'<g fill="{fill}"{c}{o}>{run}</g>')
        return width

    def gradient_text(self, s, x, y, size, font, stops, track=0) -> float:
        """Gradient across the whole run, painted through a mask so it doesn't restart per glyph."""
        run, width = self.glyph_runs(s, font, size, x, y, track)
        mid = self.uid("m")
        self.defs[mid] = f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{self.w}" height="{self.h}"><g fill="#fff">{run}</g></mask>'
        fill = self.gradient(stops, user=(x, 0, x + width, 0))
        self.add(f'<rect x="{x:.1f}" y="{y - size:.1f}" width="{width + 2:.1f}" height="{size * 1.35:.1f}" fill="{fill}" mask="url(#{mid})"/>')
        return width

    def render(self) -> str:
        css = f"<style>{''.join(self.css)}{REDUCED}</style>" if self.css else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                f'role="img" aria-label="{html.escape(self.label)}"><title>{html.escape(self.label)}</title>'
                f'{css}<defs>{"".join(self.defs.values())}</defs>{"".join(self.body)}</svg>\n')


def text_width(s: str, font: str, size: float, track: float = 0) -> float:
    g = KIT["fonts"][font]
    return sum(g.get(ch, g["?"])[0] for ch in s) * size / 1000 + track * max(len(s) - 1, 0)


def lum(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def brand(slug: str, x: float, y: float, size: float = 18) -> str:
    color, d = KIT["brands"][slug]
    fill = f"#{color}" if lum(color) > 0.22 else SOFT  # near-black marks would vanish on obsidian
    return f'<path transform="translate({x} {y}) scale({size / 24:.4f})" fill="{fill}" d="{d}"/>'


def line_icon(name: str, x: float, y: float, size: float, stroke: str, width: float = 1.8) -> str:
    return (f'<g transform="translate({x} {y}) scale({size / 24:.4f})" fill="none" stroke="{stroke}" '
            f'stroke-width="{width * 24 / size:.2f}" stroke-linecap="round" stroke-linejoin="round">'
            f'{KIT["lines"][name]}</g>')


def save(name: str, svg: Svg) -> None:
    path = ASSETS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg.render(), encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.1f} KB)")


class Rand:
    """Tiny deterministic LCG so stars stay put between builds."""

    def __init__(self, seed: int):
        self.s = seed

    def __call__(self) -> float:
        self.s = (self.s * 1103515245 + 12345) % 2**31
        return self.s / 2**31


# ---------------------------------------------------------------- hero


def hero() -> None:
    H = 440
    s = Svg(W, H, "Umar Ahamed. Software Engineer and AI Engineering. I build AI systems that are grounded, observable, and tested. Open to AI Engineering and Software Engineering internships.")
    s.css.append(
        "@keyframes breathe{0%,100%{opacity:.55}50%{opacity:1}}"
        "@keyframes twinkle{0%,100%{opacity:.15}50%{opacity:.9}}"
        "@keyframes shimmer{0%,100%{opacity:.08}50%{opacity:.45}}"
        "@keyframes pulse{0%{r:4;opacity:.9}70%,100%{r:13;opacity:0}}"
        ".glow{animation:breathe 7s ease-in-out infinite}"
        ".tw{animation:twinkle 4.8s ease-in-out infinite}"
        ".sh{animation:shimmer 5.5s ease-in-out infinite}"
        ".ring{animation:pulse 2.4s ease-out infinite}"
    )
    clip = s.uid("c")
    s.defs[clip] = f'<clipPath id="{clip}"><rect width="{W}" height="{H}" rx="22"/></clipPath>'
    s.add(f'<g clip-path="url(#{clip})">')
    s.add(f'<rect width="{W}" height="{H}" fill="{s.gradient([(0, "#070A18", 1), (1, "#0B0D2A", 1)], 0, 0, 1, 1)}"/>')

    # sky glow behind the arc
    cx, cy, r = 902, 318, 178
    s.add(f'<ellipse cx="{cx}" cy="{cy - 30}" rx="420" ry="300" fill="{s.radial([(0, "#4B2FC2", .55), (.55, "#24166E", .25), (1, "#0B0D2A", 0)])}"/>')
    rnd = Rand(15)
    for i in range(95):
        x, y = 470 + rnd() * 730, rnd() * 300
        rr = .4 + rnd() * 1.1
        cls = ' class="tw"' if i % 9 == 0 else ""
        delay = f' style="animation-delay:{rnd() * 4:.1f}s"' if cls else ""
        s.add(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rr:.2f}" fill="#DCE4FF" opacity="{.25 + rnd() * .6:.2f}"{cls}{delay}/>')

    # the arc: inner haze, glow, crisp rim
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{s.radial([(0, "#1A1450", .0), (.8, "#2A1E7A", .35), (1, "#6D4CF0", .5)])}"/>')
    rim = s.gradient([(0, "#3B2B9A", .2), (.45, "#7C5CFF", .7), (.8, "#C4B5FD", 1), (1, "#FFFFFF", 1)], 0, 1, 1, 0)
    s.add(f'<circle class="glow" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{rim}" stroke-width="10" filter="{s.blur(9)}"/>')
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{rim}" stroke-width="2.4"/>')

    # horizon light
    s.add(f'<ellipse class="glow" cx="{cx}" cy="330" rx="230" ry="26" fill="#B794F6" opacity=".7" filter="{s.blur(22)}"/>')
    s.add(f'<ellipse cx="{cx}" cy="334" rx="120" ry="6" fill="#F5D0FE" opacity=".55" filter="{s.blur(5)}"/>')

    # far ridges
    far = s.gradient([(0, "#3A2F94", 1), (1, "#141238", 1)], 0, 0, 0, 1)
    s.add(f'<path fill="{far}" d="M470 336 L530 290 L572 302 L622 248 L660 226 L690 252 L716 240 L752 286 L790 306 L830 326 L870 334 L950 334 L990 318 L1022 288 L1046 270 L1070 292 L1200 280 L1200 352 L470 352Z"/>')
    s.add('<path fill="none" stroke="#B9A7FF" stroke-opacity=".35" stroke-width="1" d="M622 248 L660 226 L690 252 L716 240 L752 286 M990 318 L1022 288 L1046 270 L1070 292"/>')
    mid = s.gradient([(0, "#1C1A55", 1), (1, "#0A0B22", 1)], 0, 0, 0, 1)
    s.add(f'<path fill="{mid}" d="M470 352 L512 316 L552 324 L596 286 L628 300 L672 278 L712 306 L760 330 L800 345 L1000 345 L1040 330 L1060 300 L1090 262 L1110 210 L1135 150 L1160 90 L1185 40 L1200 20 L1200 360 L470 360Z"/>')
    s.add('<path fill="none" stroke="#C4B5FD" stroke-opacity=".45" stroke-width="1.2" d="M1040 330 L1060 300 L1090 262 L1110 210 L1135 150 L1160 90 L1185 40 L1200 20"/>')
    s.add('<path fill="#070816" d="M1120 360 L1132 300 L1150 250 L1165 190 L1182 130 L1200 100 L1200 360Z" opacity=".85"/>')

    # water and reflection
    s.add(f'<rect x="470" y="345" width="730" height="{H - 345}" fill="{s.gradient([(0, "#1B1650", 1), (1, "#070A18", 1)], 0, 0, 0, 1)}"/>')
    s.add(f'<ellipse class="glow" cx="{cx}" cy="352" rx="150" ry="14" fill="#A78BFA" opacity=".45" filter="{s.blur(10)}"/>')
    for i, (y, w2) in enumerate([(356, 140), (366, 96), (378, 160), (392, 70), (404, 120)]):
        s.add(f'<rect class="sh" style="animation-delay:{i * .8:.1f}s" x="{cx - w2 / 2 + (i % 2) * 20 - 10}" y="{y}" width="{w2}" height="1.4" rx=".7" fill="#E9D5FF"/>')
    s.add('<path fill="#05060F" d="M470 440 L470 404 L560 392 L640 410 L720 398 L790 420 L860 412 L960 430 L1060 410 L1140 396 L1200 404 L1200 440Z"/>')

    # fade the landscape into the text column
    s.add(f'<rect x="440" width="420" height="{H}" fill="{s.gradient([(0, "#070A18", 1), (.55, "#070A18", .55), (1, "#070A18", 0)])}"/>')
    s.add(f'<rect width="470" height="{H}" fill="#070A18"/>')

    # text column
    s.text(">", 64, 96, 15, "mono", BLUE)
    s.text("whoami", 82, 96, 15, "mono", MUTE)
    wu = s.text("Umar ", 60, 178, 74, "b", TEXT, track=-1.5)
    s.gradient_text("Ahamed", 60 + wu, 178, 74, "b", [(0, BLUE, 1), (.55, "#7C6CFF", 1), (1, LILAC, 1)], track=-1.5)
    s.text("Software Engineer", 64, 228, 25, "s", "#DCE3F7")
    sw = text_width("Software Engineer", "s", 25)
    s.add(f'<circle cx="{64 + sw + 20}" cy="219" r="3" fill="{LILAC}"/>')
    s.text("AI Engineering", 64 + sw + 40, 228, 25, "s", "#DCE3F7")
    s.text("I build AI systems that are grounded,", 64, 280, 19, "r", MUTE)
    s.text("observable, and tested.", 64, 308, 19, "r", MUTE)

    # availability: a status, not a fake button
    label = "Open to AI & Software Engineering internships"
    pw = text_width(label, "m", 14) + 58
    s.add(f'<rect x="64" y="342" width="{pw:.0f}" height="38" rx="19" fill="#0C1432" stroke="{LINE2}"/>')
    s.add(f'<circle class="ring motion" cx="88" cy="361" r="4" fill="none" stroke="{CYAN}" stroke-width="1.5"/>')
    s.add(f'<circle cx="88" cy="361" r="4" fill="{CYAN}"/>')
    s.text(label, 104, 366, 14, "m", SOFT)

    s.text("BUILD  /  LEARN  /  SHIP", 1150, 418, 11, "mono", "#C7D2FE", track=2.2, anchor="end", opacity=.75)
    s.add(f'<rect x="{1150 - text_width("BUILD  /  LEARN  /  SHIP", "mono", 11, 2.2) - 34:.0f}" y="413" width="20" height="1" fill="{SKY}" opacity=".7"/>')
    s.add("</g>")
    s.add(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="{LINE}"/>')
    s.add(f'<rect x="60" y="{H - 1.5}" width="{W - 120}" height="1.5" fill="{s.gradient([(0, BLUE, 0), (.5, LILAC, .9), (1, CYAN, 0)])}"/>')
    save("hero.svg", s)


# ---------------------------------------------------------------- typing tagline

PHRASES = [
    "Building retrieval that cites its sources.",
    "Measuring faithfulness, not vibes.",
    "Writing guardrails a model can't talk past.",
]


def typing() -> None:
    w, h, size = 760, 48, 16
    s = Svg(w, h, " ".join(PHRASES))
    cycle, n = 15, len(PHRASES)
    s.add(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{PANEL}" stroke="{LINE}"/>')
    s.add(f'<circle cx="24" cy="24" r="3.5" fill="{CYAN}"/>')
    x0 = 42
    for i, p in enumerate(PHRASES):
        tw = text_width(p, "mono", size)
        a, b = i / n * 100, (i + 1) / n * 100
        typed, hold, erase = a + 1.6 / cycle * 100, b - 4, b - 0.3  # 1.6s typing, hold, 0.6s erase
        # visibility window for this phrase
        s.css.append(f"@keyframes v{i}{{0%,{max(a - .01, 0):.2f}%{{opacity:0}}{a:.2f}%,{erase:.2f}%{{opacity:1}}{b:.2f}%,100%{{opacity:0}}}}")
        # a cover slides right to reveal characters, and back to erase them
        steps = len(p)
        s.css.append(
            f"@keyframes t{i}{{0%,{a:.2f}%{{transform:translateX(0)}}{typed:.2f}%,{hold:.2f}%{{transform:translateX({tw:.1f}px)}}"
            f"{erase:.2f}%,100%{{transform:translateX(0)}}}}"
            f".p{i}{{animation:v{i} {cycle}s linear infinite}}"
            f".c{i}{{animation:t{i} {cycle}s steps({steps}) infinite}}"
        )
        static = "rm-show" if i == 0 else "rm-hide"
        s.add(f'<g class="p{i} {static}" opacity="{1 if i == 0 else 0}">')
        s.text(p, x0, 29.5, size, "mono", s.gradient([(0, SKY, 1), (.55, LILAC, 1), (1, CYAN, 1)], user=(x0, 0, x0 + 560, 0)))
        s.add(f'<g class="c{i} motion"><rect x="{x0 - 2}" y="10" width="{tw + 16:.0f}" height="28" fill="{PANEL}"/>'
              f'<rect x="{x0}" y="14" width="2" height="20" fill="{LILAC}"/></g>')
        s.add("</g>")
    save("typing.svg", s)


# ---------------------------------------------------------------- section headers

# Headers and footer sit directly on GitHub's page, so each gets a light-theme twin
# that the README swaps in through <picture> and prefers-color-scheme.
THEMES = {"": (TEXT, SKY, SOFT, "#7F8BB8", LILAC), "-light": ("#141A33", "#3557C9", "#2A3152", "#5B6690", "#6D4CE0")}


def header(name: str, title: str, icon: str, sub: str) -> None:
    for suffix, (ink, accent, _, _, violet) in THEMES.items():
        s = Svg(W, 58, f"{title}. {sub}")
        stroke = s.gradient([(0, BLUE if not suffix else "#2F5BD3", 1), (1, violet, 1)], user=(0, 0, 24, 24))
        s.add(line_icon(icon, 2, 14, 34, stroke, 1.8))
        s.text(title, 56, 43, 28, "s", ink, track=-.3)
        s.text(sub, W - 4, 41, 15, "r", accent, anchor="end")
        save(f"headers/{name}{suffix}.svg", s)


# ---------------------------------------------------------------- tech stack

def mono_badge(text: str, color: str, x: float, y: float, s: Svg, size=18) -> str:
    run, tw = s.glyph_runs(text, "b", 8.5, x + size / 2, y + size / 2 + 3.2, anchor="middle")
    return f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="5" fill="{color}"/><g fill="#fff">{run}</g>'


def chip_icon(kind, x, y, s: Svg) -> str:
    t, v = kind
    if t == "brand":
        return brand(v, x, y)
    if t == "line":
        return line_icon(v[0], x, y, 18, v[1], 2)
    if t == "mono":
        return mono_badge(v[0], v[1], x, y, s)
    if t == "chroma":  # three overlapping discs, after Chroma's mark
        return (f'<circle cx="{x + 6}" cy="{y + 9}" r="5.5" fill="#FFDE2D"/><circle cx="{x + 12}" cy="{y + 9}" r="5.5" fill="#327EFF" opacity=".9"/>'
                f'<circle cx="{x + 9}" cy="{y + 9}" r="2.6" fill="#FF6446"/>')
    if t == "graph":  # LangGraph has no Simple Icons entry: a small node graph instead
        return (f'<g fill="none" stroke="{SOFT}" stroke-width="1.5"><path d="M{x + 4} {y + 4} L{x + 14} {y + 9} L{x + 4} {y + 14}"/></g>'
                f'<circle cx="{x + 4}" cy="{y + 4}" r="2.6" fill="{SOFT}"/><circle cx="{x + 14}" cy="{y + 9}" r="2.6" fill="{CYAN}"/><circle cx="{x + 4}" cy="{y + 14}" r="2.6" fill="{SOFT}"/>')
    raise ValueError(kind)


B = lambda slug: ("brand", slug)
STACK = [
    ("brain-circuit", "AI & Machine Learning", "LLMs, RAG, agents & evaluation", [
        ("LangChain", B("langchain")), ("LangGraph", ("graph", None)), ("Gemini", B("googlegemini")), ("Claude", B("claude")),
        ("RAG", ("line", ("search", SKY))), ("ChromaDB", ("chroma", None)), ("Embeddings", ("line", ("layers", LILAC))),
        ("LLM Evaluation", ("line", ("flask-conical", CYAN))), ("Multi-Agent", ("line", ("network", SKY)))]),
    ("code-xml", "Languages", "Programming languages", [
        ("Python", B("python")), ("TypeScript", B("typescript")), ("JavaScript", B("javascript")), ("Java", B("openjdk")),
        ("C#", ("mono", ("C#", "#68217A"))), ("JSON", B("json"))]),
    ("monitor", "Frontend", "Interfaces and 3D on the web", [
        ("React", B("react")), ("Next.js", B("nextdotjs")), ("Astro", B("astro")), ("Vite", B("vite")), ("Three.js", B("threedotjs")),
        ("HTML5", B("html5")), ("CSS3", B("css3")), ("Tailwind", B("tailwindcss"))]),
    ("server", "Backend & APIs", "Services and frameworks", [
        ("Node.js", B("nodedotjs")), ("Spring", B("spring")), (".NET", B("dotnet")), ("FastAPI", B("fastapi")),
        ("Streamlit", B("streamlit")), ("Postman", B("postman"))]),
    ("database", "Databases", "Storage and retrieval", [
        ("PostgreSQL", B("postgresql")), ("MySQL", B("mysql")), ("MongoDB", B("mongodb")), ("SQLite", B("sqlite")), ("Firebase", B("firebase"))]),
    ("shield-check", "Testing & Quality", "Reliability, testing and code quality", [
        ("Pytest", B("pytest")), ("Playwright", ("mono", ("PW", "#2EAD33"))), ("Selenium", B("selenium")), ("Cucumber", B("cucumber")),
        ("mypy", ("mono", ("my", "#2A6DB2"))), ("Ruff", B("ruff"))]),
    ("cloud", "DevOps & Observability", "Infrastructure, monitoring & CI/CD", [
        ("Docker", B("docker")), ("Kubernetes", B("kubernetes")), ("GitHub Actions", B("githubactions")), ("Jenkins", B("jenkins")),
        ("Git", B("git")), ("GitHub", B("github")), ("Linux", B("linux")), ("Grafana", B("grafana")), ("Prometheus", B("prometheus"))]),
]


def tech_stack() -> None:
    chip_h, gap, x0, xmax, pad = 36, 10, 430, W - 26, 20
    rows, y = [], 0
    for icon, title, sub, items in STACK:
        lines, cx, line = [], x0, []
        for label, kind in items:
            cw = 40 + text_width(label, "m", 14) + 14
            if line and cx + cw > xmax:
                lines.append(line)
                line, cx = [], x0
            line.append((label, kind, cx, cw))
            cx += cw + gap
        lines.append(line)
        h = pad * 2 + len(lines) * chip_h + (len(lines) - 1) * gap
        rows.append((icon, title, sub, lines, y, h))
        y += h + 12
    H = y - 12 + 2
    alt = "Tech stack. " + " ".join(f"{t}: {', '.join(l for l, _ in it)}." for _, t, _, it in STACK)
    s = Svg(W, H, alt)
    stroke = s.gradient([(0, BLUE, 1), (1, LILAC, 1)], user=(0, 0, 24, 24))
    for icon, title, sub, lines, ry, h in rows:
        s.add(f'<rect x="1" y="{ry + 1}" width="{W - 2}" height="{h}" rx="16" fill="{PANEL}" stroke="{LINE}"/>')
        mid = ry + 1 + h / 2
        s.add(line_icon(icon, 30, mid - 18, 36, stroke, 1.7))
        s.text(title, 88, mid - 3, 18, "s", SKY)
        s.text(sub, 88, mid + 19, 13, "r", MUTE)
        for li, line in enumerate(lines):
            cy = ry + 1 + pad + li * (chip_h + gap)
            for label, kind, cx, cw in line:
                s.add(f'<rect x="{cx:.1f}" y="{cy}" width="{cw:.1f}" height="{chip_h}" rx="10" fill="{CHIP}" stroke="{LINE2}"/>')
                s.add(chip_icon(kind, cx + 13, cy + 9, s))
                s.text(label, cx + 40, cy + 23, 14, "m", TEXT)
    save("tech-stack.svg", s)


# ---------------------------------------------------------------- closing

def closing() -> None:
    H = 120
    s = Svg(W, H, "Open to AI Engineering and Software Engineering internships. Let's build AI that can show its work. Let's connect on LinkedIn.")
    s.css.append("@keyframes sweep{0%{stroke-dashoffset:0}100%{stroke-dashoffset:-1000}}"
                 ".sweep{animation:sweep 9s linear infinite}")
    s.add(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="{s.gradient([(0, "#14103E", 1), (.6, "#0C1233", 1), (1, "#0A1530", 1)], 0, 0, 1, 1)}" stroke="#2E2A72"/>')
    s.add(f'<rect class="sweep motion" x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="none" stroke="{LILAC}" stroke-width="1.6" '
          f'pathLength="1000" stroke-dasharray="90 910" opacity=".85"/>')
    s.add(f'<ellipse cx="200" cy="{H}" rx="320" ry="70" fill="{s.radial([(0, "#6D28D9", .25), (1, "#14103E", 0)])}"/>')
    s.add(line_icon("rocket", 44, 38, 42, s.gradient([(0, BLUE, 1), (1, LILAC, 1)], user=(0, 0, 24, 24)), 1.6))
    x = 112
    x += s.text("Open to ", x, 56, 22, "s", TEXT)
    x += s.gradient_text("AI Engineering & Software Engineering", x, 56, 22, "s", [(0, SKY, 1), (1, LILAC, 1)])
    s.text(" internships", x, 56, 22, "s", TEXT)
    s.text("Let's build AI that can show its work.", 113, 84, 15, "r", MUTE)
    bw = text_width("Let's Connect", "s", 15) + 84
    bx = W - 44 - bw
    s.add(f'<rect x="{bx:.0f}" y="34" width="{bw:.0f}" height="52" rx="26" fill="{s.gradient([(0, "#2563EB", 1), (1, "#4F46E5", 1)])}" stroke="#7DA2FF" stroke-opacity=".6"/>')
    s.add(f'<path transform="translate({bx + 24:.0f} 50) scale(.833)" fill="#fff" d="{KIT["brands"]["linkedin"][1]}"/>')
    s.text("Let's Connect", bx + 54, 65, 15, "s", "#fff")
    s.text("→", bx + 64 + text_width("Let's Connect", "s", 15), 65, 15, "s", "#fff")
    save("closing.svg", s)


def footer() -> None:
    H = 56
    for suffix, (_, _, soft, quiet, violet) in THEMES.items():
        s = Svg(W, H, "Umar Ahamed. Grounded. Observable. Tested.")
        s.css.append("@keyframes dot{0%,100%{opacity:.25}50%{opacity:1}}.d{animation:dot 2.4s ease-in-out infinite}")
        rule = LINE2 if not suffix else "#C9D1EA"
        s.add(f'<rect x="0" y="0" width="{W}" height="1" fill="{s.gradient([(0, rule, 0), (.5, rule, 1), (1, rule, 0)])}"/>')
        s.add(brand("github", 4, 18, 20).replace(f'fill="{SOFT}"', f'fill="{soft}"'))
        s.text("Umar Ahamed", 36, 34, 15, "m", soft)
        s.text("“Grounded. Observable. Tested.”", W / 2, 34, 14, "r", quiet, anchor="middle")
        for i in range(3):
            s.add(f'<circle class="d" style="animation-delay:{i * .4}s" cx="{W - 40 + i * 14}" cy="29" r="3" fill="{violet}"/>')
        save(f"footer{suffix}.svg", s)


def wordmark() -> None:
    s = Svg(120, 120, "Umar Ahamed monogram")
    s.add(f'<rect x="4" y="4" width="112" height="112" rx="30" fill="{PANEL}" stroke="{LINE2}"/>')
    s.gradient_text("UA", 60 - text_width("UA", "b", 50, -2) / 2, 78, 50, "b", [(0, BLUE, 1), (.55, "#7C6CFF", 1), (1, LILAC, 1)], track=-2)
    s.add(f'<circle cx="92" cy="30" r="3.5" fill="{CYAN}"/>')
    save("wordmark.svg", s)


# ---------------------------------------------------------------- stats (live data)

def fetch(url: str, accept="application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"{USER}-profile-build", "Accept": accept})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def public_calendar() -> list[tuple[dt.date, int, int]]:
    """The calendar exactly as an anonymous visitor sees it on the profile page."""
    page = fetch(f"https://github.com/users/{USER}/contributions", "text/html").decode("utf-8")
    counts = {}
    for cid, label in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        m = re.match(r"\s*(\d+) contributions?", label)
        counts[cid] = int(m.group(1)) if m else 0
    days = []
    for attrs in re.findall(r"<td\b([^>]*\bdata-date=[^>]*)>", page):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        days.append((dt.date.fromisoformat(a["data-date"]), int(a.get("data-level", 0)), counts.get(a.get("id"), 0)))
    days.sort()
    if len(days) < 300:
        raise RuntimeError(f"calendar parse looks wrong ({len(days)} days)")
    return days


def languages() -> tuple[list[tuple[str, float]], int]:
    repos = json.loads(fetch(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
    totals: dict[str, int] = {}
    for r in repos:
        if r["fork"] or r["name"] == USER:
            continue
        for lang, n in json.loads(fetch(r["languages_url"])).items():
            totals[lang] = totals.get(lang, 0) + n
    user = json.loads(fetch(f"https://api.github.com/users/{USER}"))
    total = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    top = [(k, v / total * 100) for k, v in ranked[:5]]
    rest = 100 - sum(p for _, p in top)
    if rest > 0.05:
        top.append(("Other", rest))
    return top, user["public_repos"]


LANG_COLORS = [BLUE, LILAC, CYAN, "#F59E0B", ROSE, DIM]
LEVELS = ["#111938", "#1E3A8A", "#3157D6", "#6A7CFF", "#B49CFF"]


def stats() -> None:
    days = public_calendar()
    langs, repos = languages()
    total = sum(c for _, _, c in days)
    active = sum(1 for _, _, c in days if c)
    longest = run = 0
    for _, _, c in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    today = dt.date.today().isoformat()
    H = 300
    lang_txt = ", ".join(f"{n} {p:.1f}%" for n, p in langs)
    s = Svg(W, H, f"GitHub stats from public data, updated {today}: {total} contributions in the last year, {active} active days, "
                  f"longest streak {longest} days, {repos} public repositories. Languages across original public repositories by bytes: {lang_txt}.")
    # left card: calendar
    LW = 760
    s.add(f'<rect x="1" y="1" width="{LW}" height="{H - 2}" rx="16" fill="{PANEL}" stroke="{LINE}"/>')
    s.add(brand("github", 28, 24, 22))
    s.text(USER, 60, 41, 16, "s", TEXT)
    metrics = [(f"{total}", "Contributions · 12 mo"), (f"{active}", "Active days"), (f"{longest}d", "Longest streak"), (f"{repos}", "Public repos")]
    for i, (v, l) in enumerate(metrics):
        x = 30 + i * 182
        s.text(v, x, 92, 28, "b", TEXT, track=-.5)
        s.text(l, x, 114, 12.5, "r", MUTE)
        if i:
            s.add(f'<rect x="{x - 18}" y="66" width="1" height="52" fill="{LINE2}"/>')
    gx, gy, cell, gap = 68, 140, 10, 3
    start = days[0][0]
    for d, lvl, _ in days:
        col = ((d - start).days + start.isoweekday() % 7) // 7
        row = d.isoweekday() % 7
        s.add(f'<rect x="{gx + col * (cell + gap)}" y="{gy + row * (cell + gap)}" width="{cell}" height="{cell}" rx="2.5" fill="{LEVELS[min(lvl, 4)]}"/>')
    for row, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        s.text(name, 30, gy + row * (cell + gap) + 9, 10.5, "r", DIM)
    seen = set()
    for d, _, _ in days:
        if d.day <= 7 and d.isoweekday() % 7 == 0 and d.month not in seen:
            seen.add(d.month)
            col = ((d - start).days + start.isoweekday() % 7) // 7
            s.text(d.strftime("%b"), gx + col * (cell + gap), gy + 7 * (cell + gap) + 14, 10.5, "r", DIM)
    s.text("less", 30, H - 24, 10, "r", DIM)
    for i, c in enumerate(LEVELS):
        s.add(f'<rect x="{58 + i * 14}" y="{H - 33}" width="10" height="10" rx="2.5" fill="{c}"/>')
    s.text("more", 132, H - 24, 10, "r", DIM)
    s.text(f"public contributions · updated {today}", LW - 24, H - 24, 10.5, "mono", DIM, anchor="end")
    # right card: languages
    x0 = LW + 20
    s.add(f'<rect x="{x0}" y="1" width="{W - x0 - 1}" height="{H - 2}" rx="16" fill="{PANEL}" stroke="{LINE}"/>')
    s.text("Top Languages", x0 + 26, 41, 16, "s", TEXT)
    s.text("original public repos, by bytes", x0 + 26, 62, 12, "r", MUTE)
    cx, cy, r = x0 + 100, 172, 64
    circ = 2 * math.pi * r
    acc = 0.0
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#111938" stroke-width="20"/>')
    for i, (name, p) in enumerate(langs):
        seg = circ * p / 100
        if seg > 0.4:
            s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{LANG_COLORS[i]}" stroke-width="20" '
                  f'stroke-dasharray="{max(seg - 1.5, .6):.2f} {circ:.2f}" stroke-dashoffset="{-acc:.2f}" transform="rotate(-90 {cx} {cy})"/>')
        acc += seg
    s.text(f"{langs[0][1]:.0f}%", cx, cy + 3, 22, "b", TEXT, anchor="middle")
    s.text(langs[0][0], cx, cy + 22, 11, "r", MUTE, anchor="middle")
    for i, (name, p) in enumerate(langs):
        ly = 112 + i * 26
        s.add(f'<circle cx="{x0 + 214}" cy="{ly - 4}" r="4.5" fill="{LANG_COLORS[i]}"/>')
        s.text(name, x0 + 228, ly, 13, "r", SOFT)
        s.text(f"{p:.1f}%", W - 26, ly, 13, "mono", MUTE, anchor="end")
    save("stats.svg", s)


BUILDERS = {"hero": hero, "typing": typing, "stack": tech_stack, "closing": closing, "footer": footer, "wordmark": wordmark, "stats": stats}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", choices=sorted(BUILDERS) + ["headers"])
    ap.add_argument("--offline", action="store_true", help="skip assets that need the network")
    a = ap.parse_args()
    names = a.only or (list(BUILDERS) + ["headers"])
    for n in names:
        if n == "stats" and a.offline:
            continue
        if n == "headers":
            header("stack", "Tech Stack", "layers", "Tools I use to build, ship and scale")
            header("stats", "GitHub Stats", "chart-column", "Public activity, refreshed daily")
            continue
        try:
            BUILDERS[n]()
        except Exception as e:  # network or parse failure must never leave a broken image behind
            if n != "stats":
                raise
            print(f"  stats skipped, keeping the previous stats.svg: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
