import streamlit as st
import pandas as pd
import json
import xmltodict
import time
import os

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Mapper Pro v28 (Req/Res)", layout="wide", page_icon="⇄")


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


# --- IMPORTADOR POSTMAN (REQ + RES) ---
def parse_postman_collection(data):
    found_endpoints = {}

    def recursive_search(items):
        for item in items:
            if 'item' in item:  # Carpeta
                recursive_search(item['item'])
            elif 'request' in item:  # Endpoint
                name = item['name']

                # 1. Analizar Request
                req_meta = {}
                try:
                    body_mode = item['request'].get('body', {}).get('mode', '')
                    if body_mode == 'raw':
                        raw = item['request']['body']['raw']
                        if raw.strip().startswith('{') or raw.strip().startswith('['):
                            js = json.loads(raw)
                            if isinstance(js, list) and js: js = js[0]
                            flat = flatten_payload(js)
                            for k, v in flat.items():
                                req_meta[k] = {"required": "?", "comment_tl": "", "example_value": str(v)[:100],
                                               "type": infer_smart_type(k, v), "is_done": False,
                                               "status_tag": "⚪ Sin Estado", "doc_desc": ""}
                except:
                    pass

                # 2. Analizar Response (Examples)
                res_meta = {}
                try:
                    if 'response' in item and item['response']:
                        # Cogemos el primer ejemplo disponible
                        first_res = item['response'][0]
                        if 'body' in first_res:
                            raw_res = first_res['body']
                            if raw_res.strip().startswith('{') or raw_res.strip().startswith('['):
                                js_res = json.loads(raw_res)
                                if isinstance(js_res, list) and js_res: js_res = js_res[0]
                                flat_res = flatten_payload(js_res)
                                for k, v in flat_res.items():
                                    res_meta[k] = {"required": "?", "comment_tl": "", "example_value": str(v)[:100],
                                                   "type": infer_smart_type(k, v), "is_done": False,
                                                   "status_tag": "⚪ Sin Estado", "doc_desc": ""}
                except:
                    pass

                found_endpoints[name] = {
                    "request": {"mapping_rules": {}, "field_metadata": req_meta},
                    "response": {"mapping_rules": {}, "field_metadata": res_meta}
                }

    if 'item' in data: recursive_search(data['item'])
    return found_endpoints


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
        "courier_name": "", "project_notes": "", "dto_library": {}, "endpoints": {}
    }
if 'current_endpoint_name' not in st.session_state: st.session_state.current_endpoint_name = None
if 'direction' not in st.session_state: st.session_state.direction = "request"  # 'request' o 'response'

# --- SIDEBAR ---
with st.sidebar:
    st.title("🚀 Mapper Pro")

    # 1. CARGAR
    with st.expander("📂 Cargar Proyecto"):
        uploaded_file = st.file_uploader("", type=["json"])
        if uploaded_file and st.button("Restaurar", use_container_width=True):
            try:
                data = json.load(uploaded_file)
                # Migración V24 -> V25 -> V28
                if "dto_library" not in data:  # V24 fix
                    old_std = data.get("internal_standard_snapshot", {})
                    data["dto_library"] = {"MainDTO": old_std} if old_std else {}

                # Migración Estructura Endpoints (Req/Res)
                for ep_name, ep_data in data.get("endpoints", {}).items():
                    if "request" not in ep_data:
                        # Convertir estructura antigua a nueva (movemos todo a 'request')
                        data["endpoints"][ep_name] = {
                            "request": {"mapping_rules": ep_data.get("mapping_rules", {}),
                                        "field_metadata": ep_data.get("field_metadata", {})},
                            "response": {"mapping_rules": {}, "field_metadata": {}}
                        }

                st.session_state.project = data
                if data.get("endpoints"): st.session_state.current_endpoint_name = list(data["endpoints"].keys())[0]
                st.toast("Proyecto restaurado y migrado.", icon="✅");
                time.sleep(0.5);
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # 2. POSTMAN
    with st.expander("orange_book: Importar Postman"):
        pm_file = st.file_uploader("Colección v2.1", type=["json"], key="pm_up")
        if pm_file and st.button("Importar", use_container_width=True):
            try:
                new_eps = parse_postman_collection(json.load(pm_file))
                added = 0
                for n, d in new_eps.items():
                    if n not in st.session_state.project["endpoints"]:
                        st.session_state.project["endpoints"][n] = d;
                        added += 1
                if added > 0:
                    st.success(f"Importados {added} endpoints.");
                    st.session_state.current_endpoint_name = list(new_eps.keys())[0];
                    time.sleep(1);
                    st.rerun()
                else:
                    st.warning("Sin endpoints nuevos.")
            except Exception as e:
                st.error(f"Error Postman: {e}")

    st.markdown("---")

    # 3. ENDPOINTS
    st.subheader("🔗 Operaciones")
    new_ep = st.text_input("Nuevo:", placeholder="Ej: CreateOrder")
    if st.button("➕ Crear", use_container_width=True) and new_ep:
        if new_ep not in st.session_state.project["endpoints"]:
            st.session_state.project["endpoints"][new_ep] = {
                "request": {"mapping_rules": {}, "field_metadata": {}},
                "response": {"mapping_rules": {}, "field_metadata": {}}
            }
            st.session_state.current_endpoint_name = new_ep;
            st.rerun()

    eps = list(st.session_state.project["endpoints"].keys())
    if eps:
        idx = 0
        if st.session_state.current_endpoint_name in eps: idx = eps.index(st.session_state.current_endpoint_name)
        sel = st.selectbox("Activa:", eps, index=idx)
        if sel != st.session_state.current_endpoint_name: st.session_state.current_endpoint_name = sel; st.rerun()
        if st.button("🗑️ Eliminar", use_container_width=True):
            del st.session_state.project["endpoints"][sel]
            st.session_state.current_endpoint_name = None;
            st.rerun()

# --- UI PRINCIPAL ---
proj = st.session_state.project
curr_ep = st.session_state.current_endpoint_name

c1, c2 = st.columns([2, 1])
with c1: proj["courier_name"] = st.text_input("📦 Courier", value=proj["courier_name"])
with c2: proj["project_notes"] = st.text_area("Notas", value=proj["project_notes"], height=68)

tab_map, tab_dtos = st.tabs(["⇄ Mapeo (Req/Res)", "📚 DTOs"])

# ==============================================================================
# TAB DTOs
# ==============================================================================
with tab_dtos:
    cl, ca = st.columns([1, 2])
    with cl:
        st.subheader("Mis DTOs")
        if not proj["dto_library"]: st.info("Vacío.")
        to_del = []
        for n in proj["dto_library"]:
            cn, cd = st.columns([3, 1])
            cn.write(f"📄 {n}");
            if cd.button("❌", key=f"d_{n}"): to_del.append(n)
        if to_del:
            for d in to_del: del proj["dto_library"][d]
            st.rerun()
    with ca:
        st.subheader("Añadir DTO")
        tup, ted = st.tabs(["Nuevo", "Editar"])
        with tup:
            nom = st.text_input("Nombre (Ej: Order)", key="nd")
            st1, st2 = st.tabs(["Archivo", "Pegar"])
            cont = None
            with st1:
                f = st.file_uploader("JSON", type=["json"], key="nf")
                if f: cont = json.load(f)
            with st2:
                txt = st.text_area("JSON Text", height=150)
                if txt: cont = json.loads(txt)
            if st.button("Añadir", use_container_width=True):
                if nom and cont: proj["dto_library"][nom] = cont; st.success("Añadido"); time.sleep(0.5); st.rerun()
        with ted:
            opts = list(proj["dto_library"].keys())
            if opts:
                eds = st.selectbox("Editar:", opts)
                val = st.text_area("JSON", value=json.dumps(proj["dto_library"][eds], indent=4), height=300)
                if st.button("Guardar", use_container_width=True): proj["dto_library"][eds] = json.loads(
                    val); st.success("Guardado")

# ==============================================================================
# TAB MAPEO (BIDIRECCIONAL)
# ==============================================================================
with tab_map:
    if not curr_ep:
        st.info("👈 Selecciona Endpoint.")
    else:
        st.markdown(f"### ⚡ Operación: `{curr_ep}`")

        # --- SELECTOR DE DIRECCIÓN ---
        # Usamos columnas para simular tabs visuales o botones grandes
        d_col1, d_col2 = st.columns(2)
        direction = st.session_state.direction

        # Botones para cambiar dirección
        btn_req_type = "primary" if direction == "request" else "secondary"
        btn_res_type = "primary" if direction == "response" else "secondary"

        with d_col1:
            if st.button("➡️ REQUEST (Input)", type=btn_req_type, use_container_width=True):
                st.session_state.direction = "request"
                st.rerun()
        with d_col2:
            if st.button("⬅️ RESPONSE (Output)", type=btn_res_type, use_container_width=True):
                st.session_state.direction = "response"
                st.rerun()

        # Cargar datos según dirección
        current_data = proj["endpoints"][curr_ep][direction]
        prev_map, prev_meta = current_data["mapping_rules"], current_data["field_metadata"]

        st.caption(f"Editando mapeo de: **{direction.upper()}**")

        # Dropdown Unificado
        u_opts = ["SELECCIONAR_CAMPO", "IGNORED_FIELD"]
        if proj["dto_library"]:
            for dn, dc in proj["dto_library"].items():
                for k, v in flatten_payload(dc).items(): u_opts.append(f"[{dn}] {k} | {v}")
            u_opts.sort()

        # Input Payload
        t1, t2 = st.tabs(["Pegar", "Subir"])
        raw = None
        with t1:
            tx = st.text_area(f"JSON {direction.title()}", height=100, key=f"tx_{curr_ep}_{direction}")
            if tx and tx.strip().startswith(("{", "[")): raw = json.loads(tx)
        with t2:
            fl = st.file_uploader("Archivo", type=['json'], key=f"fl_{curr_ep}_{direction}")
            if fl: raw = json.load(fl)

        # Procesar
        keys, exs, typs = [], [], []
        if raw:
            if isinstance(raw, list) and raw: raw = raw[0]
            flat = flatten_payload(raw)
            keys = list(flat.keys())
            for k in keys: exs.append(str(flat[k])[:100]); typs.append(infer_smart_type(k, flat[k]))
        elif prev_meta:
            keys = list(prev_meta.keys())
            for k in keys: exs.append(prev_meta[k].get("example_value", "")); typs.append(prev_meta[k].get("type", ""))

        if keys:
            rows, done = [], 0
            for i, k in enumerate(keys):
                tgt = "SELECCIONAR_CAMPO"
                for t, s in prev_map.items():
                    if s == k:
                        for o in u_opts:
                            if t == o.split(" | ")[0]: tgt = o; break
                        break
                meta = prev_meta.get(k, {})
                if meta.get("is_done"): done += 1
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
            c1.metric("Progreso", f"{done}/{len(keys)}")
            c2.progress(done / len(keys) if keys else 0)

            edited = st.data_editor(
                pd.DataFrame(rows),
                key=f"ed_{curr_ep}_{direction}",  # Key única por endpoint Y dirección
                column_config={
                    "Done": st.column_config.CheckboxColumn("✅", width="small"),
                    "Estado": st.column_config.SelectboxColumn("Estado", options=STATUS_OPTS, width="medium",
                                                               required=True),
                    "Campo Courier": st.column_config.TextColumn(disabled=True),
                    "Target (DTO)": st.column_config.SelectboxColumn("Mapeo 🎯", options=u_opts, required=True,
                                                                     width="large"),
                    "Ejemplo": st.column_config.TextColumn(disabled=True),
                    "Requerido": st.column_config.SelectboxColumn(options=["Sí", "No", "Cond", "?"], width="small"),
                }, width="stretch", hide_index=True, height=600
            )

            with st.expander("👁️ Ver Colores"):
                st.dataframe(edited.style.apply(lambda r: [get_row_color(r["Estado"])] * len(r), axis=1),
                             width="stretch", hide_index=True)

            # Guardar en memoria (solo para la dirección actual)
            nm, nmt = {}, {}
            for _, r in edited.iterrows():
                if "SELECCIONAR" not in r["Target (DTO)"] and "IGNORED" not in r["Target (DTO)"]:
                    nm[r["Target (DTO)"].split(" | ")[0]] = r["Campo Courier"]
                nmt[r["Campo Courier"]] = {
                    "required": r["Requerido"], "comment_tl": r["Nota TL"], "example_value": r["Ejemplo"],
                    "type": r["Tipo"], "is_done": r["Done"], "status_tag": r["Estado"], "doc_desc": r["Doc"]
                }
            proj["endpoints"][curr_ep][direction]["mapping_rules"] = nm
            proj["endpoints"][curr_ep][direction]["field_metadata"] = nmt
        else:
            st.info(f"Sin datos en {direction.upper()}.")

st.write("---")
if st.button("💾 Descargar Proyecto (.json)", type="primary", use_container_width=True):
    proj["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    fn = f"Int_{proj['courier_name']}.json".replace(" ", "_")
    if fn == "Int_.json": fn = "Backup.json"
    st.download_button("⬇️ Confirmar", data=json.dumps(proj, indent=4), file_name=fn, mime="application/json",
                       use_container_width=True)