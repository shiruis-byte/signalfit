# SignalFit app (Streamlit)

A brand describes its product; SignalFit searches YouTube, reads what each creator's viewers say in the comments with Gemini, and ranks creators by real needs, buying intent and trust.

## Files
- `app.py`: the screens (sign-in, search, results and its five tabs)
- `ui.py`: the look and shared pieces (colors, stylesheet, avatars, quotes, session state)
- `engine.py`: everything behind the screens (YouTube, Gemini, scoring, the live search), no Streamlit code
- `requirements.txt`, `.streamlit/config.toml`
- `app_data/<category>/` (optional): prepared examples exported by the Colab notebook (section 11). Unzip `app_data.zip` here.

## Secrets (Streamlit Cloud: App settings, Secrets)

    YOUTUBE_API_KEY = "..."
    GEMINI_API_KEY = "..."
    ACCESS_CODE = "..."   # optional: visitors need this code to enter (protects your API quota)

Never commit keys. `.streamlit/secrets.toml` is git-ignored.

## Run locally
    pip install -r requirements.txt
    streamlit run app.py

## Live search sizes
12 creators, 5 recent videos each, up to 50 top comments per video, 40 comments per creator read by Gemini.
Change them in `LIVE` near the top of `engine.py`. Each search uses about 400 YouTube quota units (daily free quota: 10,000).
