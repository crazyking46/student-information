import os
import sqlite3
from typing import List, Tuple, Optional
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


def list_students() -> List[Tuple[str, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT reg_no, name FROM students ORDER BY reg_no")
    rows = cur.fetchall()
    conn.close()
    return rows


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


def add_or_update_marks(
    reg_no: str, s1: int, s2: int, s3: int, s4: int, s5: int
) -> Tuple[int, float, str]:
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


def clear_auth():
    if "auth" in st.session_state:
        st.session_state.pop("auth")


def require_auth() -> bool:
    if st.session_state.get("auth") is True:
        return True
    st.title("Admin Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    col1, col2 = st.columns(2)
    with col1:
        login = st.button("Login")
    with col2:
        reset = st.button("Reset")
    if reset:
        clear_auth()
        st.experimental_rerun()
    env_user = os.getenv("ADMIN_USERNAME", "admin")
    env_pass = os.getenv("ADMIN_PASSWORD", "admin")
    if login:
        if username == env_user and password == env_pass:
            st.session_state["auth"] = True
            st.success("Login successful")
            st.experimental_rerun()
        else:
            st.error("Invalid credentials")
    return False


def page_add_student():
    st.header("Add Student")
    with st.form("student_form", clear_on_submit=False):
        reg_no = st.text_input("Register Number")
        name = st.text_input("Name")
        department = st.selectbox(
            "Department",
            ["CSE", "IT", "ECE", "EEE", "MECH", "CIVIL", "OTHER"],
            index=0,
        )
        year = st.selectbox("Year", [1, 2, 3, 4], index=0)
        submitted = st.form_submit_button("Save")
        if submitted:
            if reg_no and name:
                add_or_update_student(reg_no, name, department, int(year))
                st.success("Student saved")
            else:
                st.error("Please provide Register Number and Name")


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


def main():
    init_db()
    st.set_page_config(page_title="Student Result Management", layout="wide")
    if not require_auth():
        return
    st.sidebar.title("Menu")
    choice = st.sidebar.radio("Go to", ["Add Student", "Add Marks", "View Results", "Logout"])
    if choice == "Add Student":
        page_add_student()
    elif choice == "Add Marks":
        page_add_marks()
    elif choice == "View Results":
        page_results()
    elif choice == "Logout":
        clear_auth()
        st.experimental_rerun()


if __name__ == "__main__":
    main()

