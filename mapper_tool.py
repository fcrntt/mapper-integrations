import streamlit as st
import pandas as pd
import json
import xmltodict
import time
import os
import sys

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Mapper (Local)", layout="wide", page_icon="💻", initial_sidebar_state="collapsed")


# --- FUNCIONES DE LÓGICA ---
def flatten_payload(y):
    out = {}

    def flatten(x, name=''):
        if isinstance(x, dict):
            for a in x: flatten(x[a], name + a + '.')
        elif isinstance(x, list):
            if len(x) > 0:
                flatten(x[0], name)
            else:
                out[name[:-1]] = "[]"
        else:
            out[name[:-1]] = x

    flatten(y)
    return out


def unflatten_json(d):
    res = {}
    for k, v in d.items():
        parts = k.split('.')
        curr = res
        for p in parts[:-1]:
            if p not in curr: curr[p] = {}
            curr = curr[p]
        curr[parts[-1]] = v
    return res


def infer_smart_type(key, value):
    if value is not None:
        t = type(value).__name__
        m = {'str': 'String', 'int': 'Integer', 'float': 'Decimal', 'bool': 'Boolean', 'dict': 'Object',
             'list': 'Array'}
        return m.get(t, t)
    k = key.lower()
    if any(x in k for x in ['dt', 'date', 'time']): return 'DateTime?'
    if any(x in k for x in ['flag', 'is_']): return 'Boolean?'
    if any(x in k for x in ['qtd', 'peso', 'valor', 'total']): return 'Decimal?'
    if any(x in k for x in ['id', 'cod', 'num', 'cpf', 'cnpj']): return 'String?'
    return 'String? (null)'


# --- COLORES Y ESTADOS ---
STATUS_OPTS = ["⚪ Sin Estado", "🔵 Revisar con Analista", "🟡 Revisar con Courier", "✅ Valor Confirmado",
               "🌫️ Valor Omitido", "🟠 Revisar con ITX", "🟣 Validar Frontal", "🧪 Postman", "🟢 Pendiente de verificar TL"]


def get_row_color(s):
    c = {"Analista": '#e3f2fd', "Courier": '#fff9c4', "Confirmado": '#dcedc8', "Omitido": '#f5f5f5', "ITX": '#ffe0b2',
         "Frontal": '#e1bee7', "Postman": '#ffff00', "TL": '#2e7d32'}
    for k, v in c.items():
        if k in s: return f'background-color: {v}'
    return ''


# --- ESTADO DE SESIÓN (RAM) ---
# Aquí guardamos todo mientras la app está abierta. Al cerrar se pierde (como un Excel sin guardar)
if 'session_data' not in st.session_state:
    st.session_state.session_data = {
        "courier": "", "endpoint": "", "notes": "",
        "map": {}, "meta": {}, "std": {}  # std = estándar interno
    }

# --- BARRA LATERAL: CARGAR / GUARDAR ---
with st.sidebar:
    st.title("💻 Archivo")

    # 1. CARGAR PROYECTO
    st.subheader("1. Abrir Proyecto")
    uploaded_file = st.file_uploader("Sube un JSON (.json)", type=["json"])

    if uploaded_file is not None:
        # Botón para confirmar la carga (evita recargas accidentales)
        if st.button("📂 Cargar Datos"):
            try:
                data = json.load(uploaded_file)
                st.session_state.session_data["courier"] = data.get("courier_name", "")
                st.session_state.session_data["endpoint"] = data.get("endpoint", "")
                st.session_state.session_data["notes"] = data.get("project_notes", "")
                st.session_state.session_data["map"] = data.get("mapping_rules", {})
                st.session_state.session_data["meta"] = data.get("field_metadata", {})
                st.toast("Proyecto Cargado Correctamente", icon="✅")
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("---")

    # 2. CARGAR ESTÁNDAR (Opcional)
    st.subheader("2. Actualizar Estándar")
    st.caption("Si tu Tech Lead te ha pasado un nuevo fichero de campos (`standard.json`), cárgalo aquí.")
    uploaded_std = st.file_uploader("Sube estándar (.json)", type=["json"], key="std_up")

    # Lógica de Estándar: Si suben uno, usamos ese. Si no, usamos uno básico por defecto en memoria.
    std_to_use = {"order": {"id": "String", "customer": "Object"}}  # Default básico

    if uploaded_std:
        try:
            std_to_use = json.load(uploaded_std)
        except:
            pass
    elif st.session_state.session_data["std"]:
        std_to_use = st.session_state.session_data["std"]  # Usar el que ya teníamos en memoria

    st.session_state.session_data["std"] = std_to_use  # Guardar en memoria

    # Preparar opciones para el dropdown
    flat_std = flatten_payload(std_to_use)
    std_options = ["SELECCIONAR_CAMPO", "IGNORED_FIELD"] + sorted([f"{k} | {v}" for k, v in flat_std.items()])

# --- UI PRINCIPAL ---
st.markdown(f"### 🛠️ Editor Local")

sd = st.session_state.session_data

# INPUTS METADATOS
with st.container(border=True):
    c1, c2 = st.columns(2)
    # Usamos key para vincular directamente, pero actualizamos manualmente el dict
    cour = c1.text_input("📦 Courier", value=sd["courier"])
    endp = c2.text_input("🔗 Endpoint", value=sd["endpoint"])
    notas = st.text_area("📝 Notas", value=sd["notes"], height=68)

# Actualizar memoria RAM
sd["courier"] = cour
sd["endpoint"] = endp
sd["notes"] = notas

# TABS
tab_map, tab_std = st.tabs(["🧩 Mapeo", "⚙️ Ver Estándar"])

with tab_map:
    prev_map = sd["map"]
    prev_meta = sd["meta"]

    # INPUT PAYLOAD
    t1, t2 = st.tabs(["📄 Pegar Texto", "📁 Subir Payload"])
    raw = None
    with t1:
        txt = st.text_area("JSON / XML Response", height=100)
        if txt:
            if txt.strip().startswith(("{", "[")):
                raw = json.loads(txt)
            elif txt.strip().startswith("<"):
                raw = xmltodict.parse(txt)
    with t2:
        f = st.file_uploader("Archivo Payload", type=['json', 'xml'])
        if f:
            if f.name.endswith('.json'):
                raw = json.load(f)
            elif f.name.endswith('.xml'):
                raw = xmltodict.parse(f.read())

    # PROCESAMIENTO
    keys, exs, typs = [], [], []
    if raw:
        if isinstance(raw, list) and raw: raw = raw[0]
        flat = flatten_payload(raw)
        keys = list(flat.keys())
        for k in keys:
            exs.append(str(flat[k])[:100])
            typs.append(infer_smart_type(k, flat[k]))
    elif prev_meta:
        # Si no hay payload nuevo, tiramos de lo guardado
        keys = list(prev_meta.keys())
        for k in keys:
            exs.append(prev_meta[k].get("example_value", ""))
            typs.append(prev_meta[k].get("type", ""))

    if keys:
        rows, done_n = [], 0
        for i, k in enumerate(keys):
            tgt = "SELECCIONAR_CAMPO"
            # Recuperar Target
            for t, s in prev_map.items():
                if s == k:
                    for o in std_options:
                        if t == o.split(" | ")[0]: tgt = o; break
                    break

            meta = prev_meta.get(k, {})
            if meta.get("is_done"): done_n += 1

            rows.append({
                "Done": meta.get("is_done", False),
                "Estado": meta.get("status_tag", "⚪ Sin Estado"),
                "Campo del Courier": k,
                "Valor (HD)": tgt,
                "Valor de ejemplo": exs[i],
                "Tipo de atributo": typs[i],
                "Requerido": meta.get("required", "?"),
                "Limite de tamaño": meta.get("size_limit", ""),
                "Descripción Docs": meta.get("doc_desc", ""),
                "Comentario TL": meta.get("comment_tl", ""),
                "Comentario Desarrollador": meta.get("comment_dev", ""),
                "Comentario Analista": meta.get("comment_analyst", "")
            })

        # UI TABLA
        st.write("---")
        c_m, c_p = st.columns([1, 4])
        with c_m:
            st.metric("Progreso", f"{done_n}/{len(keys)}")
        with c_p:
            st.progress(done_n / len(keys) if keys else 0)

        edited = st.data_editor(pd.DataFrame(rows), column_config={
            "Done": st.column_config.CheckboxColumn("✅", width="small"),
            "Estado": st.column_config.SelectboxColumn("Estado 🎨", options=STATUS_OPTS, width="medium", required=True),
            "Campo del Courier": st.column_config.TextColumn(disabled=True),
            "Valor (HD)": st.column_config.SelectboxColumn("Target Interno 🎯", options=std_options, required=True,
                                                           width="large"),
            "Valor de ejemplo": st.column_config.TextColumn(disabled=True),
            "Requerido": st.column_config.SelectboxColumn(options=["Sí", "No", "Cond", "?"], width="small"),
        }, use_container_width=True, hide_index=True, height=500)

        with st.expander("👁️ Vista Coloreada"):
            st.dataframe(edited.style.apply(lambda r: [get_row_color(r["Estado"])] * len(r), axis=1),
                         use_container_width=True, hide_index=True)

        st.divider()

        # --- GENERACIÓN DEL JSON PARA GUARDAR ---
        f_map, f_meta, f_done = {}, {}, 0
        for _, r in edited.iterrows():
            if "SELECCIONAR" not in r["Valor (HD)"] and "IGNORED" not in r["Valor (HD)"]:
                f_map[r["Valor (HD)"].split(" | ")[0]] = r["Campo del Courier"]
            if r["Done"]: f_done += 1
            f_meta[r["Campo del Courier"]] = {
                "required": r["Requerido"], "comment_tl": r["Comentario TL"],
                "example_value": r["Valor de ejemplo"], "type": r["Tipo de atributo"],
                "is_done": r["Done"], "status_tag": r["Estado"],
                "comment_dev": r["Comentario Desarrollador"], "comment_analyst": r["Comentario Analista"],
                "size_limit": r["Limite de tamaño"], "doc_desc": r["Descripción Docs"]
            }

        out_json = {
            "courier_name": cour, "endpoint": endp, "project_notes": notas,
            "progress_stats": {"total": len(keys), "done": f_done},
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mapping_rules": f_map, "field_metadata": f_meta
        }

        # --- BOTÓN DE DESCARGA SIMPLE ---
        fn = f"spec_{cour}_{endp}.json".replace(" ", "_").lower()
        if not fn.endswith(".json"): fn = "spec_proyecto.json"

        st.download_button(
            label="💾 Descargar Proyecto (.json)",
            data=json.dumps(out_json, indent=4),
            file_name=fn,
            mime="application/json",
            type="primary",
            use_container_width=True
        )

    else:
        st.info("Sube un JSON/XML para empezar o carga un proyecto existente.")

with tab_std:
    # Solo visualización para no complicar el modo local
    st.info("Para editar el estándar, edita el JSON localmente y súbelo de nuevo.")
    st.json(std_to_use, expanded=True)