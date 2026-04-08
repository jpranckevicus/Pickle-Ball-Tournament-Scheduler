# Deploy so it works on any phone (no Wi‑Fi dependency)

This app is a Streamlit web app.

To use it from anyone’s phone **without running it on your computer**, you need to **host** it.

## Option A (easiest): Streamlit Community Cloud

1. Create a GitHub repo containing these files:
   - `streamlit_app.py`
   - `pickleball_tournament.py`
   - `requirements.txt`

2. Push the repo to GitHub.

3. Go to Streamlit Community Cloud and create a new app:
   - Repo: your GitHub repo
   - Main file path: `streamlit_app.py`

4. After it deploys, you’ll get a public URL.
   - Open that URL on any phone.
   - Share that URL with your professor.

## Option B: Host it yourself (Render/Fly/etc.)

Any host that can run a Python web process will work.

- Install deps: `pip install -r requirements.txt`
- Start command: `streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port $PORT`

(Your host will provide the `$PORT` environment variable.)
