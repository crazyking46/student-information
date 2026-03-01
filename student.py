import os
import sqlite3
import hashlib
import hmac
import binascii
import base64
from typing import Optional, Tuple, List
import streamlit as st
import pandas as pd

DB_NAME = "students.db"


def get_conn():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass
    return conn


def get_query_params() -> dict:
    try:
        # New API (Streamlit >= 1.30)
        return dict(st.query_params)
    except Exception:
        try:
            return st.experimental_get_query_params()
        except Exception:
            return {}


def set_query_params(**kwargs):
    try:
        for k, v in kwargs.items():
            st.query_params[k] = v
    except Exception:
        try:
            st.experimental_set_query_params(**kwargs)
        except Exception:
            pass


def apply_global_css():
    if st.session_state.get("_css_applied"):
        return
    st.markdown(
        """
        <style>
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stAppDeployButton"] { display: none !important; }
        #MainMenu { display: none !important; }
        header { display: none !important; }
        footer { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_css_applied"] = True


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            reg_no TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            year INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS marks (
            reg_no TEXT PRIMARY KEY,
            subject1 INTEGER NOT NULL,
            subject2 INTEGER NOT NULL,
            subject3 INTEGER NOT NULL,
            subject4 INTEGER NOT NULL,
            subject5 INTEGER NOT NULL,
            total INTEGER NOT NULL,
            average REAL NOT NULL,
            grade TEXT NOT NULL,
            FOREIGN KEY (reg_no) REFERENCES students(reg_no) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


def user_count() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    c = cur.fetchone()[0]
    conn.close()
    return int(c)


def pbkdf2_hash(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
    s = os.urandom(16) if salt is None else salt
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), s, 200000)
    return binascii.hexlify(dk).decode("utf-8"), binascii.hexlify(s).decode("utf-8")


def create_user(username: str, password: str, role: str) -> bool:
    if not username or not password:
        return False
    ph, salt_hex = pbkdf2_hash(password)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            (username.strip(), ph, salt_hex, role),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user(username: str) -> Optional[Tuple[str, str, str, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT username, password_hash, salt, role FROM users WHERE username=?",
        (username,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def verify_user(username: str, password: str) -> Optional[str]:
    row = get_user(username)
    if not row:
        return None
    _, stored_hash, salt_hex, role = row
    salt = binascii.unhexlify(salt_hex.encode("utf-8"))
    ph, _ = pbkdf2_hash(password, salt)
    if hmac.compare_digest(ph, stored_hash):
        return role
    return None


def update_user_password(username: str, new_password: str) -> bool:
    ph, salt_hex = pbkdf2_hash(new_password)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash=?, salt=? WHERE username=?", (ph, salt_hex, username.strip()))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def list_students() -> List[Tuple[str, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT reg_no, name FROM students ORDER BY reg_no")
    rows = cur.fetchall()
    conn.close()
    return rows


def add_or_update_student(reg_no: str, name: str, department: str, year: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO students (reg_no, name, department, year)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(reg_no) DO UPDATE SET
            name=excluded.name,
            department=excluded.department,
            year=excluded.year
        """,
        (reg_no.strip(), name.strip(), department.strip(), int(year)),
    )
    conn.commit()
    conn.close()


def delete_student(reg_no: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE reg_no=?", (reg_no,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def grade_for(avg: float) -> str:
    if avg >= 90:
        return "A+"
    if avg >= 80:
        return "A"
    if avg >= 70:
        return "B"
    if avg >= 60:
        return "C"
    if avg >= 50:
        return "D"
    return "F"


def add_or_update_marks(reg_no: str, s1: int, s2: int, s3: int, s4: int, s5: int):
    total = int(s1) + int(s2) + int(s3) + int(s4) + int(s5)
    average = round(total / 5.0, 2)
    grade = grade_for(average)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO marks (reg_no, subject1, subject2, subject3, subject4, subject5, total, average, grade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(reg_no) DO UPDATE SET
            subject1=excluded.subject1,
            subject2=excluded.subject2,
            subject3=excluded.subject3,
            subject4=excluded.subject4,
            subject5=excluded.subject5,
            total=excluded.total,
            average=excluded.average,
            grade=excluded.grade
        """,
        (reg_no, int(s1), int(s2), int(s3), int(s4), int(s5), total, average, grade),
    )
    conn.commit()
    conn.close()
    return total, average, grade


def get_results(search: Optional[str] = None) -> pd.DataFrame:
    conn = get_conn()
    base = """
        SELECT s.reg_no, s.name, s.department, s.year,
               m.subject1, m.subject2, m.subject3, m.subject4, m.subject5,
               m.total, m.average, m.grade
        FROM students s
        LEFT JOIN marks m ON s.reg_no = m.reg_no
    """
    params: Tuple = ()
    if search:
        base += " WHERE s.reg_no LIKE ? OR s.name LIKE ? OR s.department LIKE ?"
        q = f"%{search.strip()}%"
        params = (q, q, q)
    base += " ORDER BY s.reg_no"
    df = pd.read_sql_query(base, conn, params=params)
    conn.close()
    return df


def page_register_initial():
    st.title("Create Admin Account")
    with st.form("initial_admin"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Create Admin")
        if submitted:
            ok = create_user(username.strip(), password, "admin")
            if ok:
                st.success("Admin created. Please log in.")
                st.session_state["show_login"] = True
            else:
                st.error("Username already exists or invalid input")


def page_login() -> bool:
    st.markdown(
        """
        <style>
        :root { --accent: #F2C94C; --bg: #0f1b14; --text: #EAEAEA; }
        .stApp { background: radial-gradient(80% 120% at 0% 0%, #0d1b16 0%, #0a1210 100%); }
        .block-container { padding-top: 0.75rem; }
        .login-title { font-size: 2rem; color: var(--accent); font-weight: 800; margin-bottom: .2rem; }
        .login-sub { color: #cfcfcf; font-size: clamp(.9rem, 1.8vw, 1rem); margin-bottom: 1.2rem; display: inline-flex; align-items: baseline; gap: .35rem; flex-wrap: wrap; line-height: 1.3; }
        .login sigma {}
        .login-sub a, .login-sub span { color: var(--accent); text-decoration: none; font-weight: 700; cursor: pointer; display: inline-block; padding: .1rem .5rem; border-radius: 9999px; border: 1px solid transparent; transition: all .15s ease; }
        .login-sub a:hover, .login-sub span:hover { text-decoration: none; background: rgba(242,201,76,.15); border-color: rgba(242,201,76,.6); }
        .login-sub a:active, .login-sub span:active { transform: translateY(1px); }
        .stTextInput>div>div>input { border:1.5px solid var(--accent); border-radius:9999px; color: var(--text); background:#0d1310; }
        .stTextInput>div>label { color:#c8c8c8; }
        .stButton>button { background: var(--accent); color:#0b0b0b; border-radius: 9999px; border:none; padding:.6rem 1.2rem; font-weight:700; }
        .stButton>button:hover { filter: brightness(0.95); }
        .avatar { width: 260px; height: 260px; border-radius: 50%; background: var(--accent); display:flex; align-items:center; justify-content:center; overflow:hidden; box-shadow:0 0 0 6px #f5d64f33; margin: 1rem auto 0; }
        .avatar img { width: 100%; height: 100%; object-fit: cover; display:block; }
        .panda { width: 260px; height: 260px; border-radius: 50%; background: var(--accent); display:flex; align-items:center; justify-content:center; overflow:hidden; box-shadow:0 0 0 6px #f5d64f33; margin: 1rem auto 0; }
        .panda span { font-size: 140px; display:block; }
        .forgot { text-align:right; color:#f2c94c; font-size: clamp(.85rem, 1.6vw, .95rem); padding: .1rem .25rem; display: inline-block; }
        .forgot:hover { text-decoration: underline; cursor: pointer; }
        @media (max-width: 900px) {
            .block-container { padding-top: 1rem; }
            .login-title { font-size: clamp(1.6rem, 5vw, 2rem); text-align: center; }
            .login-sub { justify-content: center; text-align: center; padding: 0 .5rem; }
            .stButton>button { width: 100%; }
            .panda, .avatar { width: 200px; height: 200px; margin-top: .75rem; }
            .panda span { font-size: 110px; }
        }
        @media (orientation: landscape) and (min-width: 901px) {
            .block-container { padding-top: 0.5rem; }
        }
        @media (max-width: 480px) {
            .panda, .avatar { width: 160px; height: 160px; margin-top: .5rem; }
            .panda span { font-size: 90px; }
            .forgot { width: 100%; text-align: center; margin-top: .4rem; }
            .login-sub { width: 100%; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns([3, 2])
    with left:
        st.markdown('<div class="login-title">WELCOME BACK!</div>', unsafe_allow_html=True)
        st.markdown("<div class='login-sub'>Don't have an account, <a href='?view=signup'>Sign up</a></div>", unsafe_allow_html=True)
        default_username = st.session_state.get("remember_user", "")
        username = st.text_input("Username", value=default_username, placeholder="example@gmail.com", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        c1, c2 = st.columns([1, 1])
        with c1:
            remember = st.checkbox("Remember me", value=st.session_state.get("remember_me", False))
        with c2:
            st.markdown('<div class="forgot"><a href="?view=forgot" style="color:inherit;text-decoration:none;">Forget password?</a></div>', unsafe_allow_html=True)
        login = st.button("Sign In")
        reset = st.button("Reset")
    with right:
        assets_dir = "assets"
        os.makedirs(assets_dir, exist_ok=True)
        avatar_path = os.path.join(assets_dir, "login_avatar")
        img_src = None
        env_img = os.getenv("LOGIN_AVATAR")
        if env_img and os.path.exists(env_img):
            with open(env_img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                mime = "image/png" if env_img.lower().endswith(".png") else "image/jpeg"
                img_src = f"data:{mime};base64,{b64}"
        if not img_src:
            for ext in (".png", ".jpg", ".jpeg"):
                p = avatar_path + ext
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                        mime = "image/png" if ext == ".png" else "image/jpeg"
                        img_src = f"data:{mime};base64,{b64}"
                    break
        if img_src:
            st.markdown(f'<div class="avatar"><img src="{img_src}" alt="avatar"/></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="panda"><span>🐼</span></div>', unsafe_allow_html=True)
    if reset:
        for k in ["auth", "user", "remember_user", "remember_me"]:
            if k in st.session_state:
                st.session_state.pop(k)
        st.rerun()
    if login:
        role = verify_user(username.strip(), password)
        if role:
            if remember:
                st.session_state["remember_me"] = True
                st.session_state["remember_user"] = username.strip()
            else:
                st.session_state.pop("remember_me", None)
                st.session_state.pop("remember_user", None)
            st.session_state["auth"] = True
            st.session_state["user"] = {"username": username.strip(), "role": role}
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid credentials")
    return st.session_state.get("auth", False)


def page_signup():
    st.markdown('<div class="login-title">Create Your Account</div>', unsafe_allow_html=True)
    with st.form("signup_form"):
        username = st.text_input("Username (email recommended)")
        pw1 = st.text_input("Password", type="password")
        pw2 = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Sign Up")
        if submitted:
            if not username or not pw1:
                st.error("Username and password are required")
            elif pw1 != pw2:
                st.error("Passwords do not match")
            else:
                ok = create_user(username.strip(), pw1, "staff")
                if ok:
                    st.success("Account created. Please sign in.")
                    set_query_params(view="login")
                    st.rerun()
                else:
                    st.error("Username already exists")
    st.markdown("<div class='login-sub'>Already have an account? <a href='?view=login'>Sign in</a></div>", unsafe_allow_html=True)


def page_forgot():
    st.markdown('<div class="login-title">Reset Password</div>', unsafe_allow_html=True)
    st.caption("Enter your username and a new password. A reset key is required.")
    with st.form("forgot_form"):
        username = st.text_input("Username")
        new_pw1 = st.text_input("New Password", type="password")
        new_pw2 = st.text_input("Confirm New Password", type="password")
        reset_key = st.text_input("Reset Key", type="password", help="Ask your admin for the reset key")
        submitted = st.form_submit_button("Reset Password")
        if submitted:
            master = os.getenv("ADMIN_RESET_KEY", "reset123")
            if reset_key != master:
                st.error("Invalid reset key")
            elif new_pw1 != new_pw2:
                st.error("Passwords do not match")
            else:
                if update_user_password(username.strip(), new_pw1):
                    st.success("Password updated. Please sign in.")
                    set_query_params(view="login")
                    st.rerun()
                else:
                    st.error("Username not found")
    st.markdown("<div class='login-sub'><a href='?view=login'>Back to Login</a></div>", unsafe_allow_html=True)


def page_add_student():
    st.header("Add Student")
    with st.form("student_form", clear_on_submit=False):
        reg_no = st.text_input("Register Number")
        name = st.text_input("Name")
        department = st.selectbox("Department", ["CSE", "IT", "ECE", "EEE", "MECH", "CIVIL", "OTHER"], index=0)
        year = st.selectbox("Year", [1, 2, 3, 4], index=0)
        submitted = st.form_submit_button("Save")
        if submitted:
            if reg_no and name:
                add_or_update_student(reg_no, name, department, int(year))
                st.success("Student saved")
            else:
                st.error("Provide Register Number and Name")


def page_add_marks():
    st.header("Add Marks")
    students = list_students()
    if not students:
        st.info("No students found")
        with st.expander("Add New Student"):
            with st.form("quick_add_student"):
                q_reg = st.text_input("Register Number")
                q_name = st.text_input("Name")
                q_dept = st.selectbox("Department", ["CSE", "IT", "ECE", "EEE", "MECH", "CIVIL", "OTHER"], index=0, key="q_dept")
                q_year = st.selectbox("Year", [1, 2, 3, 4], index=0, key="q_year")
                q_submit = st.form_submit_button("Create Student")
                if q_submit and q_reg and q_name:
                    add_or_update_student(q_reg, q_name, q_dept, int(q_year))
                    st.success("Student created")
                    st.rerun()
        return
    mapping = {f"{r} - {n}": r for r, n in students}
    selected = st.selectbox("Student", list(mapping.keys()))
    reg_no = mapping[selected]
    c1, c2 = st.columns([1, 2])
    with c1:
        confirm_remove = st.checkbox("Confirm remove")
        if st.button("Remove Student", type="primary"):
            if confirm_remove:
                if delete_student(reg_no):
                    st.success("Student removed")
                    st.rerun()
                else:
                    st.error("Failed to remove student")
            else:
                st.warning("Check confirm remove to proceed")
    with c2:
        with st.expander("Add New Student"):
            with st.form("inline_add_student"):
                n_reg = st.text_input("Register Number", key="n_reg")
                n_name = st.text_input("Name", key="n_name")
                n_dept = st.selectbox("Department", ["CSE", "IT", "ECE", "EEE", "MECH", "CIVIL", "OTHER"], index=0, key="n_dept_inline")
                n_year = st.selectbox("Year", [1, 2, 3, 4], index=0, key="n_year_inline")
                n_submit = st.form_submit_button("Create Student")
                if n_submit and n_reg and n_name:
                    add_or_update_student(n_reg, n_name, n_dept, int(n_year))
                    st.success("Student created")
                    st.rerun()
    with st.form("marks_form", clear_on_submit=False):
        s1 = st.number_input("Advance Network", min_value=0, max_value=100, value=0, step=1)
        s2 = st.number_input("Data Mining", min_value=0, max_value=100, value=0, step=1)
        s3 = st.number_input("R Program", min_value=0, max_value=100, value=0, step=1)
        s4 = st.number_input("IOT", min_value=0, max_value=100, value=0, step=1)
        s5 = st.number_input("Mini Project", min_value=0, max_value=100, value=0, step=1)
        submitted = st.form_submit_button("Save Marks")
        if submitted:
            total, avg, grade = add_or_update_marks(reg_no, int(s1), int(s2), int(s3), int(s4), int(s5))
            st.success(f"Saved. Total: {total}, Average: {avg}, Grade: {grade}")


def page_results():
    st.header("Results")
    search = st.text_input("Search by Reg No, Name, or Department")
    df = get_results(search if search else None)
    if not df.empty:
        renamed = df.rename(
            columns={
                "subject1": "Advance Network",
                "subject2": "Data Mining",
                "subject3": "R Program",
                "subject4": "IOT",
                "subject5": "Mini Project",
            }
        )
        st.dataframe(renamed, use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)
    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name="results.csv", mime="text/csv")


def page_user_management():
    st.header("User Management")
    u = st.session_state.get("user", {})
    if u.get("role") != "admin":
        st.info("Only admin can create users")
        return
    with st.form("create_user"):
        username = st.text_input("New Username")
        password = st.text_input("New Password", type="password")
        role = st.selectbox("Role", ["admin", "staff"], index=1)
        submitted = st.form_submit_button("Create User")
        if submitted:
            ok = create_user(username.strip(), password, role)
            if ok:
                st.success("User created")
            else:
                st.error("Failed to create user")


def main():
    st.set_page_config(page_title="Student Result Management", layout="wide")
    apply_global_css()
    init_db()
    if user_count() == 0:
        page_register_initial()
        return
    if not st.session_state.get("auth"):
        params = get_query_params()
        view = params.get("view", ["login"] if isinstance(params, dict) else "login")
        if isinstance(view, list):
            view = view[0] if view else "login"
        if view == "signup":
            page_signup()
            return
        if view == "forgot":
            page_forgot()
            return
        if not page_login():
            return
    st.sidebar.title("Menu")
    choice = st.sidebar.radio(
        "Go to",
        ["Add Student", "Add Marks", "View Results", "User Management", "Logout"],
    )
    if choice == "Add Student":
        page_add_student()
    elif choice == "Add Marks":
        page_add_marks()
    elif choice == "View Results":
        page_results()
    elif choice == "User Management":
        page_user_management()
    elif choice == "Logout":
        for k in ["auth", "user"]:
            if k in st.session_state:
                st.session_state.pop(k)
        st.rerun()


if __name__ == "__main__":
    main()

