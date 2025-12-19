import streamlit as st
import pandas as pd
import json
import xmltodict
import time
import os

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Mapper Pro v26", layout="wide", page_icon="🚀")


# --- FUNCIONES CORE ---
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


# --- COLORES ---
STATUS_OPTS = ["⚪ Sin Estado", "🔵 Revisar con Analista", "🟡 Revisar con Courier", "✅ Valor Confirmado",
               "🌫️ Valor Omitido", "🟠 Revisar con ITX", "🟣 Validar Frontal", "🧪 Postman", "🟢 Pendiente de verificar TL"]


def get_row_color(s):
    c = {"Analista": '#e3f2fd', "Courier": '#fff9c4', "Confirmado": '#dcedc8', "Omitido": '#f5f5f5', "ITX": '#ffe0b2',
         "Frontal": '#e1bee7', "Postman": '#ffff00', "TL": '#2e7d32'}
    for k, v in c.items():
        if k in s: return f'background-color: {v}'
    return ''


# --- ESTADO DE SESIÓN ---
if 'project' not in st.session_state:
    st.session_state.project = {
        "courier_name": "",
        "project_notes": "",
        "dto_library": {},
        "endpoints": {}
    }

if 'current_endpoint_name' not in st.session_state:
    st.session_state.current_endpoint_name = None

# --- SIDEBAR: GESTIÓN GLOBAL ---
with st.sidebar:
    st.title("🚀 Mapper Pro")

    # 1. CARGAR PROYECTO
    uploaded_file = st.file_uploader("📂 Cargar Proyecto (.json)", type=["json"])
    if uploaded_file and st.button("Restaurar Proyecto", use_container_width=True):
        try:
            data = json.load(uploaded_file)
            # Compatibilidad v23->v25
            if "dto_library" not in data:
                old_std = data.get("internal_standard_snapshot", {})
                data["dto_library"] = {"MainDTO": old_std} if old_std else {}

            st.session_state.project = data
            if data.get("endpoints"):
                st.session_state.current_endpoint_name = list(data["endpoints"].keys())[0]
            st.toast("Proyecto restaurado.", icon="✅")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")

    # 2. GESTIÓN ENDPOINTS
    st.subheader("🔗 Endpoints")
    new_ep = st.text_input("Nuevo Endpoint:", placeholder="Ej: CreateOrder")
    if st.button("➕ Crear", use_container_width=True) and new_ep:
        if new_ep not in st.session_state.project["endpoints"]:
            st.session_state.project["endpoints"][new_ep] = {"mapping_rules": {}, "field_metadata": {}}
            st.session_state.current_endpoint_name = new_ep
            st.rerun()

    eps = list(st.session_state.project["endpoints"].keys())
    if eps:
        idx = 0
        if st.session_state.current_endpoint_name in eps: idx = eps.index(st.session_state.current_endpoint_name)
        sel = st.selectbox("Operación Activa:", eps, index=idx)
        if sel != st.session_state.current_endpoint_name:
            st.session_state.current_endpoint_name = sel
            st.rerun()
        if st.button("🗑️ Eliminar Endpoint", use_container_width=True):
            del st.session_state.project["endpoints"][sel]
            st.session_state.current_endpoint_name = None
            st.rerun()

# --- UI PRINCIPAL ---
proj = st.session_state.project
curr_ep = st.session_state.current_endpoint_name

c1, c2 = st.columns([2, 1])
with c1: proj["courier_name"] = st.text_input("📦 Nombre Courier", value=proj["courier_name"])
with c2: proj["project_notes"] = st.text_area("Notas Globales", value=proj["project_notes"], height=68)

tab_map, tab_dtos = st.tabs(["🧩 Mapeo", "📚 Gestión de DTOs (Objetos Internos)"])

# ==============================================================================
# TAB 1: GESTOR DE DTOs
# ==============================================================================
with tab_dtos:
    col_list, col_add = st.columns([1, 2])

    with col_list:
        st.subheader("Mis DTOs")
        if not proj["dto_library"]: st.info("Sin DTOs.")

        dtos_del = []
        for name in proj["dto_library"]:
            c_n, c_d = st.columns([3, 1])
            c_n.write(f"📄 **{name}**")
            if c_d.button("❌", key=f"del_{name}"): dtos_del.append(name)

        if dtos_del:
            for d in dtos_del: del proj["dto_library"][d]
            st.rerun()

    with col_add:
        st.subheader("Añadir / Editar DTO")

        t_up, t_edit = st.tabs(["➕ Añadir Nuevo", "✏️ Editar Existente"])

        with t_up:
            st.markdown("#### 1. Definir Nombre")
            new_dto_name = st.text_input("Nombre del DTO (Ej: OrderDTO)", key="new_dto_name")

            st.markdown("#### 2. Definir Contenido")
            sub_t1, sub_t2 = st.tabs(["📁 Subir Archivo", "📝 Pegar JSON"])

            content_to_add = None

            with sub_t1:
                new_dto_file = st.file_uploader("Archivo JSON", type=["json"], key="new_dto_file")
            with sub_t2:
                new_dto_text = st.text_area("Pega el JSON aquí", height=150, placeholder='{"campo": "valor"}')

            if st.button("📥 Añadir a Librería", use_container_width=True):
                if not new_dto_name:
                    st.warning("⚠️ Falta el nombre del DTO.")
                else:
                    try:
                        if new_dto_file:
                            content_to_add = json.load(new_dto_file)
                        elif new_dto_text:
                            content_to_add = json.loads(new_dto_text)

                        if content_to_add:
                            proj["dto_library"][new_dto_name] = content_to_add
                            st.success(f"✅ DTO '{new_dto_name}' añadido correctamente.")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("⚠️ Sube un archivo o pega el texto JSON.")
                    except Exception as e:
                        st.error(f"❌ JSON inválido: {e}")

        with t_edit:
            dto_opts = list(proj["dto_library"].keys())
            if dto_opts:
                edit_sel = st.selectbox("Editar DTO:", dto_opts)
                json_str = json.dumps(proj["dto_library"][edit_sel], indent=4)
                edited_json_str = st.text_area("Editor JSON", value=json_str, height=300)

                if st.button("💾 Guardar Cambios", use_container_width=True):
                    try:
                        proj["dto_library"][edit_sel] = json.loads(edited_json_str)
                        st.success(f"DTO '{edit_sel}' actualizado.")
                    except Exception as e:
                        st.error(f"Error JSON: {e}")
            else:
                st.info("Sube un DTO primero.")

# ==============================================================================
# TAB 2: MAPEO
# ==============================================================================
with tab_map:
    if not curr_ep:
        st.info("👈 Selecciona o crea un Endpoint.")
    else:
        st.markdown(f"### ⚡ Operación: `{curr_ep}`")

        # PREPARAR DROPDOWN
        unified_options = ["SELECCIONAR_CAMPO", "IGNORED_FIELD"]
        if not proj["dto_library"]:
            st.warning("⚠️ No hay DTOs cargados. Ve a la pestaña 'Gestión de DTOs'.")
        else:
            for dto_name, dto_content in proj["dto_library"].items():
                flat = flatten_payload(dto_content)
                for k, v in flat.items():
                    unified_options.append(f"[{dto_name}] {k} | {v}")
            unified_options.sort()

        ep_data = proj["endpoints"][curr_ep]
        prev_map, prev_meta = ep_data["mapping_rules"], ep_data["field_metadata"]

        t1, t2 = st.tabs(["Pegar Texto", "Subir Archivo"])
        raw = None
        with t1:
            txt = st.text_area("Request/Response JSON", height=100)
            if txt and txt.strip().startswith(("{", "[")): raw = json.loads(txt)
        with t2:
            f = st.file_uploader("Payload", type=['json'], key=f"up_{curr_ep}")
            if f: raw = json.load(f)

        keys, exs, typs = [], [], []
        if raw:
            if isinstance(raw, list) and raw: raw = raw[0]
            flat = flatten_payload(raw)
            keys = list(flat.keys())
            for k in keys:
                exs.append(str(flat[k])[:100])
                typs.append(infer_smart_type(k, flat[k]))
        elif prev_meta:
            keys = list(prev_meta.keys())
            for k in keys:
                exs.append(prev_meta[k].get("example_value", ""))
                typs.append(prev_meta[k].get("type", ""))

        if keys:
            rows, done_n = [], 0
            for i, k in enumerate(keys):
                tgt = "SELECCIONAR_CAMPO"
                for t, s in prev_map.items():
                    if s == k:
                        for o in unified_options:
                            if t == o.split(" | ")[0]: tgt = o; break
                        break
                meta = prev_meta.get(k, {})
                if meta.get("is_done"): done_n += 1

                rows.append({
                    "Done": meta.get("is_done", False),
                    "Estado": meta.get("status_tag", "⚪ Sin Estado"),
                    "Campo Courier": k,
                    "Target (DTO)": tgt,
                    "Ejemplo": exs[i],
                    "Tipo": typs[i],
                    "Requerido": meta.get("required", "?"),
                    "Doc": meta.get("doc_desc", ""),
                    "Nota TL": meta.get("comment_tl", "")
                })

            st.write("---")
            c1, c2 = st.columns([1, 4])
            c1.metric("Progreso", f"{done_n}/{len(keys)}")
            c2.progress(done_n / len(keys) if keys else 0)

            # --- FIX: width="stretch" y KEY única para evitar bug de doble click ---
            edited = st.data_editor(
                pd.DataFrame(rows),
                key=f"editor_{curr_ep}",  # <--- LA CLAVE MÁGICA PARA EL DOBLE CLICK
                column_config={
                    "Done": st.column_config.CheckboxColumn("✅", width="small"),
                    "Estado": st.column_config.SelectboxColumn("Estado", options=STATUS_OPTS, width="medium",
                                                               required=True),
                    "Campo Courier": st.column_config.TextColumn(disabled=True),
                    "Target (DTO)": st.column_config.SelectboxColumn("Mapeo Interno 🎯", options=unified_options,
                                                                     required=True, width="large"),
                    "Ejemplo": st.column_config.TextColumn(disabled=True),
                    "Requerido": st.column_config.SelectboxColumn(options=["Sí", "No", "Cond", "?"], width="small"),
                },
                width="stretch",  # <--- FIX PARA LOS LOGS (Reemplaza use_container_width=True)
                hide_index=True,
                height=600
            )

            with st.expander("👁️ Ver Colores"):
                # FIX PARA LOS LOGS EN DATAFRAME
                st.dataframe(
                    edited.style.apply(lambda r: [get_row_color(r["Estado"])] * len(r), axis=1),
                    width="stretch",
                    hide_index=True
                )

            # Guardado en memoria
            new_map, new_meta = {}, {}
            for _, r in edited.iterrows():
                if "SELECCIONAR" not in r["Target (DTO)"] and "IGNORED" not in r["Target (DTO)"]:
                    new_map[r["Target (DTO)"].split(" | ")[0]] = r["Campo Courier"]
                new_meta[r["Campo Courier"]] = {
                    "required": r["Requerido"], "comment_tl": r["Nota TL"],
                    "example_value": r["Ejemplo"], "type": r["Tipo"],
                    "is_done": r["Done"], "status_tag": r["Estado"],
                    "doc_desc": r["Doc"]
                }
            proj["endpoints"][curr_ep]["mapping_rules"] = new_map
            proj["endpoints"][curr_ep]["field_metadata"] = new_meta

st.write("---")
if st.button("💾 Descargar Proyecto (.json)", type="primary", use_container_width=True):
    proj["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    fn = f"Integracion_{proj['courier_name']}.json".replace(" ", "_")
    if fn == "Integracion_.json": fn = "Project_Backup.json"
    st.download_button("⬇️ Confirmar Descarga", data=json.dumps(proj, indent=4), file_name=fn, mime="application/json",
                       use_container_width=True)