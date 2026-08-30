import streamlit as st


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --rag-ink: #172033;
            --rag-muted: #667085;
            --rag-accent: #2f6fed;
            --rag-accent-soft: #eef4ff;
            --rag-success: #13795b;
            --rag-border: rgba(23, 32, 51, 0.12);
        }
        .stApp {
            background:
                radial-gradient(circle at 85% 0%, rgba(47,111,237,.08), transparent 28rem),
                linear-gradient(180deg, #fbfcff 0%, #f7f9fc 100%);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #121a2b 0%, #17243d 100%);
        }
        [data-testid="stSidebar"] * { color: #f7f9ff; }
        [data-testid="stSidebar"] .stCaption { color: #b8c4db; }
        [data-testid="stSidebar"] input {
            color: #172033;
            background: #ffffff;
        }
        [data-testid="stSidebar"] [data-baseweb="radio"] label {
            border-radius: .65rem;
            padding: .35rem .5rem;
        }
        .block-container { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem; }
        h1, h2, h3 { color: var(--rag-ink); letter-spacing: -.025em; }
        .rag-eyebrow {
            color: var(--rag-accent);
            font-size: .77rem;
            font-weight: 750;
            letter-spacing: .11em;
            text-transform: uppercase;
            margin-bottom: .35rem;
        }
        .rag-subtitle { color: var(--rag-muted); font-size: 1.02rem; margin: -.45rem 0 1.5rem; }
        .rag-service {
            border: 1px solid var(--rag-border);
            border-radius: .8rem;
            background: rgba(255,255,255,.8);
            padding: .8rem .9rem;
            min-height: 5.2rem;
        }
        .rag-service-name { color: var(--rag-muted); font-size: .78rem; text-transform: uppercase; }
        .rag-service-status { color: var(--rag-ink); font-size: 1.05rem; font-weight: 700; }
        .rag-source-meta { color: var(--rag-muted); font-size: .82rem; }
        .rag-pill {
            display: inline-block;
            background: var(--rag-accent-soft);
            color: #2455b5;
            border-radius: 999px;
            padding: .15rem .55rem;
            margin: .1rem .2rem .1rem 0;
            font-size: .76rem;
            font-weight: 650;
        }
        [data-testid="stMetric"] {
            border: 1px solid var(--rag-border);
            border-radius: .8rem;
            background: rgba(255,255,255,.82);
            padding: .8rem 1rem;
        }
        [data-testid="stChatMessage"] {
            border: 1px solid var(--rag-border);
            border-radius: 1rem;
            background: rgba(255,255,255,.82);
            padding: .4rem .7rem;
        }
        div.stButton > button, div.stDownloadButton > button { border-radius: .65rem; }
        div[data-testid="stFileUploader"] {
            border: 1px dashed rgba(47,111,237,.35);
            border-radius: 1rem;
            background: rgba(238,244,255,.48);
            padding: .5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_intro(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="rag-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="rag-subtitle">{subtitle}</div>', unsafe_allow_html=True)
