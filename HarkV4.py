import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime, time, timedelta
import hashlib
from contextlib import contextmanager
from io import BytesIO
import os

# ==================== CONFIGURATION ====================
st.set_page_config(page_title="HARK - Management System", layout="wide", page_icon="🦈")

# ==================== DATABASE MANAGEMENT ====================

@contextmanager
def get_db():
    """PostgreSQL connection manager - Compatible con local y Render"""
    conn = None
    try:
        # === Prioridad 1: Variables de entorno (Render, Railway, etc.) ===
        if os.getenv("DB_HOST"):
            cfg = {
                "HOST": os.getenv("DB_HOST"),
                "NAME": os.getenv("DB_NAME"),
                "USER": os.getenv("DB_USER"),
                "PASSWORD": os.getenv("DB_PASSWORD"),
                "PORT": int(os.getenv("DB_PORT", 5432)),
            }
        # === Prioridad 2: st.secrets (solo para desarrollo local) ===
        elif "DB" in st.secrets:
            cfg = st.secrets["DB"]
        else:
            st.error("❌ No se encontraron credenciales de base de datos.\nConfigura las variables de entorno en Render o el archivo secrets.toml localmente.")
            st.stop()

        # Validación
        if not all([cfg.get("HOST"), cfg.get("NAME"), cfg.get("USER"), cfg.get("PASSWORD")]):
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
    """Initialize PostgreSQL tables and seed data"""
    with get_db() as conn:
        c = conn.cursor()
        
        # Crear tablas si no existen
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
            responsable_id INTEGER REFERENCES users(id),
            responsible_name TEXT,
            notes TEXT,
            status TEXT DEFAULT 'Pending',
            reception_date TEXT NOT NULL,
            delivery_date TEXT,
            handled_by TEXT,
            is_urgent INTEGER DEFAULT 0,
            branch_id INTEGER REFERENCES branches(id)
        )''')

        # === Seed data (solo si las tablas están vacías) ===
        c.execute("SELECT COUNT(*) as total FROM branches")
        if c.fetchone()['total'] == 0:
            c.execute("INSERT INTO branches (name) VALUES ('North Agency'), ('South Agency'), ('Central Agency')")
            
            # Contraseñas hasheadas (Usuario1*, Usuario2*, Krieger1)
            users_data = [
                ('Keri Kidd', hashlib.sha256('Usuario1*'.encode()).hexdigest(), 1, 'Keri Kidd', 1),
                ('Fidel Sizemore', hashlib.sha256('Usuario2*'.encode()).hexdigest(), 1, 'Fidel Sizemore', 2),
                ('Gianni Daly', hashlib.sha256('Usuario4*'.encode()).hexdigest(), 2, 'Gianni Daly', 1),
                ('SuperSU', hashlib.sha256('Krieger1'.encode()).hexdigest(), 3, 'Administrator', None)
            ]
            c.executemany("""
                INSERT INTO users (username, password, level, full_name, branch_id) 
                VALUES (%s, %s, %s, %s, %s)
            """, users_data)
            
            print("✅ Datos iniciales insertados correctamente")
        
        conn.commit()

# ==================== CONSTANTS ====================
SERVICES_LIST = [
    "Service Wash", "Loaner", "Photo", "Full Detail the customer", 
    "Zaktek", "Show Room", "Full Detail for line", "Sold use car", "Sold new car"
]

# ==================== TIME & COLOR LOGIC ====================
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

# ==================== PAGES ====================
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
                c.execute("SELECT id, username, level, full_name FROM users WHERE username=%s AND password=%s", (username, hashed))
                user = c.fetchone()
                if user:
                    st.session_state.update({
                        "logged_in": True, "user_id": user['id'], "username": user['username'],
                        "level": user['level'], "branch_id": opts[branch_sel] if user['level'] < 3 else None,
                        "branch_name": branch_sel if user['level'] < 3 else "All (Admin)", "full_name": user['full_name']
                    })
                    st.rerun()
                else:
                    st.error("❌ Invalid Credentials")

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
            req_day = st.date_input("Required Day", min_value=datetime.now().date(), key="day_in")
            req_time = st.time_input("Required Time", value=time(9, 0), key="time_in")
            notes = st.text_area("Notes", placeholder="Observations...", key="notes_in")
        urgent = st.checkbox("🚨 Mark as URGENT (Maximum Priority)")
        if st.form_submit_button("💾 Save Vehicle", use_container_width=True, type="primary"):
            if not tag.strip():
                st.error("❌ TAG Number is required")
                st.stop()
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM vehicles WHERE tag_number=%s AND service=%s AND branch_id=%s AND status='Pending'", 
                          (tag.strip().upper(), service, st.session_state.branch_id))
                if c.fetchone():
                    st.error(f"❌ {tag.upper()} is already in the queue for {service}")
                    st.stop()
                c.execute("""
                    INSERT INTO vehicles (vin_number, tag_number, required_day, required_time, service, 
                                          notes, is_urgent, branch_id, reception_date, status, responsible_name)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    vin.strip().upper() if vin else None, tag.strip().upper(), req_day.strftime("%Y-%m-%d"),
                    req_time.strftime("%H:%M"), service, notes.strip(), 1 if urgent else 0,
                    st.session_state.branch_id, datetime.now().strftime("%Y-%m-%d %H:%M"), 'Pending', responsible_name.strip()
                ))
            st.success(f"✅ {tag.upper()} registered in **{service}**")

def page_pending():
    st.markdown("<h2>🏎️ Pending Vehicles</h2>", unsafe_allow_html=True)
    col_b1, col_b2 = st.columns([3, 1])
    with col_b1: search_term = st.text_input("🔍 Search by VIN or TAG Number", placeholder="E.g: 123ABC")
    with col_b2: btn_search = st.button("Search")
    if search_term and btn_search:
        search_val = f"%{search_term.strip().upper()}%"
        with get_db() as conn:
            where = "AND v.branch_id = %s" if st.session_state.level < 3 else ""
            params = (search_val, search_val, st.session_state.branch_id) if st.session_state.level < 3 else (search_val, search_val)
            c = conn.cursor()
            c.execute(f"""
                SELECT id, tag_number, vin_number, service, reception_date, required_day, required_time, is_urgent, responsible_name
                FROM vehicles v WHERE (v.vin_number LIKE %s OR v.tag_number LIKE %s) {where} AND v.status='Pending'
                ORDER BY v.is_urgent DESC
            """, params)
            res = c.fetchall()
            if res:
                st.success(f"✅ {len(res)} vehicle(s) found")
                for r in res:
                    color, msg, info = get_status_info(r['service'], r['reception_date'], r['required_day'], r['required_time'])
                    st.markdown(f"""
                    <div style='border-left: 6px solid {color}; background: #111; padding: 10px; border-radius: 6px; margin-bottom: 8px;'>
                        <h4 style='margin:0; color:{color};'>🚗 {r['tag_number']} | {r['service']}</h4>
                        <p style='margin:4px 0 0; font-size:0.9em; color:#ccc;'>VIN: {r['vin_number'] or 'N/A'} | Resp: {r['responsible_name'] or '-'} | {info}</p>
                    </div>""", unsafe_allow_html=True)
                    if st.button(f"✓ Deliver", key=f"btn_ent_{r['id']}"):
                        with get_db() as conn2:
                            c2 = conn2.cursor()
                            c2.execute("UPDATE vehicles SET status='Delivered', delivery_date=%s, handled_by=%s WHERE id=%s",
                                      (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.username, r['id']))
                        st.success(f"✅ {r['tag_number']} delivered")
                        st.rerun()
            else:
                st.warning("No pending vehicles found.")
            st.divider()
    with get_db() as conn:
        where = "WHERE v.status='Pending' AND v.branch_id = %s" if st.session_state.level < 3 else "WHERE v.status='Pending'"
        params = (st.session_state.branch_id,) if st.session_state.level < 3 else ()
        c = conn.cursor()
        c.execute(f"""
            SELECT id, tag_number, vin_number, service, reception_date, required_day, required_time, is_urgent, responsible_name
            FROM vehicles v {where} ORDER BY v.service, v.is_urgent DESC, v.reception_date ASC
        """, params)
        all_v = c.fetchall()
        if not all_v:
            st.info("📭 No pending vehicles.")
            return
        by_service = {}
        for v in all_v: by_service.setdefault(v['service'], []).append(v)
        for svc, vehs in by_service.items():
            with st.expander(f"**{svc}** — {len(vehs)} vehicle(s)", expanded=True):
                rows = []
                for v in vehs:
                    color, msg, info = get_status_info(v['service'], v['reception_date'], v['required_day'], v['required_time'])
                    rows.append({"TAG": v['tag_number'], "VIN": v['vin_number'] or "-", "Responsible": v['responsible_name'] or "-",
                                 "Required Day": v['required_day'], "Required Time": v['required_time'], "Date of Receipt": v['reception_date'],
                                 "Status": msg, "Time": info, "Urgent": "🚨" if v['is_urgent'] else "", "_color": color, "_id": v['id']})
                df = pd.DataFrame(rows)
                def style_rows(row): return [f'background-color: #111; color: #eee; border-left: 5px solid {row["_color"]}']*len(row)
                styled_df = df.style.apply(style_rows, axis=1).hide(["_color", "_id"], axis=1)
                st.dataframe(styled_df, hide_index=True, use_container_width=True)
                cols = st.columns(len(vehs))
                for i, v in enumerate(vehs):
                    with cols[i]:
                        if st.button(f"✓ {v['tag_number']}", key=f"btn_main_{v['id']}"):
                            with get_db() as conn2:
                                c2 = conn2.cursor()
                                c2.execute("UPDATE vehicles SET status='Delivered', delivery_date=%s, handled_by=%s WHERE id=%s",
                                          (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.username, v['id']))
                            st.success(f"✅ {v['tag_number']} delivered")
                            st.rerun()

def page_reports():
    st.markdown("<h2>📊 Reports & Statistics</h2>", unsafe_allow_html=True)
    st.subheader("📅 Date Filters")
    col1, col2, col3, col4 = st.columns(4)
    with col1: filter_type = st.selectbox("Filter by", ["Today", "Yesterday", "This Week", "Last Week", "This Month", "Last Month", "This Year", "Custom Range"])
    with col2: start_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=30)) if filter_type == "Custom Range" else None
    with col3: end_date = st.date_input("End Date", value=datetime.now().date()) if filter_type == "Custom Range" else None
    with col4: service_filter = st.selectbox("Service", ["All"] + SERVICES_LIST)
    
    pg_filters = {
        "Today": "reception_date::date = CURRENT_DATE",
        "Yesterday": "reception_date::date = CURRENT_DATE - INTERVAL '1 day'",
        "This Week": "reception_date::date >= DATE_TRUNC('week', CURRENT_DATE)",
        "Last Week": "reception_date::date BETWEEN DATE_TRUNC('week', CURRENT_DATE - INTERVAL '7 days') AND DATE_TRUNC('week', CURRENT_DATE) - INTERVAL '1 day'",
        "This Month": "DATE_TRUNC('month', reception_date::timestamp) = DATE_TRUNC('month', CURRENT_DATE)",
        "Last Month": "DATE_TRUNC('month', reception_date::timestamp) = DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')",
        "This Year": "EXTRACT(YEAR FROM reception_date::timestamp) = EXTRACT(YEAR FROM CURRENT_DATE)",
        "Custom Range": f"reception_date::date BETWEEN '{start_date}' AND '{end_date}'"
    }
    date_filter = pg_filters[filter_type]
    title_period = f"{start_date} to {end_date}" if filter_type == "Custom Range" else filter_type
    
    service_condition = "AND service = %s" if service_filter != "All" else ""
    params = (service_filter,) if service_filter != "All" else ()
    with get_db() as conn:
        df_all = pd.read_sql_query(f"SELECT * FROM vehicles WHERE {date_filter} {service_condition} ORDER BY reception_date DESC", conn, params=params)
    if df_all.empty:
        st.warning("📭 No vehicles found for the selected period.")
        return
    
    total, delivered, pending, urgent = len(df_all), len(df_all[df_all['status']=='Delivered']), len(df_all[df_all['status']=='Pending']), len(df_all[df_all['is_urgent']==1])
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Vehicles", total)
    kpi2.metric("Delivered", delivered, f"{(delivered/total*100):.1f}%" if total>0 else "0%")
    kpi3.metric("Pending", pending, f"{(pending/total*100):.1f}%" if total>0 else "0%")
    kpi4.metric("Urgent", urgent)
    
    st.divider()
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1: 
        st.subheader("📊 Vehicles by Service")
        st.bar_chart(df_all['service'].value_counts())
        
    with col_chart2: 
        st.subheader("📈 Daily Trend")
        # 🔑 FIX: Convierte fechas de forma segura, ignora valores corruptos
        df_all['reception_date'] = pd.to_datetime(df_all['reception_date'], errors='coerce')
        df_all = df_all.dropna(subset=['reception_date'])
        df_all['date'] = df_all['reception_date'].dt.date
        st.line_chart(df_all.groupby('date').size())
        
    st.subheader("📋 Status Distribution")
    st.bar_chart(df_all['status'].value_counts())
    
    if delivered > 0:
        st.subheader("⏱️ Average Delivery Time")
        df_del = df_all[df_all['status']=='Delivered'].copy()
        df_del['reception_date'] = pd.to_datetime(df_del['reception_date'], errors='coerce')
        df_del['delivery_date'] = pd.to_datetime(df_del['delivery_date'], errors='coerce')
        df_del = df_del.dropna(subset=['reception_date', 'delivery_date'])
        df_del['hours'] = (df_del['delivery_date'] - df_del['reception_date']).dt.total_seconds()/3600
        st.metric("Average Hours", f"{df_del['hours'].mean():.2f}")
        st.subheader("By Service")
        st.bar_chart(df_del.groupby('service')['hours'].mean().round(2))
        
    st.divider()
    st.subheader("📋 Detailed List")
    disp = df_all[['tag_number','vin_number','service','status','reception_date','delivery_date','is_urgent']].copy()
    disp.columns = ['TAG','VIN','Service','Status','Received','Delivered','Urgent']
    disp['Urgent'] = disp['Urgent'].map({1:'🚨 Yes', 0:'No'})
    st.dataframe(disp, use_container_width=True, hide_index=True)
    
    st.subheader("💾 Export Data")
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        pd.DataFrame({'Metric':['Total','Delivered','Pending','Urgent','Period'],'Value':[total,delivered,pending,urgent,title_period]}).to_excel(writer, sheet_name='Summary', index=False)
        df_all.to_excel(writer, sheet_name='All Vehicles', index=False)
        df_all.groupby('service').agg({'id':'count','is_urgent':'sum'}).reset_index().rename(columns={'id':'Total','is_urgent':'Urgent'}).to_excel(writer, sheet_name='By Service', index=False)
        df_all.groupby('status').size().reset_index(name='Count').to_excel(writer, sheet_name='By Status', index=False)
    output.seek(0)
    st.download_button(label="📥 Download Excel", data=output, file_name=f"HARK_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
 
def page_users():
    st.markdown("<h2>👤 User Management</h2>", unsafe_allow_html=True)
    
    # Obtener usuarios
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT u.id, u.username, u.level, u.full_name, 
                       COALESCE(b.name, 'Global/Admin') as branch_name 
                FROM users u 
                LEFT JOIN branches b ON u.branch_id=b.id 
                ORDER BY u.level DESC, u.username
            """)
            users_data = c.fetchall()
            
            if users_data:
                # Convertir a DataFrame
                df = pd.DataFrame(users_data, columns=['id', 'username', 'level', 'full_name', 'branch_name'])
                st.subheader("Current Users")
                st.dataframe(df, hide_index=True, use_container_width=True)
            else:
                st.warning("⚠️ No hay usuarios registrados en la base de datos.")
    except Exception as e:
        st.error(f"❌ Error al cargar usuarios: {e}")
    
    st.divider()
    
    # Resto del código para crear usuario...
    st.subheader("Create New User")
    with st.form("create_user_form"):
        c1, c2, c3 = st.columns(3)
        with c1: 
            nu = st.text_input("Username")
        with c2: 
            np = st.text_input("Password", type="password")
        with c3: 
            nl = st.selectbox("Level", [1, 2, 3])
        
        if st.form_submit_button("Create User"):
            if nu and np:
                try:
                    with get_db() as conn:
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO users (username, password, level, full_name, branch_id) 
                            VALUES (%s, %s, %s, %s, %s)
                        """, (nu, hashlib.sha256(np.encode()).hexdigest(), nl, nu, 
                              st.session_state.branch_id if st.session_state.level < 3 else None))
                    st.success(f"User **{nu}** created.")
                    st.rerun()
                except psycopg2.IntegrityError:
                    st.error("Username already exists.")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    st.divider()
    
    # Change Password section...
    st.subheader("Change Password")
    with st.form("change_pass_form"):
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT username, full_name FROM users ORDER BY username")
                users_list = c.fetchall()
                opts = [f"{r['username']} ({r['full_name']})" for r in users_list]
            
            if opts:
                sel = st.selectbox("Select User", opts)
                np = st.text_input("New Password", type="password")
                
                if st.form_submit_button("Update Password"):
                    if np:
                        with get_db() as conn:
                            c = conn.cursor()
                            c.execute("UPDATE users SET password=%s WHERE username=%s", 
                                     (hashlib.sha256(np.encode()).hexdigest(), sel.split(" (")[0]))
                        st.success("Password updated.")
                        st.rerun()
            else:
                st.info("No users available.")
        except Exception as e:
            st.error(f"Error: {e}")
    
    st.divider()
    
    # Delete User section...
    st.subheader("Delete User")
    with st.form("delete_user_form"):
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT username, full_name, level 
                    FROM users 
                    WHERE username != %s 
                    ORDER BY username
                """, (st.session_state.username,))
                to_del = [f"{r['username']} - {r['full_name']} (L{r['level']})" for r in c.fetchall()]
            
            if not to_del:
                st.info("No other users to delete.")
            else:
                sel = st.selectbox("User to Delete", to_del)
                conf = st.checkbox("⚠️ Confirm deletion")
                
                if st.form_submit_button("Delete User", type="primary"):
                    if conf:
                        with get_db() as conn:
                            c = conn.cursor()
                            c.execute("DELETE FROM users WHERE username=%s", (sel.split(" - ")[0],))
                        st.success("User deleted.")
                        st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

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
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
        
        # Create menu list first
        if st.session_state.level >= 2:
            menu_options = ["🚦 Ingress", "🏎️ Pending", "📊 Reports"]
        else:
            menu_options = ["🚦 Ingress", "🏎️ Pending"]
        
        if st.session_state.level == 3:
            menu_options.append("👤 Users")
        
        menu = st.sidebar.radio("Menu", menu_options)
        
        if menu == "🚦 Ingress": page_ingress()
        elif menu == "🏎️ Pending": page_pending()
        elif menu == "📊 Reports": page_reports()
        elif menu == "👤 Users": page_users()

if __name__ == "__main__":
    main()
