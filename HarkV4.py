import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime, time, timedelta
import hashlib
from contextlib import contextmanager
from io import BytesIO
import os

# ==================== CONFIGURACIÓN ====================
st.set_page_config(
    page_title="HARK - Management System",
    layout="wide",
    page_icon="🦈"
)

# ==================== BASE DE DATOS ====================
@contextmanager
def get_db():
    """Gestor de conexión PostgreSQL - Compatible con local y Render"""
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
    """Crea tablas y datos iniciales solo si no existen (seguro)"""
    with get_db() as conn:
        c = conn.cursor()

        # Tablas
        c.execute('''CREATE TABLE IF NOT EXISTS branches (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            level INTEGER NOT NULL,
            full_name TEXT,
            branch_id INTEGER REFERENCES branches(id)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS vehicles (
            id SERIAL PRIMARY KEY,
            vin_number TEXT,
            tag_number TEXT NOT NULL,
            required_day TEXT NOT NULL,
            required_time TEXT NOT NULL,
            service TEXT NOT NULL,
            responsible_name TEXT,
            notes TEXT,
            status TEXT DEFAULT 'Pending',
            reception_date TEXT NOT NULL,
            delivery_date TEXT,
            handled_by TEXT,
            is_urgent INTEGER DEFAULT 0,
            branch_id INTEGER REFERENCES branches(id)
        )''')

        # Datos iniciales solo si no existen
        c.execute("SELECT COUNT(*) as total FROM branches")
        if c.fetchone()['total'] == 0:
            c.execute("INSERT INTO branches (name) VALUES ('North Agency'), ('South Agency'), ('Central Agency')")

        c.execute("SELECT COUNT(*) as total FROM users")
        if c.fetchone()['total'] == 0:
            users_data = [
                ('SuperSU', hashlib.sha256('Krieger1'.encode()).hexdigest(), 3, 'Administrator', None),
                ('Keri Kidd', hashlib.sha256('Usuario1*'.encode()).hexdigest(), 1, 'Keri Kidd', 1),
                ('Fidel Sizemore', hashlib.sha256('Usuario2*'.encode()).hexdigest(), 1, 'Fidel Sizemore', 2),
                ('Gianni Daly', hashlib.sha256('Usuario4*'.encode()).hexdigest(), 2, 'Gianni Daly', 1)
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
        rec_date = datetime.strptime(reception_str, "%Y-%m-%d %H:%M")
        req_date = datetime.strptime(f"{req_day_str} {req_time_str}", "%Y-%m-%d %H:%M")
        now = datetime.now()

        if service == "Full Detail for line":
            hours = (now - rec_date).total_seconds() / 3600
            if hours < 24: return "#28a745", "✅ On Time", f"{hours:.1f}h since reception"
            elif hours < 48: return "#ffc107", "⚠️ Attention", f"{hours:.1f}h since reception"
            else: return "#dc3545", "🚨 Delayed", f"{hours:.1f}h since reception"
        elif service in ["Full Detail the customer", "Zaktek"]:
            hours = (req_date - now).total_seconds() / 3600
            if hours >= 2: return "#28a745", "✅ Ample Time", f"{hours:.1f}h until deadline"
            elif 1 <= hours < 2: return "#ffc107", "⚠️ Medium Time", f"{hours:.1f}h until deadline"
            elif 0 <= hours < 1: return "#dc3545", "🚨 Critical", f"{hours:.1f}h until deadline"
            else: return "#dc3545", "💀 Critical Delay", f"{hours:.1f}h until deadline"
        elif service in ["Sold use car", "Sold new car"]:
            hours = (req_date - now).total_seconds() / 3600
            if hours >= 1: return "#28a745", "✅ On Time (>1h)", f"{hours:.1f}h until deadline"
            else: return "#dc3545", "🚨 Imminent (<1h)", f"{hours:.1f}h until deadline"
        return "#28a745", "✅ Normal", "-"
    except:
        return "#6c757d", "⚠️ Date Error", "-"


# ==================== PÁGINAS ====================
def login_page():
    st.markdown("<h1 style='text-align:center; color:#1f77b4;'>🦈 HARK Login</h1>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name FROM branches WHERE active=1")
            branches = c.fetchall()
            opts = {b['name']: b['id'] for b in branches}
            branch_sel = st.selectbox("Agency", list(opts.keys()))
        
        if st.form_submit_button("Login", use_container_width=True, type="primary"):
            with get_db() as conn:
                hashed = hashlib.sha256(password.encode()).hexdigest()
                c = conn.cursor()
                c.execute("SELECT id, username, level, full_name FROM users WHERE username=%s AND password=%s", 
                         (username, hashed))
                user = c.fetchone()
                if user:
                    st.session_state.update({
                        "logged_in": True,
                        "user_id": user['id'],
                        "username": user['username'],
                        "level": user['level'],
                        "branch_id": opts.get(branch_sel),
                        "branch_name": branch_sel if user['level'] < 3 else "All (Admin)",
                        "full_name": user['full_name']
                    })
                    st.rerun()
                else:
                    st.error("❌ Credenciales inválidas")


def page_ingress():
    st.markdown("<h2>🚦 Vehicle Ingress</h2>", unsafe_allow_html=True)
    st.info(f"📍 Agency: **{st.session_state.branch_name}** | 👤 {st.session_state.full_name}")
    
    with st.form("ingress_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            vin = st.text_input("VIN Number", key="vin_in")
            tag = st.text_input("TAG Number", key="tag_in")
            responsible_name = st.text_input("Technical/Sales Man (Name)", key="res_name_in")
            service = st.selectbox("Service", SERVICES_LIST)
        
        with col2:
            today = datetime.now().date()
            default_day = today if datetime.now().hour < 20 else today + timedelta(days=1)
            
            req_day = st.date_input("Required Day", value=default_day, min_value=today, key="day_in")
            req_time = st.time_input("Required Time", value=time(9, 0), key="time_in")
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
                    (vin_number, tag_number, required_day, required_time, service, notes, 
                     is_urgent, branch_id, reception_date, status, responsible_name)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    vin.strip().upper() if vin else None,
                    tag.strip().upper(),
                    req_day.strftime("%Y-%m-%d"),
                    req_time.strftime("%H:%M"),
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

    # Búsqueda
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("🔍 Search by VIN or TAG Number", placeholder="Ej: ACURA0005")
    with col2:
        st.button("Search")

    with get_db() as conn:
        where = "AND v.branch_id = %s" if st.session_state.level < 3 else ""
        params = (st.session_state.branch_id,) if st.session_state.level < 3 else ()
        
        c = conn.cursor()
        c.execute(f"""
            SELECT id, tag_number, vin_number, service, reception_date, 
                   required_day, required_time, is_urgent, responsible_name
            FROM vehicles v 
            WHERE v.status = 'Pending' {where}
            ORDER BY v.service, v.is_urgent DESC, v.reception_date ASC
        """, params)
        all_v = c.fetchall()

    if not all_v:
        st.info("📭 No hay vehículos pendientes.")
        return

    by_service = {}
    for v in all_v:
        by_service.setdefault(v['service'], []).append(v)

    for svc, vehs in by_service.items():
        with st.expander(f"**{svc}** — {len(vehs)} vehículo(s)", expanded=True):
            rows = []
            for v in vehs:
                color, msg, info = get_status_info(
                    v['service'], v['reception_date'], v['required_day'], v['required_time']
                )
                rows.append({
                    "TAG": v['tag_number'],
                    "VIN": v['vin_number'] or "-",
                    "Responsible": v['responsible_name'] or "-",
                    "Required Day": v['required_day'],
                    "Required Time": v['required_time'],
                    "Received": v['reception_date'],
                    "Status": msg,
                    "Time": info,
                    "Urgent": "🚨" if v['is_urgent'] else "",
                    "_color": color,
                    "_id": v['id']
                })

            df = pd.DataFrame(rows)

            # Estilo y ocultar columnas internas
            styled_df = df.style.apply(
                lambda row: [f'background-color: #111; color: #eee; border-left: 5px solid {row["_color"]}'] * len(row),
                axis=1
            ).hide(["_color", "_id"], axis=1)

            st.dataframe(styled_df, hide_index=True, use_container_width=True)

            # Botones de entrega
            cols = st.columns(len(vehs))
            for i, v in enumerate(vehs):
                with cols[i]:
                    if st.button(f"✓ {v['tag_number']}", key=f"deliver_{v['id']}"):
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
                        st.success(f"✅ {v['tag_number']} entregado")
                        st.rerun()

def page_reports():
    st.markdown("<h2>📊 Reports & Statistics</h2>", unsafe_allow_html=True)
    st.subheader("🔎 Filtros Avanzados")
    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.selectbox("Período", ["All Time", "Today", "This Week", "This Month"])
    with col2:
        status_filter = st.selectbox("Estado", ["All", "Pending", "Delivered"])
    with col3:
        service_filter = st.selectbox("Servicio", ["All"] + SERVICES_LIST)

    if st.button("🔄 Actualizar Reportes", type="primary"):
        st.rerun()

    with get_db() as conn:
        # Usar cursor normal (no RealDictCursor) para evitar conflictos con pandas
        cursor = conn.cursor()
        
        query = """
            SELECT 
                v.tag_number,
                v.vin_number,
                v.service,
                v.status,
                v.reception_date,
                v.delivery_date,
                v.is_urgent,
                COALESCE(b.name, 'Global/Admin') as agency
            FROM vehicles v
            LEFT JOIN branches b ON v.branch_id = b.id
        """

        conditions = []
        params = []

        if period == "Today":
            conditions.append("v.reception_date::date = CURRENT_DATE")
        elif period == "This Week":
            conditions.append("v.reception_date::date >= DATE_TRUNC('week', CURRENT_DATE)")
        elif period == "This Month":
            conditions.append("DATE_TRUNC('month', v.reception_date::timestamp) = DATE_TRUNC('month', CURRENT_DATE)")

        if status_filter != "All":
            conditions.append("v.status = %s")
            params.append(status_filter)

        if service_filter != "All":
            conditions.append("v.service = %s")
            params.append(service_filter)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY v.reception_date DESC"

        # Ejecutar manualmente y crear DataFrame
        cursor.execute(query, params if params else None)
        rows = cursor.fetchall()
        
        # Crear DataFrame desde cero con los datos reales
        df_all = pd.DataFrame(rows, columns=[
            'tag_number', 'vin_number', 'service', 'status',
            'reception_date', 'delivery_date', 'is_urgent', 'agency'
        ])

    st.write(f"**Filas recuperadas:** {len(df_all)}")

    if df_all.empty:
        st.warning("📭 No se encontraron vehículos.")
        return

    # Crear df_display renombrando columnas
    df_display = df_all.rename(columns={
        'tag_number': 'TAG',
        'vin_number': 'VIN',
        'service': 'Service',
        'status': 'Status',
        'reception_date': 'Received',
        'delivery_date': 'Delivered',
        'is_urgent': 'Urgent',
        'agency': 'Agency'
    })

    df_display['Urgent'] = df_display['Urgent'].map({1: '🚨 Yes', 0: 'No'})

    # KPIs
    total = len(df_display)
    delivered = len(df_display[df_display['Status'] == 'Delivered'])
    pending = len(df_display[df_display['Status'] == 'Pending'])
    urgent = len(df_display[df_display['Urgent'] == '🚨 Yes'])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Vehicles", total)
    k2.metric("Delivered", delivered)
    k3.metric("Pending", pending)
    k4.metric("Urgent", urgent)

    st.divider()
    st.subheader("📋 Detailed List")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # Export Excel
    st.subheader("💾 Export Data")
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_all.to_excel(writer, sheet_name='Vehicles', index=False)
    output.seek(0)
    st.download_button(
        label="📥 Download Excel", 
        data=output, 
        file_name=f"HARK_Report_{datetime.now().strftime('%Y%m%d')}.xlsx", 
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
def page_users():
    st.markdown("<h2>👤 User Management</h2>", unsafe_allow_html=True)
    
    try:
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
                st.subheader("Usuarios Actuales")
                st.dataframe(df, hide_index=True, use_container_width=True)
    except Exception as e:
        st.error(f"❌ Error al cargar usuarios: {e}")

    # (Mantengo el resto de page_users sin cambios por ahora, ya que funciona bien)


# ==================== MAIN ====================
def main():
    init_database()

    if 'logged_in' not in st.session_state:
        login_page()
    else:
        st.sidebar.title("🦈 HARK")
        st.sidebar.write(f"👤 {st.session_state.full_name}")
        st.sidebar.write(f"📍 {st.session_state.branch_name}")
        
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

        # Menú según nivel
        if st.session_state.level >= 2:
            menu_options = ["🚦 Ingress", "🏎️ Pending", "📊 Reports"]
        else:
            menu_options = ["🚦 Ingress", "🏎️ Pending"]

        if st.session_state.level == 3:
            menu_options.append("👤 Users")

        menu = st.sidebar.radio("Menú", menu_options)

        if menu == "🚦 Ingress": page_ingress()
        elif menu == "🏎️ Pending": page_pending()
        elif menu == "📊 Reports": page_reports()
        elif menu == "👤 Users": page_users()


if __name__ == "__main__":
    main()
