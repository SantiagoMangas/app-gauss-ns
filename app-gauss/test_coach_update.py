"""Pruebas del layout entrenadores contra Google Sheets (sin importar app.py entero)."""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread

# --- mismas reglas que app.py (capa datos) ---
EVALUACIONES_INVERTIDAS = {"Sprint 30m", "Test T (Mod)"}
COL_NUM = "N°"
COL_NOMBRE = "Nombre y Apellido"
COL_FECHA_1 = "Fecha 1ª evaluación"
COL_ASOC = "Asociación"
COL_REGION = "Región"
COL_SELEC = "Selec. ARG"
COL_FECHA_2 = "Fecha 2ª evaluación"
COL_ANIO = "Año última eval"
COLS_EVAL = ["SJ", "CMJ", "ABK", "Sprint 30m", "Test T (Mod)", "30-15 IFT"]
COLS_EVAL_EXTRA = ["Vel. Promedio", "Vel. Max."]
COLS_EVAL_TODAS = COLS_EVAL + COLS_EVAL_EXTRA
ORDEN_COLUMNAS_EVAL_HOJA_NUEVO = [
    "SJ",
    "CMJ",
    "ABK",
    "Sprint 30m",
    "Vel. Promedio",
    "Vel. Max.",
    "Test T (Mod)",
    "30-15 IFT",
]
SUF_1 = " (1ª)"
SUF_2 = " (2ª)"
ANCHO_HOJA_VIEJO = 17
ANCHO_HOJA_NUEVO = 23
FILTRO_TODOS = "Todos"
FILTRO_TODAS = "Todas"
FILTRO_SELEC_ARG = "Selección Argentina"

DIR = Path(__file__).resolve().parent
CREDS = DIR / "credentials.json"
SHEET_COACH = "1-QH7kyR6Ecxen5TMoSzop1EbANq39uYFQtrNmBb0hBY"
SHEET_GUEST = "1omcULVwUMCJ5WlgsHi-q2G5jIZVKKbtB03JjXHuNOZk"


def parse_numero(valor):
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


def columnas_eval_en_df(df):
    presentes = []
    for c in COLS_EVAL_TODAS:
        if c in df.columns or f"{c}{SUF_1}" in df.columns or f"{c}{SUF_2}" in df.columns:
            presentes.append(c)
    return presentes


def consolidar_mejores(df):
    out = df.copy()
    for c in columnas_eval_en_df(out):
        c1, c2 = f"{c}{SUF_1}", f"{c}{SUF_2}"
        partes = []
        if c1 in out.columns:
            partes.append(out[c1])
        if c2 in out.columns:
            partes.append(out[c2])
        if not partes:
            continue
        stacked = pd.concat(partes, axis=1)
        out[c] = stacked.min(axis=1) if c in EVALUACIONES_INVERTIDAS else stacked.max(axis=1)
    return out


def parse_fecha(valor):
    if valor is None:
        return pd.NaT
    s = str(valor).strip()
    if not s or s.lower() in ("none", "nan"):
        return pd.NaT
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return pd.to_datetime(s, format=fmt, dayfirst=True)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def anio_ultima_evaluacion(fecha_1, fecha_2):
    fechas = [parse_fecha(fecha_1), parse_fecha(fecha_2)]
    validas = [f for f in fechas if pd.notna(f)]
    if not validas:
        return np.nan
    return int(max(validas).year)


def es_convocada_seleccion(valor):
    s = str(valor).strip().lower()
    if s in ("", "none", "nan", "no", "0"):
        return False
    return s in ("selec. arg", "selec arg") or ("selec" in s and "arg" in s)


def normalizar_clave_filtro(valor):
    s = str(valor).strip().lower()
    if not s or s in ("none", "nan"):
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("-", " ")
    return " ".join(s.split())


def opciones_filtro_texto(serie, etiqueta_todas):
    if serie is None or serie.empty:
        return [etiqueta_todas]
    por_clave = {}
    for x in serie.dropna():
        etiqueta = str(x).strip()
        if not etiqueta or etiqueta.lower() in ("none", "nan"):
            continue
        clave = normalizar_clave_filtro(etiqueta)
        if clave not in por_clave or etiqueta < por_clave[clave]:
            por_clave[clave] = etiqueta
    vals = sorted(por_clave.values(), key=lambda t: t.casefold())
    return [etiqueta_todas] + vals


def opciones_asociacion_para_region(df, filtro_region):
    if df.empty or COL_ASOC not in df.columns:
        return [FILTRO_TODAS]
    sub = df
    if filtro_region != FILTRO_TODAS and COL_REGION in df.columns:
        clave_r = normalizar_clave_filtro(filtro_region)
        sub = df[df[COL_REGION].map(normalizar_clave_filtro) == clave_r]
    return opciones_filtro_texto(sub[COL_ASOC], FILTRO_TODAS)


def filtrar_dataset(df, filtro_ano, filtro_conv, filtro_region, filtro_asoc):
    if df.empty:
        return df.copy()
    mask = pd.Series(True, index=df.index)
    if filtro_ano != FILTRO_TODOS and COL_ANIO in df.columns:
        mask &= df[COL_ANIO] == int(filtro_ano)
    if filtro_conv == FILTRO_SELEC_ARG and COL_SELEC in df.columns:
        mask &= df[COL_SELEC].map(es_convocada_seleccion)
    if filtro_region != FILTRO_TODAS and COL_REGION in df.columns:
        clave_r = normalizar_clave_filtro(filtro_region)
        mask &= df[COL_REGION].map(normalizar_clave_filtro) == clave_r
    if filtro_asoc != FILTRO_TODAS:
        clave_a = normalizar_clave_filtro(filtro_asoc)
        mask &= df[COL_ASOC].map(normalizar_clave_filtro) == clave_a
    return df.loc[mask].copy()


def cargar_datos_nuevo(hoja):
    valores = hoja.get_all_values()
    filas = [
        (fila + [""] * ANCHO_HOJA_NUEVO)[:ANCHO_HOJA_NUEVO]
        for fila in valores[1:]
        if len(fila) > 1 and str(fila[1]).strip() != ""
    ]
    registros = []
    for fila in filas:
        rec = {
            COL_NUM: fila[0],
            COL_NOMBRE: str(fila[1]).strip(),
            COL_FECHA_1: fila[2],
            COL_REGION: str(fila[3]).strip(),
            COL_ASOC: str(fila[4]).strip(),
            COL_SELEC: str(fila[5]).strip(),
            COL_FECHA_2: fila[14],
        }
        for c, raw in zip(ORDEN_COLUMNAS_EVAL_HOJA_NUEVO, fila[6:14]):
            rec[f"{c}{SUF_1}"] = parse_numero(raw)
        for c, raw in zip(ORDEN_COLUMNAS_EVAL_HOJA_NUEVO, fila[15:23]):
            rec[f"{c}{SUF_2}"] = parse_numero(raw)
        registros.append(rec)
    df = pd.DataFrame(registros)
    df = consolidar_mejores(df)
    df[COL_ANIO] = df.apply(
        lambda r: anio_ultima_evaluacion(r[COL_FECHA_1], r[COL_FECHA_2]), axis=1
    )
    return df


def cargar_datos_viejo(hoja):
    valores = hoja.get_all_values()
    filas = [
        (fila + [""] * ANCHO_HOJA_VIEJO)[:ANCHO_HOJA_VIEJO]
        for fila in valores[1:]
        if len(fila) > 1 and str(fila[1]).strip() != ""
    ]
    df = pd.DataFrame(
        filas,
        columns=[
            COL_NUM,
            COL_NOMBRE,
            COL_FECHA_1,
            COL_ASOC,
            *[f"{c}{SUF_1}" for c in COLS_EVAL],
            COL_FECHA_2,
            *[f"{c}{SUF_2}" for c in COLS_EVAL],
        ],
    )
    for c in COLS_EVAL:
        df[f"{c}{SUF_1}"] = df[f"{c}{SUF_1}"].apply(parse_numero)
        df[f"{c}{SUF_2}"] = df[f"{c}{SUF_2}"].apply(parse_numero)
    df = consolidar_mejores(df)
    df[COL_ANIO] = df.apply(
        lambda r: anio_ultima_evaluacion(r[COL_FECHA_1], r[COL_FECHA_2]), axis=1
    )
    return df


def z_de_serie(valores, invertida=False):
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


def calcular_tabla_z(df_base, cols_eval):
    tabla = pd.DataFrame({COL_NOMBRE: df_base[COL_NOMBRE].values})
    for c in cols_eval:
        valores = df_base[c].to_numpy(dtype=float)
        z, _, _ = z_de_serie(valores, invertida=c in EVALUACIONES_INVERTIDAS)
        tabla[f"{c}__z"] = z
    return tabla


def conectar(sheet_id):
    info = json.loads(CREDS.read_text(encoding="utf-8"))
    gc = gspread.authorize(
        Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    )
    return gc.open_by_key(sheet_id)


def test_filtros_cascada_y_normalizacion():
    assert normalizar_clave_filtro("NEA NORTE") == normalizar_clave_filtro("nea norte")
    assert normalizar_clave_filtro("Tucumán") == normalizar_clave_filtro("TUCUMAN")
    assert normalizar_clave_filtro("Centro-Cuyo") == normalizar_clave_filtro("Centro Cuyo")

    mini = pd.DataFrame(
        {
            COL_REGION: ["Bonaerense", "NEA NORTE", "NEA NORTE"],
            COL_ASOC: ["FHSB", "MISIONES", "Chaco"],
            COL_NOMBRE: ["A", "B", "C"],
            COL_ANIO: [2026, 2026, 2026],
            COL_SELEC: ["", "", ""],
        }
    )
    opts_b = opciones_asociacion_para_region(mini, "Bonaerense")
    assert opts_b == [FILTRO_TODAS, "FHSB"]
    opts_n = opciones_asociacion_para_region(mini, "NEA NORTE")
    assert "MISIONES" in opts_n and "FHSB" not in opts_n

    filtrado = filtrar_dataset(
        mini, FILTRO_TODOS, FILTRO_TODOS, "nea norte", "chaco"
    )
    assert len(filtrado) == 1 and filtrado.iloc[0][COL_NOMBRE] == "C"


def main():
    test_filtros_cascada_y_normalizacion()
    assert CREDS.is_file(), "falta credentials.json"
    sh = conectar(SHEET_COACH)
    df = cargar_datos_nuevo(sh.worksheet("Sub 16 Damas"))
    assert len(df) >= 180, len(df)
    for c in COLS_EVAL + COLS_EVAL_EXTRA:
        assert c in df.columns, c
    n_ift = int(df["30-15 IFT"].notna().sum())
    assert n_ift >= 100, f"30-15 IFT mal mapeado: solo {n_ift} valores"
    med_tt = float(df["Test T (Mod)"].median())
    med_vp = float(df["Vel. Promedio"].median())
    assert med_tt < 12 and med_vp > 15, (
        f"Test T ({med_tt}) y Vel. Promedio ({med_vp}) parecen intercambiados"
    )
    n_all = len(filtrar_dataset(df, FILTRO_TODOS, FILTRO_TODOS, FILTRO_TODAS, FILTRO_TODAS))
    n_selec = len(
        filtrar_dataset(df, FILTRO_TODOS, FILTRO_SELEC_ARG, FILTRO_TODAS, FILTRO_TODAS)
    )
    assert 0 < n_selec < n_all
    opts_bona = opciones_asociacion_para_region(df, "Bonaerense")
    assert "MISIONES" not in opts_bona and "CORRIENTES" not in opts_bona
    assert any(a for a in opts_bona if a not in (FILTRO_TODAS,))
    z = calcular_tabla_z(df, COLS_EVAL)
    assert len(z) == len(df) and z["SJ__z"].notna().any()

    sh_g = conectar(SHEET_GUEST)
    df_g = cargar_datos_viejo(sh_g.worksheet("Sub 16 Damas"))
    assert len(df_g) >= 150 and "SJ" in df_g.columns

    for cat in ("Sub 19  Damas", "Sub 16 Caballeros", "Sub 19 Caballeros"):
        d = cargar_datos_nuevo(sh.worksheet(cat))
        assert "Vel. Promedio" in d.columns and d["SJ"].notna().any(), cat

    print("OK carga coach Sub16:", len(df), "filas")
    print("OK selec ARG filtro:", n_selec, "de", n_all)
    print("OK z radar SJ")
    print("OK invitado layout viejo:", len(df_g), "filas")
    print("OK otras categorias coach")
    print("\nTODAS LAS PRUEBAS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
