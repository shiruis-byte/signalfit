# SignalFit: describe your product, and find the YouTube creators whose audience actually needs it.
#
# Three files:
#   app.py      the screens: sign-in, search, results and its five tabs (this file)
#   ui.py       the look and shared pieces: colors, stylesheet, avatars, quotes, session state
#   engine.py   everything behind the screens: YouTube, Gemini, scoring, the live search
# Keys come from Streamlit secrets: YOUTUBE_API_KEY, GEMINI_API_KEY and optionally ACCESS_CODE.
import hmac
import json
import html
import pickle
import re
import time
from pathlib import Path
from types import SimpleNamespace

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="SignalFit", page_icon="📶", layout="wide", initial_sidebar_state="collapsed")

import engine  # noqa: E402  (page config must come first)
from ui import (  # noqa: E402
    ACCENT,
    INK,
    LABEL_NAMES,
    LOGO,
    MUTED,
    PRIVACY_NOTICE,
    SUB_COLORS,
    SUB_HELP,
    SUBSCORES,
    TEMPLATES,
    apply_theme,
    avatar,
    brief_key,
    channel_url,
    comment_wall,
    email_box,
    examples,
    fact,
    fmt_n,
    handle_of,
    highlight,
    init_state,
    legend,
    load_example,
    meter,
    method_sections,
    nav,
    need_terms,
    quote,
    score_bar,
    score_ring,
    secret,
    shortlist_csv,
    show_chart,
    show_df,
    ss,
    toggle_shortlist,
    use_template,
)


# ==================================================================
# Sign-in
# ==================================================================

def login_page():
    st.write("")
    left, _, right = st.columns([1.15, 0.15, 1], vertical_alignment="top")
    with left:
        st.markdown(f'''<div class="sf-login-side" style="margin-top:2.2rem">{LOGO}
<h1>Find creators whose audience will <em class="sf-grad">actually buy</em></h1>
<p>SignalFit reads what each creator's viewers say in the comments and ranks creators by real needs,
buying intent and trust, not follower counts.</p>
<ul><li>Search YouTube from a short product brief</li><li>See the comments behind every score</li>
<li>Build a shortlist and draft outreach emails</li></ul>
</div>''', unsafe_allow_html=True)
        st.markdown(comment_wall("The kind of comments SignalFit reads for you"), unsafe_allow_html=True)
    with right:
        code_needed = bool(secret("ACCESS_CODE"))
        with st.form("signin"):
            st.markdown('<div class="sf-login-title">Sign in to your brand workspace</div>', unsafe_allow_html=True)
            st.caption("Your brand name is used on your shortlist and in outreach emails.")
            name = st.text_input("Your name", placeholder="e.g. Alex Chen")
            email = st.text_input("Work email", placeholder="e.g. alex@glowlab.com")
            brand = st.text_input("Brand", placeholder="e.g. Glowlab")
            code = st.text_input("Access code", type="password", help="Ask the SignalFit team for your access code.") if code_needed else ""
            agree = st.checkbox("I've read the privacy notice and agree to SignalFit analysing public YouTube data for my searches.")
            go = st.form_submit_button("Enter workspace", type="primary", use_container_width=True)
        with st.expander("Privacy notice"):
            st.markdown(PRIVACY_NOTICE)
        if not code_needed:
            st.caption("No access code is set for this app, so anyone with the link can enter. Add ACCESS_CODE to the app's secrets to require one.")
        if go:
            fails, until = ss.get("login_fails", 0), ss.get("login_locked_until", 0)
            if time.time() < until:
                st.error(f"Too many wrong codes. Try again in {int(until - time.time())} seconds.")
            elif not name.strip() or not brand.strip():
                st.error("Add your name and brand to continue.")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
                st.error("Enter a valid email address, like alex@glowlab.com.")
            elif not agree:
                st.error("Please read the privacy notice and tick the box to continue.")
            elif code_needed and not hmac.compare_digest(code.strip().encode(), str(secret("ACCESS_CODE")).encode()):
                ss.login_fails = fails + 1
                if ss.login_fails >= 5:
                    ss.login_locked_until, ss.login_fails = time.time() + 60, 0
                st.error("That access code isn't right. Check it with the SignalFit team.")
            else:
                ss.user = {"name": name.strip(), "email": email.strip(), "brand": brand.strip(),
                           "privacy_agreed_at": time.strftime("%Y-%m-%d %H:%M")}
                ss.tour_step = 0
                ss.brand = brand.strip()
                ss.login_fails = 0
                st.rerun()

# ==================================================================
# Welcome tour (after sign-in)
# ==================================================================

def tour_page():
    user = ss.user
    step = ss.get("tour_step", 0)
    bub = lambda text, tag, likes, noise=False: (f'<span class="sf-bub{" noise" if noise else ""}"><span class="t">{text}</span><b>{tag}</b>'
                                                 f'<small>♥ {likes}</small></span>')
    steps = [
        ("Welcome", f"Hi {html.escape(user['name'].split()[0])}, welcome to SignalFit",
         "Most tools rank creators by follower count. SignalFit reads what each creator's viewers actually say in the comments, "
         "so you can find the creators whose audience needs your product, asks about it and buys on their advice.",
         '<div class="sf-demo">' + bub("I have <mark class='sf'>sensitive skin</mark> and everything stings. Would this work for me?", "Needs it", "2.1K")
         + bub("Just ordered it because you recommended it!", "Wants to buy", "864") + bub("so pretty 😍😍", "Noise", "12", True) + "</div>"),
        ("Search", "Describe your product in four lines",
         "Search keywords are what we type into YouTube to find creators. \"What does your audience struggle with\" is how your customers "
         "describe the problem in their own words; we look for comments that say it. Add a budget and pick conversion or awareness.",
         '<div class="sf-demo"><div class="sf-demo-row"><div class="sf-fake"><small>Search keywords</small>vegan protein powder review</div>'
         '<div class="sf-fake"><small>Struggles</small>bloating from whey, chalky taste</div><div class="sf-fake"><small>Budget</small>$30,000</div></div>'
         '<div class="sf-fake">Not sure where to start? Pick a template like Skincare or Tech.</div></div>'),
        ("Results", "Read the ranking, then check the proof",
         "Every creator gets a match score from 0 to 100, built from five sub-scores you can see in the coloured bar. The top picks show "
         "a real comment as proof, and Gemini explains each pick using comments you can read yourself.",
         '<div class="sf-demo"><div class="sf-demo-row">' + score_ring(81) +
         '<div style="flex:1;min-width:220px"><div class="sf-bar"><i style="width:25%;background:#3E6BE6"></i><i style="width:23%;background:#FF5B2E"></i>'
         '<i style="width:12%;background:#17A974"></i><i style="width:13%;background:#F2B035"></i><i style="width:8%;background:#8C63E8"></i></div>'
         + legend({k: v for k, v in engine.WEIGHT_PRESETS["conversion"].items()}) + '</div></div></div>'),
        ("Shortlist", "Shortlist, export and reach out",
         "Your shortlist starts with the top 3. Add or remove anyone, download it as a CSV with channel IDs and links, and let Gemini "
         "draft a first outreach email based on what that creator's audience talks about. You can edit every email before sending.",
         '<div class="sf-demo"><div class="sf-demo-row"><div class="sf-fake">✓ Added to shortlist</div><div class="sf-fake">Download shortlist (CSV)</div>'
         '<div class="sf-fake">✉ Draft an outreach email</div></div></div>'),
    ]
    key, title, text, demo = steps[step]
    dots = "".join(f'<i class="{"on" if i <= step else ""}"></i>' for i in range(len(steps)))
    st.markdown(f'<div class="sf-tour">{LOGO}<div class="sf-step-k">Step {step + 1} of {len(steps)}: {key}</div>'
                f'<h1>{title}</h1><p>{text}</p>{demo}<div class="sf-dots">{dots}</div></div>', unsafe_allow_html=True)
    _, c1, c2, c3, _ = st.columns([1, 1.1, 1.1, 1.4, 1])
    if step > 0 and c1.button("Back", use_container_width=True):
        ss.tour_step = step - 1; st.rerun()
    if step < len(steps) - 1:
        if c2.button("Skip tour", use_container_width=True):
            ss.toured = True; st.rerun()
        if c3.button("Next", type="primary", use_container_width=True):
            ss.tour_step = step + 1; st.rerun()
    elif c3.button("Start my first search", type="primary", use_container_width=True):
        ss.toured = True; st.rerun()


# ==================================================================
# How scoring works
# ==================================================================

def method_page():
    nav("")
    back, _, tour = st.columns([1.2, 4, 1.2])
    if back.button("Back", use_container_width=True):
        ss.view = ss.get("prev_view", "home"); st.rerun()
    if tour.button("Replay the tour", use_container_width=True):
        ss.toured, ss.tour_step = False, 0; ss.view = ss.get("prev_view", "home"); st.rerun()
    blocks = "".join(f'<div class="sf-msec"><h3>{t}</h3>{b if b.startswith("<") else f"<p>{b}</p>"}</div>'
                     for t, b in method_sections(engine.WEIGHT_PRESETS["conversion"], engine.WEIGHT_PRESETS["awareness"]))
    st.markdown('<div class="sf-method"><h1>How SignalFit reaches its conclusions</h1>'
                '<p style="color:#6E6B7B;font-size:1.05rem">From your brief to a ranked shortlist in six steps. Every number on the '
                'results page comes from these rules.</p>' + blocks + '</div>', unsafe_allow_html=True)


# ==================================================================
# Label comments (human annotation -> Macro-F1 and kappa)
# ==================================================================

LABEL_HELP = {
    "purchase_intent": "Wants to buy, asks where to buy, or says they bought or will buy",
    "product_question": "Asks about the product: ingredients, fit, suitability, how to use, comparisons",
    "personal_experience": "Talks about their own skin, body, routine, problem or results",
    "creator_trust": "Trusts the creator's advice, or credits them for a decision",
    "price_concern": "Mentions price, value, affordability, worth it",
    "positive_reaction": "Empty praise with no product information (so pretty, love this)",
    "complaint": "Negative experience, side effect, criticism of product or creator",
    "spam": "Self-promotion, links, bots, \"first!\", off-topic",
}


# Team sets live in the GitHub repo (app/label_sets/<name>/), so they survive restarts of the hosted app:
#   comments.csv   the fixed comments to label, in order, with the AI's labels
#   set.json       title and brief
#   labels/*.csv   finished labels from each teammate (the CSVs downloaded from this page), read on every start
LABEL_SETS = Path(__file__).resolve().parent / "label_sets"


def _ann_dir(key):
    d = engine.CACHE / "annotations" / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _who(stem):
    stem = re.sub(r"^labels[-_ ]+", "", stem.lower())
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "teammate"


def _csv_labels(df):
    return {str(r.comment_id): [l for l in engine.LABELS if int(getattr(r, f"human_{l}", 0) or 0) == 1] for r in df.itertuples()}


def _load_all(key, folder=None):
    """Everyone's labels: CSVs committed to the repo first, then labels saved on this server (newer, so they win)."""
    out = {}
    if folder is not None and (folder / "labels").exists():
        for f in sorted((folder / "labels").glob("*.csv")):
            try:
                out[_who(f.stem)] = _csv_labels(pd.read_csv(f, dtype={"comment_id": str}))
            except Exception:
                continue
    for f in sorted(_ann_dir(key).glob("*.json")):
        out[f.stem] = {**out.get(f.stem, {}), **json.loads(f.read_text())}
    return out


def _team_sets():
    sets = {}
    for f in sorted(LABEL_SETS.glob("*/comments.csv")):
        try:
            meta = json.loads((f.parent / "set.json").read_text())
            c = pd.read_csv(f, dtype={"comment_id": str, "creator_id": str})
        except Exception:
            continue
        c["text"] = c["text"].fillna("")
        sets[f"Team set: {meta.get('title', f.parent.name)}"] = {"brief": meta.get("brief", {}), "source": "team",
                                                                  "comments": c, "folder": f.parent}
    return sets


def _save_team_set(res, sample, title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "team-set"
    folder = LABEL_SETS / slug
    (folder / "labels").mkdir(parents=True, exist_ok=True)
    cols = ["comment_id", "creator_id", "text"] + [l for l in engine.LABELS if l in sample]
    sample[cols].to_csv(folder / "comments.csv", index=False)
    brief = {k: v for k, v in res["brief"].items() if isinstance(v, (str, int, float, bool, list))}
    (folder / "set.json").write_text(json.dumps({"title": title, "brief": brief, "n": len(sample),
                                                 "created": time.strftime("%Y-%m-%d %H:%M")}, indent=1))
    (folder / "labels" / "README.txt").write_text("Put each teammate's labels-<name>.csv here, then push to GitHub.\n")
    return folder


def label_page():
    nav("")
    back, _ = st.columns([1.2, 5])
    if back.button("Back", use_container_width=True):
        ss.view = ss.get("prev_view", "home"); st.rerun()
    st.markdown('<div class="sf-method"><h1>Label comments</h1><p style="color:#6E6B7B;font-size:1.02rem">Label comments yourself, '
                'without seeing the AI\'s answer. SignalFit then compares your labels with the AI (Macro-F1, our target is 0.75) '
                'and with simple keyword rules, and measures how much two teammates agree (Cohen\'s kappa).</p></div>',
                unsafe_allow_html=True)
    sets = _team_sets()
    if ss.get("result") is not None:
        sets[f"Current search: {ss.result['brief']['product']}"] = ss.result
    for name, path in examples().items():
        r = load_example(str(path))
        sets.setdefault(f"Example: {r['brief']['product']}", r)
    for f in sorted((engine.CACHE / "results").glob("*.pkl"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            r = pickle.loads(f.read_bytes())
        except Exception:
            continue
        sets.setdefault(f"Earlier search: {r['brief']['product']} ({r['brief'].get('keywords', '')[:40]})", r)
    if not sets:
        st.info("There are no comments to label yet. Go back and run a search (or add the Colab examples), then come back here.")
        return
    choice = st.selectbox("Comments from", list(sets))
    res = sets[choice]
    folder = res.get("folder")
    if folder is not None:
        key = f"team_{folder.name}"
        sample = res["comments"].reset_index(drop=True)
    else:
        key = f"{brief_key(res['brief'])}_{res['source']}"
        sample = engine.annotation_sample(res["comments"])
        with st.expander("Make this a permanent team set (run this on your own computer)"):
            st.caption("Saves these exact comments into the app folder (label_sets/). Push that folder to GitHub and the hosted "
                       "site will always show them, even after it restarts. Afterwards, add everyone's label CSVs to "
                       "label_sets/<name>/labels/ and push again so the Results tab keeps the team's numbers.")
            title = st.text_input("Name of the set", res["brief"].get("product", "Team set")[:60], key=f"ts_title_{key}")
            if st.button("Save as team set", key=f"ts_save_{key}"):
                f = _save_team_set(res, sample, title.strip() or "Team set")
                st.success(f"Saved {len(sample)} comments to {f}. Now commit and push the label_sets folder.")
    me = re.sub(r"[^a-z0-9]+", "-", ss.user["name"].lower()).strip("-") or "me"
    mine_f = _ann_dir(key) / f"{me}.json"
    mine = json.loads(mine_f.read_text()) if mine_f.exists() else {}
    SHARED = 20   # everyone labels these, so the team can measure agreement (kappa)
    st.markdown("#### Split the work")
    s1, s2, s3 = st.columns([1, 1, 2.4], vertical_alignment="bottom")
    team = s1.number_input("People labelling", 1, 8, 1, key=f"team_{key}",
                           help="Everyone on the team should enter the same number here.")
    person = s2.selectbox("I'm person", list(range(1, int(team) + 1)), key=f"person_{key}",
                          help="Each teammate picks a different number.") if team > 1 else 1
    n = len(sample)
    if team > 1:
        assigned = list(range(min(SHARED, n))) + [i for i in range(SHARED, n) if (i - SHARED) % int(team) == person - 1]
        s3.caption(f"Your share: {len(assigned)} comments. The first {min(SHARED, n)} are labelled by everyone so we can measure "
                   f"agreement; the rest are split between {int(team)} people.")
    else:
        assigned = list(range(n))
        s3.caption(f"Labelling alone: all {n} comments. With teammates, set the number of people so everyone gets a share.")
    ids = [sample.iloc[i]["comment_id"] for i in assigned]
    done = sum(1 for c in ids if c in mine)

    t_label, t_results = st.tabs([f"Label ({done} of {len(assigned)})", "Results"])
    with t_label:
        st.markdown(f'<div class="sf-prog"><i style="width:{100 * done / max(1, len(assigned)):.1f}%"></i></div>', unsafe_allow_html=True)
        idx_key = f"lab_idx_{key}_{int(team)}_{person}"
        if idx_key not in ss:
            ss[idx_key] = next((k for k, c in enumerate(ids) if c not in mine), 0)
        pos = min(ss[idx_key], len(assigned) - 1)
        if done == len(assigned):
            st.success("You've labelled your whole share. Check the Results tab, or download your labels below for the team.")
        row = sample.iloc[assigned[pos]]
        cid = row["comment_id"]
        shared_tag = " (shared with everyone)" if team > 1 and assigned[pos] < SHARED else ""
        st.markdown(f'<div class="sf-lab"><div class="meta">Comment {pos + 1} of {len(assigned)}{shared_tag}'
                    f'{" (already labelled)" if cid in mine else ""}</div><div class="c">“{html.escape(str(row["text"])[:600])}”</div></div>',
                    unsafe_allow_html=True)
        picked = st.pills("Pick every label that fits (leave empty if none)", engine.LABELS, selection_mode="multi",
                          format_func=lambda l: LABEL_NAMES[l], default=mine.get(cid, []), key=f"pill_{key}_{cid}")
        with st.expander("What each label means"):
            st.markdown("\n".join(f"- **{LABEL_NAMES[l]}**: {LABEL_HELP[l]}" for l in engine.LABELS))
        b1, b2, b3, _ = st.columns([1, 1, 1.6, 2])
        if b1.button("Back", key="lab_prev", use_container_width=True, disabled=pos == 0):
            ss[idx_key] = pos - 1; st.rerun()
        if b2.button("Skip", key="lab_skip", use_container_width=True):
            ss[idx_key] = min(pos + 1, len(assigned) - 1); st.rerun()
        if b3.button("Save and next", type="primary", use_container_width=True):
            mine[cid] = list(picked or [])
            mine_f.write_text(json.dumps(mine))
            ss[idx_key] = min(pos + 1, len(assigned) - 1); st.rerun()
        st.caption("Your labels save as you go. When you finish, open the Results tab and click Download my labels (CSV).")

    with t_results:
        everyone = _load_all(key, folder)
        if not everyone:
            st.info("Label a few comments first; results appear here as you go.")
        else:
            combined = engine.combine_labels(everyone)
            ev = engine.evaluate_labels(res["comments"], combined)
            ag = engine.team_agreement(everyone)
            st.markdown(f"**Whole team:** {len(everyone)} {'person' if len(everyone) == 1 else 'people'} "
                        f"({', '.join(everyone)}), {len(combined)} different comments labelled. Where people overlap, the majority answer counts.")
            c1, c2, c3 = st.columns(3)
            c1.markdown(fact(f'{ev["macro_f1_ai"]:.2f}' if ev and ev["macro_f1_ai"] is not None else "—",
                             f"Macro-F1, AI vs team labels (n={ev['n'] if ev else 0}). Target 0.75."), unsafe_allow_html=True)
            c2.markdown(fact(f'{ev["macro_f1_keyword"]:.2f}' if ev and ev["macro_f1_keyword"] is not None else "—",
                             "Macro-F1, keyword rules vs team labels. The AI should beat this."), unsafe_allow_html=True)
            c3.markdown(fact(f'{ag["kappa_mean"]:.2f}' if ag else "—",
                             f"Cohen's kappa between teammates ({ag['pairs']} pair{'s' if ag['pairs'] != 1 else ''}, n={ag['n']})" if ag else
                             "Cohen's kappa: needs two people who labelled at least 10 of the same comments"), unsafe_allow_html=True)
            if ev:
                tab = pd.DataFrame({"Label": [LABEL_NAMES[l] for l in engine.LABELS],
                                    "AI F1": [ev["f1_ai"][l] for l in engine.LABELS],
                                    "Keyword F1": [ev["f1_keyword"][l] for l in engine.LABELS]})
                show_df(tab.round(2), hide_index=True)
                st.caption("Labels that nobody ever used are left out of the macro average. Aim for 100+ labelled comments in total.")
            if mine:
                me_ev = engine.evaluate_labels(res["comments"], mine)
                if me_ev and me_ev["macro_f1_ai"] is not None:
                    st.caption(f"Just your labels: Macro-F1 {me_ev['macro_f1_ai']:.2f} for the AI (n={me_ev['n']}).")
        st.markdown("#### Share labels with your team")
        if mine:
            d = res["comments"].drop_duplicates("comment_id").set_index("comment_id")
            out = pd.DataFrame([{"comment_id": c, "creator_id": d.loc[c, "creator_id"] if c in d.index else "",
                                 "text": d.loc[c, "text"] if c in d.index else "", **{f"human_{l}": int(l in labs) for l in engine.LABELS}}
                                for c, labs in mine.items()])
            st.download_button("Download my labels (CSV)", out.to_csv(index=False).encode(), f"labels-{me}.csv", "text/csv",
                               help="Same format as annotation_done.csv in the Colab notebook.")
        up = st.file_uploader("Add a teammate's labels (CSV downloaded from this page)", type="csv", key=f"up_{key}")
        if up is not None:
            df = pd.read_csv(up)
            cols = [f"human_{l}" for l in engine.LABELS]
            if "comment_id" not in df or not all(c in df for c in cols):
                st.error("That file doesn't have the expected columns (comment_id and human_… for each label).")
            else:
                who = _who(Path(up.name).stem)
                labs = _csv_labels(df.astype({"comment_id": str}))
                known = set(sample["comment_id"].astype(str))
                hit = sum(1 for c in labs if c in known)
                (_ann_dir(key) / f"{who}.json").write_text(json.dumps(labs))
                st.success(f"Added {len(labs)} labels as “{who}” ({hit} of them are comments in this set). Results update above.")


# ==================================================================
# Search
# ==================================================================

def run_live(brief):
    cache_f = engine.CACHE / "results" / f"{brief_key(brief)}.pkl"
    if cache_f.exists():
        ss.result = pickle.loads(cache_f.read_bytes()); ss.view = "results"; st.rerun()
    steps = {"find": "Finding creators", "collect": "Collecting videos and comments", "read": "Reading comments with Gemini",
             "score": "Scoring creators", "explain": "Explaining the top picks", "done": "Done"}
    with st.status("Finding creators for your product", expanded=True) as box:
        bar = st.progress(0.0)
        line = st.empty()

        def progress(step, msg, frac=None):
            box.update(label=steps.get(step, step))
            line.markdown(msg)
            if frac is not None:
                bar.progress(min(1.0, max(0.0, frac)))
        try:
            res = engine.run_search(brief, secret("YOUTUBE_API_KEY"), secret("GEMINI_API_KEY"), progress)
        except engine.SearchError as e:
            box.update(label="Search stopped", state="error"); st.error(str(e)); return
        except Exception as e:
            box.update(label="Search stopped", state="error")
            st.error(f"Something went wrong while searching ({type(e).__name__}). Try again, or open an example below."); return
        box.update(label=f"Found {res['feat'].shape[0]} creators in {res['funnel']['seconds']:.0f} seconds", state="complete")
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_bytes(pickle.dumps(res))
    ss.result = res; ss.view = "results"
    st.rerun()


def home_page():
    nav("Creator matching from YouTube comments")
    st.markdown('<div class="sf-land"><div class="sf-eyebrow"><i class="sf-live"></i>Reads live YouTube comments with Gemini</div>'
                '<h1>Find creators whose audience will <em>actually buy</em></h1>'
                '<p>Describe your product. SignalFit searches YouTube, reads what each creator\'s viewers say in the comments, '
                'and ranks creators by real needs, buying intent and trust, not follower counts.</p></div>', unsafe_allow_html=True)
    st.markdown(comment_wall(), unsafe_allow_html=True)
    keys_ok = bool(secret("YOUTUBE_API_KEY") and secret("GEMINI_API_KEY"))
    _, mid, _ = st.columns([1, 3.2, 1])
    with mid:
        st.markdown('<div class="sf-tpl">Start from a template</div>', unsafe_allow_html=True)
        tcols = st.columns(len(TEMPLATES))
        for col, name in zip(tcols, TEMPLATES):
            col.button(name, key=f"tpl_{name}", on_click=use_template, args=(name,), use_container_width=True)
        f = ss.form
        with st.form("brief"):
            product = st.text_input("Product", f["product"], placeholder="e.g. Plant-based protein powder for women who lift")
            keywords = st.text_input("Search keywords", f["keywords"], placeholder="e.g. protein powder review, vegan protein, gym meal prep",
                                     help="Up to 3, separated by commas. SignalFit searches YouTube with each one to find creators.")
            audience = st.text_input("Target audience", f["target_audience"], placeholder="e.g. Women in their 20s starting strength training")
            needs = st.text_area("What does your audience struggle with?", f["audience_need_keywords"], height=80,
                                 placeholder="e.g. bloating from whey, chalky taste, not enough protein on a vegan diet, muscle recovery",
                                 help="The problems your product solves, in your customers' words. SignalFit looks for comments that talk about them.")
            c1, c2 = st.columns(2)
            budget = c1.number_input("Budget per creator (USD)", 500, 200000, int(f["budget_usd"]), 500)
            goal = c2.radio("Goal", ["Conversion", "Awareness"], index=0 if f["goal"] == "Conversion" else 1, horizontal=True,
                            help="Conversion weights buying intent and trust more; awareness weights content fit and community more.")
            go = st.form_submit_button("Find creators", type="primary", use_container_width=True, disabled=not keys_ok)
        if not keys_ok:
            st.info("Live search needs YOUTUBE_API_KEY and GEMINI_API_KEY in the app's secrets. You can still open the examples below.")
        else:
            st.caption("A search reads about 500 comments from 12 creators and takes around a minute. Searching the same brief again is instant.")
        if go:
            ss.form = {"product": product, "keywords": keywords, "target_audience": audience, "audience_need_keywords": needs,
                       "budget_usd": budget, "goal": goal}
            missing = [n for n, v in [("a product", product), ("search keywords", keywords), ("a target audience", audience)] if not v.strip()]
            if missing:
                st.error("Add " + ", ".join(missing) + " to search.")
            else:
                run_live({"product": product.strip(), "keywords": keywords.strip(), "target_audience": audience.strip(),
                          "audience_need_keywords": needs.strip() or keywords.strip(), "budget_usd": int(budget), "goal": goal.lower()})

    ex = examples()
    if ex:
        st.markdown('<div class="sf-ex-title">Or open an example we prepared</div>', unsafe_allow_html=True)
        _, mid2, _ = st.columns([1, 3.2, 1])
        cols = mid2.columns(len(ex))
        for col, (name, path) in zip(cols, ex.items()):
            r = load_example(str(path))
            label = f"**{r['brief']['product']}**  \n{len(r['feat'])} creators, {r['funnel'].get('comments', len(r['comments'])):,} comments"
            if col.button(label, key=f"ex_{name}", use_container_width=True):
                ss.result = r; ss.view = "results"; st.rerun()

# ==================================================================
# Results: tab 'All creators'
# ==================================================================

def tab_creators(ctx):
    brief, weights, ranked, elig, sl_key = ctx.brief, ctx.weights, ctx.ranked, ctx.elig, ctx.sl_key
    if len(elig):
        sort_by = st.radio("Sort", ["Match score", "Value for money"], horizontal=True, label_visibility="collapsed")
        view = elig.sort_values("value_per_1k", ascending=False) if sort_by == "Value for money" else elig
        st.markdown(legend(weights), unsafe_allow_html=True)
        on_list = set(ss[sl_key])
        st.markdown('<div class="sf-rowline"></div>', unsafe_allow_html=True)
        for i, (cid, r) in enumerate(view.iterrows(), 1):
            tags = f'<span class="sf-chip">{r["value_per_1k"]:.1f} points per $1K</span><span class="sf-chip">{r["loyalty_ratio"]:.0%} repeat commenters</span>'
            if r["n_comments"] < 30:
                tags += '<span class="sf-chip">Few comments, low confidence</span>'
            c_who, c_bar, c_score, c_btn = st.columns([2.3, 2.4, 0.55, 1], vertical_alignment="center")
            c_who.markdown(f'<div class="sf-rowl"><div class="rk">{i}</div>{avatar(r)}'
                           f'<div class="nm">{html.escape(r["creator_name"])}<small>{html.escape(handle_of(r) + ", " if handle_of(r) else "")}'
                           f'{fmt_n(r["subscribers"])} subscribers, about ${r["est_cost"]:,.0f} per video</small></div></div>', unsafe_allow_html=True)
            c_bar.markdown(f'{score_bar(r, weights)}<div class="sf-tags">{tags}</div>', unsafe_allow_html=True)
            c_score.markdown(f'<div class="sf-rowsc">{r["match_score"]:.0f}</div>', unsafe_allow_html=True)
            added = cid in on_list
            c_btn.button("Added ✓" if added else "Add", key=f"row_{cid}", type="primary" if added else "secondary",
                         on_click=toggle_shortlist, args=(sl_key, cid), use_container_width=True,
                         help="Remove from your shortlist" if added else "Add to your shortlist")
            st.markdown('<div class="sf-rowline"></div>', unsafe_allow_html=True)
        st.caption("Costs are estimated from subscriber counts, not real quotes. Scores compare creators within this search only.")
        slug = re.sub(r"[^a-z0-9]+", "-", brief["product"].lower()).strip("-")[:40] or "search"
        st.download_button("Download shortlist (CSV)", shortlist_csv(elig, weights), f"signalfit-{slug}.csv", "text/csv",
                           help="Every creator on this list with handle, channel ID, link, scores and estimated cost.")
    out = ranked[~ranked["eligible"]]
    if len(out):
        with st.expander(f"{len(out)} creators left out"):
            show_df(out[["creator_name", "subscribers", "est_cost", "n_comments", "filter_reason"]]
                         .rename(columns={"creator_name": "Creator", "subscribers": "Subscribers", "est_cost": "Est. cost ($)",
                                          "n_comments": "Comments read", "filter_reason": "Why"}),
                         hide_index=True,
                         column_config={"Subscribers": st.column_config.NumberColumn(format="%d"),
                                        "Est. cost ($)": st.column_config.NumberColumn(format="$%d")})

# ==================================================================
# Results: tab 'My shortlist'
# ==================================================================

def tab_shortlist(ctx):
    brief, comments, terms, names, weights, ranked, sl_key = ctx.brief, ctx.comments, ctx.terms, ctx.names, ctx.weights, ctx.ranked, ctx.sl_key
    st.multiselect("Creators on your shortlist", list(ranked.index), key=sl_key, format_func=lambda i: names[i],
                   placeholder="Add creators here, or from their details page")
    sel = ss[sl_key]
    if not sel:
        st.info("Your shortlist is empty. Add creators above, use the button for the top 3, or open a creator's details and add them there.")
    else:
        ss.brand = st.text_input("Your brand name (used in outreach emails)", ss.brand, placeholder="e.g. Glowlab")
        for start in range(0, len(sel), 3):
            cols = st.columns(3, gap="medium")
            for col, cid in zip(cols, sel[start:start + 3]):
                r = ranked.loc[cid]
                ev = engine.evidence(comments, cid, n=1)
                sc_txt = "—" if pd.isna(r["match_score"]) else f'{r["match_score"]:.0f}'
                with col:
                    kv = [("Estimated cost", f'${r["est_cost"]:,.0f}'),
                          ("Points per $1,000", "—" if pd.isna(r["value_per_1k"]) else f'{r["value_per_1k"]:.1f}'),
                          ("Repeat commenters", f'{r["loyalty_ratio"]:.0%}')] + \
                         [(SUBSCORES[k], f"{r[k]:.0f}") for k in weights]
                    st.markdown(f'<div class="sf-card"><div class="who">{avatar(r)}<div class="nm">{html.escape(r["creator_name"])}'
                                f'<small>{html.escape(handle_of(r))}</small><small>{fmt_n(r["subscribers"])} subscribers</small></div>'
                                f'<div class="sc">{sc_txt}</div></div>'
                                + "".join(f'<div class="sf-kv"><span>{a}</span><span>{b}</span></div>' for a, b in kv)
                                + (quote(ev.iloc[0], terms, 200) if len(ev) else "") + "</div>", unsafe_allow_html=True)
                    email_box(ctx, cid, r, "sl")
                    st.button("Remove", key=f"rm_{cid}", on_click=toggle_shortlist, args=(sl_key, cid))
        slug = re.sub(r"[^a-z0-9]+", "-", brief["product"].lower()).strip("-")[:40] or "search"
        st.download_button("Download my shortlist (CSV)", shortlist_csv(ranked.loc[sel], weights), f"signalfit-shortlist-{slug}.csv", "text/csv")

# ==================================================================
# Results: tab 'Creator details'
# ==================================================================

def tab_details(ctx):
    res, brief, comments, videos, rationales, terms, names, weights, ranked, elig, sl_key = ctx.res, ctx.brief, ctx.comments, ctx.videos, ctx.rationales, ctx.terms, ctx.names, ctx.weights, ctx.ranked, ctx.elig, ctx.sl_key
    options = list(elig.index) + [i for i in ranked.index if i not in elig.index]
    cid = st.selectbox("Creator", options, format_func=lambda i: names[i] + ("" if i in elig.index else " (left out)"))
    row = ranked.loc[cid]
    cc = comments[comments["creator_id"] == cid]
    place = f"Ranked {list(elig.index).index(cid) + 1} of {len(elig)}" if cid in elig.index else f"Left out: {row['filter_reason']}"
    link = f' <a href="{html.escape(channel_url(cid, row))}" target="_blank">Open on YouTube</a>' if str(cid).startswith("UC") else ""
    h = handle_of(row)
    st.markdown(f'<div class="sf-head">{avatar(row, "lg")}<div><h2>{html.escape(row["creator_name"])}</h2>'
                f'<div class="sub">{html.escape(h + ", " if h else "")}{fmt_n(row["subscribers"])} subscribers. {html.escape(place)}.{link}</div></div></div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="sf-ids">Channel ID <code>{html.escape(str(cid))}</code></div>', unsafe_allow_html=True)
    on_list = cid in ss[sl_key]
    st.button("Remove from my shortlist" if on_list else "Add to my shortlist", key=f"tg_{cid}", type="secondary" if on_list else "primary",
              on_click=toggle_shortlist, args=(sl_key, cid))
    a, b, c, d = st.columns(4)
    a.markdown(fact("—" if pd.isna(row["match_score"]) else f'{row["match_score"]:.0f}', "Match score out of 100"), unsafe_allow_html=True)
    b.markdown(fact(f'${row["est_cost"]:,.0f}', "Estimated cost per video"), unsafe_allow_html=True)
    c.markdown(fact("—" if pd.isna(row["value_per_1k"]) else f'{row["value_per_1k"]:.1f}', "Match points per $1,000"), unsafe_allow_html=True)
    d.markdown(fact(f'{row["loyalty_ratio"]:.0%}', "Viewers who commented on 2+ videos"), unsafe_allow_html=True)
    if row["n_comments"] < 30:
        st.caption(f"Only {int(row['n_comments'])} comments read for this creator, so treat the score as a rough guide.")
    st.write("")
    left, right = st.columns([1, 1.3], gap="large")
    with left:
        st.markdown("#### Score breakdown")
        st.markdown("".join(meter(f"{SUBSCORES[k]} ({weights[k]:.0%})", row[k], SUB_COLORS[k], SUB_HELP[k]) for k in weights), unsafe_allow_html=True)
        st.markdown("#### What viewers talk about")
        mix = pd.DataFrame({"Intent": [LABEL_NAMES[l] for l in engine.LABELS], "Share": [cc[l].mean() if len(cc) else 0 for l in engine.LABELS]})
        show_chart(alt.Chart(mix).mark_bar(color=INK, cornerRadiusEnd=3, height=14).encode(
            x=alt.X("Share:Q", axis=alt.Axis(format="%", grid=False, domain=False, tickCount=4), title=None),
            y=alt.Y("Intent:N", sort="-x", title=None, axis=alt.Axis(domain=False, ticks=False, labelPadding=8)),
            tooltip=["Intent", alt.Tooltip("Share:Q", format=".0%")]).properties(height=230).configure_view(strokeWidth=0))
    with right:
        st.markdown("#### Why this creator")
        r = rationales.get(cid)
        if not r and res["source"] == "live" and cid in elig.index and secret("GEMINI_API_KEY"):
            if st.button("Explain this creator with Gemini"):
                with st.spinner("Asking Gemini"):
                    try:
                        r = engine.explain(row, engine.evidence(comments, cid), brief, secret("GEMINI_API_KEY"))
                        rationales[cid] = r
                    except Exception:
                        st.warning("Gemini is busy right now. Try again in a minute.")
        by_id = comments.drop_duplicates("comment_id").set_index("comment_id")
        if r:
            st.write(r.get("summary", ""))
            for claim in r.get("claims", []):
                st.markdown(f'<div class="sf-claim">{html.escape(claim.get("claim", ""))}</div>', unsafe_allow_html=True)
                for i in claim.get("comment_ids", []):
                    st.markdown(quote(by_id.loc[i].to_dict(), terms) if i in by_id.index
                                else f'<div class="sf-quote">Comment {html.escape(str(i))} isn\'t in our data.</div>', unsafe_allow_html=True)
            n_cl = len(r.get("claims", []))
            if n_cl:
                st.caption(f"{r.get('claims_supported', 0)} of {n_cl} claims cite comments that exist in our data. Highlighted words match your audience's needs.")
        else:
            st.caption("The comments that count most toward this creator's score:")
            for _, e in engine.evidence(comments, cid).iterrows():
                st.markdown(quote(e, terms), unsafe_allow_html=True)
        st.markdown("#### Reach out")
        email_box(ctx, cid, row, "dt")
        if len(videos):
            vv = videos[videos["creator_id"] == cid].sort_values("published_at", ascending=False).head(5)
            if len(vv):
                st.markdown("#### Recent videos")
                st.markdown("".join(f'<div class="sf-video"><a href="https://www.youtube.com/watch?v={html.escape(str(v.video_id))}" target="_blank">'
                                    f'{html.escape(str(v.title))}</a><span>{fmt_n(v.views)} views</span></div>' for v in vv.itertuples()),
                            unsafe_allow_html=True)

# ==================================================================
# Results: tab 'Compare with follower counts'
# ==================================================================

def tab_compare(ctx):
    names, elig = ctx.names, ctx.elig
    if len(elig) < 3:
        st.info("At least three creators need to pass the filters to compare rankings.")
    else:
        cmp = pd.DataFrame({"Creator": elig["creator_name"],
                            "SignalFit": elig["match_score"].rank(ascending=False, method="first").astype(int),
                            "Followers": elig["subscribers"].rank(ascending=False, method="first").astype(int),
                            "Engagement rate": elig["engagement_rate"].rank(ascending=False, method="first").astype(int)})
        base = st.radio("Compare with", ["Followers", "Engagement rate"], horizontal=True)
        rho = cmp["SignalFit"].corr(cmp[base])  # both columns are ranks, so Pearson on them = Spearman (no scipy needed)
        n = len(cmp)
        slope = cmp.melt(id_vars="Creator", value_vars=[base, "SignalFit"], var_name="Method", value_name="Rank")
        moved = dict(zip(cmp["Creator"], (cmp[base] - cmp["SignalFit"]).abs() >= max(2, n // 4)))
        slope["Moved"] = slope["Creator"].map(moved)
        y = alt.Y("Rank:Q", scale=alt.Scale(domain=[n + 0.5, 0.5]), axis=None)
        x = alt.X("Method:N", sort=[base, "SignalFit"], title=None,
                  axis=alt.Axis(labelAngle=0, labelFontSize=13, labelFontWeight=600, domain=False, ticks=False, labelColor=INK))
        enc = alt.Chart(slope).encode(x=x, y=y, detail="Creator:N",
                                      color=alt.condition("datum.Moved", alt.value(ACCENT), alt.value("#C9CAD1")), tooltip=["Creator", "Method", "Rank"])
        lab_r = alt.Chart(slope[slope["Method"] == "SignalFit"]).mark_text(align="left", dx=9, fontSize=12, color=INK).encode(
            x=x, y=y, text="label:N").transform_calculate(label="datum.Rank + '. ' + datum.Creator")
        lab_l = alt.Chart(slope[slope["Method"] == base]).mark_text(align="right", dx=-9, fontSize=12, color=MUTED).encode(
            x=x, y=y, text="label:N").transform_calculate(label="datum.Creator + '  ' + datum.Rank")
        l, rcol = st.columns([1.7, 1], gap="large")
        with l:
            show_chart((enc.mark_line(strokeWidth=2.2) + enc.mark_circle(size=55, opacity=1) + lab_r + lab_l)
                            .properties(height=max(300, 28 * n), padding={"left": 160, "right": 170}).configure_view(strokeWidth=0))
        with rcol:
            st.markdown(fact(f"{rho:.2f}", f"Rank correlation with {base.lower()}. 1 means the same order; near 0 means reading comments "
                             "picks very different creators."), unsafe_allow_html=True)
            diff = (cmp[base] - cmp["SignalFit"]).sort_values()
            up, down = diff.index[-1], diff.index[0]
            st.write("")
            st.markdown(f"**Moved up most:** {html.escape(names[up])}, from {cmp.loc[up, base]} to {cmp.loc[up, 'SignalFit']}.")
            st.markdown(f"**Moved down most:** {html.escape(names[down])}, from {cmp.loc[down, base]} to {cmp.loc[down, 'SignalFit']}. "
                        f"{elig.loc[down, 'generic_ratio']:.0%} of its comments are generic praise.")

# ==================================================================
# Results: tab 'How we found them'
# ==================================================================

def tab_method(ctx):
    res, brief, feat, comments, videos, fun = ctx.res, ctx.brief, ctx.feat, ctx.comments, ctx.videos, ctx.fun
    l, rcol = st.columns([1, 1], gap="large")
    with l:
        qs = fun.get("queries") or [q.strip() for q in brief.get("keywords", "").split(",") if q.strip()]
        if res["source"] == "live" or res.get("creator_source") == "search":
            found = (f"Searched YouTube for {', '.join(html.escape(q) for q in qs)}. Found {fun.get('channels_found', fun.get('discovery_found', '—'))} channels; "
                     f"kept {fun.get('creators', len(feat))} active, English-speaking creators that aren't brand or store accounts.")
        else:
            found = f"Started from a list of {fun.get('candidate_creators', len(feat))} creators in this category."
        steps = [("Find creators", found),
                 ("Collect public data", f"{fun.get('videos', len(videos))} recent videos and {fun.get('comments', len(comments)):,} top comments, "
                                         "through the official YouTube Data API."),
                 ("Clean", f"Flagged {fun.get('spam_rule', 0)} spam, {fun.get('dup_text', 0)} copy-paste and {fun.get('non_english', 0)} "
                           "non-English comments. Their share counts against comment quality."),
                 ("Read comments with AI", f"Gemini labeled {fun.get('classified', len(comments)):,} comments with eight intents, and whether "
                                           "each one describes your audience's need."),
                 ("Score and explain", "Five weighted sub-scores make the match sengine. Gemini explains the top picks and may only cite real comment IDs.")]
        st.markdown("#### From your brief to this list")
        st.markdown("".join(f'<div class="sf-step"><div class="n">{i}</div><div><b>{a}</b><span>{b}</span></div></div>'
                            for i, (a, b) in enumerate(steps, 1)), unsafe_allow_html=True)
        if fun.get("seconds"):
            st.caption(f"This search took {fun['seconds']:.0f} seconds.")
    with rcol:
        disc = res.get("discovery")
        if disc is not None and len(disc):
            st.markdown("#### Channels YouTube returned")
            dd = disc.copy()
            dd["rejected_by"] = dd["rejected_by"].fillna("")
            dd["Result"] = dd.apply(lambda x: "Kept" if bool(x.get("selected")) else (x["rejected_by"] or "Ranked lower"), axis=1)
            dd["Subscribers"] = dd["subscribers"].apply(fmt_n)
            show_df(dd.sort_values("n_hits", ascending=False)[["channel_title", "Subscribers", "n_hits", "Result"]].rename(
                columns={"channel_title": "Channel", "n_hits": "Search hits"}), hide_index=True, height=300)
        m = res.get("metrics") or {}
        g = m.get("grounding") or {}
        if g.get("rate") is not None or m.get("sensitivity"):
            st.markdown("#### Checks on this example")
            c1, c2 = st.columns(2)
            c1.markdown(fact(f'{g["rate"]:.0%}' if g.get("rate") is not None else "—", "Explanation claims citing real comments"), unsafe_allow_html=True)
            s = m.get("sensitivity") or {}
            c2.markdown(fact(f'{s["top3_overlap"]:.0%}' if s else "—", "Top 3 that stay top 3 when weights move ±20%"), unsafe_allow_html=True)
    st.markdown("#### Limits")
    st.markdown("YouTube doesn't publish sales or watch-through rates, so buying intent in comments stands in for sales. "
                "Costs are estimated from subscriber counts. Scores compare creators within one search, and live searches read a "
                "smaller sample of comments than our prepared examples.")

def set_shortlist(key, cids):
    ss[key] = list(cids)


# ==================================================================
# Results screen
# ==================================================================

def results_page():
    res = ss.result
    brief = res["brief"]
    feat, comments, videos, rationales, fun = res["feat"], res["comments"], res["videos"], res["rationales"], res["funnel"]
    terms = need_terms(brief)
    names = feat["creator_name"].to_dict()

    nav('<i class="sf-live"></i>Live search' if res["source"] == "live" else "Prepared example")
    top_l, top_r = st.columns([5, 1.2])
    with top_r:
        if st.button("New search", use_container_width=True):
            if res["source"] == "live":
                ss.form = {"product": brief["product"], "keywords": brief.get("keywords", ""), "target_audience": brief["target_audience"],
                           "audience_need_keywords": brief.get("audience_need_keywords", ""), "budget_usd": brief["budget_usd"],
                           "goal": brief.get("goal", "conversion").title()}
            ss.view = "home"; st.rerun()
    if res.get("mock"):
        st.markdown('<div class="sf-banner"><b>Demo data.</b> These creators and comments were generated to test the layout. '
                    'Replace app_data with the files exported from Colab to see real results.</div>', unsafe_allow_html=True)
    with top_l:
        kw = "".join(f'<span class="sf-chip">{html.escape(k.strip())}</span>' for k in re.split(r"[,;]", brief.get("keywords", "")) if k.strip())
        st.markdown(f'<div class="sf-brief"><h1>{html.escape(brief["product"])}</h1></div>'
                    f'<div class="sf-sub">For {html.escape(brief["target_audience"][0].lower() + brief["target_audience"][1:])}. '
                    f'We read {fun.get("comments", len(comments)):,} comments on {len(feat)} creators.<br>{kw}</div>', unsafe_allow_html=True)

    with st.expander("Adjust ranking", expanded=False):
        a1, a2, a3 = st.columns([1.2, 1, 1])
        goal = a1.radio("Goal", ["Conversion", "Awareness", "Custom"], index=0 if brief.get("goal", "conversion") == "conversion" else 1, horizontal=True)
        budget = a2.number_input("Budget per creator (USD)", 500, 200000, int(brief.get("budget_usd", 30000)), 500)
        min_c = a3.slider("Minimum comments read", 5, 100, 15 if res["source"] == "live" else 30, 5,
                          help="Creators with fewer AI-read comments are left out; their ratios aren't reliable.")
        if goal == "Custom":
            cs = st.columns(5)
            raw = {k: cs[i].slider(SUBSCORES[k], 0, 100, int(engine.WEIGHT_PRESETS["conversion"][k] * 100), 5, help=SUB_HELP[k])
                   for i, k in enumerate(SUBSCORES)}
            tot = sum(raw.values()) or 1
            weights = {k: v / tot for k, v in raw.items()}
        else:
            weights = engine.WEIGHT_PRESETS[goal.lower()]
    ranked = engine.score(feat, weights, budget, min_c)
    elig = ranked[ranked["eligible"]]

    if len(elig):
        cards = []
        for i, (cid, r) in enumerate(elig.head(3).iterrows()):
            ev = engine.evidence(comments, cid, n=1)
            q = f'<div class="q">“{highlight(ev.iloc[0]["text"][:170], terms)}”</div>' if len(ev) else ""
            cards.append(f'<div class="sf-pick{" first" if i == 0 else ""}"><span class="sf-badge">{["Best match", "Runner-up", "Third"][i]}</span>'
                         f'<div class="who">{avatar(r, ring=True)}<div class="nm">{html.escape(r["creator_name"])}<small>{html.escape(handle_of(r))}</small><small>{fmt_n(r["subscribers"])} subscribers</small></div>'
                         f'{score_ring(r["match_score"])}</div>{q}</div>')
        st.markdown(f'<div class="sf-picks">{"".join(cards)}</div>', unsafe_allow_html=True)
    else:
        st.info("No creator fits these settings. Raise the budget or lower the minimum number of comments in Adjust ranking.")

    sl_key = f"sl_{brief_key(brief)}_{res['source']}"
    ss.setdefault(sl_key, list(elig.index[:3]))          # the shortlist starts with the top 3; brands can change it freely
    ss[sl_key] = [c for c in ss[sl_key] if c in ranked.index]
    if len(elig):
        n_sl = len(ss[sl_key])
        tip, reset = st.columns([4, 1.3], vertical_alignment="center")
        tip.caption(f"Your shortlist has {n_sl} creator{'s' if n_sl != 1 else ''}. It starts with the top 3; "
                    "add or remove anyone with the buttons in the list below.")
        reset.button("Reset to top 3", on_click=set_shortlist, args=(sl_key, list(elig.index[:3])), use_container_width=True)
        with st.expander("How was this score calculated?"):
            pick = st.selectbox("Creator", list(elig.index), format_func=lambda i: names[i], key="math_pick")
            r = elig.loc[pick]
            body = "".join(f'<tr><td>{SUBSCORES[k]}</td><td>{r[k]:.0f}</td><td>× {weights[k]:.0%}</td><td>= {r[k] * weights[k]:.1f}</td></tr>'
                           for k in weights)
            st.markdown(f'<table class="sf-math"><tr><td style="color:#6E6B7B">Sub-score (0–100, relative to this search)</td><td></td>'
                        f'<td style="color:#6E6B7B">Weight</td><td style="color:#6E6B7B">Points</td></tr>{body}'
                        f'<tr class="total"><td>Match score</td><td></td><td></td><td>{r["match_score"]:.0f}</td></tr></table>',
                        unsafe_allow_html=True)
            st.caption(f'Estimated cost ${r["est_cost"]:,.0f}, so value for money is {r["value_per_1k"]:.1f} match points per $1,000. '
                       "Use “How scoring works” at the top for what each sub-score measures.")

    ctx = SimpleNamespace(res=res, brief=brief, feat=feat, comments=comments, videos=videos, rationales=rationales, fun=fun,
                          terms=terms, names=names, weights=weights, ranked=ranked, elig=elig, sl_key=sl_key)
    t1, t5, t2, t3, t4 = st.tabs(["All creators", f"My shortlist ({len(ss[sl_key])})", "Creator details",
                                  "Compare with follower counts", "How we found them"])
    with t1:
        tab_creators(ctx)
    with t5:
        tab_shortlist(ctx)
    with t2:
        tab_details(ctx)
    with t3:
        tab_compare(ctx)
    with t4:
        tab_method(ctx)

# ==================================================================
# Start
# ==================================================================

apply_theme()
init_state()

if not ss.get("user"):
    login_page()
elif not ss.get("toured"):
    tour_page()
elif ss.view == "method":
    method_page()
elif ss.view == "label":
    label_page()
elif ss.view == "results" and ss.result is not None:
    results_page()
else:
    home_page()
