import os
import sqlite3
import hashlib
import hmac
import binascii
from typing import Optional, Tuple, List
import streamlit as st
import pandas as pd

DB_NAME = "students.db"


def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


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
    st.title("Admin Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    col1, col2 = st.columns(2)
    with col1:
        login = st.button("Login")
    with col2:
        reset = st.button("Reset")
    if reset:
        for k in ["auth", "user"]:
            if k in st.session_state:
                st.session_state.pop(k)
        st.rerun()
    if login:
        role = verify_user(username.strip(), password)
        if role:
            st.session_state["auth"] = True
            st.session_state["user"] = {"username": username.strip(), "role": role}
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid credentials")
    return st.session_state.get("auth", False)


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
        return
    mapping = {f"{r} - {n}": r for r, n in students}
    selected = st.selectbox("Student", list(mapping.keys()))
    reg_no = mapping[selected]
    with st.form("marks_form", clear_on_submit=False):
        s1 = st.number_input("Subject 1", min_value=0, max_value=100, value=0, step=1)
        s2 = st.number_input("Subject 2", min_value=0, max_value=100, value=0, step=1)
        s3 = st.number_input("Subject 3", min_value=0, max_value=100, value=0, step=1)
        s4 = st.number_input("Subject 4", min_value=0, max_value=100, value=0, step=1)
        s5 = st.number_input("Subject 5", min_value=0, max_value=100, value=0, step=1)
        submitted = st.form_submit_button("Save Marks")
        if submitted:
            total, avg, grade = add_or_update_marks(reg_no, int(s1), int(s2), int(s3), int(s4), int(s5))
            st.success(f"Saved. Total: {total}, Average: {avg}, Grade: {grade}")


def page_results():
    st.header("Results")
    search = st.text_input("Search by Reg No, Name, or Department")
    df = get_results(search if search else None)
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
    init_db()
    if user_count() == 0:
        page_register_initial()
        return
    if not st.session_state.get("auth"):
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

