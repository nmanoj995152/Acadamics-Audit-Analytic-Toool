import streamlit as st


def apply_theme() -> None:
    st.markdown("""
    <style>
    :root { color-scheme: light; }
    [data-testid="stAppViewContainer"] { background: #f3f6fb; color: #17243a; }
    [data-testid="stHeader"] { background: rgba(243,246,251,.92); }
    .block-container { max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem; }
    h1,h2,h3,h4,p,label,span,small { color: #17243a; }
    h1 { letter-spacing: -.035em; font-weight: 750; }
    [data-testid="stMetric"] { background: #fff; border: 1px solid #dce4ef; padding: 1rem 1.1rem; border-radius: 14px; box-shadow: 0 3px 12px #1c36500a; }
    [data-testid="stMetricLabel"] { color: #52647c !important; }
    [data-testid="stMetricValue"] { color: #123d68 !important; }
    [data-testid="stVerticalBlockBorderWrapper"] { background: #fff; border-color: #dce4ef !important; border-radius: 16px; }
    [data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid #dce4ef; border-radius: 12px; }
    .stButton > button, [data-testid="stFormSubmitButton"] button { background: #145b91; color: #fff; border: 0; border-radius: 9px; font-weight: 650; }
    .stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover { background: #0e456f; color: #fff; }
    div[data-baseweb="input"] input, div[data-baseweb="select"] > div, textarea { background: #fff; color: #17243a; border-color: #bdcad9; }
    [data-testid="stSidebar"] { background: #102b46; }
    [data-testid="stSidebar"] * { color: #edf5fc !important; }
    [data-testid="stAlert"] { border-radius: 10px; }
    </style>""", unsafe_allow_html=True)
