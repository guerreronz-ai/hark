import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import hashlib
from contextlib import contextmanager
from io import BytesIO
import os


# ==================== CONFIGURACIÓN VISUAL PROFESIONAL ====================
st.set_page_config(
    page_title="HARK - Management System",
    layout="wide",
    page_icon="🦈",
    initial_sidebar_state="expanded"
)

# ==================== CSS Profesional - MODO CLARO ====================
st.markdown("""
    <style>
    /* Fondo general suave */
    .stApp {
        background-color: #f4f6f9 !important;
    }
    
    /* Títulos oscuros para contraste */
    h1, h2, h3 {
        color: #1e293b !important;
        font-weight: 700;
    }
    
    /* Sidebar blanca y limpia */
    .sidebar .sidebar-content {
        background-color: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
    }
    
    /* Botones modernos azules */
    .stButton>button {
        background: linear-gradient(90deg, #2563eb, #1d4ed8) !important;
        color: white !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        border: none !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #1d4ed8, #1e40af) !important;
    }
    
    /* Expanders (Cajas desplegables) */
    .stExpander {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    /* Inputs y Selects */
    .stTextInput input, 
    .stSelectbox select, 
    .stTextArea textarea {
        background-color: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        color: #0f172a !important;
        border-radius: 6px !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==================== BASE DE DATOS ====================
@contextmanager
def get_db():
    conn = None
    try:
        if os.getenv("DB_HOST"):
            cfg = {
                "HOST": os.getenv("DB_HOST"),
                "NAME": os.getenv("DB_NAME"),
                "USER": os.getenv("DB_USER"),
                "PASSWORD": os.getenv("DB_PASSWORD"),
                "PORT": int(os.getenv("DB_PORT", 5432)),
            }
        elif "DB" in st.secrets:
            cfg = st.secrets["DB"]
        else:
            st.error("❌ No se encontraron credenciales de base de datos.")
            st.stop()

        if not all([cfg.get(k) for k in ["HOST", "NAME", "USER", "PASSWORD"]]):
            st.error("❌ Faltan credenciales de la base de datos.")
            st.stop()

        conn = psycopg2.connect(
            host=cfg["HOST"],
            dbname=cfg["NAME"],
            user=cfg["USER"],
            password=cfg["PASSWORD"],
            port=cfg.get("PORT", 5432),
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        conn.autocommit = False

        # ✅ CONFIGURAR ZONA HORARIA (DALLAS, TX)
        with conn.cursor() as temp_cursor:
            temp_cursor.execute("SET TIME ZONE 'America/Chicago'")

        yield conn
        conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"⚠️ Database Error: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()
            
def init_database():
    with get_db() as conn:
        c = conn.cursor()
        
        # 1. Crear tablas si no existen
        c.execute('''CREATE TABLE IF NOT EXISTS branches (
            id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, active INTEGER DEFAULT 1
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            level INTEGER NOT NULL, full_name TEXT, branch_id INTEGER REFERENCES branches(id)
        )''')
        
        # NUEVA: Tabla de preferencias de usuario
        c.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
            id SERIAL PRIMARY KEY, 
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            preference_key TEXT NOT NULL,
            preference_value TEXT,
            UNIQUE(user_id, preference_key)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS vehicles (
            id SERIAL PRIMARY KEY, vin_number TEXT, tag_number TEXT NOT NULL,
            marca TEXT, modelo TEXT, required_day TEXT, required_time TEXT,
            service TEXT NOT NULL, responsible_name TEXT, notes TEXT, status TEXT DEFAULT 'Pending',
            reception_date TEXT NOT NULL, delivery_date TEXT, handled_by TEXT,
            is_urgent INTEGER DEFAULT 0, branch_id INTEGER REFERENCES branches(id)
        )''')

        # 2. Insertar Agencias por defecto si no existen
        c.execute("SELECT COUNT(*) as total FROM branches")
        if c.fetchone()['total'] == 0:
            c.execute("INSERT INTO branches (name) VALUES ('North Agency'), ('South Agency'), ('Central Agency')")

        # 3. Insertar Usuarios por defecto si no existen
        c.execute("SELECT COUNT(*) as total FROM users")
        if c.fetchone()['total'] == 0:
            c.execute("SELECT id, name FROM branches")
            branches_map = {row['name']: row['id'] for row in c.fetchall()}
            
            north_id = branches_map.get('North Agency')
            central_id = branches_map.get('Central Agency')
            south_id = branches_map.get('South Agency')

            users_data = [
                ('SuperSU', hashlib.sha256('Krieger1'.encode()).hexdigest(), 3, 'Administrator', None),
                ('User1', hashlib.sha256('User123'.encode()).hexdigest(), 1, 'Agent North', north_id),
                ('User2', hashlib.sha256('User123'.encode()).hexdigest(), 1, 'Agent Central', central_id),
                ('User3', hashlib.sha256('User123'.encode()).hexdigest(), 1, 'Agent South', south_id),
                ('Super1', hashlib.sha256('Super123'.encode()).hexdigest(), 2, 'Supervisor North', north_id),
                ('Super2', hashlib.sha256('Super123'.encode()).hexdigest(), 2, 'Supervisor Central', central_id),
                ('Super3', hashlib.sha256('Super123'.encode()).hexdigest(), 2, 'Supervisor South', south_id),
            ]
            
            c.executemany("""
                INSERT INTO users (username, password, level, full_name, branch_id) 
                VALUES (%s, %s, %s, %s, %s)
            """, users_data)
        
        conn.commit()

# ==================== CONSTANTES ====================
SERVICES_LIST = [
    "Service Wash", "Loaner", "Photo", "Full Detail the customer",
    "Zaktek", "Show Room", "Full Detail for line", "Sold use car", "Sold new car"
]

def get_status_info(service, reception_str, req_day_str, req_time_str):
    try:
        service_clean = service.strip()
        dallas_tz = ZoneInfo("America/Chicago")
        now_dallas = datetime.now(dallas_tz)

        rec_date = datetime.strptime(reception_str, "%Y-%m-%d %H:%M").replace(tzinfo=dallas_tz)
        req_date = datetime.strptime(f"{req_day_str} {req_time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=dallas_tz)

        hours_since_reception = (now_dallas - rec_date).total_seconds() / 3600
        hours_until_deadline = (req_date - now_dallas).total_seconds() / 3600

        # === FULL DETAIL FOR LINE ===
        if service_clean == "Full Detail for line":
            if hours_since_reception < 24:
                return "#28a745", "✅ On Time", f"{hours_since_reception:.1f}h since reception"
            elif hours_since_reception < 48:
                return "#ffc107", "⚠️ Attention", f"{hours_since_reception:.1f}h since reception"
            else:
                return "#dc3545", "🚨 Delayed", f"{hours_since_reception:.1f}h since reception"

        # === FULL DETAIL THE CUSTOMER, ZAKTEK, SOLD NEW CAR, SOLD USE CAR ===
        elif service_clean in ["Full Detail the customer", "Zaktek", "Sold new car", "Sold use car"]:
            if hours_until_deadline > 2.0:
                return "#28a745", "✅ Ample Time", f"{hours_until_deadline:.1f}h until deadline"
            elif hours_until_deadline > 1.0:
                return "#ffc107", "⚠️ Medium Time", f"{hours_until_deadline:.1f}h until deadline"
            else:
                return "#dc3545", "🚨 Critical", f"{hours_until_deadline:.1f}h until deadline"

        # Servicios restantes (Service Wash, Loaner, Photo, Show Room) - mantengo lógica anterior o la ajustas si quieres
        else:
            if hours_since_reception < 24:
                return "#28a745", "✅ On Time", f"{hours_since_reception:.1f}h since reception"
            elif hours_since_reception < 48:
                return "#ffc107", "⚠️ Attention", f"{hours_since_reception:.1f}h since reception"
            else:
                return "#dc3545", "🚨 Delayed", f"{hours_since_reception:.1f}h since reception"

    except Exception:
        return "#6c757d", "⚠️ Error", "-"

def get_user_preference(user_id, key, default=None):
    """Obtener preferencia del usuario desde la BD"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT preference_value FROM user_preferences 
            WHERE user_id = %s AND preference_key = %s
        """, (user_id, key))
        result = c.fetchone()
        return result['preference_value'] if result else default

def save_user_preference(user_id, key, value):
    """Guardar preferencia del usuario en la BD"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_preferences (user_id, preference_key, preference_value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, preference_key) 
            DO UPDATE SET preference_value = EXCLUDED.preference_value
        """, (user_id, key, value))
        conn.commit()
        
# ==================== PÁGINAS ====================
def login_page():
    st.markdown("<h1 style='text-align:center; color:#00d4ff;'>🦈 HARK Login</h1>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.form_submit_button("Login", use_container_width=True, type="primary"):
            with get_db() as conn:
                hashed = hashlib.sha256(password.encode()).hexdigest()
                c = conn.cursor()
                
                c.execute("""
                    SELECT u.id, u.username, u.level, u.full_name, u.branch_id,
                           COALESCE(b.name, 'Global/Admin') as branch_name
                    FROM users u
                    LEFT JOIN branches b ON u.branch_id = b.id
                    WHERE u.username = %s AND u.password = %s
                """, (username, hashed))
                
                user = c.fetchone()
                
                if user:
                    st.session_state.update({
                        "logged_in": True,
                        "user_id": user['id'],
                        "username": user['username'],
                        "level": user['level'],
                        "branch_id": user['branch_id'],
                        "branch_name": user['branch_name'],
                        "full_name": user['full_name']
                    })
                    st.success(f"✅ Bienvenido, {user['full_name']}")
                    st.rerun()
                else:
                    st.error("❌ Credenciales inválidas")

def page_ingress():
    st.markdown("<h2>🚦 Vehicle Ingress</h2>", unsafe_allow_html=True)
    st.info(f"📍 Agency: **{st.session_state.branch_name}** | 👤 {st.session_state.full_name}")

    with st.form("ingress_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            vin = st.text_input("VIN Number", key="vin_in")
            tag = st.text_input("TAG Number", key="tag_in")
            marca = st.text_input("Marca (Brand)", key="marca_in", placeholder="Ej: Acura")
        
        with col2:
            modelo = st.text_input("Modelo (Model)", key="modelo_in", placeholder="Ej: MDX")
            responsible_name = st.text_input("Technical/Sales Man (Name)", key="res_name_in")
            service = st.selectbox("Service", SERVICES_LIST)
        
        with col3:
            today = datetime.now().date()
            default_day = today if datetime.now().hour < 20 else today + timedelta(days=1)
            
            # Solo mostrar Required Day/Time si NO es "Full Detail for line"
            if service != "Full Detail for line":
                req_day = st.date_input("Required Day", value=default_day, min_value=today, key="day_in")
                req_time = st.time_input("Required Time", value=time(9, 0), key="time_in")
            else:
                req_day = None
                req_time = time(9, 0)  # Valor por defecto
                st.info("ℹ️ Full Detail for Line no requiere fecha/hora específica")
            
            notes = st.text_area("Notes", placeholder="Observations...", key="notes_in")
        
        urgent = st.checkbox("🚨 Mark as URGENT (Maximum Priority)")
        
        if st.form_submit_button("💾 Save Vehicle", use_container_width=True, type="primary"):
            if not tag.strip():
                st.error("❌ TAG Number is required")
                st.stop()
            
            with get_db() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT id FROM vehicles 
                    WHERE tag_number=%s AND service=%s AND branch_id=%s AND status='Pending'
                """, (tag.strip().upper(), service, st.session_state.branch_id))
                
                if c.fetchone():
                    st.error(f"❌ {tag.upper()} ya está en la cola para {service}")
                    st.stop()
                
                c.execute("""
                    INSERT INTO vehicles 
                    (vin_number, tag_number, marca, modelo, required_day, required_time, service, notes,
                     is_urgent, branch_id, reception_date, status, responsible_name)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    vin.strip().upper() if vin else None,
                    tag.strip().upper(),
                    marca.strip() if marca else None,
                    modelo.strip() if modelo else None,
                    req_day.strftime("%Y-%m-%d") if req_day else None,
                    req_time.strftime("%H:%M") if service != "Full Detail for line" else None,
                    service,
                    notes.strip(),
                    1 if urgent else 0,
                    st.session_state.branch_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    'Pending',
                    responsible_name.strip()
                ))
            
            st.success(f"✅ {tag.upper()} registrado correctamente")
            st.rerun()
            
def page_pending():
    st.markdown("<h2>🏎️ Pending Vehicles</h2>", unsafe_allow_html=True)
    
    # Mensaje superior según el nivel del usuario
    if st.session_state.level < 3:
        st.info(f"📍 Agency: **{st.session_state.branch_name}** | 👤 {st.session_state.full_name}")
    else:
        st.info(f"👑 Administrator Mode - Viendo todas las agencias | 👤 {st.session_state.full_name}")

    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("🔍 Search by VIN or TAG Number", placeholder="Ej: ACURA0005", key="search_pending")
    with col2:
        search_clicked = st.button("🔍 Search")

    # ====================== CONSULTA A LA BASE DE DATOS ======================
    with get_db() as conn:
        c = conn.cursor()
        
        if st.session_state.level < 3:   # Nivel 1 y 2 → Solo su agencia
            base_query = """
                SELECT v.id, v.tag_number, v.vin_number, v.marca, v.modelo, b.name as agency_name,
                       v.service, v.reception_date, v.required_day, v.required_time, 
                       v.is_urgent, v.responsible_name
                FROM vehicles v 
                LEFT JOIN branches b ON v.branch_id = b.id
                WHERE v.status = 'Pending' 
                  AND v.branch_id = %s
            """
            # Agregar filtro de búsqueda si existe
            if search_term:
                base_query += " AND (v.vin_number ILIKE %s OR v.tag_number ILIKE %s)"
                params = (st.session_state.branch_id, f"%{search_term}%", f"%{search_term}%")
            else:
                params = (st.session_state.branch_id,)
            
            base_query += " ORDER BY v.service, v.is_urgent DESC, v.reception_date ASC"
        else:                            # Nivel 3 (Admin) → Todas las agencias
            base_query = """
                SELECT v.id, v.tag_number, v.vin_number, v.marca, v.modelo, b.name as agency_name,
                       v.service, v.reception_date, v.required_day, v.required_time, 
                       v.is_urgent, v.responsible_name
                FROM vehicles v
                LEFT JOIN branches b ON v.branch_id = b.id
                WHERE v.status = 'Pending'
            """
            # Agregar filtro de búsqueda si existe
            if search_term:
                base_query += " AND (v.vin_number ILIKE %s OR v.tag_number ILIKE %s)"
                params = (f"%{search_term}%", f"%{search_term}%")
            else:
                params = ()
            
            base_query += " ORDER BY b.name, v.service, v.is_urgent DESC, v.reception_date ASC"

        c.execute(base_query, params)
        all_v = c.fetchall()

    if not all_v:
        if search_term:
            st.warning(f"📭 No se encontraron vehículos pendientes que coincidan con '{search_term}'")
        else:
            st.info("📭 No hay vehículos pendientes.")
        return

    # ====================== AGRUPACIÓN POR SERVICIO ======================
    by_service = {}
    for v in all_v:
        by_service.setdefault(v['service'], []).append(v)

    # ====================== MOSTRAR POR SERVICIO ======================
    for svc, vehs in by_service.items():
        with st.expander(f"**{svc}** — {len(vehs)} vehículo(s)", expanded=True):
            rows = []
            for v in vehs:
                # Aplicamos las nuevas reglas de colores y mensajes
                color, msg, info = get_status_info(
                    v['service'], 
                    v['reception_date'], 
                    v['required_day'], 
                    v['required_time']
                )
                
                rows.append({
                    "TAG": v['tag_number'],
                    "VIN": v['vin_number'] or "-",
                    "Marca": v.get('marca') or "-",
                    "Modelo": v.get('modelo') or "-",
                    "Agency": v.get('agency_name') or "-",
                    "Responsible": v['responsible_name'] or "-",
                    "Required Day": v['required_day'],
                    "Required Time": v['required_time'],
                    "Received": v['reception_date'],
                    "Status": msg,
                    "Time": info,
                    "Urgent": "🚨" if v['is_urgent'] else " ",
                    "_color": color,
                    "_id": v['id']
                })

            df = pd.DataFrame(rows)
            
            # Estilo visual: barra de color a la izquierda según estado
            def highlight_status(row):
                return [f'background-color: #ffffff; color: #333333; border-left: 5px solid {row["_color"]}'] * len(row)

            styled_df = df.style.apply(highlight_status, axis=1).hide(["_color", "_id"], axis=1)

            st.dataframe(styled_df, hide_index=True, use_container_width=True)

            # ====================== BOTONES DE ENTREGA ======================
            cols = st.columns(len(vehs))
            for i, v in enumerate(vehs):
                with cols[i]:
                    label = f"✓ {v['tag_number']}"
                    if v.get('marca'):
                        label += f" ({v.get('marca')} {v.get('modelo') or ''})"
                    
                    if st.button(label, key=f"deliver_{v['id']}"):
                        with get_db() as conn2:
                            c2 = conn2.cursor()
                            c2.execute("""
                                UPDATE vehicles 
                                SET status = 'Delivered', 
                                    delivery_date = %s, 
                                    handled_by = %s 
                                WHERE id = %s
                            """, (datetime.now().strftime("%Y-%m-%d %H:%M"), 
                                  st.session_state.username, v['id']))
                        st.success(f"✅ {v['tag_number']} entregado correctamente")
                        st.rerun()
def page_reports():
    # 🔒 Restricción de acceso - Solo niveles 2 y 3
    if st.session_state.level < 2:
        st.error("🚫 No tienes permisos para acceder a los Reportes.")
        st.info("Esta sección está disponible solo para Supervisores y Administradores.")
        st.stop()

    st.markdown("<h2>📊 Reports & Statistics</h2>", unsafe_allow_html=True)
    st.subheader("🔎 Filtros Avanzados")

    # Obtener lista de agencias para el filtro (solo visible para Admin)
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name FROM branches WHERE active=1 ORDER BY name")
        branches = c.fetchall()

    branch_opts = {"🌐 All Agencies": None}
    for b in branches:
        branch_opts[b['name']] = b['id']

    # Layout de filtros (4 columnas)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        period = st.selectbox("Período", ["All Time", "Today", "This Week", "This Month"])
    with col2:
        status_filter = st.selectbox("Estado", ["All", "Pending", "Delivered"])
    with col3:
        service_filter = st.selectbox("Servicio", ["All"] + SERVICES_LIST)
    with col4:
        # Solo el Admin puede filtrar por agencia
        if st.session_state.level == 3:
            selected_agency = st.selectbox("🏢 Agency", list(branch_opts.keys()))
            branch_id_filter = branch_opts[selected_agency]
        else:
            # Nivel 2 solo ve su propia agencia
            branch_id_filter = st.session_state.branch_id

    if st.button("🔄 Actualizar Reportes", type="primary"):
        st.rerun()

    # ====================== CONSULTA A LA BASE DE DATOS ======================
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                v.tag_number, v.vin_number, v.marca, v.modelo, v.service,
                v.status, v.reception_date, v.delivery_date, v.is_urgent,
                COALESCE(b.name, 'Global/Admin') as agency
            FROM vehicles v
            LEFT JOIN branches b ON v.branch_id = b.id
        """
        conditions = []
        params = []

        # Filtro de agencia
        if branch_id_filter is not None:
            conditions.append("v.branch_id = %s")
            params.append(branch_id_filter)

        # Filtros de tiempo
        if period == "Today":
            conditions.append("v.reception_date::date = CURRENT_DATE")
        elif period == "This Week":
            conditions.append("v.reception_date::timestamp >= DATE_TRUNC('week', CURRENT_DATE)")
        elif period == "This Month":
            conditions.append("DATE_TRUNC('month', v.reception_date::timestamp) = DATE_TRUNC('month', CURRENT_DATE)")

        # Filtros de estado y servicio
        if status_filter != "All":
            conditions.append("v.status = %s")
            params.append(status_filter)
        if service_filter != "All":
            conditions.append("v.service = %s")
            params.append(service_filter)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY v.reception_date DESC"

        cursor.execute(query, params if params else None)
        rows = cursor.fetchall()

        df_all = pd.DataFrame(rows, columns=[
            'tag_number', 'vin_number', 'marca', 'modelo', 'service',
            'status', 'reception_date', 'delivery_date', 'is_urgent', 'agency'
        ])

    if df_all.empty:
        st.warning("📭 No se encontraron vehículos con los filtros aplicados.")
        return

    # ====================== PREPARACIÓN DEL DATAFRAME PARA MOSTRAR ======================
    df_display = df_all.copy()
    df_display = df_display.rename(columns={
        'tag_number': 'TAG',
        'vin_number': 'VIN',
        'marca': 'Brand',
        'modelo': 'Model',
        'service': 'Service',
        'status': 'Status',
        'reception_date': 'Received',
        'delivery_date': 'Delivered',
        'is_urgent': 'Urgent',
        'agency': 'Agency'
    })

    df_display['Urgent'] = df_display['Urgent'].map({1: '🚨 Yes', 0: 'No'})

    # Métricas
    total = len(df_display)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Vehicles", total)
    k2.metric("Delivered", len(df_display[df_display['Status'] == 'Delivered']))
    k3.metric("Pending", len(df_display[df_display['Status'] == 'Pending']))
    k4.metric("Urgent", len(df_display[df_display['Urgent'] == '🚨 Yes']))

    st.divider()
    st.subheader("📋 Detailed List")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ====================== EXPORTAR A EXCEL ======================
    st.subheader("💾 Export Data")
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_all.to_excel(writer, sheet_name='Vehicles', index=False)
    output.seek(0)
    st.download_button(
        label="📥 Download Excel",
        data=output,
        file_name=f"HARK_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # ==========================================
    # 🔁 NUEVA FUNCIÓN: REVERTIR ENTREGAS (Solo Nivel >= 2)
    # ==========================================
    if st.session_state.level >= 2:
        st.divider()
        st.subheader("↩️ Revertir Entregas (Corrección de Errores)")
        st.caption("⚠️ Esta acción regresará el vehículo a 'Pending' y limpiará la fecha de entrega.")

        # Consulta específica para vehículos entregados
        rev_query = """
            SELECT v.id, v.tag_number, v.vin_number, v.marca, v.modelo, v.service, 
                   v.delivery_date, v.handled_by, b.name as agency
            FROM vehicles v
            LEFT JOIN branches b ON v.branch_id = b.id
            WHERE v.status = 'Delivered'
        """
        rev_conditions = []
        rev_params = []

        # Si es supervisor, solo muestra entregas de su sucursal
        if st.session_state.level == 2:
            rev_conditions.append("v.branch_id = %s")
            rev_params.append(st.session_state.branch_id)

        if rev_conditions:
            rev_query += " WHERE " + " AND ".join(rev_conditions)
        
        # Limitamos a las últimas 100 entregas para optimizar rendimiento
        rev_query += " ORDER BY v.delivery_date DESC LIMIT 100"

        with get_db() as conn:
            c = conn.cursor()
            c.execute(rev_query, rev_params)
            delivered_list = c.fetchall()

        if delivered_list:
            rev_df = pd.DataFrame(delivered_list)
            display_df = rev_df[['tag_number', 'marca', 'modelo', 'service', 'agency', 'handled_by', 'delivery_date']]
            st.dataframe(display_df, hide_index=True, use_container_width=True)

            # Selector seguro para revertir
            vehicle_options = {
                f"{v['tag_number']} | {v['marca']} {v['modelo']} (Entregado: {v['delivery_date']})": v['id'] 
                for v in delivered_list
            }
            selected_vehicle = st.selectbox("📍 Selecciona el vehículo a revertir:", list(vehicle_options.keys()), index=None)
            
            confirm_revert = st.checkbox("✅ Confirmo que deseo revertir esta entrega a Pendiente")

            if st.button("🔄 Revertir Vehículo", type="secondary", disabled=not (selected_vehicle and confirm_revert)):
                vid = vehicle_options[selected_vehicle]
                with get_db() as conn2:
                    c2 = conn2.cursor()
                    # Regresa a Pending y limpia datos de entrega
                    c2.execute("""
                        UPDATE vehicles 
                        SET status = 'Pending', 
                            delivery_date = NULL, 
                            handled_by = NULL 
                        WHERE id = %s AND status = 'Delivered'
                    """, (vid,))
                st.success(f"✅ Vehículo revertido correctamente a estado 'Pending'.")
                st.rerun()
        else:
            st.info("📭 No hay vehículos entregados recientemente para revertir.")
    
def page_users():
    st.markdown("<h2>👤 User Management</h2>", unsafe_allow_html=True)

    if st.session_state.level != 3:
        st.warning("🔒 Acceso denegado. Solo los Administradores pueden gestionar usuarios.")
        return

    # === FORMULARIO PARA CREAR USUARIO ===
    with st.expander("➕ Agregar Nuevo Usuario", expanded=False):
        with st.form("create_user_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                new_username = st.text_input("Username", placeholder="ej: john.doe")
                new_pass = st.text_input("Password", type="password")
            with col2:
                new_fullname = st.text_input("Full Name", placeholder="John Doe")
                new_level = st.selectbox("Access Level", [1, 2, 3], format_func=lambda x: {1: "👤 Agent", 2: "🛡️ Supervisor", 3: "👑 Admin"}[x])
            with col3:
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute("SELECT id, name FROM branches WHERE active=1 ORDER BY name")
                    branches = c.fetchall()
                    branch_opts = {b['name']: b['id'] for b in branches}
                selected_branch = st.selectbox("Assign Agency", list(branch_opts.keys()))

            if st.form_submit_button("💾 Crear Usuario", use_container_width=True, type="primary"):
                if not new_username or not new_pass or not new_fullname:
                    st.error("❌ Todos los campos son obligatorios.")
                else:
                    hashed = hashlib.sha256(new_pass.encode()).hexdigest()
                    branch_id = branch_opts[selected_branch]
                    try:
                        with get_db() as conn:
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO users (username, password, level, full_name, branch_id)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (new_username.strip(), hashed, new_level, new_fullname.strip(), branch_id))
                        st.success(f"✅ Usuario '{new_username}' creado exitosamente en **{selected_branch}**.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error al crear usuario: {e}")

    st.divider()
    st.subheader("📋 Usuarios Registrados")

    # === LISTADO DE USUARIOS ===
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.id, u.username, u.level, u.full_name,
                   COALESCE(b.name, 'Global/Admin') as branch_name
            FROM users u
            LEFT JOIN branches b ON u.branch_id = b.id
            ORDER BY u.level DESC, u.username
        """)
        users_data = c.fetchall()

    if users_data:
        df = pd.DataFrame(users_data, columns=['id', 'username', 'level', 'full_name', 'branch_name'])
        df['level'] = df['level'].map({1: '👤 Agent', 2: '🛡️ Supervisor', 3: '👑 Admin'})
        st.dataframe(df, hide_index=True, use_container_width=True)

        st.divider()
        st.subheader("🔧 Gestión de Usuarios")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # === RESETEAR CONTRASEÑA ===
            st.markdown("### 🔑 Restablecer Contraseña")
            user_list = {f"{u['username']} ({u['full_name']})": u['id'] for u in users_data}
            selected_user = st.selectbox("Seleccionar Usuario", list(user_list.keys()))
            new_password = st.text_input("Nueva Contraseña", type="password", key="reset_pass")
            
            if st.button("🔄 Actualizar Contraseña", use_container_width=True):
                if new_password:
                    hashed = hashlib.sha256(new_password.encode()).hexdigest()
                    user_id = user_list[selected_user]
                    with get_db() as conn:
                        c = conn.cursor()
                        c.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user_id))
                    st.success(f"✅ Contraseña actualizada para {selected_user}")
                    st.rerun()
                else:
                    st.error("❌ Ingresa una contraseña")
        
        with col2:
            # === ELIMINAR USUARIO ===
            st.markdown("### 🗑️ Eliminar Usuario")
            delete_list = {f"{u['username']} - {u['full_name']} (Nivel {u['level']})": u['id'] for u in users_data if u['id'] != st.session_state.user_id}
            
            if delete_list:
                selected_delete = st.selectbox("Seleccionar Usuario a Eliminar", list(delete_list.keys()))
                confirm_delete = st.checkbox("Confirmar eliminación", key="confirm_del")
                
                if st.button("🗑️ Eliminar Usuario", use_container_width=True, disabled=not confirm_delete):
                    user_id = delete_list[selected_delete]
                    with get_db() as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM users WHERE id = %s", (user_id,))
                    st.success(f"✅ Usuario {selected_delete} eliminado")
                    st.rerun()
            else:
                st.info("ℹ️ No hay otros usuarios para eliminar")
    else:
        st.info("📭 No hay usuarios registrados.")


# ==================== MAIN ====================
def main():
    init_database()

    if 'logged_in' not in st.session_state:
        login_page()
    else:
        # Sidebar profesional
        st.sidebar.markdown(f"""
        <div style='text-align:center; padding: 20px 0;'>
            <h1 style='color:#00d4ff; margin:0; font-size:2.4em;'>🦈 HARK</h1>
            <p style='color:#94a3b8; margin:10px 0 0 0;'>
                {st.session_state.full_name}<br>
                <small style='color:#64748b;'>{st.session_state.branch_name}</small>
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

               # Menú según nivel de usuario
        menu_options = ["🚦 Ingress", "🏎️ Pending"]

        if st.session_state.level >= 2:          # Nivel 2 y 3 ven Reports
            menu_options.append("📊 Reports")

        if st.session_state.level == 3:
            menu_options.append("👤 Users")
            
        menu = st.sidebar.radio("Menú", menu_options)

        if menu == "🚦 Ingress": page_ingress()
        elif menu == "🏎️ Pending": page_pending()
        elif menu == "📊 Reports": page_reports()
        elif menu == "👤 Users": page_users()


if __name__ == "__main__":
    main()
