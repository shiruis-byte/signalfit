"""SignalFit look and shared pieces: colors and stylesheet, session state, small components, the outreach email box."""
import base64
import hashlib
import html
import json
import re
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

import engine


# ==================================================================
# Theme: colors, labels, stylesheet
# ==================================================================

INK, MUTED, LINE, SURFACE, ACCENT, MARKC = "#17151C", "#6E6B7B", "#ECEAF2", "#F6F5FA", "#FF5B2E", "#FFE0D4"
PINK, VIOLET = "#FF3D7F", "#7C5CFF"
GRAD = f"linear-gradient(120deg, {ACCENT} 0%, {PINK} 52%, {VIOLET} 100%)"   # the "signal" gradient


SUB_COLORS = {"content_relevance": "#3E6BE6", "audience_need": "#FF5B2E", "purchase_trust": "#17A974",
              "engagement_quality": "#F2B035", "community": "#8C63E8"}


SUBSCORES = {"content_relevance": "Content fit", "audience_need": "Audience need", "purchase_trust": "Purchase & trust",
             "engagement_quality": "Comment quality", "community": "Community"}


SUB_HELP = {
    "content_relevance": "How closely the creator's recent videos match your product's category.",
    "audience_need": "Comments describing the problem your product solves, plus product questions and personal experiences.",
    "purchase_trust": "Comments showing buying intent, or trust in the creator's advice.",
    "engagement_quality": "Meaningful comments, minus spam, copy-paste and empty praise.",
    "community": "Viewers who comment on several videos, plus comments and likes per 1,000 views.",
}


LABEL_NAMES = {"purchase_intent": "Wants to buy", "product_question": "Product question", "personal_experience": "Own experience",
               "creator_trust": "Trusts creator", "price_concern": "Price", "positive_reaction": "Generic praise",
               "complaint": "Complaint", "spam": "Spam"}


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700;12..96,800&display=swap');
html, body, .stApp, [data-testid="stMarkdownContainer"], button, input, textarea, select, label, [data-baseweb] {{
  font-family: 'Geist', system-ui, -apple-system, sans-serif; }}
.stApp {{ background: radial-gradient(#E7E4F0 1px, transparent 1.2px) 0 0 / 22px 22px, #FCFBFF; color: {INK}; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"], [data-testid="stHeader"], [data-testid="stToolbar"] {{ display: none; }}
.block-container {{ padding-top: 1.2rem; max-width: 1120px; }}
h1, h2, h3, h4 {{ font-family: 'Bricolage Grotesque', 'Geist', sans-serif !important; color: {INK}; letter-spacing: -0.03em; font-weight: 750 !important; }}
.sf-disp {{ font-family: 'Bricolage Grotesque', 'Geist', sans-serif; }}
a {{ color: {INK}; }}

.sf-who {{ text-align:right; color:{MUTED}; font-size:.85rem; line-height:1.4; }}
.sf-who span {{ color:#9A9CA5; }}
.sf-rule {{ border-bottom:1px solid {LINE}; margin: .3rem 0 1.4rem; }}
.sf-login-side h1 {{ font-size: clamp(2.2rem, 4.4vw, 3.4rem); line-height:1; margin:.8rem 0 1rem; }}
.sf-login-side h1 em {{ font-style:normal; background:{GRAD}; -webkit-background-clip:text; background-clip:text; color:transparent; }}
.sf-login-side p {{ color:{MUTED}; font-size:1.05rem; line-height:1.55; max-width: 30rem; }}
.sf-login-side ul {{ padding-left: 1.1rem; color:{INK}; line-height:1.8; margin: .8rem 0 1.4rem; }}
.sf-demo-q {{ border:1px solid {LINE}; border-radius:14px; padding:.9rem 1rem; max-width: 30rem; background:#fff; }}
.sf-demo-q small {{ display:block; color:{MUTED}; margin-top:.4rem; font-size:.8rem; }}
.sf-login-title {{ font-weight:650; font-size:1.25rem; letter-spacing:-0.02em; margin:0 0 .2rem; }}
.sf-nav {{ display:flex; align-items:center; justify-content:space-between; padding: .2rem 0 1.1rem; border-bottom: 1px solid {LINE}; margin-bottom: 1.4rem; }}
.sf-logo {{ font-weight: 700; font-size: 1.2rem; letter-spacing: -0.03em; display:flex; align-items:center; gap:.45rem; }}
.sf-logo i {{ display:inline-flex; gap:2px; align-items:flex-end; height:16px; }}
.sf-logo {{ font-family:'Bricolage Grotesque', 'Geist', sans-serif; font-weight:800; font-size:1.35rem; }}
.sf-logo i b {{ width:4px; background:{GRAD}; border-radius:2px; display:block; }}
.sf-live {{ display:inline-block; width:.5rem; height:.5rem; border-radius:50%; background:#22C55E; margin-right:.4rem; vertical-align:1px;
  box-shadow:0 0 0 0 rgba(34,197,94,.6); }}
.sf-nav span.tag {{ color:{MUTED}; font-size:.9rem; }}

/* landing */
.sf-land {{ max-width: 760px; margin: 2.2rem auto 1.6rem; text-align: center; }}
.sf-land h1 {{ font-size: clamp(2.4rem, 6vw, 4.3rem); line-height: .98; margin: 0 0 1rem; }}
.sf-land h1 em {{ font-style:normal; background:{GRAD}; -webkit-background-clip:text; background-clip:text; color:transparent; }}
.sf-eyebrow {{ display:inline-flex; align-items:center; gap:.45rem; background:#fff; border:1px solid {LINE}; border-radius:999px;
  padding:.3rem .8rem; font-size:.85rem; color:{MUTED}; margin-bottom:1.1rem; box-shadow:0 2px 10px rgba(23,21,28,.04); }}
.sf-land p {{ color:{MUTED}; font-size: 1.12rem; line-height:1.55; margin: 0 auto; max-width: 600px; }}
[data-testid="stForm"] {{ border: 1px solid {LINE}; border-radius: 24px; padding: 1.6rem 1.6rem 1.2rem; background: #fff;
  box-shadow: 0 1px 2px rgba(23,21,28,.04), 0 18px 50px rgba(124,92,255,.10); }}
[data-testid="stForm"] label p {{ font-weight: 550; color: {INK}; }}
.stTextInput input, .stTextArea textarea, .stNumberInput input {{ border-radius: 10px !important; }}
[data-testid="stFormSubmitButton"] button, .stButton button[kind="primary"] {{ background:{GRAD}; border:none; color:#fff; border-radius: 12px;
  font-weight: 650; padding: .6rem 1.2rem; box-shadow: 0 6px 20px rgba(255,61,127,.28); }}
[data-testid="stFormSubmitButton"] button:hover, .stButton button[kind="primary"]:hover {{ filter: brightness(1.06) saturate(1.05); color:#fff; border:none; }}
.stButton button {{ border-radius: 12px; font-weight: 550; background:#fff; }}
.stButton button[kind="secondary"]:hover {{ border-color:{PINK}; color:{PINK}; }}
.sf-tpl {{ color:{MUTED}; font-size:.9rem; margin: 0 0 .4rem; }}
.sf-card {{ border:1px solid {LINE}; border-radius:22px; padding:1rem 1.05rem; background:#fff; box-shadow:0 10px 30px rgba(23,21,28,.05); }}
.sf-card .who {{ display:flex; gap:.7rem; align-items:center; margin-bottom:.8rem; }}
.sf-card .nm {{ font-weight:650; line-height:1.2; }}
.sf-card .nm small {{ display:block; color:{MUTED}; font-weight:400; font-size:.8rem; margin-top:.1rem; }}
.sf-card .sc {{ margin-left:auto; font-size:1.8rem; font-weight:700; letter-spacing:-0.04em; }}
.sf-kv {{ display:flex; justify-content:space-between; font-size:.88rem; padding:.3rem 0; border-top:1px solid {LINE}; }}
.sf-kv span:first-child {{ color:{MUTED}; }}
.sf-tour {{ max-width: 720px; margin: 1.2rem auto 0; background:#fff; border:1px solid {LINE}; border-radius:28px; padding:2rem 2.2rem 1.4rem;
  box-shadow: 0 24px 60px rgba(124,92,255,.12); }}
.sf-tour h1 {{ font-size: clamp(1.8rem, 3.6vw, 2.5rem); line-height:1.05; margin:.4rem 0 .7rem; }}
.sf-tour p {{ color:{MUTED}; font-size:1.04rem; line-height:1.6; }}
.sf-dots {{ display:flex; gap:.4rem; }}
.sf-dots i {{ width:28px; height:5px; border-radius:3px; background:#E6E3EF; display:block; }}
.sf-dots i.on {{ background:{GRAD}; }}
.sf-step-k {{ color:{MUTED}; font-size:.85rem; font-weight:600; margin-top:.9rem; }}
.sf-demo {{ background:{SURFACE}; border-radius:20px; padding:1rem; margin:1rem 0 .4rem; display:flex; flex-direction:column; gap:.55rem; }}
.sf-demo .sf-bub {{ white-space:normal; align-self:flex-start; }}
.sf-demo-row {{ display:flex; gap:.8rem; align-items:center; flex-wrap:wrap; }}
.sf-fake {{ background:#fff; border:1px solid {LINE}; border-radius:12px; padding:.55rem .8rem; font-size:.9rem; }}
.sf-fake small {{ display:block; color:{MUTED}; font-size:.75rem; }}
.sf-method {{ max-width: 860px; margin: 0 auto; }}
.sf-method h1 {{ font-size: clamp(2rem, 4vw, 2.8rem); line-height:1.05; margin:.2rem 0 .6rem; }}
.sf-msec {{ background:#fff; border:1px solid {LINE}; border-radius:22px; padding:1.1rem 1.3rem; margin:.8rem 0; }}
.sf-msec h3 {{ font-size:1.2rem; margin:0 0 .4rem; }}
.sf-msec, .sf-msec p {{ color:#3B3946; line-height:1.6; font-size:.97rem; }}
.sf-mrow {{ display:grid; grid-template-columns:1.2rem 1fr; gap:.4rem; padding:.45rem 0; border-top:1px solid {LINE}; }}
.sf-mrow span {{ display:block; color:{MUTED}; font-size:.93rem; }}
.sf-mnote {{ color:{MUTED}; font-size:.88rem; margin:.6rem 0 0; }}
.sf-mtab {{ border-collapse:collapse; width:100%; max-width:480px; font-size:.93rem; }}
.sf-mtab th, .sf-mtab td {{ text-align:left; padding:.35rem .6rem; border-bottom:1px solid {LINE}; }}
.sf-mtab th {{ color:{MUTED}; font-weight:600; }}
.sf-math {{ width:100%; border-collapse:collapse; font-size:.93rem; }}
.sf-math td {{ padding:.35rem .5rem; border-bottom:1px solid {LINE}; }}
.sf-math td:not(:first-child) {{ text-align:right; font-variant-numeric: tabular-nums; }}
.sf-math tr.total td {{ font-weight:750; border-bottom:none; font-size:1.05rem; }}
.sf-lab {{ background:#fff; border:1px solid {LINE}; border-radius:22px; padding:1.3rem 1.4rem; margin:.6rem 0 1rem;
  box-shadow:0 14px 40px rgba(124,92,255,.08); }}
.sf-lab .c {{ font-size:1.15rem; line-height:1.55; }}
.sf-lab .meta {{ color:{MUTED}; font-size:.82rem; margin-bottom:.6rem; }}
.sf-prog {{ height:6px; border-radius:3px; background:#EFEDF5; overflow:hidden; margin:.3rem 0 .2rem; }}
.sf-prog i {{ display:block; height:100%; background:{GRAD}; }}
.sf-ex-title {{ text-align:center; color:{MUTED}; margin: 1.8rem 0 .7rem; font-size:.95rem; }}

/* results header */
.sf-brief h1 {{ font-size: clamp(1.6rem, 3.2vw, 2.3rem); margin:0; line-height:1.15; }}
.sf-sub {{ color:{MUTED}; font-size: .98rem; margin: .35rem 0 1rem; line-height:1.6; }}
.sf-chip {{ display:inline-block; background:{SURFACE}; border:1px solid {LINE}; border-radius:999px; padding:.08rem .6rem; font-size:.8rem; color:{INK}; margin: 0 .25rem .25rem 0; }}
.sf-chip.hot {{ background:{INK}; border-color:{INK}; color:#fff; }}
.sf-banner {{ background:#FFF6E0; border:1px solid #F3D48A; color:#6A4B00; padding:.6rem .9rem; border-radius:10px; font-size:.9rem; margin-bottom:1rem; }}

/* top picks */
.sf-picks {{ display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 1rem; margin: .4rem 0 1.6rem; }}
.sf-pick {{ border:1px solid {LINE}; border-radius:22px; padding: 1.15rem 1.2rem; background:#fff; display:flex; flex-direction:column; gap:.8rem;
  box-shadow: 0 10px 30px rgba(23,21,28,.05); }}
.sf-pick.first {{ border:2px solid transparent; background: linear-gradient(#fff,#fff) padding-box, {GRAD} border-box;
  box-shadow: 0 16px 40px rgba(255,61,127,.16); }}
.sf-badge {{ display:inline-block; align-self:flex-start; border-radius:999px; padding:.15rem .65rem; font-size:.78rem; font-weight:650;
  background:{SURFACE}; color:{MUTED}; }}
.sf-pick.first .sf-badge {{ background:{GRAD}; color:#fff; }}
.sf-ringav {{ display:inline-flex; padding:2.5px; border-radius:50%; background:{GRAD}; flex:0 0 auto; }}
.sf-ringav .sf-av {{ border:2.5px solid #fff; }}
.sf-ring {{ --p:0; width:62px; height:62px; flex:0 0 62px; margin-left:auto; border-radius:50%; position:relative; display:grid; place-items:center;
  background: conic-gradient({ACCENT} 0%, {PINK} calc(var(--p) * .5%), {VIOLET} calc(var(--p) * 1%), #EEEDF4 calc(var(--p) * 1%)); }}
.sf-ring::before {{ content:""; position:absolute; inset:6px; border-radius:50%; background:#fff; }}
.sf-ring span {{ position:relative; font-family:'Bricolage Grotesque','Geist',sans-serif; font-weight:800; font-size:1.35rem; letter-spacing:-0.04em; }}
.sf-pick .who {{ display:flex; gap:.7rem; align-items:center; }}
.sf-pick .nm {{ font-weight:650; line-height:1.2; }}
.sf-pick .nm small {{ display:block; color:{MUTED}; font-weight:400; font-size:.82rem; margin-top:.1rem; }}
.sf-pick .sc {{ margin-left:auto; text-align:right; font-size:2rem; font-weight:700; letter-spacing:-0.04em; line-height:1; }}
.sf-pick .sc small {{ display:block; font-size:.72rem; color:{MUTED}; font-weight:500; letter-spacing:0; margin-top:.2rem; }}
.sf-pick .q {{ font-size:.93rem; line-height:1.5; color:{INK}; }}
.sf-pick .rank {{ font-size:.8rem; color:{MUTED}; font-weight:550; }}
.sf-pick .q {{ background:{SURFACE}; border-radius:16px 16px 16px 4px; padding:.65rem .8rem; }}

mark.sf {{ background: linear-gradient(transparent 8%, {MARKC} 8%, #FFD9EA 92%, transparent 92%); color:{INK}; padding: 0 .15em; border-radius: 3px; }}
.sf-wall {{ position:relative; overflow:hidden; padding:.4rem 0; margin: 1.6rem auto .4rem; max-width: 1100px;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 9%, #000 91%, transparent); mask-image: linear-gradient(90deg, transparent, #000 9%, #000 91%, transparent); }}
.sf-track {{ display:flex; gap:.75rem; width:max-content; padding:.35rem 0; }}
.sf-bub {{ display:inline-flex; align-items:center; gap:.55rem; white-space:nowrap; background:#fff; border:1px solid {LINE};
  border-radius:18px 18px 18px 5px; padding:.5rem .8rem; font-size:.9rem; box-shadow:0 4px 14px rgba(23,21,28,.05); }}
.sf-bub b {{ font-weight:600; font-size:.72rem; border-radius:999px; padding:.1rem .5rem; color:#fff; background:{GRAD}; }}
.sf-bub.noise {{ opacity:.5; }}
.sf-bub b, .sf-bub small {{ flex:0 0 auto; white-space:nowrap; }}
.sf-bub.noise b {{ background:#C9C6D3; }}
.sf-bub small {{ color:{MUTED}; font-size:.75rem; }}
.sf-wall-cap {{ text-align:center; color:{MUTED}; font-size:.85rem; margin-bottom:1rem; }}
.sf-quote {{ background:{SURFACE}; border-radius:12px; padding:.75rem .9rem; margin:.5rem 0; line-height:1.5; font-size:.95rem; }}
.sf-quote .meta {{ color:{MUTED}; font-size:.78rem; margin-top:.45rem; }}

.sf-av {{ width:42px; height:42px; border-radius:50%; flex:0 0 42px; background:#ECEDF1 center/cover no-repeat; display:flex;
         align-items:center; justify-content:center; font-weight:650; color:{INK}; font-size:.9rem; }}
.sf-av img {{ width:100%; height:100%; border-radius:50%; object-fit:cover; display:block; }}
.sf-av.lg {{ width:60px; height:60px; flex-basis:60px; font-size:1.2rem; }}

.sf-list {{ border-top:1px solid {LINE}; }}
.sf-rowl {{ display:flex; gap:.8rem; align-items:center; }}
.sf-rowl .rk {{ color:{MUTED}; font-weight:600; width:1.4rem; text-align:right; flex:0 0 1.4rem; }}
.sf-rowl .nm {{ font-weight:600; line-height:1.25; }}
.sf-rowl .nm small {{ display:block; color:{MUTED}; font-weight:400; font-size:.82rem; margin-top:.12rem; }}
.sf-rowsc {{ font-family:'Bricolage Grotesque','Geist',sans-serif; font-weight:800; font-size:1.55rem; letter-spacing:-0.04em; text-align:right; }}
.sf-rowline {{ border-bottom:1px solid {LINE}; margin:.15rem 0 .35rem; }}
.sf-row {{ display:grid; grid-template-columns: 1.6rem 42px minmax(0,1.5fr) minmax(0,2.2fr) 3.4rem; gap:1rem; align-items:center; padding:.85rem .2rem; border-bottom:1px solid {LINE}; }}
.sf-row .rk {{ color:{MUTED}; font-weight:600; text-align:right; }}
.sf-row .nm {{ font-weight:600; line-height:1.25; }}
.sf-row .nm small {{ display:block; color:{MUTED}; font-weight:400; font-size:.82rem; margin-top:.12rem; }}
.sf-row .sc {{ font-weight:700; font-size:1.45rem; letter-spacing:-0.03em; text-align:right; }}
.sf-bar {{ display:flex; height:10px; border-radius:5px; overflow:hidden; background:#EFEDF5; gap:2px; }}
.sf-bar i {{ border-radius:3px; }}
.sf-bar i {{ display:block; height:100%; }}
.sf-tags {{ margin-top:.45rem; }}
.sf-legend {{ display:flex; flex-wrap:wrap; gap:.4rem 1rem; font-size:.84rem; color:{MUTED}; margin:.2rem 0 .8rem; }}
.sf-legend b {{ display:inline-block; width:.65rem; height:.65rem; border-radius:50%; margin-right:.35rem; vertical-align:0; }}

.sf-head {{ display:flex; gap:1rem; align-items:center; margin:.6rem 0 1.1rem; }}
.sf-head h2 {{ margin:0; font-size:1.7rem; padding:0; }}
.sf-head .sub {{ color:{MUTED}; font-size:.92rem; }}
.sf-ids {{ color:{MUTED}; font-size:.85rem; margin:-.5rem 0 1rem; }}
.sf-ids code {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:6px; padding:.1rem .4rem; color:{INK}; font-size:.82rem; user-select:all; }}
.stDownloadButton button {{ border-radius:10px; font-weight:550; }}
.sf-fact {{ border:1px solid {LINE}; border-radius:18px; padding:.9rem 1rem; height:100%; background:#fff; }}
.sf-fact .v {{ font-family:'Bricolage Grotesque','Geist',sans-serif; font-weight:800; font-size:1.75rem; letter-spacing:-0.04em; line-height:1.1; }}
.sf-fact .k {{ color:{MUTED}; font-size:.84rem; margin-top:.15rem; line-height:1.4; }}
.sf-meter {{ margin:.2rem 0 1rem; }}
.sf-meter .top {{ display:flex; justify-content:space-between; font-size:.92rem; font-weight:550; }}
.sf-meter .track {{ height:6px; background:#F0F0F3; border-radius:3px; margin-top:.35rem; overflow:hidden; }}
.sf-meter .fill {{ height:100%; border-radius:3px; }}
.sf-meter .help {{ color:{MUTED}; font-size:.8rem; margin-top:.3rem; line-height:1.4; }}
.sf-claim {{ margin:.9rem 0 .1rem; font-weight:600; }}
.sf-video {{ padding:.5rem 0; border-top:1px solid {LINE}; font-size:.92rem; display:flex; justify-content:space-between; gap:1rem; }}
.sf-video a {{ text-decoration:none; }}
.sf-video span {{ color:{MUTED}; white-space:nowrap; }}
.sf-step {{ display:grid; grid-template-columns: 1.8rem 1fr; gap:.5rem; padding:.75rem 0; border-top:1px solid {LINE}; }}
.sf-step .n {{ width:1.5rem; height:1.5rem; border-radius:50%; background:{SURFACE}; border:1px solid {LINE}; font-size:.8rem; font-weight:650;
              display:flex; align-items:center; justify-content:center; }}
.sf-step b {{ display:block; font-weight:600; }}
.sf-step span {{ color:{MUTED}; font-size:.92rem; line-height:1.45; }}
.stTabs [data-baseweb="tab-list"] {{ gap:.3rem; background:#F1EFF7; padding:.3rem; border-radius:999px; width:fit-content; max-width:100%; overflow-x:auto; }}
.stTabs [data-baseweb="tab"] {{ font-weight:600; padding:.45rem 1rem; border-radius:999px; height:auto; }}
.stTabs [aria-selected="true"] {{ background:#fff; box-shadow:0 2px 10px rgba(23,21,28,.08); }}
.stTabs [aria-selected="true"] p {{ color:{INK}; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}
.stTabs [role="tablist"] {{ gap:.3rem; background:#F1EFF7; padding:.3rem; border-radius:999px; width:fit-content; max-width:100%;
  overflow-x:auto; border:none !important; box-shadow:none; }}
.stTabs [role="tab"] {{ padding:.45rem 1rem; border-radius:999px; font-weight:600; border:none !important; }}
.stTabs [role="tab"][aria-selected="true"] {{ background:#fff; box-shadow:0 2px 10px rgba(23,21,28,.08); }}
.stTabs [role="tab"] p {{ font-weight:600; }}
.stTabs .react-aria-SelectionIndicator {{ display:none; }}
.stTabs [data-orientation="horizontal"] {{ border-bottom:none !important; box-shadow:none; }}
@media (max-width: 760px) {{
  .sf-picks {{ grid-template-columns: 1fr; }}
  .sf-row {{ grid-template-columns: 1.3rem 40px minmax(0,1fr) 2.8rem; gap:.6rem; }}
  .sf-row .barcell {{ grid-column: 2 / -1; }}
  .block-container {{ padding-left:1rem; padding-right:1rem; }}
  [data-testid="stForm"] {{ padding: 1.1rem 1rem .8rem; }}
}}
@media (prefers-reduced-motion: no-preference) {{
  .sf-track {{ animation: sfscroll 46s linear infinite; }}
  .sf-track.rev {{ animation-duration: 58s; animation-direction: reverse; }}
  .sf-wall:hover .sf-track {{ animation-play-state: paused; }}
  @keyframes sfscroll {{ to {{ transform: translateX(-50%); }} }}
  .sf-live {{ animation: sfpulse 1.8s ease-out infinite; }}
  @keyframes sfpulse {{ to {{ box-shadow: 0 0 0 7px rgba(34,197,94,0); }} }}
  .sf-bar i {{ animation: sfgrow .7s cubic-bezier(.2,.7,.2,1) both; transform-origin:left; }}
  @keyframes sfgrow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
}}
</style>
"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


# ==================================================================
# Session state, secrets, templates
# ==================================================================

DATA = Path(__file__).resolve().parent / "app_data"


ss = st.session_state


def init_state():
    ss.setdefault("view", "home")
    ss.setdefault("result", None)
    ss.setdefault("form", {"product": "", "keywords": "", "target_audience": "", "audience_need_keywords": "", "budget_usd": 30000, "goal": "Conversion"})
    ss.setdefault("emails", {})
    ss.setdefault("brand", "")


def secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return ""


def examples():
    if not DATA.exists():
        return {}
    return {p.name: p for p in sorted(DATA.iterdir()) if p.is_dir() and (p / "features.csv").exists()}


@st.cache_data(show_spinner=False)
def load_example(path_str):
    return engine.load_example(Path(path_str))


def brief_key(b):
    return hashlib.md5(json.dumps(b, sort_keys=True).encode()).hexdigest()


TEMPLATES = {
    "Skincare": {"product": "Fragrance-free gentle cleanser for sensitive skin",
                 "keywords": "sensitive skin routine, gentle cleanser review, dermatologist skincare",
                 "target_audience": "Gen Z consumers with sensitive, reactive or acne-prone skin",
                 "audience_need_keywords": "redness, stinging, irritation, damaged skin barrier, eczema, rosacea, breakouts, fragrance-free"},
    "Running": {"product": "Lightweight cushioned running shoe for beginner runners",
                "keywords": "best running shoes for beginners, running shoe review, beginner running tips",
                "target_audience": "New runners training for their first 5K to half marathon",
                "audience_need_keywords": "shin splints, knee pain, plantar fasciitis, blisters, wide feet, sizing, cushioning"},
    "Fitness nutrition": {"product": "Plant-based protein powder for women who lift",
                          "keywords": "vegan protein powder review, protein powder taste test, high protein meal prep",
                          "target_audience": "Women in their 20s starting strength training",
                          "audience_need_keywords": "bloating from whey, chalky taste, not enough protein on a vegan diet, muscle recovery"},
    "Tech": {"product": "Noise-cancelling wireless earbuds under $100",
             "keywords": "budget earbuds review, best wireless earbuds, airpods alternative",
             "target_audience": "College students who commute and study in noisy places",
             "audience_need_keywords": "battery life, noise cancelling, earbuds falling out, call quality, too expensive compared to AirPods"},
}


def use_template(name):
    ss.form = {**ss.form, **TEMPLATES[name]}


def toggle_shortlist(key, cid):
    cur = list(ss.get(key, []))
    ss[key] = [c for c in cur if c != cid] if cid in cur else cur + [cid]


def add_many(key, cids):
    cur = list(ss.get(key, []))
    ss[key] = cur + [c for c in cids if c not in cur]


def sign_out():
    for k in ["user", "result", "emails", "toured", "tour_step"]:
        ss.pop(k, None)
    ss.view = "home"


# ==================================================================
# Components
# ==================================================================

def show_df(df, **kw):
    """Full-width table on both new (width=) and older (use_container_width=) Streamlit versions."""
    try:
        return st.dataframe(df, width="stretch", **kw)
    except TypeError:
        return st.dataframe(df, use_container_width=True, **kw)


def show_chart(chart, **kw):
    try:
        return st.altair_chart(chart, width="stretch", **kw)
    except TypeError:
        return st.altair_chart(chart, use_container_width=True, **kw)


STOP = {"with", "after", "skin", "the", "and", "for", "from", "first", "your", "that", "this", "their"}


def need_terms(brief):
    terms = set()
    for phrase in engine.need_text(brief).split(","):
        phrase = phrase.strip().lower()
        if phrase:
            terms.add(phrase)
            terms.update(w for w in re.findall(r"[a-z\-]{4,}", phrase) if w not in STOP)
    return sorted(terms, key=len, reverse=True)


def highlight(text, terms):
    safe = html.escape(str(text))
    if not terms:
        return safe
    return re.sub(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\w*", lambda m: f'<mark class="sf">{m.group(0)}</mark>', safe, flags=re.I)


def initials(name):
    parts = re.findall(r"[A-Za-z0-9]+", str(name))
    return html.escape("".join(p[0] for p in parts[:2]).upper() or "?")


@st.cache_data(show_spinner=False, ttl=7 * 24 * 3600)
def thumb_data_uri(url):
    """Fetch a channel picture on the server and inline it, so the browser never has to hotlink YouTube's image host."""
    try:
        r = requests.get(url, timeout=4)
        kind = r.headers.get("content-type", "")
        if r.status_code == 200 and kind.startswith("image/") and len(r.content) < 400_000:
            return f"data:{kind.split(';')[0]};base64,{base64.b64encode(r.content).decode()}"
    except Exception:
        pass
    return ""


def avatar(row, size="", ring=False):
    url = str(row.get("thumbnail", "") or "")
    src = thumb_data_uri(url) if url.startswith("https://") else ""
    inner = (f'<div class="sf-av {size}"><img src="{src}" alt=""></div>' if src
             else f'<div class="sf-av {size}">{initials(row["creator_name"])}</div>')
    return f'<div class="sf-ringav">{inner}</div>' if ring else inner


def score_ring(value):
    v = 0 if pd.isna(value) else float(value)
    return f'<div class="sf-ring" style="--p:{v:.0f}"><span>{v:.0f}</span></div>'


WALL = [  # illustrative comments: the kind SignalFit counts as signal, and the noise it ignores
    ("I have <mark class='sf'>sensitive skin</mark> and everything stings. Would this work for me?", "Needs it", "2.1K"),
    ("so pretty 😍😍", "Noise", "12"),
    ("Just ordered it because you recommended it!", "Wants to buy", "864"),
    ("Whey always makes me <mark class='sf'>bloated</mark>. Is this one different?", "Needs it", "1.3K"),
    ("first!!", "Noise", "3"),
    ("You're the only reviewer I trust for this stuff", "Trusts creator", "540"),
    ("My <mark class='sf'>knees hurt</mark> after every 5K. Which shoe do you run in?", "Needs it", "977"),
    ("Are these worth $140 or should I wait for a sale?", "Price", "402"),
    ("Do these earbuds <mark class='sf'>fall out</mark> when you run?", "Needs it", "688"),
    ("sub to my channel for daily vlogs!!", "Noise", "1"),
    ("Where can I buy this in Canada?", "Wants to buy", "1.1K"),
    ("<mark class='sf'>Thinning hair</mark> at 24. Did minoxidil actually work for you?", "Needs it", "2.6K"),
]


def comment_wall(caption="SignalFit reads comments like these and tells signal from noise"):
    def bubbles(items):
        return "".join(f'<span class="sf-bub{" noise" if tag == "Noise" else ""}"><span class="t">{text}</span><b>{tag}</b><small>♥ {likes}</small></span>'
                       for text, tag, likes in items)
    a, b = WALL[::2], WALL[1::2]
    return (f'<div class="sf-wall"><div class="sf-track">{bubbles(a) * 2}</div>'
            f'<div class="sf-track rev">{bubbles(b) * 2}</div></div><div class="sf-wall-cap">{caption}</div>')


def handle_of(row):
    h = str(row.get("handle", "") or "").strip()
    return "" if not h or h == "nan" else (h if h.startswith("@") else "@" + h)


def channel_url(cid, row=None):
    h = handle_of(row) if row is not None else ""
    return f"https://www.youtube.com/{h}" if h else f"https://www.youtube.com/channel/{cid}"


def shortlist_csv(elig, weights):
    out = pd.DataFrame({
        "rank": range(1, len(elig) + 1), "creator": elig["creator_name"].values,
        "handle": [handle_of(r) for _, r in elig.iterrows()], "channel_id": elig.index,
        "channel_url": [channel_url(c, r) for c, r in elig.iterrows()],
        "subscribers": elig["subscribers"].astype(int).values, "est_cost_usd": elig["est_cost"].round(0).astype(int).values,
        "match_score": elig["match_score"].values, "points_per_1k_usd": elig["value_per_1k"].round(2).values,
        **{SUBSCORES[k].lower().replace(" & ", "_").replace(" ", "_"): elig[k].round(1).values for k in weights},
        "repeat_commenters": elig["loyalty_ratio"].round(3).values, "comments_read": elig["n_comments"].astype(int).values,
    })
    return out.to_csv(index=False).encode()


def fmt_n(x):
    x = float(x)
    return f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.0f}K" if x >= 1e3 else f"{x:.0f}"


def chips(row):
    hot = {"purchase_intent", "creator_trust"}
    return "".join(f'<span class="sf-chip{" hot" if l in hot else ""}">{LABEL_NAMES[l]}</span>' for l in engine.LABELS if int(row.get(l, 0) or 0) == 1)


def quote(row, terms, n=380):
    need = '<span class="sf-chip">Matches the audience need</span>' if int(row.get("need_match", 0) or 0) == 1 else ""
    return (f'<div class="sf-quote">“{highlight(str(row["text"])[:n], terms)}”'
            f'<div class="meta">{int(row.get("likes", 0))} likes &nbsp; {chips(row)}{need}</div></div>')


def score_bar(row, weights):
    return '<div class="sf-bar">' + "".join(
        f'<i style="width:{weights[k] * row[k]:.2f}%;background:{SUB_COLORS[k]}" title="{SUBSCORES[k]}: {weights[k] * row[k]:.1f} points"></i>'
        for k in weights) + "</div>"


def legend(weights):
    return '<div class="sf-legend">' + "".join(
        f'<span><b style="background:{SUB_COLORS[k]}"></b>{SUBSCORES[k]} {weights[k]:.0%}</span>' for k in weights) + "</div>"


def meter(label, value, color, help_text):
    return (f'<div class="sf-meter"><div class="top"><span>{label}</span><span>{value:.0f}</span></div>'
            f'<div class="track"><div class="fill" style="width:{max(value, 1):.1f}%;background:{color}"></div></div>'
            f'<div class="help">{help_text}</div></div>')


def fact(value, label):
    return f'<div class="sf-fact"><div class="v">{value}</div><div class="k">{label}</div></div>'


LOGO = '<div class="sf-logo"><i><b style="height:6px"></b><b style="height:11px"></b><b style="height:16px"></b></i>SignalFit</div>'


def open_view(view):
    if ss.get("view") not in ("method", "label"):
        ss.prev_view = ss.get("view", "home")
    ss.view = view


def nav(right=""):
    user = ss.get("user") or {}
    left, mid, lb, hb, rb = st.columns([1.5, 2.3, 1.45, 1.65, 1], vertical_alignment="center")
    left.markdown(LOGO, unsafe_allow_html=True)
    who = f'{html.escape(user.get("brand", ""))} workspace, signed in as {html.escape(user.get("name", ""))}' if user else ""
    mid.markdown(f'<div class="sf-who">{who}<br><span>{right}</span></div>', unsafe_allow_html=True)
    if user:
        lb.button("Label comments", on_click=open_view, args=("label",), use_container_width=True, key="nav_label")
        hb.button("How scoring works", on_click=open_view, args=("method",), use_container_width=True, key="nav_method")
        rb.button("Sign out", on_click=sign_out, use_container_width=True, key="signout")
    st.markdown('<div class="sf-rule"></div>', unsafe_allow_html=True)


# ==================================================================
# Privacy notice and method explainer
# ==================================================================

PRIVACY_NOTICE = """
**What you give us.** Your name, work email and brand, used only to personalise this session (for example the sign-off in
outreach emails). They live in your browser session and are not written to a database.

**What we analyse.** Public YouTube data: channel details, recent videos and public top comments, fetched through the
official YouTube Data API.

**Who processes it.** Comment text and your brief are sent to Google's Gemini API to label comments and to write
explanations and email drafts. Google's API terms apply to that processing.

**What is stored.** To keep repeat searches fast, API responses, your search briefs and their results are cached on the
app's server. The cache holds public comments and public channel IDs, not your name or email.

**Your choices.** Sign out at any time to clear your session. Please don't enter confidential product details.

SignalFit is a student prototype built for USC COMM 586. It is not a commercial service.
"""


def method_sections(weights_conv, weights_aware):
    """(title, html) blocks explaining exactly how a match score is built."""
    pct = lambda w: f"{w * 100:.0f}%"
    rows = "".join(f'<tr><td>{SUBSCORES[k]}</td><td>{pct(weights_conv[k])}</td><td>{pct(weights_aware[k])}</td></tr>' for k in SUBSCORES)
    subs = [
        ("content_relevance", "How closely the creator's recent videos match your category. In a live search Gemini rates the titles of their "
                              "5 latest videos from 0 to 100; prepared examples use MiniLM text similarity on titles, descriptions and tags."),
        ("audience_need", "50% the share of comments that describe your audience's struggle, plus 25% product questions and 25% personal "
                          "experiences. This is the clearest sign that the audience needs the product."),
        ("purchase_trust", "60% comments with buying intent (\"just ordered\", \"where can I buy\") plus 40% comments that trust the "
                           "creator's advice."),
        ("engagement_quality", "The share of meaningful comments, minus 0.5 × spam, 0.3 × empty praise (\"so pretty 😍\") and 0.2 × "
                               "copy-pasted comments."),
        ("community", "40% viewers who comment on two or more videos, 40% comments per 1,000 views, 20% likes per 1,000 views."),
    ]
    sub_html = "".join(f'<div class="sf-mrow"><b style="color:{SUB_COLORS[k]}">●</b><div><b>{SUBSCORES[k]}</b><span>{t}</span></div></div>'
                       for k, t in subs)
    return [
        ("1. Find creators", "We search YouTube with your keywords (up to 3), keep channels that show up across searches, and drop brand or "
                             "store accounts, inactive channels, non-English-speaking countries and channels your budget can't afford."),
        ("2. Read the comments", "For each creator we collect recent videos and their top comments. Rules flag spam, copy-paste and "
                                 "non-English comments. Gemini then labels a sample of comments with eight intents (wants to buy, product "
                                 "question, own experience, trusts creator, price, generic praise, complaint, spam) and marks comments that "
                                 "describe your audience's struggle."),
        ("3. Five sub-scores", sub_html + '<p class="sf-mnote">Each sub-score is turned into 0 to 100 relative to the creators in the same '
                               'search: the best creator gets 100, the weakest 0. So scores compare creators with each other, not against '
                               'an absolute standard.</p>'),
        ("4. One match score", f'<p>Match score = the weighted sum of the five sub-scores. Weights depend on your goal:</p>'
                               f'<table class="sf-mtab"><tr><th>Sub-score</th><th>Conversion</th><th>Awareness</th></tr>{rows}</table>'
                               '<p class="sf-mnote">You can set your own weights under Adjust ranking on the results page.</p>'),
        ("5. Filters and value", "Before scoring, creators are left out if their estimated cost is more than 1.5× your budget, if under 60% of "
                                 "their comments are in English, or if we read too few of their comments to judge. Estimated cost is $20 per "
                                 "1,000 subscribers below 1M subscribers and $15 above. Value for money = match points per $1,000 of that "
                                 "estimate."),
        ("6. Explanations you can check", "Gemini explains the top picks, but it may only cite comment IDs we give it, and the app checks that "
                                          "every cited comment exists. You can read the comments behind every claim."),
        ("What it can't see", "YouTube doesn't publish sales or watch-through rates, so buying intent in comments stands in for sales. "
                              "Costs are estimates, not quotes. Creators with few comments get less reliable scores."),
    ]


# ==================================================================
# Outreach email (used by two tabs)
# ==================================================================

def email_box(ctx, cid, row, where):
    comments, brief = ctx.comments, ctx.brief
    key = secret("GEMINI_API_KEY")
    if cid in ss.emails:
        e = ss.emails[cid]
        st.text_input("Subject", e.get("subject", ""), key=f"subj_{where}_{cid}")
        st.text_area("Email", e.get("body", ""), height=230, key=f"body_{where}_{cid}",
                     help="Edit freely before sending. Written by Gemini from this creator's audience comments.")
    elif key:
        if st.button("Draft an outreach email", key=f"mail_{where}_{cid}"):
            with st.spinner("Gemini is writing"):
                try:
                    ss.emails[cid] = engine.draft_email(row, engine.evidence(comments, cid), brief, key, ss.brand)
                    st.rerun()
                except Exception:
                    st.warning("Gemini is busy right now. Try again in a minute.")
    else:
        st.caption("Add GEMINI_API_KEY to the app's secrets to draft outreach emails.")
