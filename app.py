import streamlit as st
import pandas as pd
import json
import time
import io
import xlsxwriter

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Mapper Pro v41", layout="wide", page_icon="🏷️")

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


# --- LÓGICA DE TIPOS LIMPIA ---
def clean_type_name(val_type, is_nullable=False):
    m = {'str': 'String', 'int': 'Integer', 'float': 'Decimal', 'bool': 'Boolean', 'dict': 'Object', 'list': 'Array',
         'nonetype': 'String'}
    t_lower = str(val_type).lower()
    base = m.get(t_lower, str(val_type).capitalize())
    base = base.replace("(null)", "").replace("?", "").strip()
    if is_nullable: return f"{base}?"
    return base


def infer_smart_type(key, value):
    if value is not None:
        return clean_type_name(type(value).__name__, is_nullable=False)
    k = key.lower()
    base = "String"
    if any(x in k for x in ['dt', 'date', 'time']):
        base = 'DateTime'
    elif any(x in k for x in ['flag', 'is_']):
        base = 'Boolean'
    elif any(x in k for x in ['qtd', 'peso', 'valor', 'total', 'price']):
        base = 'Decimal'
    elif any(x in k for x in ['id', 'cod', 'num']):
        base = 'Integer'
    elif any(x in k for x in ['list', 'array', 'items']):
        base = 'Array'
    return f"{base}?"


# --- GENERADOR DE EXCEL PRO ---
def generate_excel_pro(df_main, df_extras_dict, dropdown_target_options):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        sheet_name = 'Mapeo'
        workbook = writer.book

        # ESTILOS
        base_fmt = workbook.add_format(
            {'font_name': 'Calibri', 'font_size': 11, 'valign': 'vcenter', 'border': 1, 'border_color': '#D9D9D9'})
        header_fmt = workbook.add_format(
            {'font_name': 'Calibri', 'font_size': 12, 'bold': True, 'font_color': 'white', 'bg_color': '#2C3E50',
             'valign': 'vcenter', 'align': 'center', 'border': 1})
        section_title_fmt = workbook.add_format(
            {'font_name': 'Calibri', 'font_size': 14, 'bold': True, 'font_color': '#2C3E50', 'underline': True})

        color_map = {
            "🔵 Revisar con Analista": '#E3F2FD', "🟡 Revisar con Courier": '#FFF9C4',
            "✅ Valor Confirmado": '#DCEDC8', "🌫️ Valor Omitido": '#F5F5F5',
            "🟠 Revisar con ITX": '#FFE0B2', "🟣 Validar Frontal": '#E1BEE7',
            "🧪 Postman": '#FFFFE0', "🟢 Pendiente de verificar TL": '#A5D6A7', "⚪ Sin Estado": '#FFFFFF'
        }

        # DATOS EXTRA (Aquí es donde se usa la tablita pequeña)
        if df_extras_dict:
            list_data = [{"Clave": k, "Valor": v} for k, v in df_extras_dict.items()]
            df_extras = pd.DataFrame(list_data, columns=["Clave", "Valor"])
        else:
            df_extras = pd.DataFrame(columns=["Clave", "Valor"])

        # ESCRITURA
        pd.DataFrame().to_excel(writer, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]
        current_row = 0

        # TABLA EXTRAS (La pequeña arriba)
        if not df_extras.empty:
            worksheet.write(current_row, 0, "DATOS ADICIONALES", section_title_fmt)
            current_row += 1
            worksheet.write(current_row, 0, "Clave", header_fmt)
            worksheet.write(current_row, 1, "Valor", header_fmt)
            current_row += 1
            for _, row in df_extras.iterrows():
                worksheet.write(current_row, 0, row['Clave'], base_fmt)
                worksheet.write(current_row, 1, row['Valor'], base_fmt)
                current_row += 1
            current_row += 2

        # TABLA PRINCIPAL
        worksheet.write(current_row, 0, "MAPEO DE CAMPOS", section_title_fmt)
        current_row += 1
        main_header_row = current_row

        df_main.to_excel(writer, sheet_name=sheet_name, index=False, startrow=main_header_row + 1, header=False)
        for col_num, value in enumerate(df_main.columns.values):
            worksheet.write(main_header_row, col_num, value, header_fmt)
        for i in range(len(df_main)):
            worksheet.set_row(main_header_row + 1 + i, 20)

        # FORMATO CONDICIONAL & FREEZE
        first_data_row = main_header_row + 2
        if len(df_main) > 0:
            last_data_row = first_data_row + len(df_main) - 1
            last_col_char = chr(65 + len(df_main.columns) - 1)
            range_full = f"A{first_data_row}:{last_col_char}{last_data_row}"

            for status_text, bg_color in color_map.items():
                f = workbook.add_format(
                    {'bg_color': bg_color, 'border': 1, 'border_color': '#D9D9D9', 'valign': 'vcenter'})
                if "Omitido" in status_text: f.set_font_color('#9E9E9E')
                worksheet.conditional_format(range_full,
                                             {'type': 'formula', 'criteria': f'=$A{first_data_row}="{status_text}"',
                                              'format': f})

            ws_data = workbook.add_worksheet('Data_Validation')
            ws_data.hide()
            for i, opt in enumerate(STATUS_OPTS): ws_data.write(i, 0, opt)
            range_status = f'=Data_Validation!$A$1:$A${len(STATUS_OPTS)}'
            worksheet.data_validation(main_header_row + 1, 0, main_header_row + len(df_main), 0,
                                      {'validate': 'list', 'source': range_status})

            if dropdown_target_options:
                for i, opt in enumerate(dropdown_target_options): ws_data.write(i, 1, opt)
                range_target = f'=Data_Validation!$B$1:$B${len(dropdown_target_options)}'
                idx_target = df_main.columns.get_loc("Target (DTO)") if "Target (DTO)" in df_main.columns else 2
                worksheet.data_validation(main_header_row + 1, idx_target, main_header_row + len(df_main), idx_target,
                                          {'validate': 'list', 'source': range_target, 'show_error': False})

            worksheet.autofilter(main_header_row, 0, main_header_row + len(df_main), len(df_main.columns) - 1)
            worksheet.freeze_panes(main_header_row + 1, 2)
            worksheet.set_column(0, 0, 30);
            worksheet.set_column(1, 1, 35);
            worksheet.set_column(2, 2, 55)

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
                found_endpoints[name] = {"method": item['request'].get('method', 'GET'), "extra_metadata": {},
                                         "request": {"mapping_rules": {}, "field_metadata": {}},
                                         "response": {"mapping_rules": {}, "field_metadata": {}}}

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
        uploaded_file = st.file_uploader("Subir Proyecto", type=["json"], label_visibility="collapsed")
        if uploaded_file and st.button("Restaurar", use_container_width=True):
            try:
                st.session_state.project = json.load(uploaded_file)
                if st.session_state.project.get("endpoints"):
                    st.session_state.current_endpoint_name = list(st.session_state.project["endpoints"].keys())[0]
                st.rerun()
            except:
                st.error("Error al cargar.")

    with st.expander("🟠 Importar Postman"):
        pm_file = st.file_uploader("Subir Postman", type=["json"], key="pm_up", label_visibility="collapsed")
        if pm_file and st.button("Importar", use_container_width=True):
            try:
                new_eps = parse_postman_collection(json.load(pm_file))
                for n, d in new_eps.items():
                    if n not in st.session_state.project["endpoints"]: st.session_state.project["endpoints"][n] = d
                if new_eps: st.session_state.current_endpoint_name = list(new_eps.keys())[0]; st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("---")
    new_ep = st.text_input("Nuevo Endpoint:")
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

with tab_dtos:
    cl, ca = st.columns([1, 2])
    with cl:
        st.caption("DTOs Cargados")
        to_del = []
        for n in proj["dto_library"]:
            if st.button(f"🗑 {n}", key=f"d_{n}"): to_del.append(n)
        for d in to_del: del proj["dto_library"][d]; st.rerun()
    with ca:
        n_dto = st.text_input("Nombre DTO")
        txt_dto = st.text_area("JSON DTO")
        if st.button("Añadir DTO") and n_dto and txt_dto:
            try:
                proj["dto_library"][n_dto] = json.loads(txt_dto); st.success("OK"); st.rerun()
            except:
                st.error("JSON Inválido")

with tab_map:
    if not curr_ep:
        st.info("👈 Selecciona Endpoint.")
    else:
        st.markdown(f"### ⚡ Operación: `{curr_ep}`")

        # --- SELECCIÓN MÉTODO Y DATOS EXTRA (TABLA PEQUEÑA RESTAURADA) ---
        with st.container(border=True):
            mc1, mc2 = st.columns([1, 3])
            with mc1:
                cur_meth = proj["endpoints"][curr_ep].get("method", "GET")
                opts_meth = ["GET", "POST", "PUT", "DELETE", "PATCH"]
                new_meth = st.selectbox("Método", opts_meth,
                                        index=opts_meth.index(cur_meth) if cur_meth in opts_meth else 0)
                proj["endpoints"][curr_ep]["method"] = new_meth

            with mc2:
                # AQUÍ ESTÁ LA TABLA PEQUEÑA QUE QUERÍAS
                st.caption("📝 Datos Adicionales (Cabecera del Excel)")
                current_extras = proj["endpoints"][curr_ep].get("extra_metadata", {})

                # Convertimos a DataFrame para editar
                if current_extras:
                    list_data = [{"Clave": k, "Valor": v} for k, v in current_extras.items()]
                    df_extras = pd.DataFrame(list_data, columns=["Clave", "Valor"]).astype(str)
                else:
                    df_extras = pd.DataFrame(columns=["Clave", "Valor"]).astype(str)

                # Editor pequeño
                edited_extras = st.data_editor(
                    df_extras,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    height=120,
                    key=f"meta_{curr_ep}",
                    column_config={
                        "Clave": st.column_config.TextColumn("Clave", required=True),
                        "Valor": st.column_config.TextColumn("Valor")
                    }
                )

                # Guardado automático de esta sección en memoria
                new_extras_dict = {}
                for _, row in edited_extras.iterrows():
                    if row.get("Clave") and str(row["Clave"]).strip() and str(row["Clave"]) != "nan":
                        new_extras_dict[row["Clave"]] = row["Valor"]
                proj["endpoints"][curr_ep]["extra_metadata"] = new_extras_dict

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

        # --- IMPORTAR DOCUMENTACIÓN (SCHEMA) ---
        with st.expander("📄 Importar Esquema / Doc (JSON)"):
            st.caption(
                'Formato esperado: `[{"id": "cnpjEmbarcadorOrigem", "doc": "CNPJ del Embarcador", "opcional": 0, "tipo": "String"}, {"id": "listaSolicitacoes.Destinatario.nome", "doc": "Nombre del Destinatario", "opcional": 0, "tipo": "String"}]`')
            schema_txt = st.text_area("JSON Esquema", height=100, key=f"schema_{curr_ep}_{direction}")
            if st.button("Procesar Esquema Doc", use_container_width=True):
                if not schema_txt.strip():
                    st.warning("El campo está vacío.")
                else:
                    try:
                        # Limpieza básica de comillas inteligentes o espacios raros
                        clean_txt = schema_txt.replace("“", '"').replace("”", '"').strip()
                        schema_json = json.loads(clean_txt)
                        if isinstance(schema_json, dict): schema_json = [schema_json]
                        count_imp = 0

                        for item in schema_json:
                            k_id = next((item[k] for k in item if k.lower() in ['id', 'name', 'key', 'campo']), None)
                            if not k_id: continue

                            k_doc = next((item[k] for k in item if k.lower() in ['doc', 'description', 'desc']), "")
                            k_opt = next((item[k] for k in item if k.lower() in ['opcional', 'optional', 'nullable']),
                                         None)
                            k_type = next((item[k] for k in item if k.lower() in ['tipo', 'type']), "String")

                            is_opt = False
                            if k_opt is not None:
                                if str(k_opt).lower() in ["1", "true", "yes"]: is_opt = True

                            req_val = "No" if is_opt else "Sí"
                            clean_t = clean_type_name(k_type, is_nullable=is_opt)

                            if k_id not in prev_meta:
                                prev_meta[k_id] = {
                                    "status_tag": "⚪ Sin Estado", "required": "?",
                                    "comment_tl": "", "comment_analyst": "", "comment_dev": "",
                                    "example_value": "", "type": "String", "is_done": False, "doc_desc": ""
                                }

                            prev_meta[k_id]["doc_desc"] = str(k_doc)
                            prev_meta[k_id]["required"] = req_val
                            prev_meta[k_id]["type"] = clean_t
                            count_imp += 1

                        st.success(f"Procesados {count_imp} campos.");
                        time.sleep(1);
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("JSON Inválido: Revisa comas, comillas o corchetes.")
                    except Exception as e:
                        st.error(f"Error procesando: {e}")

        # --- CARGA DE JSON RAW ---
        st.caption("O importa un Payload Raw (ejemplo real):")
        tx = st.text_area(f"JSON Raw payload", height=70, key=f"tx_{curr_ep}_{direction}")
        if tx and st.button("Analizar Payload"):
            try:
                clean_tx = tx.replace("“", '"').replace("”", '"').strip()
                raw = json.loads(clean_tx)
                if isinstance(raw, list) and raw: raw = raw[0]
                flat = flatten_payload(raw)
                for k, v in flat.items():
                    if k not in prev_meta:
                        prev_meta[k] = {
                            "status_tag": "⚪ Sin Estado", "required": "?",
                            "comment_tl": "", "comment_analyst": "", "comment_dev": "",
                            "example_value": str(v)[:100], "type": infer_smart_type(k, v),
                            "is_done": False, "doc_desc": ""
                        }
                st.rerun()
            except:
                st.error("JSON Inválido en Payload.")

        # --- CONSTRUCCIÓN TABLA ---
        u_opts = ["SELECCIONAR_CAMPO", "IGNORED_FIELD"]
        if proj["dto_library"]:
            for dn, dc in proj["dto_library"].items():
                for k, v in flatten_payload(dc).items(): u_opts.append(f"[{dn}] {k} | {v}")
            u_opts.sort()

        rows = []
        for k in list(prev_meta.keys()):
            tgt = "SELECCIONAR_CAMPO"
            for t, s in prev_map.items():
                if s == k:
                    match = next((o for o in u_opts if t == o.split(" | ")[0]), t)
                    tgt = match;
                    break

            meta = prev_meta.get(k, {})
            rows.append({
                "Estado": meta.get("status_tag", "⚪ Sin Estado"),
                "Campo Courier": k,
                "Target (DTO)": tgt,
                "Ejemplo": meta.get("example_value", ""),
                "Tipo": meta.get("type", "String"),
                "Requerido": meta.get("required", "?"),
                "Doc": meta.get("doc_desc", ""),
                "Coment. Analista": meta.get("comment_analyst", ""),
                "Coment. TL": meta.get("comment_tl", ""),
                "Coment. Dev": meta.get("comment_dev", "")
            })

        st.divider()
        df_table = pd.DataFrame(rows)
        if df_table.empty: df_table = pd.DataFrame(
            columns=["Estado", "Campo Courier", "Target (DTO)", "Ejemplo", "Tipo", "Requerido", "Doc",
                     "Coment. Analista", "Coment. TL", "Coment. Dev"])

        # --- EDITOR ---
        with st.form(key=f"form_map_{curr_ep}_{direction}"):
            edited = st.data_editor(
                df_table,
                key=f"ed_{curr_ep}_{direction}",
                num_rows="dynamic",
                column_config={
                    "Estado": st.column_config.SelectboxColumn("Estado", options=STATUS_OPTS, width="medium",
                                                               required=True),
                    "Campo Courier": st.column_config.TextColumn("Campo Courier", disabled=False),
                    "Target (DTO)": st.column_config.SelectboxColumn("Mapeo 🎯", options=u_opts, required=True,
                                                                     width="large"),
                    "Requerido": st.column_config.SelectboxColumn(options=["Sí", "No", "Cond", "?"], width="small"),
                    "Tipo": st.column_config.TextColumn(width="small"),
                    "Coment. Analista": st.column_config.TextColumn("💬 Analista", width="medium"),
                    "Coment. TL": st.column_config.TextColumn("🟢 TL", width="medium"),
                    "Coment. Dev": st.column_config.TextColumn("👨‍💻 Dev", width="medium"),
                },
                width="stretch", hide_index=True, height=600
            )

            if st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                nm, nmt = {}, {}
                for _, r in edited.iterrows():
                    c_courier = r.get("Campo Courier")
                    if not c_courier or pd.isna(c_courier): continue
                    c_courier = str(c_courier).strip()

                    tgt_val = r["Target (DTO)"]
                    clean_target = tgt_val.split(" | ")[0] if " | " in tgt_val else tgt_val

                    if "SELECCIONAR" not in clean_target and "IGNORED" not in clean_target: nm[clean_target] = c_courier

                    nmt[c_courier] = {
                        "required": r.get("Requerido", "?"),
                        "comment_tl": r.get("Coment. TL", ""),
                        "comment_analyst": r.get("Coment. Analista", ""),
                        "comment_dev": r.get("Coment. Dev", ""),
                        "example_value": r.get("Ejemplo", ""),
                        "type": r.get("Tipo", "String"),
                        "is_done": ("SELECCIONAR" not in clean_target),
                        "status_tag": r["Estado"],
                        "doc_desc": r.get("Doc", "")
                    }

                proj["endpoints"][curr_ep][direction]["mapping_rules"] = nm
                proj["endpoints"][curr_ep][direction]["field_metadata"] = nmt
                st.success("Guardado.");
                time.sleep(0.5);
                st.rerun()

        st.markdown("#### 📤 Exportar")
        # Aseguramos que se usen los extras actuales del estado (ya actualizados arriba)
        extras_to_export = proj["endpoints"][curr_ep].get("extra_metadata", {})
        excel_bytes = generate_excel_pro(df_table, extras_to_export, u_opts)
        st.download_button(label="📥 Descargar Excel", data=excel_bytes, file_name=f"Map_{curr_ep}_{direction}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

st.write("---")
if st.button("💾 Descargar Proyecto JSON"):
    st.download_button("JSON", data=json.dumps(proj, indent=4), file_name="Project.json")