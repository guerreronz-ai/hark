import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime, timedelta
from datetime import time as dt_time
import time
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

# ==================== LOGO HARK ====================
st.logo(
    "hark_logo.png",
    size="large"
)

# ==================== CSS Profesional ====================
st.markdown("""
<style>
.stApp { background-color: #f4f6f9 !important; }
#MainMenu { visibility: hidden !important; }
footer { visibility: hidden !important; }
[data-testid="stSidebar"] { background-color: #ffffff !important; }
h1, h2, h3 { color: #1e293b !important; font-weight: 700; }
.sidebar .sidebar-content { background-color: #ffffff !important; border-right: 1px solid #e2e8f0 !important; }
.stButton>button { background: linear-gradient(90deg, #2563eb, #1d4ed8) !important; color: white !important; border-radius: 6px !important; font-weight: 600 !important; border: none !important; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.stButton>button:hover { background: linear-gradient(90deg, #1d4ed8, #1e40af) !important; }
.stExpander { background-color: #ffffff !important; border: 1px solid #e2e8f0 !important; border-radius: 10px !important; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
.stTextInput input, .stSelectbox select, .stTextArea textarea { background-color: #f8fafc !important; border: 1px solid #cbd5e1 !important; color: #0f172a !important; border-radius: 6px !important; }
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
            st.error("❌ No database credentials were found.")
            st.stop()

        if not all([cfg.get(k) for k in ["HOST", "NAME", "USER", "PASSWORD"]]):
            st.error("❌ Database credentials are missing.")
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
        c.execute('''CREATE TABLE IF NOT EXISTS branches (
            id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            level INTEGER NOT NULL, full_name TEXT, branch_id INTEGER REFERENCES branches(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
            id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            preference_key TEXT NOT NULL, preference_value TEXT,
            UNIQUE(user_id, preference_key)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS vehicles (
            id SERIAL PRIMARY KEY, vin_number TEXT, tag_number TEXT,
            brand TEXT, model TEXT, required_day TEXT, required_time TEXT,
            service TEXT NOT NULL, responsible_name TEXT, notes TEXT, status TEXT DEFAULT 'Pending',
            reception_date TEXT NOT NULL, delivery_date TEXT, handled_by TEXT,
            is_urgent INTEGER DEFAULT 0, branch_id INTEGER REFERENCES branches(id)
        )''')

        try:
            c.execute("ALTER TABLE vehicles ALTER COLUMN tag_number DROP NOT NULL")
            c.execute("ALTER TABLE vehicles ALTER COLUMN required_day DROP NOT NULL")
            c.execute("ALTER TABLE vehicles ALTER COLUMN required_time DROP NOT NULL")
            c.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS brand TEXT")
            c.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS model TEXT")
            c.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS responsible_name TEXT")
            c.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS who_done TEXT")
        except Exception:
            pass

        c.execute("SELECT COUNT(*) as total FROM branches")
        if c.fetchone()['total'] == 0:
            c.execute("INSERT INTO branches (name) VALUES ('BMW Arlington'), ('Five Star Subaru'), ('Vandergriff Acura')")

        c.execute("SELECT COUNT(*) as total FROM users")
        if c.fetchone()['total'] == 0:
            c.execute("SELECT id, name FROM branches")
            branches = c.fetchall()
            branches_map = {row['name']: row['id'] for row in branches}
            bmw_id = branches_map.get('BMW Arlington')
            acura_id = branches_map.get('Vandergriff Acura')
            subaru_id = branches_map.get('Five Star Subaru')

            users_data = [
                ('SuperSU', hashlib.sha256('Krieger1'.encode()).hexdigest(), 3, 'Administrator', None),
                ('Admin', hashlib.sha256('Admin123*'.encode()).hexdigest(), 3, 'Administrator', None),
                ('User1', hashlib.sha256('User123'.encode()).hexdigest(), 1, 'Agent bmw', bmw_id),
                ('User2', hashlib.sha256('User123'.encode()).hexdigest(), 1, 'Agent Central', acura_id),
                ('User3', hashlib.sha256('User123'.encode()).hexdigest(), 1, 'Agent South', subaru_id),
                ('Super1', hashlib.sha256('Super123'.encode()).hexdigest(), 2, 'Supervisor bmw', bmw_id),
                ('Super2', hashlib.sha256('Super123'.encode()).hexdigest(), 2, 'Supervisor Central', acura_id),
                ('Super3', hashlib.sha256('Super123'.encode()).hexdigest(), 2, 'Supervisor South', subaru_id),
            ]
            c.executemany(
                "INSERT INTO users (username, password, level, full_name, branch_id) VALUES (%s, %s, %s, %s, %s)", 
                users_data
            )
        conn.commit()

# ==================== CONSTANTES ====================

TIME_12H_OPTIONS = []
for h in range(24):
    for m in [0, 15, 30, 45]:
        # Generamos la hora en formato AM/PM (09:00 AM, 01:00 PM, etc.)
        dt_obj = datetime(2026, 5, 2, h, m) 
        TIME_12H_OPTIONS.append(dt_obj.strftime("%I:%M %p"))

SERVICES_LIST = [
    "Service Wash", "Loaner", "Photo", "Full Detail the customer",
    "Zaktek", "Show Room", "Full Detail for line", "Sold Detail", "Sold use car", "Sold new car"
]
SERVICE_FIELD_REQUIREMENTS = {
    "Service Wash": "tag",
    "Loaner": "tag",
    "Photo": "vin",
    "Full Detail the customer": "tag",
    "Zaktek": "tag",
    "Show Room": "vin",
    "Full Detail for line": "vin",
    "Sold Detail": "vin",
    "Sold use car": "vin",
    "Sold new car": "vin"
}

# ==================== FUNCIONES AUXILIARES ====================
def get_user_preference(user_id, key, default=None):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT preference_value FROM user_preferences WHERE user_id = %s AND preference_key = %s", (user_id, key))
        res = c.fetchone()
        return res['preference_value'].split(',') if res and res['preference_value'] else default

def save_user_preference(user_id, key, value_list):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_preferences (user_id, preference_key, preference_value)
            VALUES (%s, %s, %s) ON CONFLICT (user_id, preference_key)
            DO UPDATE SET preference_value = EXCLUDED.preference_value
        """, (user_id, key, ",".join(value_list)))
        conn.commit()

def get_status_info(service, reception_str, req_day_str, req_time_str):
    try:
        service_clean = service.strip() if service else ""
        dallas_tz = ZoneInfo("America/Chicago")
        now_dallas = datetime.now(dallas_tz)
        
        if not reception_str:
            return "#6c757d", "⚠️ No Date", "-"
        
        try:
            rec_date = datetime.strptime(reception_str, "%Y-%m-%d %I:%M %p")
        except ValueError:
            rec_date = datetime.strptime(reception_str, "%Y-%m-%d %H:%M")
        rec_date = rec_date.replace(tzinfo=dallas_tz)
        
        if service_clean == "Full Detail for line":
            hours_since_reception = (now_dallas - rec_date).total_seconds() / 3600
            if hours_since_reception < 24:
                return "#28a745", "✅ On Time", f"{hours_since_reception:.1f}h since reception"
            elif hours_since_reception < 48:
                return "#ffc107", "⚠️ Attention", f"{hours_since_reception:.1f}h since reception"
            else:
                return "#dc3545", "🚨 Delayed", f"{hours_since_reception:.1f}h since reception"
        
        if not req_day_str or not req_time_str:
            return "#6c757d", "⚠️ No Deadline", "-"
        
        try:
            req_date = datetime.strptime(f"{req_day_str} {req_time_str}", "%Y-%m-%d %I:%M %p")
        except ValueError:
            req_date = datetime.strptime(f"{req_day_str} {req_time_str}", "%Y-%m-%d %H:%M")
        req_date = req_date.replace(tzinfo=dallas_tz)
        
        hours_since_reception = (now_dallas - rec_date).total_seconds() / 3600
        hours_until_deadline = (req_date - now_dallas).total_seconds() / 3600
        
        if service_clean in ["Full Detail the customer", "Zaktek", "Sold Detail", "Sold new car", "Sold use car"]:
            if hours_until_deadline > 2.0:
                return "#28a745", "✅ Ample Time", f"{hours_until_deadline:.1f}h until deadline"
            elif hours_until_deadline > 1.0:
                return "#ffc107", "⚠️ Medium Time", f"{hours_until_deadline:.1f}h until deadline"
            else:
                return "#dc3545", "🚨 Critical", f"{hours_until_deadline:.1f}h until deadline"
        else:
            if hours_since_reception < 24:
                return "#28a745", "✅ On Time", f"{hours_since_reception:.1f}h since reception"
            elif hours_since_reception < 48:
                return "#ffc107", "⚠️ Attention", f"{hours_since_reception:.1f}h since reception"
            else:
                return "#dc3545", "🚨 Delayed", f"{hours_since_reception:.1f}h since reception"
    except Exception as e:
        return "#6c757d", "⚠️ Error", "-"

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
                    FROM users u LEFT JOIN branches b ON u.branch_id = b.id
                    WHERE u.username = %s AND u.password = %s
                """, (username, hashed))
                user = c.fetchone()
                if user:
                    st.session_state.update({
                        "logged_in": True,
                        "login_timestamp": time.time(),
                        "user_id": user['id'],
                        "username": user['username'],
                        "level": user['level'],
                        "branch_id": user['branch_id'],
                        "branch_name": user['branch_name'],
                        "full_name": user['full_name']
                    })
                    st.success(f"✅ Welcome, {user['full_name']}")
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials")

    st.divider()
    st.markdown("### Do you need to bring in a vehicle??")
    if st.button("🚦 Start without login", use_container_width=True, type="secondary"):
        st.session_state.guest_mode = True
        st.rerun()

def page_ingress():
    st.markdown("<h2>🚦 Vehicle Ingress</h2>", unsafe_allow_html=True)
    st.info(f"📍 Agency: {st.session_state.branch_name} | 👤 {st.session_state.full_name}")
    with st.form("ingress_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            service = st.selectbox("Service", SERVICES_LIST, key="service_sel")
            req_type = SERVICE_FIELD_REQUIREMENTS.get(service, "both")
            vin = st.text_input("VIN Number", key="vin_in")
            tag = st.text_input("TAG Number", key="tag_in")
            brand = st.text_input("Brand", key="brand_in", placeholder="")
        with col2:
            model = st.text_input("Model", key="model_in", placeholder="")
            responsible_name = st.text_input("Technical/Sales Man (Name)", key="res_name_in")
        with col3:
            today = datetime.now().date()
            default_day = today if datetime.now().hour < 20 else today + timedelta(days=1)
            if service == "Full Detail for line":
                req_day = None
                req_time = None
                st.info("ℹ️ *Full Detail for Line* does not require specific date/time.")
            else:
                req_day = st.date_input("Required Day", value=default_day, min_value=today, key="day_in")
                req_time = st.selectbox("Required Time (AM/PM)", TIME_12H_OPTIONS, index=36, key="time_in")
            notes = st.text_area("Notes", placeholder="Observations...", key="notes_in")
        urgent = st.checkbox("🚨 Waiting Customer")
        
        if st.form_submit_button("💾 Save Vehicle", use_container_width=True, type="primary"):
            if req_type == "both" and (not vin.strip() or not tag.strip()):
                st.error("❌ This service requires both VIN and TAG"); st.stop()
            elif req_type == "vin" and not vin.strip():
                st.error("❌ This service requires a VIN Number"); st.stop()
            elif req_type == "tag" and not tag.strip():
                st.error("❌ This service requires a TAG Number"); st.stop()
            
            dallas_tz = ZoneInfo("America/Chicago")
            dallas_now = datetime.now(dallas_tz).strftime("%Y-%m-%d %I:%M %p")
            check_val = (vin if req_type in ["vin", "both"] else tag).strip().upper()
            check_col = "vin_number" if req_type in ["vin", "both"] else "tag_number"
            
            with get_db() as conn:
                c = conn.cursor()
                c.execute(f"SELECT id FROM vehicles WHERE {check_col}=%s AND service=%s AND branch_id=%s AND status='Pending'", 
                          (check_val, service, st.session_state.branch_id))
                if c.fetchone():
                    st.error(f"❌ {check_val} is already registered for {service}"); st.stop()
                
                c.execute("""
                    INSERT INTO vehicles (vin_number, tag_number, brand, model, required_day, required_time, service, notes,
                     is_urgent, branch_id, reception_date, status, responsible_name)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    vin.strip().upper() if vin and req_type in ["vin", "both"] else None,
                    tag.strip().upper() if tag and req_type in ["tag", "both"] else None,
                    brand.strip() if brand else None, model.strip() if model else None,
                    req_day.strftime("%Y-%m-%d") if req_day else None,
                    req_time if req_time else None,
                    service, notes.strip(), 1 if urgent else 0, st.session_state.branch_id,
                    dallas_now, 'Pending', responsible_name.strip()
                ))
            st.success("✅ Vehicle registered successfully")
            st.rerun()

def page_pending():
    st.markdown("<h2>🏎️ Pending Vehicles</h2>", unsafe_allow_html=True)
    if st.session_state.level < 3:
        st.info(f"📍 Agency: {st.session_state.branch_name} | 👤 {st.session_state.full_name}")
    else:
        st.info(f"⚙️ Administrator Mode - Viewing all agencies | 👤 {st.session_state.full_name}")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("🔍 Search by VIN or TAG Number", placeholder="", key="search_pending")
    with col2:
        st.button("🔍 Search", key="btn_search_pending")

    with get_db() as conn:
        c = conn.cursor()
        if st.session_state.level < 3:
            base_query = """
                SELECT v.id, v.tag_number, v.vin_number, v.brand, v.model, b.name as agency_name,
                       v.service, v.reception_date, v.required_day, v.required_time, v.is_urgent, v.responsible_name, v.notes
                FROM vehicles v LEFT JOIN branches b ON v.branch_id = b.id
                WHERE v.status = 'Pending' AND v.branch_id = %s
            """
            params = (st.session_state.branch_id,)
            if search_term:
                base_query += " AND (v.vin_number ILIKE %s OR v.tag_number ILIKE %s)"
                params = (st.session_state.branch_id, f"%{search_term}%", f"%{search_term}%")
            base_query += " ORDER BY v.service, v.is_urgent DESC, v.reception_date ASC"
        else:
            base_query = """
                SELECT v.id, v.tag_number, v.vin_number, v.brand, v.model, b.name as agency_name,
                       v.service, v.reception_date, v.required_day, v.required_time, v.is_urgent, v.responsible_name, v.notes
                FROM vehicles v LEFT JOIN branches b ON v.branch_id = b.id WHERE v.status = 'Pending'
            """
            params = ()
            if search_term:
                base_query += " AND (v.vin_number ILIKE %s OR v.tag_number ILIKE %s)"
                params = (f"%{search_term}%", f"%{search_term}%")
            base_query += " ORDER BY b.name, v.service, v.is_urgent DESC, v.reception_date ASC"

        c.execute(base_query, params)
        all_v = c.fetchall()

    if not all_v:
        st.warning(f"No pending vehicles were found that matched '{search_term}'" if search_term else "There are no pending vehicles.")
        return

    by_service = {}
    for v in all_v:
        by_service.setdefault(v['service'], []).append(v)

    for svc, vehs in by_service.items():
        with st.expander(f"**{svc}** — {len(vehs)} vehicle(s)", expanded=True):
            rows = []
            for v in vehs:
                color, msg, info = get_status_info(v['service'], v['reception_date'], v['required_day'], v['required_time'])
                rows.append({
                    "Complete": False, "Status": msg, "TAG": v['tag_number'],
                    "VIN": v['vin_number'] or "-", "Brand": v.get('brand') or "-",
                    "Model": v.get('model') or "-", "Agency": v.get('agency_name') or "-",
                    "Responsible": v['responsible_name'] or "-",
                    "Required Day": v['required_day'] or "-", "Required Time": v['required_time'] or "-",
                    "Received": v['reception_date'], "Time Info": info,
                    "Urgent": "🚨" if v['is_urgent'] else "",
                    "Who's Done": "", "_id": v['id'], "_color": color,
                    "Notes ": v.get('notes') or "-"
                })

            df = pd.DataFrame(rows)
            column_config = {
                "Complete": st.column_config.CheckboxColumn("Complete", help="Mark as DONE", default=False),
                "Who's Done": st.column_config.TextColumn("Who's Done", help="Mandatory: Click here to type name", required=True),
                "Status": st.column_config.TextColumn(disabled=True),
                "TAG": st.column_config.TextColumn(disabled=True), "VIN": st.column_config.TextColumn(disabled=True),
                "Brand": st.column_config.TextColumn(disabled=True), "Model": st.column_config.TextColumn(disabled=True),
                "Agency": st.column_config.TextColumn(disabled=True), "Responsible": st.column_config.TextColumn(disabled=True),
                "Required Day": st.column_config.TextColumn(disabled=True), "Required Time": st.column_config.TextColumn(disabled=True),
                "Received": st.column_config.TextColumn(disabled=True), "Time Info": st.column_config.TextColumn(disabled=True),
                "Urgent": st.column_config.TextColumn(disabled=True), "Notes ": st.column_config.TextColumn(disabled=True)
            }

            edited_df = st.data_editor(
                df.drop(columns=['_id', '_color']), column_config=column_config,
                hide_index=True, use_container_width=True, num_rows="fixed",
                key=f"editor_{svc.replace(' ', '_')}"
            )

        if st.button("✅ Done", key=f"btn_deliver_{svc.replace(' ', '_')}", use_container_width=True, type="primary"):
            selected_rows = edited_df[edited_df["Complete"] == True]
            if selected_rows.empty:
                st.warning("⚠️ You have not selected a vehicle.")
            else:
                missing_who = selected_rows[
                    selected_rows["Who's Done"].isna() | 
                    (selected_rows["Who's Done"].astype(str).str.strip() == "")
                ]
                if not missing_who.empty:
                    st.error("❌ Please fill in 'Who's Done' for all selected vehicles before marking them as Done.")
                    st.stop()
                
                count = 0
                dallas_tz = ZoneInfo("America/Chicago")
                delivery_time = datetime.now(dallas_tz).strftime("%Y-%m-%d %I:%M %p")
                
                try:
                    with get_db() as conn2:
                        c2 = conn2.cursor()
                        for idx in selected_rows.index:
                            original_id = int(df.loc[idx, '_id'])
                            who_done_val = str(edited_df.loc[idx, "Who's Done"]).strip()
                            c2.execute("""
                                UPDATE vehicles SET status = 'Delivered', delivery_date = %s, handled_by = %s, who_done = %s 
                                WHERE id = %s
                            """, (delivery_time, st.session_state.username, who_done_val, original_id))
                            count += 1
                    st.success(f"✅ {count} Vehicle(s) finished correctly.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error updating vehicles: {e}")

def page_reports():
    if 'logged_in' not in st.session_state or 'level' not in st.session_state:
        st.error("🚫 Session expired. Please login again.")
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    if st.session_state.level < 2:
        st.error("🚫 You do not have permissions to access Reports.")
        st.info("This section is available only for Supervisors and Administrators.")
        st.stop()

    st.markdown("<h2>📊 Reports & Statistics</h2>", unsafe_allow_html=True)
    st.subheader("🔎 Advanced Filters")

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name FROM branches WHERE active=1 ORDER BY name")
        branches = c.fetchall()

    branch_opts = {"🌐 All Agencies": None}
    for b in branches: branch_opts[b['name']] = b['id']

    col1, col2, col3, col4 = st.columns(4)
    with col1: period = st.selectbox("Period", ["All Time", "Today", "This Week", "This Month"])
    with col2: status_filter = st.selectbox("Status", ["All", "Pending", "Delivered"])
    with col3: service_filter = st.selectbox("Service", ["All"] + SERVICES_LIST)
    with col4:
        if st.session_state.level == 3:
            selected_agency = st.selectbox("🏢 Agency", list(branch_opts.keys()))
            branch_id_filter = branch_opts[selected_agency]
        else:
            branch_id_filter = st.session_state.branch_id

    if st.button("🔄 Update Reports", type="primary"): st.rerun()

    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT v.tag_number, v.vin_number, v.brand, v.model, v.service, v.status, 
                   v.reception_date, v.delivery_date, v.is_urgent, COALESCE(b.name, 'Global/Admin') as agency, v.who_done
            FROM vehicles v LEFT JOIN branches b ON v.branch_id = b.id
        """
        conditions, params = [], []
        if branch_id_filter is not None: conditions.append("v.branch_id = %s"); params.append(branch_id_filter)
        if period == "Today": conditions.append("v.reception_date::date = CURRENT_DATE")
        elif period == "This Week": conditions.append("v.reception_date::timestamp >= DATE_TRUNC('week', CURRENT_DATE)")
        elif period == "This Month": conditions.append("DATE_TRUNC('month', v.reception_date::timestamp) = DATE_TRUNC('month', CURRENT_DATE)")
        if status_filter != "All": conditions.append("v.status = %s"); params.append(status_filter)
        if service_filter != "All": conditions.append("v.service = %s"); params.append(service_filter)

        if conditions: query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY v.reception_date DESC"
        cursor.execute(query, params if params else None)
        rows = cursor.fetchall()
        df_all = pd.DataFrame(rows, columns=['tag_number', 'vin_number', 'brand', 'model', 'service', 'status', 'reception_date', 'delivery_date', 'is_urgent', 'agency', 'who_done'])

    if df_all.empty:
        st.warning("📭 No vehicles with the filters applied were found.")
        return

    df_display = df_all.copy().rename(columns={
        'tag_number': 'TAG', 'vin_number': 'VIN', 'brand': 'Brand', 'model': 'Model',
        'service': 'Service', 'status': 'Status', 'reception_date': 'Received',
        'delivery_date': 'Delivered', 'is_urgent': 'Urgent', 'agency': 'Agency', 'who_done': "Who's Done"
    })
    df_display['Urgent'] = df_display['Urgent'].map({1: '🚨 Yes', 0: 'No'})

    total = len(df_display)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Vehicles", total)
    k2.metric("Delivered", len(df_display[df_display['Status'] == 'Delivered']))
    k3.metric("Pending", len(df_display[df_display['Status'] == 'Pending']))
    k4.metric("Urgent", len(df_display[df_display['Urgent'] == '🚨 Yes']))

    st.divider()
    st.subheader("📋 Detailed List")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.subheader("💾 Export Data")
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df_all.to_excel(writer, sheet_name='Vehicles', index=False)
    output.seek(0)
    st.download_button(label="📥 Download Excel", data=output, file_name=f"HARK_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if st.session_state.level >= 2:
        st.divider()
        st.subheader("↩️ Reverting Deliveries (Error Correction)")
        st.caption("⚠️ This action will return the vehicle to 'Pending' and clear the delivery date.")
        rev_query = """
            SELECT v.id, v.tag_number, v.vin_number, v.brand, v.model, v.service, 
                   v.delivery_date, v.handled_by, b.name as agency
            FROM vehicles v LEFT JOIN branches b ON v.branch_id = b.id
            WHERE v.status = 'Delivered' AND v.delivery_date::timestamp >= NOW() - INTERVAL '24 hours'
        """
        rev_conditions, rev_params = [], []
        if st.session_state.level == 2: rev_conditions.append("v.branch_id = %s"); rev_params.append(st.session_state.branch_id)
        if rev_conditions: rev_query += " WHERE " + " AND ".join(rev_conditions)
        rev_query += " ORDER BY v.delivery_date DESC LIMIT 100"

        with get_db() as conn:
            c = conn.cursor()
            c.execute(rev_query, rev_params)
            delivered_list = c.fetchall()

        if delivered_list:
            rev_df = pd.DataFrame(delivered_list)
            display_df = rev_df[['tag_number', 'brand', 'model', 'service', 'agency', 'handled_by', 'delivery_date']]
            st.dataframe(display_df, hide_index=True, use_container_width=True)
            vehicle_options = {f"{v['tag_number']} | {v['brand']} {v['model']} (Delivered: {v['delivery_date']})": v['id'] for v in delivered_list}
            selected_vehicle = st.selectbox("📍 Select the vehicle to reverse:", list(vehicle_options.keys()), index=None)
            confirm_revert = st.checkbox("✅ I confirm that I wish to revert this submission to Pending")
            
            if st.button("🔄 Reverse Vehicle", type="secondary", disabled=not (selected_vehicle and confirm_revert)):
                vid = vehicle_options[selected_vehicle]
                with get_db() as conn2:
                    c2 = conn2.cursor()
                    c2.execute("UPDATE vehicles SET status = 'Pending', delivery_date = NULL, handled_by = NULL WHERE id = %s AND status = 'Delivered'", (vid,))
                st.success("✅ Vehicle successfully reverted to state 'Pending'.")
                st.rerun()
        else:
            st.info("📭 There are no recently delivered vehicles to reverse.")
def page_users():
    st.markdown("<h1>👤 User & Agency Management</h1>", unsafe_allow_html=True)
    if st.session_state.level != 3:
        st.warning("🔒 Access denied. Only Administrators can manage users.")
        return

    # ====================  GESTIÓN DE USUARIOS ====================
    st.subheader("👤 User Management")

    # --- CREAR NUEVO USUARIO ---
    with st.expander("➕ Add New User", expanded=False):
        with st.form("create_user_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                new_username = st.text_input("Username", placeholder="ej: john.doe")
                new_pass = st.text_input("Password", type="password")
            with col2:
                new_fullname = st.text_input("Full Name", placeholder="John Doe")
                new_level = st.selectbox("Access Level", [1, 2, 3], format_func=lambda x: {1: "👤 Agent", 2: "🛡️ Supervisor", 3: "⚙️ Admin"}[x])
            with col3:
                # Obtener agencias actualizadas (incluyendo las recién creadas)
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute("SELECT id, name FROM branches WHERE active=1 ORDER BY name")
                    branches = c.fetchall()
                    branch_opts = {b['name']: b['id'] for b in branches}
                
                # Si es Admin, no asignar agencia (Global)
                if new_level == 3:
                    st.info("🌐 Admin users are Global/Admin")
                    selected_branch = None
                else:
                    selected_branch_name = st.selectbox("Assign Agency", list(branch_opts.keys()))
                    selected_branch = branch_opts[selected_branch_name]

            if st.form_submit_button("💾 Create User", use_container_width=True, type="primary"):
                if not new_username or not new_pass or not new_fullname:
                    st.error("❌ All fields are required.")
                else:
                    hashed = hashlib.sha256(new_pass.encode()).hexdigest()
                    try:
                        with get_db() as conn:
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO users (username, password, level, full_name, branch_id)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (new_username.strip(), hashed, new_level, new_fullname.strip(), selected_branch))
                        st.success(f"✅ User '{new_username}' successfully created.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error creating user: {e}")

    st.divider()

    # --- VER LISTA DE USUARIOS ---
    with st.expander("📋 Registered Users List", expanded=False):
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT u.id, u.username, u.level, u.full_name,
                       COALESCE(b.name, 'Global/Admin') as branch_name,
                       u.branch_id
                FROM users u
                LEFT JOIN branches b ON u.branch_id = b.id
                ORDER BY u.level DESC, u.username
            """)
            users_data = c.fetchall()

        if users_data:
            df = pd.DataFrame(users_data, columns=['id', 'username', 'level', 'full_name', 'branch_name', 'branch_id'])
            df['level'] = df['level'].map({1: ' Agent', 2: '🛡️ Supervisor', 3: '⚙️ Admin'})
            st.dataframe(df[['id', 'username', 'level', 'full_name', 'branch_name']], hide_index=True, use_container_width=True)
        else:
            st.info("📭 No users found.")

    # --- EDITAR AGENCIA DE USUARIO ---
    with st.expander("✏️ Edit User - Change Agency", expanded=False):
        # Recargar datos para el selector
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT u.id, u.username, u.level, u.full_name,
                       COALESCE(b.name, 'Global/Admin') as branch_name, u.branch_id
                FROM users u LEFT JOIN branches b ON u.branch_id = b.id
                ORDER BY u.username
            """)
            users_data = c.fetchall()
            
            user_dict = {f"{u['username']} - {u['full_name']} ({u['branch_name']})": u for u in users_data if u['id'] != st.session_state.user_id}
            
            if user_dict:
                selected_user_key = st.selectbox("Select User to Edit", list(user_dict.keys()))
                selected_user = user_dict[selected_user_key]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Current Agency:** {selected_user['branch_name']}")
                
                with col2:
                    c.execute("SELECT id, name FROM branches WHERE active=1 ORDER BY name")
                    branches = c.fetchall()
                    branch_opts = {b['name']: b['id'] for b in branches}
                    
                    # Permitir volver a Global/Admin si el usuario es Admin
                    if selected_user['level'] == 3:
                        branch_options_edit = {"🌐 Global/Admin": None}
                        branch_options_edit.update(branch_opts)
                    else:
                        branch_options_edit = branch_opts
                    
                    new_branch_name = st.selectbox("New Agency", list(branch_options_edit.keys()), key="edit_branch_select")
                    new_branch_id = branch_options_edit[new_branch_name]
                    
                    if st.button("💾 Update Agency", type="primary"):
                        if new_branch_id != selected_user['branch_id']:
                            with get_db() as conn2:
                                c2 = conn2.cursor()
                                c2.execute("UPDATE users SET branch_id = %s WHERE id = %s", (new_branch_id, selected_user['id']))
                            st.success(f"✅ {selected_user['username']}'s agency updated to **{new_branch_name}**")
                            st.rerun()
                        else:
                            st.info("ℹ️ Same agency selected.")
            else:
                st.info("ℹ️ No other users to edit.")

    st.divider()

    # --- ACCIONES AVANZADAS (Password / Delete) ---
    with st.expander("🔧 Advanced Actions (Password / Delete)", expanded=False):
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT u.id, u.username, u.level, u.full_name,
                       COALESCE(b.name, 'Global/Admin') as branch_name
                FROM users u LEFT JOIN branches b ON u.branch_id = b.id
                ORDER BY u.username
            """)
            users_data = c.fetchall()

        if users_data:
            user_list = {f"{u['username']} ({u['full_name']})": u for u in users_data if u['id'] != st.session_state.user_id}
            
            if user_list:
                col1, col2 = st.columns(2)
                
                # Columna 1: Reset Password
                with col1:
                    st.markdown("### 🔑 Reset Password")
                    selected_user_pass = st.selectbox("Select User", list(user_list.keys()), key="reset_pass_user")
                    new_password = st.text_input("New Password", type="password", key="reset_pass_input")
                    
                    if st.button("🔄 Update Password", use_container_width=True):
                        if new_password:
                            hashed = hashlib.sha256(new_password.encode()).hexdigest()
                            user_id = user_list[selected_user_pass]['id']
                            with get_db() as conn2:
                                c2 = conn2.cursor()
                                c2.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user_id))
                            st.success(f"✅ Password updated for {selected_user_pass}")
                            st.rerun()
                        else:
                            st.error(" Enter a password")
                
                # Columna 2: Delete User
                with col2:
                    st.markdown("### 🗑️ Delete User")
                    delete_list = {f"{u['username']} - {u['full_name']}": u['id'] for u in users_data if u['id'] != st.session_state.user_id}
                    
                    if delete_list:
                        selected_delete = st.selectbox("Select User to Delete", list(delete_list.keys()), key="delete_user_select")
                        confirm_delete = st.checkbox("Confirm deletion", key="confirm_del_checkbox")
                        
                        if st.button("🗑️ Delete User", use_container_width=True, disabled=not confirm_delete):
                            user_id = delete_list[selected_delete]
                            with get_db() as conn2:
                                c2 = conn2.cursor()
                                c2.execute("DELETE FROM users WHERE id = %s", (user_id,))
                            st.success(f"✅ User {selected_delete} Deleted")
                            st.rerun()
                    else:
                        st.info("ℹ️ No other users to delete.")
        else:
            st.info(" No users found.")
    # ==================== GESTIÓN DE AGENCIAS ====================
    st.subheader("🏢 Agency Management")
    
    # --- AGREGAR NUEVA AGENCIA ---
    with st.expander("➕ Add New Agency", expanded=True):
        with st.form("add_branch_form"):
            col1, col2 = st.columns([3, 1])
            with col1:
                new_branch_name = st.text_input("Agency Name", placeholder="e.g. BMW Downtown")
            with col2:
                is_active_default = st.checkbox("Active", value=True)
            
            if st.form_submit_button("💾 Create Agency", use_container_width=True, type="primary"):
                if not new_branch_name.strip():
                    st.error("❌ Name is required.")
                else:
                    try:
                        with get_db() as conn:
                            c = conn.cursor()
                            c.execute("INSERT INTO branches (name, active) VALUES (%s, %s)", 
                                      (new_branch_name.strip(), 1 if is_active_default else 0))
                        st.success(f"✅ Agency '{new_branch_name}' created successfully!")
                        st.rerun()
                    except Exception as e:
                        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                            st.error(f"❌ Agency '{new_branch_name}' already exists.")
                        else:
                            st.error(f"❌ Error: {e}")

    st.divider()

    # --- EDITAR AGENCIAS EXISTENTES ---
    with st.expander("✏️ Edit Existing Agencies", expanded=False):
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, active FROM branches ORDER BY id")
            branches = c.fetchall()

        if branches:
            for b in branches:
                col_a, col_b, col_c, col_d = st.columns([4, 2, 1, 1])
                
                with col_a:
                    new_name = st.text_input(f"Agency #{b['id']}", value=b['name'], key=f"branch_name_{b['id']}")
                    
                with col_b:
                    if st.button("💾 Update Name", key=f"upd_branch_{b['id']}"):
                        new_name_clean = new_name.strip()
                        if not new_name_clean:
                            st.warning("❌ Name cannot be empty.")
                        elif new_name_clean == b['name']:
                            st.info("ℹ️ Name unchanged.")
                        else:
                            try:
                                with get_db() as conn2:
                                    c2 = conn2.cursor()
                                    c2.execute("UPDATE branches SET name = %s WHERE id = %s", (new_name_clean, b['id']))
                                st.success(f"✅ Renamed: '{b['name']}' → '{new_name_clean}'")
                                st.rerun()
                            except Exception as e:
                                err = str(e).lower()
                                if "duplicate key" in err or "unique" in err:
                                    st.error(f"❌ Name '{new_name_clean}' already exists.")
                                else:
                                    st.error(f"❌ DB Error: {e}")
                                
                with col_c:
                    is_active = b['active'] == 1
                    new_active = st.checkbox("Active", value=is_active, key=f"branch_act_{b['id']}")
                    
                with col_d:
                    if st.button("💾 Status", key=f"stat_branch_{b['id']}"):
                        if new_active != is_active:
                            with get_db() as conn2:
                                c2 = conn2.cursor()
                                c2.execute("UPDATE branches SET active = %s WHERE id = %s", (1 if new_active else 0, b['id']))
                            st.success(f"✅ Status updated for {b['name']}")
                            st.rerun()
        else:
            st.info("📭 No agencies found in database.")

    st.divider()

def page_public_ingress_level0():
    st.markdown("<h1 style='text-align:center; color:#00d4ff;'>🚦 Vehicle Entrance</h1>", unsafe_allow_html=True)
    if 'guest_branch_id' not in st.session_state or 'guest_branch_name' not in st.session_state:
        st.info("👋 Select your agency to get started")
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name FROM branches WHERE active=1 ORDER BY name")
            branches = c.fetchall()
        branch_dict = {b['name']: b['id'] for b in branches}
        selected_branch_name = st.selectbox("🏢 Select your Agency", list(branch_dict.keys()), key="guest_branch_select")
        if st.button("✅ Confirm Agency and Continue", type="primary", use_container_width=True):
            st.session_state.guest_branch_id = branch_dict[selected_branch_name]
            st.session_state.guest_branch_name = selected_branch_name
            st.success(f"✅ Agency set up: **{selected_branch_name}**")
            st.rerun()
        st.stop() 

    st.info(f"📍 Selected agency: **{st.session_state.guest_branch_name}**")
    with st.form("guest_ingress_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            service = st.selectbox("Service", SERVICES_LIST, key="guest_service")
            req_type = SERVICE_FIELD_REQUIREMENTS.get(service, "both")
            vin = st.text_input("VIN Number *", key="guest_vin")
            tag = st.text_input("TAG Number *", key="guest_tag")
            brand = st.text_input("Brand", placeholder="", key="guest_brand")
        with col2:
            model = st.text_input("Model", placeholder="", key="guest_model")
            responsible_name = st.text_input("Responsible", key="guest_responsible")
        with col3:
            today = datetime.now().date()
            default_day = today if datetime.now().hour < 20 else today + timedelta(days=1)
            if service == "Full Detail for line":
                req_day = None; req_time = None
                st.info("ℹ️ Full Detail for line does not require a specific date/time.")
            else:
                req_day = st.date_input("Required Day", value=default_day, min_value=today, key="guest_day")
                req_time = st.selectbox("Required Time (AM/PM)", TIME_12H_OPTIONS, index=36, key="time_in")
            notes = st.text_area("Notes", placeholder="Observations...", key="guest_notes")
        urgent = st.checkbox("🚨 Waiting Customer")

        if st.form_submit_button("💾Save Vehicle", use_container_width=True, type="primary"):
            req_type = SERVICE_FIELD_REQUIREMENTS.get(service, "both")
            if req_type == "both" and (not vin.strip() or not tag.strip()): st.error("❌ This service requires VIN y TAG"); st.stop()
            elif req_type == "vin" and not vin.strip(): st.error("❌ This service requires VIN"); st.stop()
            elif req_type == "tag" and not tag.strip(): st.error("❌ This service requires TAG"); st.stop()

            dallas_now = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %I:%M %p")
            with get_db() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO vehicles (vin_number, tag_number, brand, model, required_day, required_time, 
                     service, notes, is_urgent, branch_id, reception_date, status, responsible_name)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    vin.strip().upper() if vin else None, tag.strip().upper() if tag else None,
                    brand.strip() if brand else None, model.strip() if model else None,
                    req_day.strftime("%Y-%m-%d") if req_day else None,
                    req_time if req_time else None,
                    service, notes.strip(), 1 if urgent else 0, st.session_state.guest_branch_id,
                    dallas_now, 'Pending', responsible_name.strip()
                ))
            st.success("✅ Vehicle correctly registered in " + st.session_state.guest_branch_name)
            st.rerun()

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Change Agency"):
            if 'guest_branch_id' in st.session_state: del st.session_state.guest_branch_id
            if 'guest_branch_name' in st.session_state: del st.session_state.guest_branch_name
            st.rerun()
    with col_b:
        if st.button("👤Go to Normal Login"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

# ==================== MAIN ====================
def main():
    init_database()
    if st.session_state.get("guest_mode", False):
        page_public_ingress_level0()
        return   

    if 'logged_in' in st.session_state and st.session_state.level == 1:
        if 'login_timestamp' not in st.session_state: st.session_state.login_timestamp = time.time()
        five_hours_seconds = 5 * 60 * 60
        if time.time() - st.session_state.login_timestamp > five_hours_seconds:
            st.error("⏰ Session expired (5 hours limit). Please login again.")
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    if 'logged_in' not in st.session_state:
        login_page()
    else:
        st.sidebar.markdown(f"""
          <div style='text-align:center; padding: 20px 0;'>
              <h1 style='color:#00d4ff; margin:0; font-size:2.4em;'>🦈 HARK</h1>
              <p style='color:#94a3b8; margin:10px 0 0 0;'>
                {st.session_state.full_name}<br>
                <small style='color:#64748b;'>{st.session_state.branch_name}</small>
              </p>
          </div>
        """, unsafe_allow_html=True)

        if st.sidebar.button("🚪 Sign Out", use_container_width=True):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

        menu_options = ["🚦 Ingress", "🏎️ Pending"]
        if st.session_state.level >= 2: menu_options.append("📊 Reports")
        if st.session_state.level == 3: menu_options.append("👤 Users")
        
        menu = st.sidebar.radio("Menu", menu_options)
        if menu == "🚦 Ingress": page_ingress()
        elif menu == "🏎️ Pending": page_pending()
        elif menu == "📊 Reports": page_reports()
        elif menu == "👤 Users": page_users()

if __name__ == "__main__":
    main()
