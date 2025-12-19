import streamlit as st
import pandas as pd
import json
import time
import io
import xlsxwriter

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Mapper Pro v36", layout="wide", page_icon="🏷️")

# --- COLORES Y ESTADOS (GLOBAL) ---
STATUS_OPTS = [
    "⚪ Sin Estado",
    "🔵 Revisar con Analista",
    "🟡 Revisar con Courier",
    "✅ Valor Confirmado",
    "🌫️ Valor Omitido",
    "🟠 Revisar con ITX",
    "🟣 Validar Frontal",
    "🧪 Postman",
    "🟢 Pendiente de verificar TL"
]


def get_row_color(s):
    c = {
        "Analista": '#e3f2fd', "Courier": '#fff9c4', "Confirmado": '#dcedc8',
        "Omitido": '#f5f5f5', "ITX": '#ffe0b2', "Frontal": '#e1bee7',
        "Postman": '#ffff00', "TL": '#2e7d32'
    }
    for k, v in c.items():
        if k in s: return f'background-color: {v}'
    return ''


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


# --- GENERADOR DE EXCEL PRO (CON MINI TABLA ARRIBA) ---
def generate_excel_pro(df_main, df_extras_dict, dropdown_target_options):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        sheet_name = 'Mapeo'
        workbook = writer.book

        # --- 1. ESTILOS ---
        base_fmt = workbook.add_format(
            {'font_name': 'Calibri', 'font_size': 11, 'valign': 'vcenter', 'border': 1, 'border_color': '#D9D9D9'})
        header_fmt = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 12, 'bold': True,
            'font_color': 'white', 'bg_color': '#2C3E50',
            'valign': 'vcenter', 'align': 'center', 'border': 1
        })
        section_title_fmt = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 14, 'bold': True, 'font_color': '#2C3E50', 'underline': True
        })

        color_map = {
            "🔵 Revisar con Analista": '#E3F2FD', "🟡 Revisar con Courier": '#FFF9C4',
            "✅ Valor Confirmado": '#DCEDC8', "🌫️ Valor Omitido": '#F5F5F5',
            "🟠 Revisar con ITX": '#FFE0B2', "🟣 Validar Frontal": '#E1BEE7',
            "🧪 Postman": '#FFFFE0', "🟢 Pendiente de verificar TL": '#A5D6A7', "⚪ Sin Estado": '#FFFFFF'
        }

        # --- 2. PREPARACIÓN DE DATOS EXTRA ---
        # Convertimos el dict de extras a DataFrame para escribirlo fácil
        if df_extras_dict:
            list_data = [{"Clave": k, "Valor": v} for k, v in df_extras_dict.items()]
            df_extras = pd.DataFrame(list_data, columns=["Clave", "Valor"])
        else:
            df_extras = pd.DataFrame(columns=["Clave", "Valor"])

        # --- 3. ESCRITURA ---

        # Escribimos un DF temporal vacío solo para iniciar la hoja
        pd.DataFrame().to_excel(writer, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]

        current_row = 0

        # --- A) TABLA DATOS ADICIONALES (MINI TABLA) ---
        if not df_extras.empty:
            worksheet.write(current_row, 0, "DATOS ADICIONALES", section_title_fmt)
            current_row += 1

            # Headers Extras
            worksheet.write(current_row, 0, "Clave", header_fmt)
            worksheet.write(current_row, 1, "Valor", header_fmt)
            current_row += 1

            # Data Extras
            for _, row in df_extras.iterrows():
                worksheet.write(current_row, 0, row['Clave'], base_fmt)
                worksheet.write(current_row, 1, row['Valor'], base_fmt)
                current_row += 1

            # Espacio separador
            current_row += 2

        # --- B) TABLA PRINCIPAL (MAPEO) ---
        worksheet.write(current_row, 0, "MAPEO DE CAMPOS", section_title_fmt)
        current_row += 1

        # Guardamos donde empieza el header de la tabla principal
        main_header_row = current_row

        # Escribimos los datos de la tabla principal
        # startrow = main_header_row + 1 (porque to_excel escribiría header, pero lo haremos manual para estilo)
        df_main.to_excel(writer, sheet_name=sheet_name, index=False, startrow=main_header_row + 1, header=False)

        # Escribir Headers Manualmente con Estilo
        for col_num, value in enumerate(df_main.columns.values):
            worksheet.write(main_header_row, col_num, value, header_fmt)

        # Altura filas tabla principal
        for i in range(len(df_main)):
            worksheet.set_row(main_header_row + 1 + i, 20)

        # --- 4. FORMATO CONDICIONAL (VIVO) ---
        # Calculamos el rango basado en la posición variable
        first_data_row = main_header_row + 2  # Excel row index (1-based)
        last_data_row = first_data_row + len(df_main) - 1
        last_col_char = chr(65 + len(df_main.columns) - 1)

        # Rango ej: A15:E50
        range_full = f"A{first_data_row}:{last_col_char}{last_data_row}"

        for status_text, bg_color in color_map.items():
            f = workbook.add_format({'bg_color': bg_color, 'border': 1, 'border_color': '#D9D9D9', 'valign': 'vcenter'})
            if "Omitido" in status_text: f.set_font_color('#9E9E9E')

            # La fórmula debe apuntar a la columna A de la fila de inicio
            # IMPORTANTE: $A{first_data_row} fija la columna A pero deja la fila relativa
            worksheet.conditional_format(range_full, {
                'type': 'formula',
                'criteria': f'=$A{first_data_row}="{status_text}"',
                'format': f
            })

        # --- 5. VALIDACIÓN DE DATOS (DROPDOWNS) ---
        ws_data = workbook.add_worksheet('Data_Validation')
        ws_data.hide()

        # Lista Estados
        for i, opt in enumerate(STATUS_OPTS): ws_data.write(i, 0, opt)
        range_status = f'=Data_Validation!$A$1:$A${len(STATUS_OPTS)}'

        # Aplicar Dropdown Estado (Columna A)
        worksheet.data_validation(main_header_row + 1, 0, main_header_row + len(df_main), 0, {
            'validate': 'list', 'source': range_status, 'input_title': 'Estado'
        })

        # Lista Targets
        if dropdown_target_options:
            for i, opt in enumerate(dropdown_target_options): ws_data.write(i, 1, opt)
            range_target = f'=Data_Validation!$B$1:$B${len(dropdown_target_options)}'

            idx_target = df_main.columns.get_loc("Target (DTO)") if "Target (DTO)" in df_main.columns else 2
            worksheet.data_validation(main_header_row + 1, idx_target, main_header_row + len(df_main), idx_target, {
                'validate': 'list', 'source': range_target, 'input_title': 'Target'
            })

        # --- 6. DETALLES FINALES ---
        worksheet.autofilter(main_header_row, 0, main_header_row + len(df_main), len(df_main.columns) - 1)

        # Congelar paneles justo debajo del header principal
        worksheet.freeze_panes(main_header_row + 1, 0)

        # Anchos
        worksheet.set_column(0, 0, 30)  # Estado / Clave
        worksheet.set_column(1, 1, 35)  # Courier / Valor
        worksheet.set_column(2, 2, 55)  # Target
        worksheet.set_column(3, 3, 30)  # Ejemplo

    return output.getvalue()


# --- IMPORTADOR POSTMAN ---
def parse_postman_collection(data):
    found_endpoints = {}

    def recursive_search(items):
        for item in items:
            if 'item' in item:
                recursive_search(item['item'])
            elif 'request' in item:
                name = item['name']
                method = item['request'].get('method', 'GET')
                req_meta = {}
                try:
                    body_mode = item['request'].get('body', {}).get('mode', '')
                    if body_mode == 'raw':
                        raw = item['request']['body']['raw']
                        if raw.strip().startswith(("{", "[")):
                            js = json.loads(raw)
                            if isinstance(js, list) and js: js = js[0]
                            flat = flatten_payload(js)
                            for k, v in flat.items(): req_meta[k] = {"required": "?", "comment_tl": "",
                                                                     "example_value": str(v)[:100],
                                                                     "type": infer_smart_type(k, v), "is_done": False,
                                                                     "status_tag": "⚪ Sin Estado", "doc_desc": ""}
                except:
                    pass
                res_meta = {}
                try:
                    if 'response' in item and item['response']:
                        first_res = item['response'][0]
                        if 'body' in first_res:
                            raw_res = first_res['body']
                            if raw_res.strip().startswith(("{", "[")):
                                js_res = json.loads(raw_res)
                                if isinstance(js_res, list) and js_res: js_res = js_res[0]
                                flat_res = flatten_payload(js_res)
                                for k, v in flat_res.items(): res_meta[k] = {"required": "?", "comment_tl": "",
                                                                             "example_value": str(v)[:100],
                                                                             "type": infer_smart_type(k, v),
                                                                             "is_done": False,
                                                                             "status_tag": "⚪ Sin Estado",
                                                                             "doc_desc": ""}
                except:
                    pass
                found_endpoints[name] = {"method": method, "extra_metadata": {},
                                         "request": {"mapping_rules": {}, "field_metadata": req_meta},
                                         "response": {"mapping_rules": {}, "field_metadata": res_meta}}

    if 'item' in data: recursive_search(data['item'])
    return found_endpoints


# --- ESTADO DE SESIÓN ---
if 'project' not in st.session_state:
    st.session_state.project = {"courier_name": "", "project_notes": "", "dto_library": {}, "endpoints": {}}
if 'current_endpoint_name' not in st.session_state: st.session_state.current_endpoint_name = None
if 'direction' not in st.session_state: st.session_state.direction = "request"

# --- SIDEBAR ---
with st.sidebar:
    st.title("🚀 Mapper Pro")
    with st.expander("📂 Cargar Proyecto"):
        uploaded_file = st.file_uploader("", type=["json"])
        if uploaded_file and st.button("Restaurar", use_container_width=True):
            try:
                data = json.load(uploaded_file)
                if "dto_library" not in data:
                    old_std = data.get("internal_standard_snapshot", {})
                    data["dto_library"] = {"MainDTO": old_std} if old_std else {}
                for ep_name, ep_data in data.get("endpoints", {}).items():
                    if "request" not in ep_data:
                        data["endpoints"][ep_name] = {"method": "GET", "extra_metadata": {},
                                                      "request": {"mapping_rules": ep_data.get("mapping_rules", {}),
                                                                  "field_metadata": ep_data.get("field_metadata", {})},
                                                      "response": {"mapping_rules": {}, "field_metadata": {}}}
                    elif "method" not in ep_data:
                        ep_data["method"] = "GET";
                        ep_data["extra_metadata"] = {}
                st.session_state.project = data
                if data.get("endpoints"): st.session_state.current_endpoint_name = list(data["endpoints"].keys())[0]
                st.toast("Restaurado OK", icon="✅");
                time.sleep(0.5);
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    with st.expander("🟠 Importar Postman"):
        pm_file = st.file_uploader("Colección v2.1", type=["json"], key="pm_up")
        if pm_file and st.button("Importar", use_container_width=True):
            try:
                new_eps = parse_postman_collection(json.load(pm_file))
                added = 0
                for n, d in new_eps.items():
                    if n not in st.session_state.project["endpoints"]: st.session_state.project["endpoints"][
                        n] = d; added += 1
                if added > 0:
                    st.success(f"Importados {added}.");
                    st.session_state.current_endpoint_name = list(new_eps.keys())[0];
                    time.sleep(1);
                    st.rerun()
                else:
                    st.warning("Sin nuevos endpoints.")
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("---")
    new_ep = st.text_input("Nuevo Endpoint:", placeholder="Ej: CreateOrder")
    if st.button("➕ Crear", use_container_width=True) and new_ep:
        if new_ep not in st.session_state.project["endpoints"]:
            st.session_state.project["endpoints"][new_ep] = {"method": "POST", "extra_metadata": {},
                                                             "request": {"mapping_rules": {}, "field_metadata": {}},
                                                             "response": {"mapping_rules": {}, "field_metadata": {}}}
            st.session_state.current_endpoint_name = new_ep;
            st.rerun()

    eps = list(st.session_state.project["endpoints"].keys())
    if eps:
        idx = 0
        if st.session_state.current_endpoint_name in eps: idx = eps.index(st.session_state.current_endpoint_name)
        sel = st.selectbox("Activa:", eps, index=idx)
        if sel != st.session_state.current_endpoint_name: st.session_state.current_endpoint_name = sel; st.rerun()
        if st.button("🗑️ Eliminar", use_container_width=True): del st.session_state.project["endpoints"][
            sel]; st.session_state.current_endpoint_name = None; st.rerun()

# --- UI PRINCIPAL ---
proj = st.session_state.project
curr_ep = st.session_state.current_endpoint_name

c1, c2 = st.columns([2, 1])
with c1: proj["courier_name"] = st.text_input("📦 Courier", value=proj["courier_name"])
with c2: proj["project_notes"] = st.text_area("Notas Globales", value=proj["project_notes"], height=68)

tab_map, tab_dtos = st.tabs(["⇄ Mapeo y Datos", "📚 DTOs"])

# --- TAB DTOs ---
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
            nom = st.text_input("Nombre", key="nd")
            st1, st2 = st.tabs(["Archivo", "Pegar"])
            cont = None
            with st1:
                f = st.file_uploader("JSON", type=["json"], key="nf")
                if f: cont = json.load(f)
            with st2:
                txt = st.text_area("JSON Text", height=150)
                if txt: cont = json.loads(txt)
            if st.button("Añadir", use_container_width=True):
                if nom and cont: proj["dto_library"][nom] = cont; st.success("OK"); time.sleep(0.5); st.rerun()
        with ted:
            opts = list(proj["dto_library"].keys())
            if opts:
                eds = st.selectbox("Editar:", opts)
                val = st.text_area("JSON", value=json.dumps(proj["dto_library"][eds], indent=4), height=300)
                if st.button("Guardar", use_container_width=True): proj["dto_library"][eds] = json.loads(
                    val); st.success("Guardado")

# --- TAB MAPEO ---
with tab_map:
    if not curr_ep:
        st.info("👈 Selecciona Endpoint.")
    else:
        st.markdown(f"### ⚡ Operación: `{curr_ep}`")

        # --- METADATOS EXTRA ---
        with st.container(border=True):
            mc1, mc2 = st.columns([1, 3])
            with mc1:
                cur_meth = proj["endpoints"][curr_ep].get("method", "GET")
                opts_meth = ["GET", "POST", "PUT", "DELETE", "PATCH"]
                new_meth = st.selectbox("Método HTTP", opts_meth,
                                        index=opts_meth.index(cur_meth) if cur_meth in opts_meth else 0)
                proj["endpoints"][curr_ep]["method"] = new_meth

            with mc2:
                st.caption("🏷️ Datos Adicionales")
                current_extras = proj["endpoints"][curr_ep].get("extra_metadata", {})
                if current_extras:
                    list_data = [{"Clave": k, "Valor": v} for k, v in current_extras.items()]
                    df_extras = pd.DataFrame(list_data, columns=["Clave", "Valor"]).astype(str)
                else:
                    df_extras = pd.DataFrame(columns=["Clave", "Valor"]).astype(str)

                with st.form(key=f"form_meta_{curr_ep}"):
                    edited_extras = st.data_editor(
                        df_extras, num_rows="dynamic", use_container_width=True, hide_index=True, height=150,
                        key=f"meta_{curr_ep}",
                        column_config={"Clave": st.column_config.TextColumn("Clave", required=True),
                                       "Valor": st.column_config.TextColumn("Valor")}
                    )
                    if st.form_submit_button("💾 Guardar Datos Extra", use_container_width=True):
                        new_extras_dict = {}
                        for _, row in edited_extras.iterrows():
                            if row.get("Clave") and str(row["Clave"]).strip() and str(row["Clave"]) != "nan":
                                new_extras_dict[row["Clave"]] = row["Valor"]
                        proj["endpoints"][curr_ep]["extra_metadata"] = new_extras_dict
                        st.success("Guardado.");
                        time.sleep(0.5);
                        st.rerun()

        st.divider()

        # --- SELECCION DIRECCIÓN ---
        d_col1, d_col2 = st.columns(2)
        direction = st.session_state.direction
        btn_req = "primary" if direction == "request" else "secondary"
        btn_res = "primary" if direction == "response" else "secondary"

        with d_col1:
            if st.button("➡️ REQUEST (Input)", type=btn_req,
                         use_container_width=True): st.session_state.direction = "request"; st.rerun()
        with d_col2:
            if st.button("⬅️ RESPONSE (Output)", type=btn_res,
                         use_container_width=True): st.session_state.direction = "response"; st.rerun()

        current_data = proj["endpoints"][curr_ep][direction]
        prev_map, prev_meta = current_data["mapping_rules"], current_data["field_metadata"]

        u_opts = ["SELECCIONAR_CAMPO", "IGNORED_FIELD"]
        if proj["dto_library"]:
            for dn, dc in proj["dto_library"].items():
                for k, v in flatten_payload(dc).items(): u_opts.append(f"[{dn}] {k} | {v}")
            u_opts.sort()

        # --- CARGA DE JSON ---
        t1, t2 = st.tabs(["Pegar", "Subir"])
        raw = None
        with t1:
            tx = st.text_area(f"JSON {direction.title()}", height=100, key=f"tx_{curr_ep}_{direction}")
            if tx and tx.strip().startswith(("{", "[")): raw = json.loads(tx)
        with t2:
            fl = st.file_uploader("Archivo", type=['json'], key=f"fl_{curr_ep}_{direction}")
            if fl: raw = json.load(fl)

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
            rows = []
            for i, k in enumerate(keys):
                tgt = "SELECCIONAR_CAMPO"
                for t, s in prev_map.items():
                    if s == k:
                        for o in u_opts:
                            if t == o.split(" | ")[0]: tgt = o; break
                        break
                meta = prev_meta.get(k, {})
                rows.append({
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
            df_table = pd.DataFrame(rows)

            # --- EDITOR ---
            with st.form(key=f"form_map_{curr_ep}_{direction}"):
                st.caption("📝 Edita la tabla y pulsa Guardar para actualizar colores y descargar.")
                edited = st.data_editor(
                    df_table,
                    key=f"ed_{curr_ep}_{direction}",
                    column_config={
                        "Estado": st.column_config.SelectboxColumn("Estado", options=STATUS_OPTS, width="medium",
                                                                   required=True),
                        "Campo Courier": st.column_config.TextColumn(disabled=True),
                        "Target (DTO)": st.column_config.SelectboxColumn("Mapeo 🎯", options=u_opts, required=True,
                                                                         width="large"),
                        "Ejemplo": st.column_config.TextColumn(disabled=True),
                        "Requerido": st.column_config.SelectboxColumn(options=["Sí", "No", "Cond", "?"], width="small"),
                    }, width="stretch", hide_index=True, height=600
                )

                # BOTÓN GUARDAR
                if st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                    nm, nmt = {}, {}
                    for _, r in edited.iterrows():
                        if "SELECCIONAR" not in r["Target (DTO)"] and "IGNORED" not in r["Target (DTO)"]:
                            nm[r["Target (DTO)"].split(" | ")[0]] = r["Campo Courier"]
                        is_mapped = "SELECCIONAR" not in r["Target (DTO)"]
                        nmt[r["Campo Courier"]] = {
                            "required": r["Requerido"], "comment_tl": r["Nota TL"], "example_value": r["Ejemplo"],
                            "type": r["Tipo"], "is_done": is_mapped, "status_tag": r["Estado"], "doc_desc": r["Doc"]
                        }
                    proj["endpoints"][curr_ep][direction]["mapping_rules"] = nm
                    proj["endpoints"][curr_ep][direction]["field_metadata"] = nmt
                    st.success("Guardado.");
                    time.sleep(0.5);
                    st.rerun()

            # --- ZONA DE DESCARGA ---
            st.markdown("#### 📤 Exportar")
            c_exp1, c_exp2 = st.columns([3, 1])
            with c_exp1:
                st.info("💡 Si has hecho cambios, asegúrate de **Guardar** antes de descargar.")
            with c_exp2:
                # Obtenemos los extras actuales del estado
                extras_to_export = proj["endpoints"][curr_ep].get("extra_metadata", {})

                excel_bytes = generate_excel_pro(df_table, extras_to_export, u_opts)
                file_n = f"Map_{curr_ep}_{direction}.xlsx"
                st.download_button(
                    label="📥 Descargar Excel",
                    data=excel_bytes,
                    file_name=file_n,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            # --- VISUALIZACIÓN DE COLORES ---
            with st.expander("👁️ Ver Colores (Previsualización)"):
                st.dataframe(df_table.style.apply(lambda r: [get_row_color(r["Estado"])] * len(r), axis=1),
                             width="stretch", hide_index=True)

        else:
            st.info(f"Sin datos en {direction.upper()}.")

st.write("---")
if st.button("💾 Descargar Proyecto Completo (.json)", type="secondary", use_container_width=True):
    proj["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    fn = f"Int_{proj['courier_name']}.json".replace(" ", "_")
    if fn == "Int_.json": fn = "Backup.json"
    st.download_button("⬇️ Confirmar JSON", data=json.dumps(proj, indent=4), file_name=fn, mime="application/json",
                       use_container_width=True)