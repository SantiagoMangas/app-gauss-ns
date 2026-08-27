"""
NC Dashboard — Evaluaciones Concentración Nacional (Sub16/Sub19, Damas/Caballeros)
Pestaña 1: Campana de Gauss, búsqueda y alta (entrenador → Google Sheet; invitado → sesión).
Pestaña 2: Gráfico Radar y ranking por suma de Z-score.
"""

import base64
import hmac
import html as html_lib
import json
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from scipy import stats
import gspread
from google.oauth2.service_account import Credentials

OPCION_VACIA = "— Ninguno —"
DIR_APP = Path(__file__).resolve().parent
DIR_ASSETS = DIR_APP / "assets"
DIR_LOGOS = DIR_APP.parent / "Logos NS Dash"
CREDENTIALS_FILE = DIR_APP / "credentials.json"
SPREADSHEET_ID_FALLBACK = "1-QH7kyR6Ecxen5TMoSzop1EbANq39uYFQtrNmBb0hBY"
HOJA_VIDEOS = "Videos"

# Evaluaciones donde un valor MÁS BAJO es mejor (tiempos).
# En estas se invierte el signo del Z-score para que "mejor" sea siempre positivo.
EVALUACIONES_INVERTIDAS = {"Sprint 30m", "Test T (Mod)"}

# Nombres internos de las columnas. El orden de COLS_EVAL debe coincidir con el
# de las columnas E-J (1ª evaluación) y L-Q (2ª evaluación) del Google Sheet.
COL_NUM = "N°"
COL_NOMBRE = "Nombre y Apellido"
COL_FECHA_1 = "Fecha 1ª evaluación"
COL_ASOC = "Asociación"
COL_FECHA_2 = "Fecha 2ª evaluación"
COLS_EVAL = ["SJ", "CMJ", "ABK", "Sprint 30m", "Test T (Mod)", "30-15 IFT"]
SUF_1 = " (1ª)"
SUF_2 = " (2ª)"
ANCHO_HOJA = 17  # columnas A hasta Q


# ======================================================================
# ESTÉTICA
# Todo lo visual vive acá: una sola paleta, una sola tipografía y un solo
# set de bordes/sombras que se reutiliza en la landing, la barra de sesión,
# los widgets de Streamlit, las tablas HTML y los gráficos de Plotly.
# CSS_BASE se inyecta en las dos vistas (landing y dashboard) para que el
# estilo sea idéntico en toda la app; CSS_LANDING y CSS_DASHBOARD solo
# agregan lo propio de cada superficie (oscura y clara).
# ======================================================================
CSS_BASE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  :root{
    --ns-navy:#16304F;
    --ns-navy-soft:#1E3A5F;
    --ns-ice:#7EB6E0;
    --ns-ice-soft:#9EC5E8;
    --ns-ink:#16202E;
    --ns-muted:#5B6B7F;
    --ns-line:#E4EAF1;
    --ns-tint:#EEF4FB;
    --ns-shadow-sm:0 1px 2px rgba(16,32,52,.05), 0 1px 3px rgba(16,32,52,.04);
    --ns-shadow-md:0 6px 20px rgba(16,32,52,.09), 0 1px 3px rgba(16,32,52,.04);
  }

  /* --- Tipografía ---
     Inter solo en texto legible. NO en span/button/div globales:
     Streamlit usa ligatures Material Icons (visibility, arrow_drop_down)
     en spans y botones internos; si les pisamos la fuente, se ve el texto. */
  .stApp{
    font-family:'Inter','Segoe UI',system-ui,-apple-system,'Helvetica Neue',sans-serif;
  }
  .stApp p, .stApp label, .stApp li,
  .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
  .stApp input, .stApp textarea,
  [data-testid="stMarkdown"] p,
  [data-testid="stWidgetLabel"] p,
  [data-testid="stCaptionContainer"] p,
  [data-testid="stMetricValue"],
  [data-testid="stMetricLabel"] p,
  [role="option"]{
    font-family:inherit;
  }
  .stApp h1{ font-weight:800; letter-spacing:-.022em; }
  .stApp h2{ font-weight:700; letter-spacing:-.015em; }
  .stApp h3{ font-weight:700; letter-spacing:-.012em; }
  .stApp h4{ font-weight:700; letter-spacing:-.006em; }

  [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label{
    font-size:.85rem; font-weight:600; color:var(--ns-muted);
  }
  [data-testid="stCaptionContainer"] p{
    font-size:.82rem; line-height:1.6; color:var(--ns-muted);
  }

  /* --- Botones de acción (excluye iconos internos: ojo, flecha, etc.) --- */
  .stApp button[kind]:not([kind="icon"]),
  .stApp [data-testid^="stBaseButton-"]:not([data-testid="stBaseButton-icon"]){
    border-radius:10px !important;
    font-weight:600 !important;
    letter-spacing:.01em;
    transition:transform .12s ease, box-shadow .18s ease,
               background-color .18s ease, border-color .18s ease;
  }
  .stApp button[kind]:not([kind="icon"]):active,
  .stApp [data-testid^="stBaseButton-"]:not([data-testid="stBaseButton-icon"]):active{
    transform:translateY(0);
  }

  .stApp button[kind="primary"],
  .stApp button[kind="primaryFormSubmit"],
  .stApp [data-testid="stBaseButton-primary"],
  .stApp [data-testid="stBaseButton-primaryFormSubmit"]{
    background:linear-gradient(180deg,#27496F,#1A3252) !important;
    border:1px solid #14293F !important;
    color:#FFFFFF !important;
    box-shadow:0 1px 2px rgba(16,32,52,.18) !important;
  }
  .stApp button[kind="primary"]:hover,
  .stApp button[kind="primaryFormSubmit"]:hover,
  .stApp [data-testid="stBaseButton-primary"]:hover,
  .stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover{
    transform:translateY(-1px);
    box-shadow:0 8px 20px rgba(22,48,79,.26) !important;
  }
  .stApp button[kind="secondary"],
  .stApp button[kind="secondaryFormSubmit"],
  .stApp [data-testid="stBaseButton-secondary"],
  .stApp [data-testid="stBaseButton-secondaryFormSubmit"]{
    background:#FFFFFF !important;
    border:1px solid var(--ns-line) !important;
    color:var(--ns-navy-soft) !important;
  }
  .stApp button[kind="secondary"]:hover,
  .stApp button[kind="secondaryFormSubmit"]:hover,
  .stApp [data-testid="stBaseButton-secondary"]:hover,
  .stApp [data-testid="stBaseButton-secondaryFormSubmit"]:hover{
    border-color:var(--ns-ice) !important; background:#F8FBFE !important;
    transform:translateY(-1px);
  }

  /* --- Campos de texto y desplegables --- */
  [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"]{
    border-radius:10px !important;
  }
  [data-baseweb="input"] > div, [data-baseweb="select"] > div,
  [data-baseweb="textarea"] > div{
    border-radius:10px !important;
    border-color:var(--ns-line) !important;
    transition:border-color .16s ease, box-shadow .16s ease;
  }
  [data-baseweb="input"] > div:focus-within, [data-baseweb="select"] > div:focus-within,
  [data-baseweb="textarea"] > div:focus-within{
    border-color:var(--ns-navy-soft) !important;
    box-shadow:0 0 0 3px rgba(126,182,224,.30) !important;
  }
  [data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"]{
    border-radius:12px !important;
    border:1px solid var(--ns-line) !important;
    box-shadow:var(--ns-shadow-md) !important;
    overflow:hidden;
  }
  [role="option"]{ font-size:.9rem; }
  [role="option"]:hover{ background:var(--ns-tint) !important; }
  [data-baseweb="tag"]{
    background:var(--ns-navy-soft) !important;
    border-radius:8px !important;
    color:#FFFFFF !important;
    font-weight:600;
  }
  [data-baseweb="tag"] svg{ fill:#FFFFFF; }

  /* Iconos Material de Streamlit/BaseWeb: no tocar tipografía ni estilo */
  [data-testid="stTextInput"] button,
  [data-baseweb="input"] button,
  [data-baseweb="select"] [data-baseweb="icon"],
  [data-baseweb="select"] [aria-hidden="true"],
  [data-baseweb="select"] svg,
  .stApp button[kind="icon"],
  .stApp [data-testid="stBaseButton-icon"],
  .stApp .material-icons,
  .stApp .material-symbols-outlined,
  .stApp .material-symbols-rounded{
    font-family:"Material Icons","Material Symbols Rounded",sans-serif !important;
    font-weight:400 !important;
    letter-spacing:normal !important;
    text-transform:none !important;
    background:transparent !important;
    border:none !important;
    box-shadow:none !important;
    transform:none !important;
    border-radius:6px !important;
  }
  [data-testid="stTextInput"] button:hover,
  [data-baseweb="input"] button:hover,
  .stApp button[kind="icon"]:hover,
  .stApp [data-testid="stBaseButton-icon"]:hover{
    background:rgba(126,182,224,.12) !important;
    box-shadow:none !important;
    transform:none !important;
  }

  /* --- Tablas HTML propias (Gauss y Radar) --- */
  .ns-table-wrap{
    border:1px solid var(--ns-line);
    border-radius:14px;
    overflow:hidden;
    background:#FFFFFF;
    box-shadow:var(--ns-shadow-sm);
  }
  .ns-table{
    width:100%;
    border-collapse:collapse;
    font-size:14px;
    font-variant-numeric:tabular-nums;
    font-feature-settings:"tnum";
  }
  .ns-table-hover tbody tr{ transition:background-color .12s ease; }
  .ns-table-hover tbody tr:hover td{ background:var(--ns-tint) !important; }

  /* --- Tarjeta de referencias --- */
  .ns-legend{
    border:1px solid var(--ns-line);
    border-radius:14px;
    padding:16px 18px;
    background:linear-gradient(180deg,#FFFFFF,#F8FBFE);
    box-shadow:var(--ns-shadow-sm);
    display:flex; flex-wrap:wrap; gap:18px;
  }
  .ns-legend-title{
    width:100%; font-size:13px; font-weight:700;
    color:var(--ns-navy); letter-spacing:.02em;
  }
  .ns-legend-item{ font-size:12.4px; color:#48566B; }
  .ns-legend-item b{ color:var(--ns-ink); }

  /* --- Barra de scroll --- */
  ::-webkit-scrollbar{ width:10px; height:10px; }
  ::-webkit-scrollbar-track{ background:transparent; }
  ::-webkit-scrollbar-thumb{
    background:#CBD8E6; border-radius:8px;
    border:2px solid transparent; background-clip:padding-box;
  }
  ::-webkit-scrollbar-thumb:hover{ background:#B0C4D8; background-clip:padding-box; }
</style>
"""

CSS_LANDING = """
<style>
  [data-testid="stAppViewContainer"],
  [data-testid="stMain"],
  .stApp{
    background:
      radial-gradient(1200px 560px at 50% -12%, rgba(126,182,224,.18), transparent 62%),
      radial-gradient(760px 420px at 108% 106%, rgba(30,58,95,.42), transparent 66%),
      #05080C !important;
  }
  .stApp header, header[data-testid="stHeader"]{ background:transparent !important; }
  .block-container { padding-top: 2.2rem; max-width: 980px; }
  [data-testid="stToolbar"], footer { visibility: hidden; height: 0; }

  /* Solo el wordmark del login: no se selecciona ni se arrastra.
     No aplica a inputs, botones ni al resto de la página. */
  [class*="st-key-ns_landing_logo"] [data-testid="stImage"],
  [class*="st-key-ns_landing_logo"] img{
    -webkit-user-select:none !important;
    -moz-user-select:none !important;
    user-select:none !important;
    -webkit-user-drag:none !important;
    user-drag:none !important;
    -webkit-touch-callout:none !important;
    pointer-events:none;
    filter:drop-shadow(0 8px 26px rgba(126,182,224,.20));
  }

  /* Solo las dos tarjetas de acceso, no cualquier bloque vertical
     (el data-testid de borde lo lleva todo contenedor, tarjeta o no). */
  [class*="st-key-ns_card_"]{
    background:linear-gradient(180deg, rgba(23,31,42,.96), rgba(12,17,24,.96)) !important;
    border:1px solid rgba(126,182,224,.30) !important;
    border-radius:18px !important;
    box-shadow:0 20px 44px rgba(0,0,0,.46), inset 0 1px 0 rgba(255,255,255,.05) !important;
    transition:border-color .2s ease, box-shadow .2s ease;
  }
  [class*="st-key-ns_card_"]:hover{
    border-color:rgba(126,182,224,.52) !important;
    box-shadow:0 26px 56px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.06) !important;
  }
  [data-testid="stForm"]{
    background:rgba(126,182,224,.04) !important;
    border:1px solid rgba(126,182,224,.16) !important;
    border-radius:14px !important;
    box-shadow:none !important;
  }

  [data-testid="stHeading"] *,
  [data-testid="stMarkdown"] p,
  [data-testid="stCaptionContainer"] *,
  [data-testid="stWidgetLabel"] *,
  [data-testid="stWidgetLabel"] p,
  label, h1, h2, h3, h4 {
    color: #eef3f8 !important;
  }
  [data-testid="stWidgetLabel"] p{ color:#B7CDDF !important; }

  [data-testid="InputInstructions"] { display: none !important; }

  [data-testid="stTextInput"] input,
  [data-baseweb="input"] input,
  input[type="text"],
  input[type="password"] {
    color: #1a1d21 !important;
    -webkit-text-fill-color: #1a1d21 !important;
    background-color: #ffffff !important;
    border-radius:9px !important;
  }
  [data-baseweb="input"] > div{
    background-color:#ffffff !important;
    border-color:rgba(126,182,224,.35) !important;
  }
  [data-baseweb="input"] > div:focus-within{
    border-color:#9EC5E8 !important;
    box-shadow:0 0 0 3px rgba(126,182,224,.28) !important;
  }
  [data-testid="stTextInput"] input::placeholder {
    color: #6b7280 !important;
    -webkit-text-fill-color: #6b7280 !important;
  }

  /* CTA claro sobre fondo oscuro */
  .stApp button[kind="primary"],
  .stApp button[kind="primaryFormSubmit"],
  .stApp [data-testid="stBaseButton-primary"],
  .stApp [data-testid="stBaseButton-primaryFormSubmit"]{
    background:linear-gradient(180deg,#9CCBEE,#5F9FD2) !important;
    border:1px solid rgba(255,255,255,.18) !important;
    color:#06121E !important;
    border-radius:11px !important;
    font-weight:700 !important;
    letter-spacing:.02em;
    box-shadow:0 10px 24px rgba(95,159,210,.26) !important;
  }
  .stApp button[kind="primary"]:hover,
  .stApp button[kind="primaryFormSubmit"]:hover,
  .stApp [data-testid="stBaseButton-primary"]:hover,
  .stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover{
    filter:brightness(1.05);
    box-shadow:0 14px 32px rgba(126,182,224,.36) !important;
  }

  [data-testid="stAlert"]{ border-radius:12px; }
  ::-webkit-scrollbar-thumb{ background:#28374A; background-clip:padding-box; }
  ::-webkit-scrollbar-thumb:hover{ background:#35485E; background-clip:padding-box; }
</style>
"""

CSS_DASHBOARD = """
<style>
  /* Ocultar la barra nativa de Streamlit (evita la franja oscura doble arriba) */
  header[data-testid="stHeader"] {
    display: none !important;
  }
  [data-testid="stToolbar"], footer { visibility: hidden; height: 0; }
  [data-testid="stAppViewContainer"] { overflow-x: hidden; }
  .block-container { padding-top: 0 !important; }

  /* --- Barra superior fija (HTML), ancho real 100% --- */
  .ns-topbar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 999;
    background: linear-gradient(180deg,#07090D 0%,#0C1724 100%);
    border-bottom: 1px solid rgba(126,182,224,.38);
    box-shadow: 0 8px 22px rgba(7,12,20,.18);
    padding: 10px max(1.25rem, 5vw);
    box-sizing: border-box;
  }
  .ns-topbar-inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    max-width: 72rem;
    margin: 0 auto;
    min-height: 48px;
  }
  .ns-topbar-logo { flex: 0 1 auto; min-width: 0; }
  .ns-topbar-pill { flex: 0 1 auto; text-align: center; }
  .ns-topbar-slot { flex: 0 0 7.5rem; }
  .ns-nav-logo {
    height: 48px;
    width: auto;
    max-width: min(280px, 46vw);
    object-fit: contain;
    display: block;
  }
  .ns-nav-fallback {
    color: #eef3f8;
    font-weight: 700;
    letter-spacing: 0.08em;
    font-size: 0.95rem;
    line-height: 48px;
    white-space: nowrap;
  }
  .ns-pill {
    display: inline-block;
    padding: 7px 14px;
    border: 1px solid rgba(126,182,224,.55);
    border-radius: 999px;
    background: rgba(126,182,224,.08);
    color: #9ec5e8;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }
  /* Espacio para que el contenido no quede debajo de la barra fija */
  .ns-topbar-spacer { height: 74px; }

  /* Botón Salir: anclado a la derecha de la barra.
     .stApp + [kind] gana al hover secondary de CSS_BASE (#F8FBFE + texto claro). */
  .stApp [class*="st-key-ns_logout"] {
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
    border: none !important;
    background: transparent !important;
  }
  .stApp [class*="st-key-ns_logout"] button[kind],
  .stApp [class*="st-key-ns_logout"] [data-testid="stBaseButton-secondary"] {
    position: fixed !important;
    top: 14px !important;
    right: max(1.25rem, 5vw) !important;
    z-index: 1000 !important;
    width: 7.5rem !important;
    background: rgba(126,182,224,.12) !important;
    color: #eef3f8 !important;
    -webkit-text-fill-color: #eef3f8 !important;
    border: 1px solid rgba(126,182,224,.55) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    box-shadow: none !important;
    transform: none !important;
    filter: none !important;
    min-height: 40px !important;
  }
  .stApp [class*="st-key-ns_logout"] button[kind] p,
  .stApp [class*="st-key-ns_logout"] button[kind] span {
    color: #eef3f8 !important;
    -webkit-text-fill-color: #eef3f8 !important;
    background: transparent !important;
  }
  .stApp [class*="st-key-ns_logout"] button[kind]:hover,
  .stApp [class*="st-key-ns_logout"] [data-testid="stBaseButton-secondary"]:hover {
    background: #1E3A5F !important;
    color: #eef3f8 !important;
    -webkit-text-fill-color: #eef3f8 !important;
    border-color: #9ec5e8 !important;
    box-shadow: 0 4px 14px rgba(126,182,224,.28) !important;
    transform: none !important;
    filter: none !important;
  }
  .stApp [class*="st-key-ns_logout"] button[kind]:hover p,
  .stApp [class*="st-key-ns_logout"] button[kind]:hover span {
    color: #eef3f8 !important;
    -webkit-text-fill-color: #eef3f8 !important;
    background: transparent !important;
  }

  /* --- Pestañas: segmentos a todo el ancho, no agrupados a la izquierda. --- */
  [data-testid="stTabs"] > div,
  [data-baseweb="tabs"]{
    width:100% !important;
  }
  [data-baseweb="tab-list"], [role="tablist"]{
    display:flex !important;
    width:100% !important;
    justify-content:space-between !important;
    gap:12px !important;
    background:#F1F5FA;
    padding:8px;
    border-radius:14px;
    border:1px solid var(--ns-line);
    box-shadow:inset 0 1px 2px rgba(16,32,52,.04);
  }
  [role="tablist"] button[role="tab"],
  [data-baseweb="tab"]{
    flex:1 1 0 !important;
    min-width:0 !important;
    justify-content:center !important;
    text-align:center !important;
    border-radius:10px !important;
    padding:10px 12px !important;
    background:transparent !important;
    color:var(--ns-muted) !important;
    font-weight:600 !important;
    transition:background-color .16s ease, color .16s ease, box-shadow .16s ease;
  }
  [role="tablist"] button[role="tab"]:hover,
  [data-baseweb="tab"]:hover{
    background:rgba(255,255,255,.72) !important;
    color:var(--ns-navy-soft) !important;
  }
  [role="tablist"] button[role="tab"][aria-selected="true"],
  [data-baseweb="tab"][aria-selected="true"]{
    background:#FFFFFF !important;
    color:var(--ns-navy) !important;
    box-shadow:var(--ns-shadow-sm);
  }
  [data-baseweb="tab-highlight"], [data-baseweb="tab-border"]{ display:none !important; }

  /* --- Métricas como tarjetas --- */
  [data-testid="stMetric"], [data-testid="metric-container"]{
    background:#FFFFFF;
    border:1px solid var(--ns-line);
    border-radius:12px;
    padding:12px 14px;
    box-shadow:var(--ns-shadow-sm);
  }
  [data-testid="stMetricLabel"] p{
    font-size:.7rem !important;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.09em;
    color:var(--ns-muted);
  }
  [data-testid="stMetricValue"]{
    font-size:1.42rem;
    font-weight:700;
    color:var(--ns-navy);
    font-variant-numeric:tabular-nums;
  }

  /* --- Desplegables (expander): los únicos details/summary de la app --- */
  [data-testid="stExpander"], .stApp details{
    border:1px solid var(--ns-line) !important;
    border-radius:14px !important;
    background:#FFFFFF !important;
    box-shadow:var(--ns-shadow-sm);
    overflow:hidden;
  }
  [data-testid="stExpander"] details{
    border:none !important;
    box-shadow:none;
  }
  .stApp summary{
    font-weight:700 !important;
    color:var(--ns-navy) !important;
    background:#FBFDFF;
  }
  .stApp summary:hover{ background:var(--ns-tint); }

  /* --- Avisos --- */
  [data-testid="stAlert"], [data-testid="stNotification"]{
    border-radius:12px;
    border:1px solid rgba(22,48,79,.07);
    box-shadow:var(--ns-shadow-sm);
  }
  [data-testid="stAlert"] p{ font-size:.88rem; }

  hr{ border-color:var(--ns-line) !important; }

  /* --- Tarjetas de video --- */
  [class*="st-key-ns_video_"]{
    border:1px solid var(--ns-line) !important;
    border-radius:16px !important;
    background:#FFFFFF !important;
    box-shadow:var(--ns-shadow-sm);
    transition:box-shadow .18s ease, border-color .18s ease;
  }
  [class*="st-key-ns_video_"]:hover{
    border-color:#CBDCEC !important;
    box-shadow:var(--ns-shadow-md);
  }
  [class*="st-key-ns_video_"] iframe,
  [class*="st-key-ns_video_"] video{ border-radius:12px; }
</style>
"""

# Estilo del encabezado de las tablas HTML (Gauss y Radar comparten el mismo).
TH_TABLA = (
    "padding:11px 10px;background:#1E3A5F;color:#EAF2FA;font-weight:700;"
    "font-size:14px;letter-spacing:.07em;text-transform:uppercase;"
    "border-bottom:1px solid #12283F;"
)

# Plantilla visual para todos los gráficos: misma tipografía, grillas suaves
# y tooltips consistentes con el resto de la interfaz. No toca los colores
# de las series (cada gráfico define los suyos) ni ningún dato.
pio.templates["ns_progress"] = go.layout.Template(
    layout=dict(
        font=dict(
            family="Inter, 'Segoe UI', system-ui, sans-serif",
            size=14,
            color="#41526A",
        ),
        title=dict(font=dict(size=22, color="#16202E")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            gridcolor="#EDF1F7",
            zerolinecolor="#DDE5EE",
            linecolor="#E4EAF1",
            tickfont=dict(size=14, color="#5B6B7F"),
            title=dict(font=dict(size=15, color="#5B6B7F")),
        ),
        yaxis=dict(
            gridcolor="#EDF1F7",
            zerolinecolor="#DDE5EE",
            linecolor="#E4EAF1",
            tickfont=dict(size=14, color="#5B6B7F"),
            title=dict(font=dict(size=15, color="#5B6B7F")),
        ),
        legend=dict(
            bgcolor="rgba(255,255,255,.86)",
            bordercolor="#E4EAF1",
            borderwidth=1,
            font=dict(size=14, color="#41526A"),
        ),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor="#D9E3EF",
            font=dict(family="Inter, 'Segoe UI', sans-serif", size=14, color="#16202E"),
        ),
        polar=dict(
            bgcolor="#FBFCFE",
            radialaxis=dict(
                gridcolor="#E7EDF5",
                linecolor="#E4EAF1",
                tickfont=dict(size=14, color="#8494A8"),
            ),
            angularaxis=dict(
                gridcolor="#E7EDF5",
                linecolor="#DDE5EE",
                tickfont=dict(size=15, color="#41526A"),
            ),
        ),
    )
)
pio.templates.default = "plotly_white+ns_progress"


def inyectar_css(*bloques):
    """Inyecta CSS global en el documento principal (solo bloques <style>)."""
    st.markdown("".join(bloques), unsafe_allow_html=True)


def ruta_logo(tipo="wordmark"):
    """Logos oficiales: primero assets/, si no la carpeta 'Logos NS Dash'."""
    por_tipo = {
        "wordmark": (
            "ns-progress-wordmark.png",
            "Logo 1 (7).png",
            "Logo 1 (1).png",
        ),
        "mark": (
            "ns-mark.png",
            "Logo 1 (3).png",
        ),
        "sesma": (
            "nico-sesma.png",
            "Logo 1 (6).png",
        ),
    }
    for carpeta in (DIR_ASSETS, DIR_LOGOS):
        for nombre in por_tipo.get(tipo, ()):
            candidato = carpeta / nombre
            if candidato.is_file():
                return candidato
    return None


@st.cache_data
def _logo_navbar_data_uri():
    """Logo del navbar embebido: evita el placeholder feo de st.image al cargar."""
    wordmark = ruta_logo("wordmark")
    if not wordmark or not wordmark.is_file():
        return None
    suf = wordmark.suffix.lower()
    mime = "image/svg+xml" if suf == ".svg" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(wordmark.read_bytes()).decode('ascii')}"


_logo_icono = ruta_logo("mark")
st.set_page_config(
    page_title="NS Progress Dashboard",
    page_icon=str(_logo_icono) if _logo_icono else "■",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _secreto(clave, default=None):
    try:
        return st.secrets[clave]
    except Exception:
        return default


def spreadsheet_id():
    return str(_secreto("spreadsheet_id") or SPREADSHEET_ID_FALLBACK)


def info_cuenta_servicio():
    """Credenciales desde secrets; si no hay, credentials.json local (gitignored)."""
    try:
        sa = st.secrets["gcp_service_account"]
        return {k: sa[k] for k in sa}
    except Exception:
        if CREDENTIALS_FILE.is_file():
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        return None


# ----------------------------------------------------------------------
# CONEXIÓN A GOOGLE SHEETS
# ----------------------------------------------------------------------
@st.cache_resource
def conectar():
    info = info_cuenta_servicio()
    if not info:
        raise RuntimeError(
            "Faltan las credenciales de Google. Completá .streamlit/secrets.toml "
            "(ver secrets.toml.example) o dejá credentials.json en esta carpeta."
        )
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    cliente = gspread.authorize(creds)
    return cliente.open_by_key(spreadsheet_id())


def _bytes_iguales(a, b):
    aa = a.encode("utf-8") if isinstance(a, str) else a
    bb = b.encode("utf-8") if isinstance(b, str) else b
    if len(aa) != len(bb):
        return False
    return hmac.compare_digest(aa, bb)


def credenciales_entrenador_ok(email, password):
    try:
        esperado_email = str(st.secrets["coach"]["email"]).strip().lower()
        esperado_pass = str(st.secrets["coach"]["password"])
    except Exception:
        return False
    return _bytes_iguales(email.strip().lower(), esperado_email) and _bytes_iguales(
        password, esperado_pass
    )


def mostrar_landing():
    inyectar_css(CSS_BASE, CSS_LANDING)
    wordmark = ruta_logo("wordmark")
    if wordmark:
        with st.container(key="ns_landing_logo"):
            c0, c1, c2 = st.columns([0.5, 3, 0.5])
            with c1:
                st.image(str(wordmark), use_container_width=True)
    else:
        st.markdown(
            "<h1 style='text-align:center;color:#eef3f8;'>NS PROGRESS DASHBOARD</h1>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "<p style='text-align:center;color:#9ec5e8;margin:8px 0 40px;"
        "letter-spacing:0.16em;font-size:0.95rem;font-weight:600;'>"
        "EVALUACIONES · CONCENTRACIÓN NACIONAL</p>",
        unsafe_allow_html=True,
    )
    col_reg, col_inv = st.columns(2, gap="large")
    with col_reg:
        with st.container(border=True, key="ns_card_coach"):
            st.markdown(
                "<h3 style='color:#eef3f8;margin:4px 0 8px;'>Usuario registrado</h3>"
                "<p style='color:#c5d4e0;margin:0 0 12px;font-size:0.95rem;'>"
                "Entrenadores: mail y contraseña. Pueden editar la planilla.</p>",
                unsafe_allow_html=True,
            )
            try:
                _ = st.secrets["coach"]["email"]
            except Exception:
                st.markdown(
                    "<p style='color:#f0c674;'>Falta configurar el usuario en secrets.toml.</p>",
                    unsafe_allow_html=True,
                )
            with st.form("form_login_entrenador"):
                email = st.text_input("Email", placeholder="admin@ns.com")
                password = st.text_input("Contraseña", type="password")
                entrar = st.form_submit_button(
                    "Entrar", type="primary", use_container_width=True
                )
            if entrar:
                if credenciales_entrenador_ok(email, password):
                    st.session_state.rol = "coach"
                    st.rerun()
                else:
                    st.error("Email o contraseña incorrectos.")
    with col_inv:
        with st.container(border=True, key="ns_card_guest"):
            st.markdown(
                "<h3 style='color:#eef3f8;margin:4px 0 8px;'>Usuario invitado</h3>"
                "<p style='color:#c5d4e0;margin:0 0 28px;font-size:0.95rem;'>"
                "Podés mirar y cargar a alguien para compararte. "
                "Al cerrar, se borra. No toca la planilla.</p>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Entrar como invitado",
                use_container_width=True,
                type="primary",
                key="btn_invitado",
            ):
                st.session_state.rol = "guest"
                st.session_state.guest_altas = {}
                st.rerun()


def barra_sesion(es_entrenador):
    inyectar_css(CSS_BASE, CSS_DASHBOARD)

    texto = (
        "ENTRENADOR · edita la planilla"
        if es_entrenador
        else "INVITADO · no se guarda"
    )
    data_uri = _logo_navbar_data_uri()
    if data_uri:
        logo_html = (
            f'<img class="ns-nav-logo" src="{data_uri}" alt="NS Progress Dashboard">'
        )
    else:
        logo_html = '<span class="ns-nav-fallback">NS PROGRESS DASHBOARD</span>'

    st.markdown(
        f'<div class="ns-topbar">'
        f'  <div class="ns-topbar-inner">'
        f'    <div class="ns-topbar-logo">{logo_html}</div>'
        f'    <div class="ns-topbar-pill"><span class="ns-pill">{html_lib.escape(texto)}</span></div>'
        f'    <div class="ns-topbar-slot" aria-hidden="true"></div>'
        f'  </div>'
        f'</div>'
        f'<div class="ns-topbar-spacer"></div>',
        unsafe_allow_html=True,
    )

    with st.container(key="ns_logout"):
        if st.button("Salir", use_container_width=True, key="btn_salir_nav"):
            for k in ("rol", "guest_altas"):
                st.session_state.pop(k, None)
            st.rerun()


def parse_numero(valor):
    """Convierte '30,1' o '30.1' o '' en float / NaN, tolerando ambos formatos."""
    if valor is None:
        return np.nan
    s = str(valor).strip()
    if s == "":
        return np.nan
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def formato_celda(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(valor).strip()
    return texto.replace(".", ",")


def consolidar_mejores(df):
    """Por cada test, se queda con la mejor marca (ignora vacíos)."""
    out = df.copy()
    for c in COLS_EVAL:
        stacked = pd.concat([out[f"{c}{SUF_1}"], out[f"{c}{SUF_2}"]], axis=1)
        out[c] = stacked.min(axis=1) if c in EVALUACIONES_INVERTIDAS else stacked.max(axis=1)
    return out


def z_de_serie(valores, invertida=False):
    """Z-score; si el desvío es 0 o no hay datos, Z = 0 (o NaN si el valor falta)."""
    arr = np.asarray(valores, dtype=float).ravel()
    n_validos = int(np.count_nonzero(~np.isnan(arr)))
    if n_validos == 0:
        return np.full(arr.shape, np.nan), np.nan, np.nan
    media = float(np.nanmean(arr))
    desvio = float(np.nanstd(arr, ddof=1)) if n_validos > 1 else 0.0
    if not np.isfinite(desvio) or desvio == 0:
        z = np.where(np.isnan(arr), np.nan, 0.0)
    else:
        z = (arr - media) / desvio
        if invertida:
            z = -z
    return z, media, desvio


def fila_alta_vacia(nombre, asoc):
    fila = {
        COL_NUM: "",
        COL_NOMBRE: nombre,
        COL_FECHA_1: "",
        COL_ASOC: asoc,
        COL_FECHA_2: "",
    }
    for c in COLS_EVAL:
        fila[f"{c}{SUF_1}"] = np.nan
        fila[f"{c}{SUF_2}"] = np.nan
        fila[c] = np.nan
    return fila


def aplicar_altas_invitado(df, categoria):
    altas = st.session_state.get("guest_altas", {}).get(categoria, [])
    if not altas:
        return df
    out = df.copy()
    for alta in altas:
        objetivo = normalizar(alta[COL_NOMBRE])
        idx = out.index[out[COL_NOMBRE].map(normalizar) == objetivo]
        if len(idx):
            i = idx[0]
            for k, v in alta.items():
                if k == COL_NOMBRE or k not in out.columns:
                    continue
                vacio = v is None or v == "" or (isinstance(v, float) and pd.isna(v))
                if not vacio:
                    out.at[i, k] = v
        else:
            out = pd.concat([out, pd.DataFrame([alta])], ignore_index=True)
    return consolidar_mejores(out)


def buscar_fila_en_hoja(hoja, nombre):
    valores = hoja.get_all_values()
    objetivo = normalizar(nombre)
    for i, fila in enumerate(valores[1:], start=2):
        if len(fila) > 1 and normalizar(fila[1]) == objetivo:
            return i
    return None


def primera_fila_libre(hoja):
    valores = hoja.get_all_values()
    for i, fila in enumerate(valores[1:], start=2):
        if len(fila) < 2 or str(fila[1]).strip() == "":
            return i
    return len(valores) + 1


def guardar_entrenador(hoja, nombre, asoc, fecha, cual_eval, celdas):
    fila = buscar_fila_en_hoja(hoja, nombre)
    nueva = fila is None
    if nueva:
        fila = primera_fila_libre(hoja)
    if cual_eval == "1ª evaluación":
        if nueva:
            hoja.update(
                f"B{fila}:J{fila}",
                [[nombre, fecha, asoc] + celdas],
                value_input_option="USER_ENTERED",
            )
        else:
            hoja.update(
                f"C{fila}:J{fila}",
                [[fecha, asoc] + celdas],
                value_input_option="USER_ENTERED",
            )
    else:
        if nueva:
            hoja.update(
                f"B{fila}:D{fila}",
                [[nombre, "", asoc]],
                value_input_option="USER_ENTERED",
            )
        hoja.update(
            f"K{fila}:Q{fila}",
            [[fecha] + celdas],
            value_input_option="USER_ENTERED",
        )
    return nueva


@st.cache_data(ttl=30)
def cargar_datos(_hoja, categoria):
    """Lee la hoja con el layout A-Q y devuelve un DataFrame normalizado.

    Layout esperado (igual en todas las hojas de categorías):
      A = N°            B = Nombre y Apellido   C = Fecha 1ª evaluación
      D = Asociación    E-J = SJ, CMJ, ABK, Sprint 30m, Test T, 30-15 IFT (1ª)
      K = Fecha 2ª evaluación
      L-Q = SJ, CMJ, ABK, Sprint 30m, Test T, 30-15 IFT (2ª)

    Por cada evaluación se guardan tres columnas:
      '<eval> (1ª)', '<eval> (2ª)' y '<eval>' (la MEJOR de las dos).
    En tiempos (Sprint 30m, Test T) "mejor" = valor más bajo; en el resto, el más alto.

    'categoria' se pasa aparte (además de _hoja) para que Streamlit cachee un
    resultado distinto por cada hoja, aunque _hoja no se use para el cacheo.
    """
    valores = _hoja.get_all_values()
    filas = [
        (fila + [""] * ANCHO_HOJA)[:ANCHO_HOJA]  # rellena filas cortas para que no falten columnas
        for fila in valores[1:]
        if len(fila) > 1 and str(fila[1]).strip() != ""
    ]

    df = pd.DataFrame(
        filas,
        columns=[
            COL_NUM, COL_NOMBRE, COL_FECHA_1, COL_ASOC,
            *[f"{c}{SUF_1}" for c in COLS_EVAL],
            COL_FECHA_2,
            *[f"{c}{SUF_2}" for c in COLS_EVAL],
        ],
    )
    df[COL_NOMBRE] = df[COL_NOMBRE].astype(str).str.strip()

    for c in COLS_EVAL:
        df[f"{c}{SUF_1}"] = df[f"{c}{SUF_1}"].apply(parse_numero)
        df[f"{c}{SUF_2}"] = df[f"{c}{SUF_2}"].apply(parse_numero)

    df = consolidar_mejores(df)
    return df, list(COLS_EVAL)


def normalizar(nombre):
    return " ".join(str(nombre).strip().lower().split())


@st.cache_data(ttl=30)
def cargar_videos(_libro):
    """Lee la pestaña 'Videos' (Título, Link, Descripción). Si no existe todavía,
    devuelve una tabla vacía en vez de romper la app."""
    columnas = ["Título", "Link", "Descripción"]
    try:
        hoja_videos = _libro.worksheet(HOJA_VIDEOS)
    except gspread.WorksheetNotFound:
        return pd.DataFrame(columns=columnas)

    valores = hoja_videos.get_all_values()
    if len(valores) < 2:
        return pd.DataFrame(columns=columnas)

    filas = [fila[:3] + [""] * (3 - len(fila[:3])) for fila in valores[1:] if fila and fila[0].strip()]
    return pd.DataFrame(filas, columns=columnas)


if "rol" not in st.session_state:
    st.session_state.rol = None
if "guest_altas" not in st.session_state:
    st.session_state.guest_altas = {}

if st.session_state.rol not in ("coach", "guest"):
    mostrar_landing()
    st.stop()

es_entrenador = st.session_state.rol == "coach"
barra_sesion(es_entrenador)

try:
    libro = conectar()
except Exception as exc:
    st.error(
        "No se pudo abrir el Google Sheet. Revisá secrets / credentials.json "
        "y que la planilla esté compartida con el bot."
    )
    st.caption(str(exc))
    st.stop()

todas_las_hojas = libro.worksheets()
categorias = [ws.title for ws in todas_las_hojas if ws.title != HOJA_VIDEOS]

st.caption("Evaluaciones · Concentración Nacional")
categoria = st.selectbox("Categoría:", categorias)
hoja = next(ws for ws in todas_las_hojas if ws.title == categoria)

df, _ = cargar_datos(hoja, categoria)
df = df.copy()
if not es_entrenador:
    df = aplicar_altas_invitado(df, categoria)

con_2da = df[[f"{c}{SUF_2}" for c in COLS_EVAL]].notna().any(axis=1).sum()
extras_invitado = (not es_entrenador) and bool(st.session_state.guest_altas.get(categoria))
st.caption(
    f"{categoria} · {len(df)} jugadoras cargadas · {con_2da} con 2ª evaluación · "
    "En cada evaluación se usa la mejor de las dos fechas · Fuente: Google Sheet"
    + (" · más pruebas de esta sesión" if extras_invitado else "")
)


# ----------------------------------------------------------------------
# Tabla con Z-score de TODAS las evaluaciones (se usa en la pestaña Radar).
# Se calcula una sola vez, antes de las pestañas, para no mezclarse con el
# procesamiento de la pestaña 1 (que trabaja sobre una sola evaluación a la vez).
# ----------------------------------------------------------------------
def calcular_tabla_z(df_base, cols_eval, invertidas):
    tabla = pd.DataFrame(
        {COL_NOMBRE: df_base[COL_NOMBRE].values, COL_ASOC: df_base[COL_ASOC].values}
    )
    for c in cols_eval:
        valores = df_base[c].to_numpy(dtype=float)  # ya viene consolidada (mejor marca)
        z, _, _ = z_de_serie(valores, invertida=c in invertidas)
        tabla[f"{c}__valor"] = valores
        tabla[f"{c}__z"] = z
    cols_z = [f"{c}__z" for c in cols_eval]
    cols_valor = [f"{c}__valor" for c in cols_eval]
    tabla["Total"] = tabla[cols_z].sum(axis=1, skipna=True)
    n_evals = tabla[cols_valor].notna().sum(axis=1)
    tabla["Promedio"] = tabla["Total"] / n_evals.replace(0, np.nan)
    tabla["evaluaciones_completas"] = tabla[cols_valor].notna().all(axis=1)

    # Posición de cada resultado dentro de su propia evaluación (1° = mejor),
    # calculada sobre todas las deportistas que tienen ese dato cargado.
    for c in cols_eval:
        tabla[f"{c}__rank"] = tabla[f"{c}__z"].rank(method="min", ascending=False)

    # Posición del puntaje Total (suma de Z-score) entre todas las deportistas
    # con las evaluaciones completas de la categoría (misma población que se
    # usa para armar el Top N). Ej: si hay 156 completas, la que menos sumó es la 156.
    tabla["Total__rank"] = np.nan
    completas = tabla["evaluaciones_completas"]
    tabla.loc[completas, "Total__rank"] = tabla.loc[completas, "Total"].rank(
        method="min", ascending=False
    )

    return tabla


z_completo = calcular_tabla_z(df, COLS_EVAL, EVALUACIONES_INVERTIDAS)

tab1, tab2, tab3, tab5, tab4 = st.tabs(
    [
        "📊 Campana de Gauss",
        "🕸️ Gráfico Radar",
        "📦 Boxplot",
        "📊 Comparativas",
        "🎥 Video Tutoriales",
    ]
)

# ========================================================================
# PESTAÑA 1 — CAMPANA DE GAUSS (igual a como estaba funcionando)
# ========================================================================
with tab1:
    col_izq, col_der = st.columns([1, 2], gap="large")

    with col_izq:
        st.subheader("Configuración")

        evaluacion = st.selectbox("Evaluación a analizar:", COLS_EVAL, key="eval_gauss")

        df["valor"] = df[evaluacion]  # mejor marca entre 1ª y 2ª evaluación
        datos = df.dropna(subset=["valor"]).copy()

        z_vals, media, desvio = z_de_serie(
            datos["valor"].values if not datos.empty else [],
            invertida=evaluacion in EVALUACIONES_INVERTIDAS,
        )
        if datos.empty:
            media, desvio = np.nan, np.nan
        else:
            datos["z"] = z_vals
            if evaluacion in EVALUACIONES_INVERTIDAS:
                st.caption("En esta evaluación, menor tiempo = mejor resultado (Z-score ajustado).")

        c1, c2, c3 = st.columns(3)
        c1.metric("Media", "—" if pd.isna(media) else f"{media:.2f}")
        c2.metric("Desvío estándar", "—" if pd.isna(desvio) else f"{desvio:.2f}")
        c3.metric("N", len(datos))

        st.divider()
        st.subheader("🔍 Buscar jugadora")
        nombres_gauss = sorted(datos[COL_NOMBRE].dropna().unique().tolist())
        busqueda = st.selectbox(
            "Nombre:", [OPCION_VACIA] + nombres_gauss, key="busqueda_gauss"
        )

        st.divider()
        st.subheader("Agregar jugadora")
        etiqueta_guardar = (
            "Guardar en el Google Sheet" if es_entrenador else "Probar en esta sesión"
        )
        if not es_entrenador:
            st.caption("En modo invitado esto no se escribe en la planilla.")
        with st.form("form_nueva_jugadora", clear_on_submit=True):
            nombre_nuevo = st.text_input("Nombre y Apellido *")
            asoc_nueva = st.text_input("Asociación")
            fecha_nueva = st.text_input("Fecha de la evaluación")
            cual_eval = st.radio(
                "¿A qué evaluación corresponden estos datos?",
                ["1ª evaluación", "2ª evaluación"],
                horizontal=True,
            )
            st.caption("Resultados (podés dejar vacío lo que no tengas todavía):")
            vals_nuevos = {}
            for c in COLS_EVAL:
                vals_nuevos[c] = st.text_input(c, key=f"nuevo_{c}")
            enviar = st.form_submit_button(etiqueta_guardar, type="primary")

            if enviar:
                if nombre_nuevo.strip() == "":
                    st.error("El nombre es obligatorio.")
                else:
                    invalidos = [
                        c
                        for c in COLS_EVAL
                        if vals_nuevos[c].strip() != ""
                        and pd.isna(parse_numero(vals_nuevos[c]))
                    ]
                    if invalidos:
                        st.error(
                            "Estos resultados no son números: " + ", ".join(invalidos)
                        )
                    else:
                        numeros = [parse_numero(vals_nuevos[c]) for c in COLS_EVAL]
                        celdas = [formato_celda(n) for n in numeros]
                        nombre_ok = nombre_nuevo.strip()
                        asoc_ok = asoc_nueva.strip()
                        fecha_ok = fecha_nueva.strip()
                        if es_entrenador:
                            nueva = guardar_entrenador(
                                hoja, nombre_ok, asoc_ok, fecha_ok, cual_eval, celdas
                            )
                            st.cache_data.clear()
                            if nueva:
                                st.success(f"{nombre_ok} guardada en el Sheet.")
                            else:
                                st.success(
                                    f"Se actualizó la {cual_eval.lower()} de {nombre_ok}."
                                )
                            st.rerun()
                        else:
                            alta = fila_alta_vacia(nombre_ok, asoc_ok)
                            if cual_eval == "1ª evaluación":
                                alta[COL_FECHA_1] = fecha_ok
                                for c, n in zip(COLS_EVAL, numeros):
                                    alta[f"{c}{SUF_1}"] = n
                            else:
                                alta[COL_FECHA_2] = fecha_ok
                                for c, n in zip(COLS_EVAL, numeros):
                                    alta[f"{c}{SUF_2}"] = n
                            por_cat = st.session_state.guest_altas.setdefault(categoria, [])
                            objetivo = normalizar(nombre_ok)
                            previa = next(
                                (a for a in por_cat if normalizar(a[COL_NOMBRE]) == objetivo),
                                None,
                            )
                            if previa is None:
                                por_cat.append(alta)
                            else:
                                for k, v in alta.items():
                                    vacio = (
                                        v is None
                                        or v == ""
                                        or (isinstance(v, float) and pd.isna(v))
                                    )
                                    if not vacio:
                                        previa[k] = v
                            st.success(
                                f"{nombre_ok} cargada en esta sesión. Al salir, se borra."
                            )
                            st.rerun()

    with col_der:
        x = np.linspace(-4, 4, 400)
        y = stats.norm.pdf(x, 0, 1)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=x, y=y, mode="lines", name="Distribución normal",
                line=dict(color="#4C78A8", width=2), hoverinfo="skip",
            )
        )

        asociaciones = datos[COL_ASOC] if COL_ASOC in datos.columns else [""] * len(datos)
        if not datos.empty:
            fig.add_trace(
                go.Scatter(
                    x=datos["z"],
                    y=stats.norm.pdf(datos["z"], 0, 1),
                    mode="markers",
                    name="Jugadoras",
                    marker=dict(
                        size=10,
                        color=datos["z"],
                        colorscale="RdYlGn",  # rojo (bajo) -> amarillo (cerca de 0) -> verde (alto)
                        cmin=-4,
                        cmax=4,
                        line=dict(width=1, color="white"),
                        colorbar=dict(
                            title=dict(text="Z-score", side="top", font=dict(size=11, color="#666")),
                            orientation="h",
                            thickness=10,
                            len=0.55,
                            x=0.5,
                            xanchor="center",
                            y=-0.22,
                            yanchor="top",
                            outlinewidth=0,
                            ticks="outside",
                            tickfont=dict(size=10, color="#888"),
                            tickcolor="#ccc",
                        ),
                    ),
                    customdata=np.stack(
                        [datos[COL_NOMBRE], asociaciones, datos["valor"], datos["z"]], axis=-1
                    ),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Asociación: %{customdata[1]}<br>"
                        "Resultado: %{customdata[2]}<br>"
                        "Z-score: %{customdata[3]:.2f}<extra></extra>"
                    ),
                )
            )

        if busqueda != OPCION_VACIA:
            encontrada = datos[datos[COL_NOMBRE] == busqueda]
            if not encontrada.empty:
                y_encontrada = stats.norm.pdf(encontrada["z"], 0, 1)
                # Anillo tipo "mira/diana": dos círculos huecos concéntricos alrededor
                # del punto, dejando visible el color del degradé en el centro.
                fig.add_trace(
                    go.Scatter(
                        x=encontrada["z"], y=y_encontrada,
                        mode="markers",
                        name="Resultado búsqueda",
                        marker=dict(size=34, symbol="circle-open",
                                    line=dict(width=1.5, color="rgba(30,58,95,0.35)")),
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=encontrada["z"], y=y_encontrada,
                        mode="markers",
                        name="Resultado búsqueda",
                        marker=dict(size=24, symbol="circle-open",
                                    line=dict(width=3, color="#1E3A5F")),
                        hoverinfo="skip",
                    )
                )
                f = encontrada.iloc[0]
                st.success(
                    f"**{f[COL_NOMBRE]}** ({f[COL_ASOC]}) — Resultado: {f['valor']} — Z-score: {f['z']:.2f}"
                )

        fig.update_layout(
            title=f"Campana de Gauss — {categoria} — {evaluacion}",
            xaxis_title="Z-score",
            yaxis_title="Densidad",
            height=610,
            margin=dict(b=90),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )

        evento = st.plotly_chart(
            fig, use_container_width=True, on_select="rerun", key="campana"
        )

        if evento and evento.get("selection") and evento["selection"].get("points"):
            punto = evento["selection"]["points"][0]
            cd = punto.get("customdata")
            if cd:
                st.info(
                    f"**Jugadora seleccionada:** {cd[0]}  \n"
                    f"**Asociación:** {cd[1]}  \n"
                    f"**Resultado:** {cd[2]}  \n"
                    f"**Z-score:** {float(cd[3]):.2f}"
                )

        st.divider()
        TOP_N_GAUSS = 24
        if datos.empty or "z" not in datos.columns:
            st.info("No hay resultados numéricos para armar el ranking de esta evaluación.")
            top_gauss = datos
        else:
            top_gauss = datos.sort_values("z", ascending=False).head(TOP_N_GAUSS).reset_index(drop=True)

        def fmt_gauss(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "—"
            return f"{v:,.2f}"

        if "z" in top_gauss.columns and not top_gauss.empty:
            filas_html_gauss = []
            for i, fila in top_gauss.iterrows():
                color = "#ffffff" if i % 2 == 0 else "#F7F9FC"
                nombre = html_lib.escape(str(fila[COL_NOMBRE]))
                asoc_val = fila[COL_ASOC] if COL_ASOC in fila else ""
                asociacion = html_lib.escape(str(asoc_val)) if str(asoc_val).strip() else "—"
                filas_html_gauss.append(
                    f'<tr>'
                    f'<td style="padding:9px 10px;text-align:center;background:{color};font-weight:800;color:#16304F;">{i + 1}</td>'
                    f'<td style="padding:9px 10px;text-align:left;background:{color};font-weight:600;color:#16202E;">{nombre}</td>'
                    f'<td style="padding:9px 10px;text-align:left;background:{color};color:#5B6B7F;">{asociacion}</td>'
                    f'<td style="padding:9px 10px;text-align:center;background:{color};color:#16202E;">{fmt_gauss(fila["valor"])}</td>'
                    f'<td style="padding:9px 10px;text-align:center;background:{color};font-weight:700;color:#1E3A5F;">{fmt_gauss(fila["z"])}</td>'
                    f"</tr>"
                )

            tabla_html_gauss = (
                '<div class="ns-table-wrap">'
                '<table class="ns-table ns-table-hover">'
                "<thead><tr>"
                f'<th style="{TH_TABLA}">Puesto</th>'
                f'<th style="{TH_TABLA}text-align:left;">Nombre y Apellido</th>'
                f'<th style="{TH_TABLA}text-align:left;">Asociación</th>'
                f'<th style="{TH_TABLA}">Resultado</th>'
                f'<th style="{TH_TABLA}">Z-score</th>'
                "</tr></thead><tbody>"
                + "".join(filas_html_gauss)
                + "</tbody></table></div>"
            )

            with st.expander(f"Top {TOP_N_GAUSS} — {categoria} — {evaluacion}", expanded=True):
                st.markdown(tabla_html_gauss, unsafe_allow_html=True)

# ========================================================================
# PESTAÑA 2 — GRÁFICO RADAR
# ========================================================================
with tab2:
    st.subheader(f"🕸️ Gráfico Radar — {categoria}")
    st.caption(
        "La 'Media' representa a la categoría completa (Z-score = 0 en todos los ejes). "
        "Elegí uno o dos deportistas para comparar su perfil contra la media."
    )

    nombres_disponibles = sorted(z_completo[COL_NOMBRE].dropna().unique().tolist())

    col_a, col_b = st.columns(2)
    with col_a:
        deportista_a = st.selectbox(
            "Deportista A:", [OPCION_VACIA] + nombres_disponibles, key="radar_a"
        )
    with col_b:
        deportista_b = st.selectbox(
            "Deportista B:", [OPCION_VACIA] + nombres_disponibles, key="radar_b"
        )

    # "Promedio Total" va primero para que quede arriba (12 en punto) del gráfico.
    ejes = ["Promedio Total"] + list(COLS_EVAL)
    ejes_cerrado = ejes + [ejes[0]]

    def valores_radar(nombre):
        fila = z_completo[z_completo[COL_NOMBRE] == nombre]
        if fila.empty:
            return None
        fila = fila.iloc[0]
        return [fila["Promedio"]] + [fila[f"{c}__z"] for c in COLS_EVAL]

    fig_radar = go.Figure()

    # Media de la categoría: referencia en cero en todos los ejes.
    r_media = [0] * len(ejes)
    fig_radar.add_trace(
        go.Scatterpolar(
            r=r_media + [r_media[0]],
            theta=ejes_cerrado,
            fill="toself",
            name="Media (categoría)",
            line=dict(color="#B0B0B0", dash="dash"),
            fillcolor="rgba(176,176,176,0.15)",
        )
    )

    if deportista_a != OPCION_VACIA:
        r_a = valores_radar(deportista_a)
        if r_a is not None:
            fig_radar.add_trace(
                go.Scatterpolar(
                    r=r_a + [r_a[0]],
                    theta=ejes_cerrado,
                    fill="toself",
                    name=f"A: {deportista_a}",
                    line=dict(color="#4C78A8"),
                    fillcolor="rgba(76,120,168,0.3)",
                )
            )

    if deportista_b != OPCION_VACIA:
        r_b = valores_radar(deportista_b)
        if r_b is not None:
            fig_radar.add_trace(
                go.Scatterpolar(
                    r=r_b + [r_b[0]],
                    theta=ejes_cerrado,
                    fill="toself",
                    name=f"B: {deportista_b}",
                    line=dict(color="#E45756"),
                    fillcolor="rgba(228,87,86,0.3)",
                )
            )

    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[-4, 4]),
            angularaxis=dict(rotation=90, direction="clockwise"),
        ),
        height=560,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        title=f"Perfil de rendimiento — {categoria}",
        dragmode=False,  # evita que arrastrar el mouse gire/deforme el gráfico
    )

    st.plotly_chart(
        fig_radar,
        use_container_width=True,
        key="radar_chart",
        config={
            "displayModeBar": False,  # sin botones de zoom/pan/rotar de Plotly
            "scrollZoom": False,       # sin zoom con rueda del mouse o gesto de trackpad
            "doubleClick": False,      # doble clic no resetea/deforme la vista
        },
    )
    st.caption(
        "El gráfico está bloqueado (no se puede girar ni hacer zoom sin querer) — para "
        "verlo más grande, pasá el mouse por arriba y usá el ícono de pantalla completa "
        "en la esquina superior derecha. El eje 'Promedio Total' (arriba) es el promedio "
        "de los 6 Z-score (suma ÷ 6), por eso queda en la misma escala que el resto."
    )

    st.divider()
    TOP_N_RADAR = 24
    st.subheader(f"🏆 Top {TOP_N_RADAR} — Ranking por suma de Z-score")

    completos = z_completo[z_completo["evaluaciones_completas"]].copy()
    ranking = completos.sort_values("Total", ascending=False).reset_index(drop=True)
    top_radar = ranking.head(TOP_N_RADAR)
    puesto_busqueda = TOP_N_RADAR + 1  # ej: si el top es 24, la búsqueda va en la 25

    st.caption(
        f"Se consideran solo deportistas con las {len(COLS_EVAL)} evaluaciones completas. "
        f"({len(completos)} de {len(z_completo)} cumplen esta condición.)"
    )

    def fmt(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        return f"{v:,.2f}"

    def fmt_rank(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        return f"{int(v)}°"

    def construir_bloque_html(puesto, fila, color_fondo, destacado=False):
        """Arma las tres filas <tr> (Resultado / Z-score / Posición) de un
        deportista, con Puesto/Nombre/Asociación fusionados (rowspan) para
        que se lea como un solo bloque en vez de filas sueltas.
        Cuando 'destacado' es True, el borde naranja se reparte entre las
        tres filas (arriba en la primera, nada en la del medio, abajo en la
        última, laterales en las tres) para que se vea como un único
        recuadro y no como filas separadas."""
        nombre = html_lib.escape(str(fila[COL_NOMBRE]))
        asoc_val = fila[COL_ASOC]
        asociacion = html_lib.escape(str(asoc_val)) if pd.notna(asoc_val) and str(asoc_val).strip() else "—"

        if destacado:
            lateral = "border-left:3px solid #F5A623;border-right:3px solid #F5A623;"
        else:
            lateral = ""
        borde_arriba = lateral + ("border-top:3px solid #F5A623;" if destacado else "border-top:2px solid #E4EAF1;")
        borde_medio = lateral
        borde_abajo = lateral + ("border-bottom:3px solid #F5A623;" if destacado else "")
        # Las celdas con rowspan cubren las tres filas: llevan el borde de arriba Y el de abajo.
        borde_rowspan = lateral + ("border-top:3px solid #F5A623;border-bottom:3px solid #F5A623;" if destacado else "border-top:2px solid #E4EAF1;")

        resultado_tds = "".join(
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};color:#16202E;{borde_arriba}">'
            f'{fmt(fila[f"{c}__valor"])}</td>'
            for c in COLS_EVAL
        )
        zscore_tds = "".join(
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'font-weight:600;color:#1E3A5F;{borde_medio}">{fmt(fila[f"{c}__z"])}</td>'
            for c in COLS_EVAL
        )
        rank_tds = "".join(
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'font-size:12px;color:#9A6A08;{borde_abajo}">{fmt_rank(fila[f"{c}__rank"])}</td>'
            for c in COLS_EVAL
        )

        fila1 = (
            f"<tr>"
            f'<td rowspan="3" style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'font-weight:800;vertical-align:middle;color:#16304F;{borde_rowspan}">{puesto}</td>'
            f'<td rowspan="3" style="padding:9px 10px;text-align:left;background:{color_fondo};'
            f'font-weight:700;vertical-align:middle;color:#16202E;{borde_rowspan}">{nombre}</td>'
            f'<td rowspan="3" style="padding:9px 10px;text-align:left;background:{color_fondo};'
            f'vertical-align:middle;color:#5B6B7F;{borde_rowspan}">{asociacion}</td>'
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'color:#7A8899;font-size:13px;font-weight:700;letter-spacing:.05em;'
            f'text-transform:uppercase;{borde_arriba}">Resultado</td>'
            f"{resultado_tds}"
            f'<td style="padding:9px 10px;background:{color_fondo};{borde_arriba}"></td>'
            f'<td style="padding:9px 10px;background:{color_fondo};{borde_arriba}"></td>'
            f"</tr>"
        )
        fila2 = (
            f"<tr>"
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'color:#1E3A5F;font-size:13px;font-weight:700;letter-spacing:.05em;'
            f'text-transform:uppercase;{borde_medio}">Z-score</td>'
            f"{zscore_tds}"
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'font-weight:700;color:#16202E;{borde_medio}">{fmt(fila["Total"])}</td>'
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'font-weight:700;color:#16202E;{borde_medio}">{fmt(fila["Promedio"])}</td>'
            f"</tr>"
        )
        fila3 = (
            f"<tr>"
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'color:#9A6A08;font-size:13px;font-weight:700;letter-spacing:.05em;'
            f'text-transform:uppercase;{borde_abajo}">Posición</td>'
            f"{rank_tds}"
            f'<td style="padding:9px 10px;text-align:center;background:{color_fondo};'
            f'font-weight:700;color:#9A6A08;{borde_abajo}">{fmt_rank(fila["Total__rank"])}</td>'
            f'<td style="padding:9px 10px;background:{color_fondo};{borde_abajo}"></td>'
            f"</tr>"
        )
        return fila1 + fila2 + fila3

    tabla_placeholder = st.empty()

    nombres_radar_todos = sorted(z_completo[COL_NOMBRE].dropna().unique().tolist())
    busqueda21 = st.selectbox(
        f"🔍 Agregar jugadora como fila {puesto_busqueda}:",
        [OPCION_VACIA] + nombres_radar_todos,
        key="busqueda_radar_extra",
    )

    encabezados_eval = "".join(
        f'<th style="{TH_TABLA}">{html_lib.escape(c)}</th>' for c in COLS_EVAL
    )
    tabla_html = (
        '<div class="ns-table-wrap">'
        '<table class="ns-table">'
        "<thead><tr>"
        f'<th style="{TH_TABLA}">Puesto</th>'
        f'<th style="{TH_TABLA}text-align:left;">Nombre y Apellido</th>'
        f'<th style="{TH_TABLA}text-align:left;">Asociación</th>'
        f'<th style="{TH_TABLA}"></th>'
        f"{encabezados_eval}"
        f'<th style="{TH_TABLA}">Total</th>'
        f'<th style="{TH_TABLA}">Promedio</th>'
        "</tr></thead><tbody>"
    )

    bloques = []
    for i, (_, fila) in enumerate(top_radar.iterrows()):
        color = "#ffffff" if i % 2 == 0 else "#F7F9FC"
        bloques.append(construir_bloque_html(i + 1, fila, color))

    if busqueda21 != OPCION_VACIA:
        encontrada21 = z_completo[z_completo[COL_NOMBRE] == busqueda21]
        if not encontrada21.empty:
            fila21 = encontrada21.iloc[0]
            bloques.append(construir_bloque_html(puesto_busqueda, fila21, "#FFF7E6", destacado=True))

    tabla_html += "".join(bloques) + "</tbody></table></div>"

    tabla_placeholder.markdown(tabla_html, unsafe_allow_html=True)
    st.caption(
        "Cada deportista ocupa un bloque de tres filas (Resultado, Z-score y Posición) "
        "con fondo compartido para que se lea como una sola unidad; el color alterna "
        "entre deportistas consecutivos. La fila 'Posición' indica el puesto de ese "
        "resultado dentro de esa evaluación específica (1° = mejor), considerando a "
        "todas las deportistas de la categoría con ese dato cargado. "
        "La fila agregada por búsqueda se resalta con borde naranja."
    )

# ========================================================================
# PESTAÑA 3 — BOXPLOT COMPARATIVO ENTRE CATEGORÍAS
# ========================================================================
with tab3:
    st.subheader("📦 Boxplot comparativo entre categorías")
    st.caption(
        "Elegí una evaluación y las categorías que querés comparar en el mismo gráfico. "
        "Cada caja muestra la mediana (línea sólida) y los percentiles 25%-75% (bordes de "
        "la caja); la línea punteada marca la media, y los puntos fuera de los bigotes son "
        "valores atípicos."
    )

    col_cat, col_eval = st.columns([2, 1])
    with col_cat:
        categorias_boxplot = st.multiselect(
            "Categorías a comparar:", categorias, default=categorias, key="cats_boxplot"
        )
    with col_eval:
        evaluacion_boxplot = st.selectbox("Evaluación:", COLS_EVAL, key="eval_boxplot")

    modo_boxplot = st.radio(
        "Ver:", ["Resultado crudo", "Z-score"], horizontal=True, key="modo_boxplot"
    )

    if not categorias_boxplot:
        st.info("Elegí al menos una categoría para ver el gráfico.")
    else:
        # Misma paleta que el resto de la app. Las altas de invitado se aplican
        # sobre el DataFrame completo (no adentro del cache de cargar_datos),
        # igual que en Campana, Radar y Comparativas.
        PALETA_BOXPLOT = [
            "#2563EB", "#0EA5A4", "#F59E0B", "#DC2626",
            "#7C3AED", "#059669", "#DB2777", "#475569",
        ]

        series_por_categoria = {}
        for cat in categorias_boxplot:
            hoja_cat = next((ws for ws in todas_las_hojas if ws.title == cat), None)
            if hoja_cat is None:
                continue
            df_cat, _ = cargar_datos(hoja_cat, cat)
            if not es_entrenador:
                df_cat = aplicar_altas_invitado(df_cat, cat)
            if evaluacion_boxplot not in df_cat.columns:
                continue
            datos_cat = pd.DataFrame(
                {"nombre": df_cat[COL_NOMBRE], "valor": df_cat[evaluacion_boxplot]}
            ).dropna(subset=["valor"])
            if not datos_cat.empty:
                series_por_categoria[cat] = datos_cat

        fig_box = go.Figure()
        for i, (cat, datos_cat) in enumerate(series_por_categoria.items()):
            nombres_cat = datos_cat["nombre"].values
            valores_crudos = datos_cat["valor"].values

            if modo_boxplot == "Z-score":
                z_graf, _, _ = z_de_serie(
                    datos_cat["valor"].values,
                    invertida=evaluacion_boxplot in EVALUACIONES_INVERTIDAS,
                )
                valores_graf = z_graf
            else:
                valores_graf = valores_crudos

            color_cat = PALETA_BOXPLOT[i % len(PALETA_BOXPLOT)]
            r = int(color_cat[1:3], 16)
            g = int(color_cat[3:5], 16)
            b = int(color_cat[5:7], 16)
            fig_box.add_trace(
                go.Box(
                    y=valores_graf,
                    name=cat,
                    boxmean=True,
                    fillcolor=f"rgba({r},{g},{b},0.40)",
                    line=dict(color=f"rgba({r},{g},{b},0.90)", width=2),
                    marker=dict(color=color_cat, size=5, opacity=0.88),
                    customdata=np.stack([nombres_cat, valores_crudos], axis=-1),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        f"{evaluacion_boxplot}: " + "%{customdata[1]:.2f}<extra></extra>"
                    ),
                )
            )

            # Etiqueta con media y mediana justo arriba de cada caja, para
            # que las estadísticas se lean directamente sin pasar el mouse.
            mediana_cat = np.median(valores_graf)
            media_valor = np.mean(valores_graf)
            tope_caja = np.max(valores_graf)
            fig_box.add_annotation(
                x=cat,
                y=tope_caja,
                yshift=18,
                text=f"x̄ {media_valor:.2f} · Md {mediana_cat:.2f}",
                showarrow=False,
                font=dict(size=14, color=color_cat),
                align="center",
            )

        fig_box.update_layout(
            title=f"{evaluacion_boxplot} — comparación entre categorías",
            yaxis_title=("Z-score" if modo_boxplot == "Z-score" else evaluacion_boxplot),
            height=740,
            showlegend=False,
            margin=dict(t=88),
            dragmode=False,  # evita que arrastrar el mouse/dedo mueva o deforme el gráfico
            xaxis=dict(fixedrange=True),  # sin zoom/paneo horizontal
            yaxis=dict(fixedrange=True),  # sin zoom/paneo vertical
        )
        evento_box = st.plotly_chart(
            fig_box,
            use_container_width=True,
            key="boxplot_chart",
            on_select="rerun",
            config={
                "displayModeBar": False,  # sin botones de zoom/pan de Plotly
                "scrollZoom": False,       # sin zoom con rueda del mouse o gesto táctil
                "doubleClick": False,      # doble clic/doble tap no resetea ni deforma la vista
            },
        )

        if evento_box and evento_box.get("selection") and evento_box["selection"].get("points"):
            punto_box = evento_box["selection"]["points"][0]
            cd_box = punto_box.get("customdata")
            categoria_punto = punto_box.get("x")
            if cd_box:
                st.info(
                    f"**Jugadora seleccionada:** {cd_box[0]}  \n"
                    f"**Categoría:** {categoria_punto}  \n"
                    f"**{evaluacion_boxplot}:** {float(cd_box[1]):.2f}"
                )
            else:
                st.caption(
                    "Ese punto pertenece al rango normal de la caja (no es un valor "
                    "atípico) — hacé clic sobre uno de los puntos sueltos para ver su nombre."
                )

        st.markdown(
            textwrap.dedent(
                """
                <div class="ns-legend">
                  <div class="ns-legend-title">📖 Referencias</div>
                  <div class="ns-legend-item"><b>Caja (Q1–Q3):</b> 50% central de los datos</div>
                  <div class="ns-legend-item">▬ <b>Línea sólida:</b> mediana</div>
                  <div class="ns-legend-item">┄ <b>Línea punteada:</b> media (x̄)</div>
                  <div class="ns-legend-item"><b>Bigotes:</b> rango habitual (±1.5×RIC)</div>
                  <div class="ns-legend-item">● <b>Puntos sueltos:</b> valores atípicos</div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

# ========================================================================
# PESTAÑA 5 — COMPARATIVAS (gráfico de columnas 1ª vs 2ª evaluación)
# ========================================================================
with tab5:
    st.subheader("📊 Comparativas — 1ª vs 2ª evaluación")
    st.caption(
        "Las barras están en Z-score (para poder mostrar todas las evaluaciones en la "
        "misma escala) y la etiqueta sobre cada barra muestra el resultado real. "
        "Elegí hasta 3 deportistas para compararlas entre sí."
    )

    col_cat_comp, col_evals_comp = st.columns([1, 2])
    with col_cat_comp:
        categoria_comp = st.selectbox("Categoría:", categorias, key="cat_comparativas")
    with col_evals_comp:
        evals_comp = st.multiselect(
            "Evaluaciones a comparar:", COLS_EVAL, default=COLS_EVAL, key="evals_comparativas"
        )

    hoja_comp = next((ws for ws in todas_las_hojas if ws.title == categoria_comp), None)
    df_comp, _ = cargar_datos(hoja_comp, categoria_comp) if hoja_comp is not None else (pd.DataFrame(), None)
    if not es_entrenador and not df_comp.empty:
        df_comp = aplicar_altas_invitado(df_comp, categoria_comp)

    if df_comp.empty or not evals_comp:
        st.info("Elegí una categoría con datos y al menos una evaluación.")
    else:
        nombres_comp = sorted(df_comp[COL_NOMBRE].dropna().unique().tolist())
        cols_sel = st.columns(3)
        seleccionados = []
        for idx, col_sel in enumerate(cols_sel, start=1):
            with col_sel:
                elegido = st.selectbox(
                    f"Deportista {idx}:",
                    [OPCION_VACIA] + nombres_comp,
                    key=f"comp_deportista_{idx}",
                )
                if elegido != OPCION_VACIA and elegido not in seleccionados:
                    seleccionados.append(elegido)

        if not seleccionados:
            st.info("Elegí al menos un deportista para ver la comparativa.")
        else:
            # Media y desvío de cada evaluación, calculados sobre la MEJOR marca
            # de toda la categoría, para que el Z-score sea comparable.
            referencia = {}
            for c in evals_comp:
                serie_cat = df_comp[c].dropna()
                referencia[c] = (serie_cat.mean(), serie_cat.std())

            def z_de(valor, evaluacion):
                media_e, desvio_e = referencia[evaluacion]
                if pd.isna(valor) or not desvio_e or pd.isna(desvio_e) or desvio_e == 0:
                    return np.nan if pd.isna(valor) else 0.0
                z = (valor - media_e) / desvio_e
                return -z if evaluacion in EVALUACIONES_INVERTIDAS else z

            COLORES_COMP = ["#2563EB", "#DC2626", "#059669"]
            fig_comp = go.Figure()

            for idx_dep, nombre_dep in enumerate(seleccionados):
                fila_dep = df_comp[df_comp[COL_NOMBRE] == nombre_dep].iloc[0]
                color_dep = COLORES_COMP[idx_dep % len(COLORES_COMP)]

                for sufijo, opacidad, etiqueta in (
                    (SUF_1, 1.0, "1ª eval."),
                    (SUF_2, 0.55, "2ª eval."),
                ):
                    valores_reales = [fila_dep[f"{c}{sufijo}"] for c in evals_comp]
                    z_vals = [z_de(v, c) for v, c in zip(valores_reales, evals_comp)]
                    if all(pd.isna(z) for z in z_vals):
                        continue  # esa fecha no tiene ningún dato cargado

                    fig_comp.add_trace(
                        go.Bar(
                            x=evals_comp,
                            y=z_vals,
                            name=f"{nombre_dep} — {etiqueta}",
                            marker=dict(color=color_dep, opacity=opacidad),
                            text=[
                                "" if pd.isna(v) else f"{v:.2f}" for v in valores_reales
                            ],
                            textposition="outside",
                            textfont=dict(size=10),
                            customdata=np.array(valores_reales, dtype=float),
                            hovertemplate=(
                                f"<b>{nombre_dep}</b> — {etiqueta}<br>"
                                "%{x}<br>Resultado: %{customdata:.2f}<br>"
                                "Z-score: %{y:.2f}<extra></extra>"
                            ),
                        )
                    )

            if not fig_comp.data:
                st.warning("Los deportistas elegidos no tienen resultados cargados en esas evaluaciones.")
            else:
                fig_comp.add_hline(
                    y=0, line_width=1.5, line_dash="dash", line_color="#94A3B8",
                    annotation_text="Media de la categoría", annotation_position="right",
                    annotation_font=dict(size=14, color="#64748B"),
                )
                # Debajo del nombre de cada evaluación, mostrar a qué valor real
                # equivale el 0 (la media de esa evaluación en esta categoría),
                # para tener la referencia sin ir a la Campana de Gauss.
                etiquetas_eje = []
                for c in evals_comp:
                    media_e, _ = referencia[c]
                    if pd.isna(media_e):
                        etiquetas_eje.append(c)
                    else:
                        etiquetas_eje.append(
                            f"{c}<br><span style='font-size:13px;color:#64748B'>"
                            f"0 = {media_e:.2f}</span>"
                        )

                fig_comp.update_layout(
                    barmode="group",
                    title=f"{categoria_comp} — comparativa por evaluación",
                    yaxis_title="Z-score",
                    height=740,
                    margin=dict(t=100, b=88),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    dragmode=False,
                    xaxis=dict(
                        fixedrange=True,
                        tickmode="array",
                        tickvals=evals_comp,
                        ticktext=etiquetas_eje,
                    ),
                    yaxis=dict(fixedrange=True),
                )
                st.plotly_chart(
                    fig_comp,
                    use_container_width=True,
                    key="comparativas_chart",
                    config={
                        "displayModeBar": False,
                        "scrollZoom": False,
                        "doubleClick": False,
                    },
                )
                st.caption(
                    "Barra intensa = 1ª evaluación · Barra clara = 2ª evaluación. "
                    "La altura es el Z-score y el número sobre cada barra es el resultado "
                    "real. Debajo de cada evaluación figura a qué valor equivale el 0, "
                    "es decir la media de esa evaluación en la categoría elegida. "
                    "En tiempos (Sprint 30m, Test T) el Z-score ya está invertido, "
                    "así que una barra más alta siempre significa mejor rendimiento."
                )

# ========================================================================
# PESTAÑA 4 — VIDEO TUTORIALES
# ========================================================================
with tab4:
    st.subheader("🎥 Video Tutoriales")
    st.caption(
        "Tutoriales sobre cómo usar la app. Esta lista es independiente de la "
        "categoría elegida arriba."
    )

    videos_df = cargar_videos(libro)
    videos_df = videos_df[videos_df["Link"].astype(str).str.strip() != ""]

    if videos_df.empty:
        st.info(
            "Todavía no hay videos cargados.\n\n"
            f"Para agregar uno: en tu Google Sheet, creá una pestaña llamada exactamente "
            f"**{HOJA_VIDEOS}** con las columnas **Título**, **Link** y **Descripción** "
            "(esta última es opcional). En cada fila pegá el link de YouTube del video "
            "(puede ser 'Oculto', no hace falta que sea público). Los videos van a aparecer "
            "acá automáticamente, mostrando solo el reproductor — nunca el link."
        )
    else:
        columnas_grid = st.columns(2)
        for i, (_, video) in enumerate(videos_df.iterrows()):
            with columnas_grid[i % 2]:
                with st.container(border=True, key=f"ns_video_{i}"):
                    titulo = str(video["Título"]).strip() or "Video sin título"
                    st.markdown(f"**{titulo}**")
                    descripcion = str(video["Descripción"]).strip()
                    if descripcion:
                        st.caption(descripcion)
                    try:
                        st.video(video["Link"].strip())
                    except Exception:
                        st.warning("No se pudo cargar este video. Revisá que el link sea válido.")
