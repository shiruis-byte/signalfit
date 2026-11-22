"""SignalFit engine: everything behind the screens, with no Streamlit code.

  Settings        model names, labels, weights, live-search sizes, filters
  API clients     YouTube Data API and Gemini, cached on disk
  Brief           turn a brand's brief into search queries and AI instructions
  AI              Gemini labels comments, rates relevance, explains picks, drafts emails
  Scoring         cleaning, creator features, the 0-100 match score (same maths as the Colab notebook)
  Live search     brief -> YouTube -> comments -> Gemini -> scores -> explanations
  Examples        load prepared results exported by the Colab notebook
"""
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests


# ==================================================================
# Settings
# ==================================================================

CACHE = Path(__file__).resolve().parent / ".cache"   # API responses, labels and finished searches


YT_URL = "https://www.googleapis.com/youtube/v3/"


GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"]


LABELS = ["purchase_intent", "product_question", "personal_experience", "creator_trust",
          "price_concern", "positive_reaction", "complaint", "spam"]


SUBSCORES = ["content_relevance", "audience_need", "purchase_trust", "engagement_quality", "community"]


WEIGHT_PRESETS = {
    "conversion": {"content_relevance": 0.25, "audience_need": 0.25, "purchase_trust": 0.20, "engagement_quality": 0.15, "community": 0.15},
    "awareness":  {"content_relevance": 0.30, "audience_need": 0.20, "purchase_trust": 0.10, "engagement_quality": 0.15, "community": 0.25},
}


# Live search sizes: smaller than the Colab run so a search finishes in about a minute.
LIVE = dict(n_creators=12, n_videos=5, comments_per_video=50, classify_per_creator=40, batch=40,
            ai_workers=6,       # Gemini calls in parallel; lower to 3 if you see many "busy" retries on the free tier
            explain_top=3,      # explanations written during the search; others are written on demand
            min_subs=10_000, max_subs=5_000_000, max_queries=3)


COUNTRIES = {"US", "GB", "CA", "AU", "IE", "NZ", ""}


EXCLUDE = ["official", "store", "shop", "warehouse", "outlet", "news", "nike", "adidas", "asics", "brooks running", "hoka",
           "new balance", "saucony", "puma", "on running", "sephora", "ulta", "cerave", "la roche", "the ordinary", "amazon"]


SPAM = re.compile(r"(?:check (?:out )?my channel|sub(?:scribe)? to (?:me|my)|sub to my|https?://|www\.|follow me|"
                  r"free followers|giveaway|dm me|whatsapp|telegram)", re.I)


EMOJI_ONLY = re.compile(r"^[\W_\d\s]+$")


class SearchError(RuntimeError):
    pass


# ==================================================================
# API clients
# ==================================================================

def _key(*parts):
    return hashlib.md5(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


# Creators often write a business email in their channel or video description,
# sometimes disguised as "name [at] gmail [dot] com". The YouTube API never returns
# the private "View email address" field, so this public text is all we can use.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_AT = re.compile(r"\s*[\[(]\s*at\s*[\])]\s*|\s+at\s+(?=[A-Za-z0-9-]+\s*(?:[\[(]\s*dot\s*[\])]|\.))", re.I)
_DOT = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*|\s+dot\s+(?=[A-Za-z]{2,}\b)", re.I)


def find_email(text):
    """First public email in a description, or ''."""
    text = str(text or "")
    for t in (text, _DOT.sub(".", _AT.sub("@", text))):
        for m in _EMAIL.finditer(t):
            e = m.group(0).strip(".").lower()
            if not e.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                return e
    return ""


def yt_get(endpoint, api_key, **params):
    f = CACHE / "yt" / f"{endpoint}_{_key(endpoint, params)}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = requests.get(YT_URL + endpoint, params={**params, "key": api_key}, timeout=20)
    if r.status_code == 403 and "quota" in r.text.lower():
        raise SearchError("The YouTube API's daily quota is used up. It resets at midnight Pacific time; the examples still work.")
    if r.status_code != 200:
        raise RuntimeError(f"YouTube {endpoint} {r.status_code}")
    data = r.json()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data))
    return data


def gemini(prompt, api_key, json_mode=True, timeout=40, tries=5, first_model=None):
    """One Gemini call with model rotation on busy/unavailable models. Returns (text, model, seconds)."""
    models = ([first_model] if first_model else []) + [m for m in GEMINI_MODELS if m != first_model]
    last = ""
    for attempt in range(tries):
        m = models[attempt % len(models)]
        try:
            t0 = time.time()
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                              headers={"x-goog-api-key": api_key}, timeout=timeout,
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"temperature": 0, **({"responseMimeType": "application/json"} if json_mode else {})}})
            if r.status_code != 200:
                last = f"{m}: HTTP {r.status_code}"
                time.sleep(min(8, 1.5 * (attempt + 1)))
                continue
            return r.json()["candidates"][0]["content"]["parts"][0]["text"], m, time.time() - t0
        except Exception as e:  # network hiccup, timeout, malformed response
            last = f"{m}: {type(e).__name__}"
            time.sleep(min(8, 1.5 * (attempt + 1)))
    raise RuntimeError(f"Gemini did not answer ({last})")


def parse_json(text):
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


# ==================================================================
# Brief
# ==================================================================

def need_text(brief):
    return brief.get("audience_need_keywords") or brief.get("keywords", "")


def brief_text(b):
    return (f"{b['product']}. Category keywords: {b.get('keywords', b.get('category', ''))}. Audience: {b['target_audience']}. "
            f"What the audience struggles with: {need_text(b)}")


def label_guide(brief):
    return f"""purchase_intent: wants to buy / asks where to buy / says they bought or will buy because of the video
product_question: asks about a product's features, ingredients, fit, suitability, usage, effects or comparisons
personal_experience: describes their own situation, body, routine, problem or results
creator_trust: expresses trust in the creator's advice/expertise or credits them for a decision
price_concern: mentions price, value, affordability, "worth it"
positive_reaction: generic praise or excitement with no product information ("so pretty", "love this")
complaint: negative experience, side effect, criticism of product or creator
spam: self-promotion, links, bots, "first!", irrelevant
audience_need: the commenter describes the problem or need this product addresses ({need_text(brief)})
A comment can have several labels. Use [] only if none applies."""


def queries_from_brief(brief):
    qs = [q.strip() for q in re.split(r"[,\n;]", brief.get("keywords", "")) if q.strip()]
    if len(qs) < 2:
        qs.append(f"{brief['product']} review")
    seen, out = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower()); out.append(q)
    return out[:LIVE["max_queries"]]


# ==================================================================
# AI (Gemini)
# ==================================================================

def classify_prompt(texts, brief):
    lines = "\n".join(f"{i}: {t[:400]}" for i, t in enumerate(texts))
    return (f"You label YouTube comments for an influencer-marketing study.\nCampaign: {brief['product']} for {brief['target_audience']}.\n\n"
            f"Label definitions:\n{label_guide(brief)}\n\nReturn ONLY a JSON object mapping each comment index (string) to a list of labels "
            f"from: {LABELS + ['audience_need']}\n\nComments:\n{lines}")


def classify(sample, brief, gem_key, on_progress):
    bkey = _key(brief.get("product"), need_text(brief), brief.get("target_audience"))
    cache_f = CACHE / "labels" / f"{bkey}.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    todo = sample[~sample["comment_id"].isin(cache)]
    batches = [todo.iloc[i:i + LIVE["batch"]] for i in range(0, len(todo), LIVE["batch"])]
    done = len(sample) - len(todo)
    on_progress(done, len(sample))

    def run(b):
        out = parse_json(gemini(classify_prompt(b["text"].tolist(), brief), gem_key)[0])
        return {r.comment_id: out.get(str(i), out.get(i)) for i, r in enumerate(b.itertuples())}

    with ThreadPoolExecutor(max_workers=LIVE["ai_workers"]) as ex:
        for fu in as_completed([ex.submit(run, b) for b in batches]):
            try:
                for cid, labs in fu.result().items():
                    if isinstance(labs, list):
                        cache[cid] = labs
                        done += 1
            except Exception:
                pass
            on_progress(done, len(sample))
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(cache))
    return {k: v for k, v in cache.items() if k in set(sample["comment_id"])}


def content_relevance(picked, videos_df, brief, gem_key):
    """Gemini rates 0–100 how closely each creator's recent videos match the product's category."""
    blocks = []
    for r in picked.itertuples():
        titles = videos_df.loc[videos_df["creator_id"] == r.channel_id, "title"].head(5).tolist()
        blocks.append(f"{r.channel_id} | {r.channel_title}: " + " / ".join(t[:90] for t in titles))
    prompt = (f"A brand wants creators for this campaign: {brief_text(brief)}\n\nFor each creator below (id | name: recent video titles), "
              f"rate from 0 to 100 how closely their recent videos cover this product's category and audience. "
              f"Return ONLY a JSON object mapping creator id to an integer.\n\n" + "\n".join(blocks))
    try:
        out = parse_json(gemini(prompt, gem_key)[0])
        return pd.Series({k: float(v) for k, v in out.items() if isinstance(v, (int, float))})
    except Exception:
        words = set(re.findall(r"[a-z]{4,}", brief_text(brief).lower()))
        return videos_df.assign(hit=videos_df["title"].str.lower().apply(lambda t: len(words & set(re.findall(r"[a-z]{4,}", t))) > 0)) \
                        .groupby("creator_id")["hit"].mean() * 100


def explain(row, ev, brief, gem_key):
    ev_lines = "\n".join(f"[{r.comment_id}] {r.text[:300]}" for r in ev.itertuples())
    prompt = f"""You are a marketing analyst. In 2–3 sentences explain why this creator fits (or doesn't fit) the campaign,
then list 2–3 specific claims, each supported ONLY by comment IDs given below. Do not invent comments.
Campaign: {brief_text(brief)}
Creator: {row['creator_name']} | subscribers {int(row['subscribers']):,} | match score {row['match_score']:.0f}/100
Sub-scores (0–100): content {row['content_relevance']:.0f}, audience need {row['audience_need']:.0f}, purchase/trust {row['purchase_trust']:.0f}, comment quality {row['engagement_quality']:.0f}, community {row['community']:.0f}
Comments:
{ev_lines}
Return JSON: {{"summary": "...", "claims": [{{"claim": "...", "comment_ids": ["..."]}}]}}"""
    f = CACHE / "explain" / f"{_key(prompt)}.json"
    if f.exists():
        return json.loads(f.read_text())
    out = parse_json(gemini(prompt, gem_key)[0])
    valid = set(ev["comment_id"])
    out["claims_supported"] = sum(1 for c in out.get("claims", []) if c.get("comment_ids") and all(i in valid for i in c["comment_ids"]))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def draft_email(row, ev, brief, gem_key, brand=""):
    """Gemini drafts a first outreach email grounded in what this creator's audience actually says."""
    ev_lines = "\n".join(f"- {t[:220]}" for t in ev["text"].head(4))
    prompt = f"""Write a short first outreach email from a brand to a YouTube creator, proposing a sponsored video.
Brand: {brand or '[Brand name]'}. Product: {brief['product']}. Target audience: {brief['target_audience']}.
Budget per video: about ${int(brief.get('budget_usd', 0)):,}.
Creator: {row['creator_name']} ({int(row['subscribers']):,} subscribers).
What their viewers say in the comments (real comments):
{ev_lines}
Rules: under 140 words; friendly and specific; mention in your own words one or two things their audience asks about or struggles with,
based only on the comments above; do not quote commenters or invent facts, numbers or past collaborations; no budget figure;
end with a simple next step and sign off as [Your name], {brand or '[Brand name]'}.
Return JSON: {{"subject": "...", "body": "..."}}"""
    f = CACHE / "email" / f"{_key(prompt)}.json"
    if f.exists():
        return json.loads(f.read_text())
    out = parse_json(gemini(prompt, gem_key)[0])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


# ==================================================================
# Scoring
# ==================================================================

def clean(df):
    d = df.copy()
    d["text"] = d["text"].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    d = d[d["text"].str.len() > 0].drop_duplicates("comment_id")
    d["dup_text"] = d.duplicated(subset=["creator_id", "text"], keep="first") & (d["text"].str.split().str.len() > 3)
    d["spam_rule"] = d["text"].str.contains(SPAM) | d["text"].str.match(EMOJI_ONLY)
    d["n_words"] = d["text"].str.split().str.len()
    d["is_english"] = d["text"].apply(lambda t: (lambda a: not a or sum(c.isascii() for c in a) / len(a) > 0.8)([c for c in t if c.isalpha()]))
    return d.reset_index(drop=True)


def sample_for_ai(df, n):
    parts = []
    for _, g in df.groupby("creator_id"):
        top = g.nlargest(min(n // 3, len(g)), "likes")
        rest = g.drop(top.index)
        parts.append(pd.concat([top, rest.sample(min(n - len(top), len(rest)), random_state=42)]))
    return pd.concat(parts).reset_index(drop=True)


def features(lab, vids, creators, all_comments):
    g = lab.groupby("creator_id")
    other = ["purchase_intent", "product_question", "personal_experience", "creator_trust", "price_concern", "complaint"]
    f = pd.DataFrame({
        "n_comments": g.size(), "spam_ratio": g["spam"].mean(), "dup_ratio": g["dup_text"].mean(),
        "generic_ratio": g.apply(lambda x: ((x["positive_reaction"] == 1) & (x[other].sum(axis=1) == 0)).mean()),
        "meaningful_ratio": g.apply(lambda x: ((x["spam"] == 0) & (x["n_words"] >= 5) & (x[other].sum(axis=1) > 0)).mean()),
        "need_ratio": g["need_match"].mean(), "question_ratio": g["product_question"].mean(),
        "experience_ratio": g["personal_experience"].mean(), "purchase_ratio": g["purchase_intent"].mean(),
        "trust_ratio": g["creator_trust"].mean(), "price_ratio": g["price_concern"].mean(),
        "complaint_ratio": g["complaint"].mean(), "english_ratio": g["is_english"].mean(),
    })
    v = vids.groupby("creator_id").agg(avg_views=("views", "mean"), avg_likes=("likes", "mean"), avg_comments=("comment_count", "mean"))
    v["engagement_rate"] = (v["avg_likes"] + v["avg_comments"]) / v["avg_views"].clip(lower=1)
    v["comment_density"] = 1000 * v["avg_comments"] / v["avg_views"].clip(lower=1)
    v["like_rate"] = 1000 * v["avg_likes"] / v["avg_views"].clip(lower=1)
    out = creators.join(f, how="inner").join(v).join(loyalty(all_comments))
    num = out.select_dtypes("number").columns
    out[num] = out[num].fillna(0)
    return out


def loyalty(comments, min_commenters=50):
    d = comments[comments["author_id"].fillna("") != ""]
    d = d[d["author_id"] != d["creator_id"]]
    if d.empty:
        return pd.DataFrame(columns=["unique_commenters", "repeat_commenters", "loyalty_ratio"])
    per = d.groupby(["creator_id", "author_id"])["video_id"].nunique()
    g = per.groupby(level="creator_id")
    out = pd.DataFrame({"unique_commenters": g.size(), "repeat_commenters": g.apply(lambda s: int((s >= 2).sum()))})
    out["loyalty_ratio"] = out["repeat_commenters"] / out["unique_commenters"]
    return out


def estimated_cost(subs):
    return 20 * subs / 1000 if subs < 1_000_000 else 15 * subs / 1000


def max_affordable_subs(budget):
    """Largest subscriber count whose estimated cost stays within budget + 50% negotiation room."""
    limit = 1.5 * budget
    return int(1000 * limit / 15) if 1000 * limit / 20 >= 1_000_000 else int(1000 * limit / 20)


def minmax(s):
    lo, hi = s.min(), s.max()
    return pd.Series(50.0, index=s.index) if hi - lo < 1e-9 else 100 * (s - lo) / (hi - lo)


def score(feat, weights, budget, min_comments):
    d = feat.copy()
    for c in ["loyalty_ratio", "comment_density", "like_rate", "unique_commenters"]:
        if c not in d:
            d[c] = 0.0
    d["est_cost"] = d["subscribers"].apply(estimated_cost)
    reasons = pd.Series("", index=d.index)
    for mask, why in [(d["est_cost"] > budget * 1.5, "over budget"),
                      (d["english_ratio"] < 0.6, "audience mostly non-English"),
                      (d["n_comments"] < min_comments, "too few comments to judge")]:
        reasons[mask] = reasons[mask].where(reasons[mask] == "", reasons[mask] + "; ") + why
    d["filter_reason"] = reasons
    d["eligible"] = reasons == ""
    d["content_relevance"] = minmax(d["content_sim"])
    d["audience_need"] = minmax(0.5 * d["need_ratio"] + 0.25 * d["question_ratio"] + 0.25 * d["experience_ratio"])
    d["purchase_trust"] = minmax(0.6 * d["purchase_ratio"] + 0.4 * d["trust_ratio"])
    d["engagement_quality"] = minmax(d["meaningful_ratio"] - 0.5 * d["spam_ratio"] - 0.3 * d["generic_ratio"] - 0.2 * d["dup_ratio"])
    d["community"] = minmax(0.4 * minmax(d["loyalty_ratio"]) + 0.4 * minmax(d["comment_density"]) + 0.2 * minmax(d["like_rate"]))
    d["match_score"] = sum(weights[k] * d[k] for k in weights).round(1)
    d.loc[~d["eligible"], "match_score"] = np.nan
    d["value_per_1k"] = d["match_score"] / (d["est_cost"].clip(lower=1) / 1000)
    return d.sort_values("match_score", ascending=False)


def evidence(comments, cid, n=6):
    d = comments[(comments["creator_id"] == cid) & (comments["spam"] == 0)].copy()
    d["ev"] = (2 * d["purchase_intent"] + 1.5 * d["product_question"] + 1.5 * d["personal_experience"]
               + 1.5 * d["creator_trust"] + 2 * d["need_match"] + np.log1p(d["likes"]) * 0.3)
    return d.drop_duplicates("text").nlargest(n, "ev")


# ==================================================================
# Live search
# ==================================================================

def run_search(brief, yt_key, gem_key, progress=lambda step, msg, frac=None: None):
    """Full live pipeline. `progress(step, message, fraction)` is called as work proceeds."""
    t_start = time.time()
    queries = queries_from_brief(brief)

    # 1. discover
    progress("find", f"Searching YouTube for {', '.join(queries)}", 0.03)
    hits = {}
    for q in queries:
        d = yt_get("search", yt_key, part="snippet", q=q, type="video", maxResults=50,
                   relevanceLanguage="en", regionCode="US", order="relevance")
        for it in d.get("items", []):
            cid = it["snippet"]["channelId"]
            h = hits.setdefault(cid, {"channel_id": cid, "channel_title": it["snippet"]["channelTitle"], "n_hits": 0, "queries": set()})
            h["n_hits"] += 1; h["queries"].add(q)
    if not hits:
        raise SearchError("YouTube returned no videos for these keywords. Try broader or different keywords.")
    cand = pd.DataFrame([{**h, "n_queries": len(h["queries"]), "queries": "; ".join(sorted(h["queries"]))} for h in hits.values()])
    rows, ids = [], cand["channel_id"].tolist()
    for i in range(0, len(ids), 50):
        for ch in yt_get("channels", yt_key, part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).get("items", []):
            s, sn = ch["statistics"], ch["snippet"]
            th = sn.get("thumbnails", {})
            rows.append({"channel_id": ch["id"], "subscribers": int(s.get("subscriberCount", 0)), "hidden": bool(s.get("hiddenSubscriberCount", False)),
                         "video_count": int(s.get("videoCount", 0)), "country": sn.get("country", ""), "handle": sn.get("customUrl", ""),
                         "contact_email": find_email(sn.get("description", "")),
                         "thumbnail": (th.get("medium") or th.get("default") or {}).get("url", ""),
                         "uploads": ch["contentDetails"]["relatedPlaylists"]["uploads"]})
    cand = cand.merge(pd.DataFrame(rows), on="channel_id", how="inner")
    excl = re.compile("|".join(re.escape(w) for w in EXCLUDE), re.I)
    cap = max_affordable_subs(brief.get("budget_usd", 30000))
    checks = {"subscribers out of range": cand["subscribers"].between(LIVE["min_subs"], LIVE["max_subs"]) & ~cand["hidden"],
              "over budget": cand["subscribers"] <= cap,
              "inactive channel": cand["video_count"] >= 15,
              "not an English-speaking country": cand["country"].isin(COUNTRIES),
              "brand or store account": ~cand["channel_title"].str.contains(excl)}
    cand["rejected_by"] = ""
    for why, ok in checks.items():
        cand.loc[~ok & (cand["rejected_by"] == ""), "rejected_by"] = why
    cand["discovery_score"] = 2 * cand["n_queries"] + cand["n_hits"]
    picked = cand[cand["rejected_by"] == ""].sort_values(["discovery_score", "subscribers"], ascending=False).head(LIVE["n_creators"])
    cand["selected"] = cand["channel_id"].isin(picked["channel_id"])
    if len(picked) < 3:
        raise SearchError(f"Only {len(picked)} creators passed the filters. Try broader keywords.")
    progress("find", f"Found {len(cand)} channels, kept {len(picked)} creators", 0.15)

    # 2. collect (parallel)
    def collect(row):
        pl = yt_get("playlistItems", yt_key, part="contentDetails", playlistId=row.uploads, maxResults=LIVE["n_videos"])
        vids = [it["contentDetails"]["videoId"] for it in pl.get("items", [])]
        if not vids:
            return [], []
        vd = yt_get("videos", yt_key, part="snippet,statistics", id=",".join(vids))
        videos, comments = [], []
        for v in vd.get("items", []):
            s, st = v["snippet"], v["statistics"]
            videos.append({"video_id": v["id"], "creator_id": row.channel_id, "title": s["title"],
                           "description": s.get("description", "")[:600], "contact_email": find_email(s.get("description", "")),
                           "tags": " ".join(s.get("tags", [])[:15]),
                           "published_at": s["publishedAt"], "views": int(st.get("viewCount", 0)),
                           "likes": int(st.get("likeCount", 0)), "comment_count": int(st.get("commentCount", 0))})
            try:
                cd = yt_get("commentThreads", yt_key, part="snippet", videoId=v["id"], maxResults=LIVE["comments_per_video"],
                            order="relevance", textFormat="plainText")
            except RuntimeError:
                continue  # comments disabled
            for c in cd.get("items", []):
                top = c["snippet"]["topLevelComment"]["snippet"]
                comments.append({"comment_id": c["id"], "video_id": v["id"], "creator_id": row.channel_id,
                                 "text": top.get("textDisplay", ""), "likes": int(top.get("likeCount", 0)),
                                 "replies": int(c["snippet"].get("totalReplyCount", 0)),
                                 "author_id": (top.get("authorChannelId") or {}).get("value", "")})
        return videos, comments

    videos, comments = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(collect, r): r for r in picked.itertuples()}
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                v, c = fu.result()
                videos += v; comments += c
            except SearchError:
                raise
            except Exception:
                pass
            progress("collect", f"Collected {len(comments):,} comments from {i} of {len(picked)} creators", 0.15 + 0.25 * i / len(picked))
    if not comments:
        raise SearchError("These creators have no public comments to read. Try different keywords.")
    videos_df = pd.DataFrame(videos).drop_duplicates("video_id")
    comments_df = clean(pd.DataFrame(comments))

    # 3. AI labels (parallel batches); the content-relevance call runs at the same time
    sample = sample_for_ai(comments_df, LIVE["classify_per_creator"])
    side = ThreadPoolExecutor(max_workers=1)
    rel_future = side.submit(content_relevance, picked, videos_df, brief, gem_key)
    labels = classify(sample, brief, gem_key, lambda done, total: progress(
        "read", f"Gemini read {done:,} of {total:,} comments", 0.4 + 0.35 * done / max(total, 1)))
    lab = sample[sample["comment_id"].isin(labels)].copy()
    if lab.empty:
        raise SearchError("Gemini is busy right now and couldn't read the comments. Try again in a minute, or open an example.")
    lab["labels"] = lab["comment_id"].map(lambda i: [l for l in labels[i] if l in LABELS])
    for l in LABELS:
        lab[l] = lab["labels"].apply(lambda ls: int(l in ls))
    lab["need_match"] = lab["comment_id"].map(lambda i: int("audience_need" in labels[i]))
    lab["spam"] = ((lab["spam"] == 1) | lab["spam_rule"]).astype(int)

    # 4. content relevance
    progress("score", "Scoring creators", 0.8)
    rel = rel_future.result()
    side.shutdown(wait=False)
    creators = picked.rename(columns={"channel_id": "creator_id", "channel_title": "creator_name"}).set_index("creator_id")
    # no email in the channel description: fall back to the first one in a recent video's description
    if "contact_email" in videos_df:
        from_videos = videos_df[videos_df["contact_email"] != ""].groupby("creator_id")["contact_email"].first()
        creators["contact_email"] = [e or from_videos.get(c, "") for c, e in creators["contact_email"].items()]
    feat = features(lab, videos_df, creators[["creator_name", "handle", "subscribers", "thumbnail", "contact_email"]], comments_df)
    feat["content_sim"] = rel.reindex(feat.index).fillna(0) / 100

    # 5. explanations for the top picks
    progress("explain", "Writing explanations for the top picks", 0.88)
    ranked = score(feat, WEIGHT_PRESETS[brief.get("goal", "conversion")], brief["budget_usd"], min_comments=15)
    rationales = {}
    top_ids = list(ranked[ranked["eligible"]].index[:LIVE["explain_top"]])
    with ThreadPoolExecutor(max_workers=LIVE["explain_top"]) as ex:
        futs = {ex.submit(explain, ranked.loc[c], evidence(lab, c), brief, gem_key): c for c in top_ids}
        for fu in as_completed(futs):
            try:
                rationales[futs[fu]] = fu.result()
            except Exception:
                pass

    funnel = {"queries": queries, "channels_found": len(cand), "channels_passed": int((cand["rejected_by"] == "").sum()),
              "creators": int(feat.shape[0]), "videos": len(videos_df), "comments": len(comments_df),
              "spam_rule": int(comments_df["spam_rule"].sum()), "dup_text": int(comments_df["dup_text"].sum()),
              "non_english": int((~comments_df["is_english"]).sum()), "classified": len(lab),
              "seconds": round(time.time() - t_start, 1)}
    progress("done", f"Done in {funnel['seconds']:.0f} seconds", 1.0)
    return {"source": "live", "brief": brief, "feat": feat, "comments": lab, "videos": videos_df, "rationales": rationales,
            "funnel": funnel, "metrics": {}, "discovery": cand.drop(columns=["uploads"], errors="ignore"),
            "label_guide": label_guide(brief), "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


# ==================================================================
# Evaluation: human labels vs the AI (Macro-F1, keyword baseline, Cohen's kappa)
# ==================================================================

KEYWORD_RULES = {   # the simple baseline the AI has to beat
    "purchase_intent": r"where (can|do) i (buy|get)|ordered|just bought|buying|add(ed)? to cart|gonna buy|\bbought\b",
    "product_question": r"\?",
    "personal_experience": r"\bmy\b|\bi have\b|\bi get\b|\bi keep\b|i've been",
    "creator_trust": r"trust (you|your)|because you recommended|your advice|thank you",
    "price_concern": r"price|expensive|cheap|worth|afford|budget|sale|\$\d",
    "positive_reaction": r"pretty|love|queen|gorgeous|obsessed|amazing|beast|goat|😍|🔥",
    "complaint": r"hate|worst|disappoint|didn'?t work|broke me out|blister|fell apart|returned|side effect",
    "spam": r"check (out )?my channel|sub(scribe)? to|sub to my|http",
}


def keyword_labels(text):
    return [l for l, p in KEYWORD_RULES.items() if re.search(p, str(text), re.I)]


def annotation_sample(comments, n=200, seed=1):
    """The same comments for every annotator: an even sample per creator, fixed seed."""
    per = max(1, n // max(1, comments["creator_id"].nunique()))
    s = pd.concat([g.sample(min(len(g), per), random_state=seed) for _, g in comments.groupby("creator_id")])
    return s.drop_duplicates("comment_id").head(n).reset_index(drop=True)


def _matrix(label_lists):
    return np.array([[int(l in ls) for l in LABELS] for ls in label_lists])


def f1_per_label(y_true, y_pred):
    out = {}
    for j, l in enumerate(LABELS):
        tp = int(((y_true[:, j] == 1) & (y_pred[:, j] == 1)).sum())
        fp = int(((y_true[:, j] == 0) & (y_pred[:, j] == 1)).sum())
        fn = int(((y_true[:, j] == 1) & (y_pred[:, j] == 0)).sum())
        out[l] = None if tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)   # None: label never used by either side
    return out


def macro(f1s):
    vals = [v for v in f1s.values() if v is not None]
    return float(np.mean(vals)) if vals else None


def kappa_per_label(a, b):
    out = {}
    for j, l in enumerate(LABELS):
        x, y = a[:, j], b[:, j]
        po = float((x == y).mean())
        pe = float(x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean()))
        out[l] = None if pe >= 1 else (po - pe) / (1 - pe)
    return out


def evaluate_labels(comments, human):
    """human: {comment_id: [labels]}. Compares with the AI's labels and with keyword rules."""
    d = comments.drop_duplicates("comment_id").set_index("comment_id")
    ids = [i for i in human if i in d.index]
    if not ids:
        return None
    y_true = _matrix([human[i] for i in ids])
    y_ai = d.loc[ids, LABELS].fillna(0).astype(int).values
    y_kw = _matrix([keyword_labels(t) for t in d.loc[ids, "text"]])
    f_ai, f_kw = f1_per_label(y_true, y_ai), f1_per_label(y_true, y_kw)
    return {"n": len(ids), "macro_f1_ai": macro(f_ai), "macro_f1_keyword": macro(f_kw), "f1_ai": f_ai, "f1_keyword": f_kw}


def agreement(h1, h2):
    """Cohen's kappa between two annotators on the comments both labelled."""
    ids = [i for i in h1 if i in h2]
    if len(ids) < 10:
        return None
    k = kappa_per_label(_matrix([h1[i] for i in ids]), _matrix([h2[i] for i in ids]))
    vals = [v for v in k.values() if v is not None]
    return {"n": len(ids), "kappa_mean": float(np.mean(vals)) if vals else None, "kappa": k}


def combine_labels(everyone):
    """Merge several annotators into one answer per comment: majority vote, ties go to the first annotator by name."""
    names = sorted(everyone)
    ids = sorted({i for n in names for i in everyone[n]})
    out = {}
    for i in ids:
        voters = [n for n in names if i in everyone[n]]
        labs = []
        for l in LABELS:
            votes = sum(l in everyone[n][i] for n in voters)
            if votes * 2 > len(voters) or (votes * 2 == len(voters) and l in everyone[voters[0]][i]):
                labs.append(l)
        out[i] = labs
    return out


def team_agreement(everyone):
    """Mean Cohen's kappa over every pair of annotators who share at least 10 comments."""
    names = sorted(everyone)
    pairs = [agreement(everyone[a], everyone[b]) for k, a in enumerate(names) for b in names[k + 1:]]
    pairs = [p for p in pairs if p and p["kappa_mean"] is not None]
    if not pairs:
        return None
    return {"pairs": len(pairs), "n": min(p["n"] for p in pairs), "kappa_mean": float(np.mean([p["kappa_mean"] for p in pairs]))}


# ==================================================================
# Examples from Colab
# ==================================================================

def load_example(folder: Path):
    feat = pd.read_csv(folder / "features.csv", index_col=0)
    for c in ["thumbnail", "handle", "contact_email"]:
        feat[c] = feat[c].fillna("") if c in feat else ""
    meta = json.loads((folder / "brief.json").read_text())
    brief = dict(meta["brief"])
    brief.setdefault("keywords", ", ".join(meta.get("discovery_queries", [])) or brief.get("category", ""))
    metrics = json.loads((folder / "metrics.json").read_text()) if (folder / "metrics.json").exists() else {}
    return {"source": "example", "mock": bool(meta.get("mock")), "brief": brief, "feat": feat,
            "comments": pd.read_csv(folder / "comments.csv"),
            "videos": pd.read_csv(folder / "videos.csv") if (folder / "videos.csv").exists() else pd.DataFrame(),
            "rationales": json.loads((folder / "rationales.json").read_text()),
            "funnel": metrics.get("funnel", {}), "metrics": metrics,
            "discovery": pd.read_csv(folder / "discovery.csv") if (folder / "discovery.csv").exists() else None,
            "label_guide": meta.get("label_guide", ""), "created_at": meta.get("exported_at", ""),
            "creator_source": meta.get("creator_source", "manual"), "live_examples": meta.get("live_examples", [])}
