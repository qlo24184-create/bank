import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# BANK PYTHON - 教學用互動式網路銀行
# 技術：Streamlit + SQLite + Pandas + Plotly
# 注意：僅供本機教學/展示，不可用於真實金融交易。
# ============================================================

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "bank_python.db"

st.set_page_config(
    page_title="BANK PYTHON｜智慧網路銀行",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------- 樣式 -----------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: Inter, sans-serif; }
    .stApp { background: #F4F6FA; }
    [data-testid="stSidebar"] { background: #102B4E; }
    [data-testid="stSidebar"] * { color: #F5F7FB !important; }
    .brand {
        background: linear-gradient(115deg, #102B4E 0%, #1D4775 100%);
        color: white; padding: 26px 30px; border-radius: 18px;
        margin-bottom: 22px; box-shadow: 0 8px 24px rgba(16,43,78,.12);
    }
    .brand small { color: #C8D6E8; letter-spacing: 2px; }
    .brand h1 { color: white; margin: 5px 0 2px 0; font-size: 30px; }
    .brand p { color: #D9E4F0; margin: 0; }
    .metric-card {
        background: white; padding: 18px 20px; border-radius: 15px;
        border: 1px solid #E7EBF1; min-height: 112px;
        box-shadow: 0 3px 12px rgba(20,45,75,.04);
    }
    .metric-label { color: #66758A; font-size: 13px; }
    .metric-value { color: #142F50; font-size: 25px; font-weight: 800; margin-top: 8px; }
    .metric-note { color: #7A8798; font-size: 12px; margin-top: 4px; }
    .section-title { color: #142F50; font-size: 20px; font-weight: 700; margin: 8px 0 12px; }
    div.stButton > button[kind="primary"] {
        background: #C69A45; border: 0; color: #142F50; font-weight: 700;
        border-radius: 9px; min-height: 42px;
    }
    div.stButton > button { border-radius: 9px; }
    .login-wrap {
        background: white; border: 1px solid #E7EBF1; border-radius: 18px;
        padding: 28px; box-shadow: 0 8px 30px rgba(20,45,75,.06);
    }
    .muted { color: #6B7788; font-size: 13px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------- 資料庫 -----------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    _, candidate = hash_password(password, salt)
    return secrets.compare_digest(candidate, expected_hash)


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_no TEXT NOT NULL UNIQUE,
                account_name TEXT NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0),
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_code TEXT NOT NULL UNIQUE,
                account_id INTEGER NOT NULL,
                tx_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                description TEXT NOT NULL,
                counterparty TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tx_account_date
            ON transactions(account_id, created_at);
            """
        )

        # 建立教學用示範帳號；若已存在，不覆蓋使用者資料。
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("admin",)
        ).fetchone()

        if not existing:
            salt, pw_hash = hash_password("python123")
            now = datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                """INSERT INTO users(username, display_name, salt, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("admin", "示範會員", salt, pw_hash, now),
            )
            user_id = cur.lastrowid
            cur = conn.execute(
                """INSERT INTO accounts(user_id, account_no, account_name, balance, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, "888800001", "BANK PYTHON 數位存款帳戶", 150000, now),
            )
            account_id = cur.lastrowid

            # 建立一筆初始餘額紀錄，讓帳務紀錄可追溯。
            conn.execute(
                """INSERT INTO transactions
                   (tx_code, account_id, tx_type, amount, balance_after,
                    description, counterparty, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "TX" + secrets.token_hex(5).upper(),
                    account_id,
                    "存款",
                    150000,
                    150000,
                    "示範帳戶開戶存入",
                    "BANK PYTHON",
                    now,
                ),
            )

        # 建立可供測試轉帳的收款帳戶（不提供登入）。
        receiver = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("receiver_demo",)
        ).fetchone()
        if not receiver:
            salt, pw_hash = hash_password(secrets.token_urlsafe(24))
            now = datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                """INSERT INTO users(username, display_name, salt, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("receiver_demo", "測試收款人", salt, pw_hash, now),
            )
            conn.execute(
                """INSERT INTO accounts(user_id, account_no, account_name, balance, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (cur.lastrowid, "888800002", "測試收款帳戶", 0, now),
            )


def get_user(username: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_account(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY id LIMIT 1",
            (user_id,),
        ).fetchone()


def get_transactions(account_id: int, limit: int | None = None) -> pd.DataFrame:
    sql = """
        SELECT tx_code AS 交易編號, tx_type AS 交易類型,
               amount AS 金額, balance_after AS 交易後餘額,
               description AS 摘要, counterparty AS 往來帳戶,
               created_at AS 交易時間
        FROM transactions
        WHERE account_id = ?
        ORDER BY created_at DESC, id DESC
    """
    params = [account_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def add_transaction(account_id: int, tx_type: str, amount: int,
                    description: str, counterparty: str = ""):
    """以單一資料庫交易更新餘額並寫入明細。amount 為正數。"""
    if amount <= 0:
        raise ValueError("金額必須大於 0。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        account = conn.execute(
            "SELECT balance FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not account:
            raise ValueError("找不到帳戶。")

        old_balance = int(account["balance"])
        if tx_type in ("提款", "轉出") and amount > old_balance:
            raise ValueError("帳戶餘額不足。")

        if tx_type in ("存款", "轉入"):
            new_balance = old_balance + amount
            signed_amount = amount
        else:
            new_balance = old_balance - amount
            signed_amount = -amount

        conn.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (new_balance, account_id),
        )
        conn.execute(
            """INSERT INTO transactions
               (tx_code, account_id, tx_type, amount, balance_after,
                description, counterparty, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "TX" + secrets.token_hex(5).upper(),
                account_id,
                tx_type,
                signed_amount,
                new_balance,
                description,
                counterparty,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return new_balance
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def transfer_money(sender_account_id: int, recipient_account_no: str, amount: int):
    """示範用帳戶間轉帳；扣款、入帳與雙方明細在同一交易中完成。"""
    if amount <= 0:
        raise ValueError("轉帳金額必須大於 0。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        sender = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (sender_account_id,)
        ).fetchone()
        recipient = conn.execute(
            "SELECT * FROM accounts WHERE account_no = ?",
            (recipient_account_no.strip(),),
        ).fetchone()

        if not recipient:
            raise ValueError("查無此收款帳號。")
        if recipient["id"] == sender_account_id:
            raise ValueError("不可轉帳給自己的同一帳戶。")
        if amount > int(sender["balance"]):
            raise ValueError("帳戶餘額不足。")

        sender_new = int(sender["balance"]) - amount
        recipient_new = int(recipient["balance"]) + amount
        now = datetime.now().isoformat(timespec="seconds")
        tx_code = "TR" + secrets.token_hex(5).upper()

        conn.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (sender_new, sender_account_id),
        )
        conn.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (recipient_new, recipient["id"]),
        )
        conn.execute(
            """INSERT INTO transactions
               (tx_code, account_id, tx_type, amount, balance_after,
                description, counterparty, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx_code, sender_account_id, "轉出", -amount, sender_new,
                "網路銀行轉帳", recipient_account_no, now,
            ),
        )
        conn.execute(
            """INSERT INTO transactions
               (tx_code, account_id, tx_type, amount, balance_after,
                description, counterparty, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx_code, recipient["id"], "轉入", amount, recipient_new,
                "網路銀行轉帳", sender["account_no"], now,
            ),
        )
        conn.commit()
        return tx_code, sender_new
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ----------------------------- 共用 UI -----------------------------
def money(value):
    return f"NT$ {int(value):,}"


def page_header(title, subtitle=""):
    st.markdown(
        f"""
        <div class="brand">
            <small>BANK PYTHON · DIGITAL BANKING</small>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label, value, note=""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------- 登入 -----------------------------
def login_page():
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        st.markdown(
            """
            <div class="brand" style="text-align:center;">
                <div style="font-size:38px;">🏦</div>
                <small>BANK PYTHON</small>
                <h1>智慧網路銀行</h1>
                <p>安全、便利、即時的個人金融管理平台</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
        st.subheader("會員登入")
        with st.form("login_form"):
            username = st.text_input("使用者帳號", placeholder="請輸入帳號")
            password = st.text_input(
                "登入密碼", type="password", placeholder="請輸入密碼"
            )
            submitted = st.form_submit_button(
                "登入網路銀行", type="primary", use_container_width=True
            )
        st.markdown("</div>", unsafe_allow_html=True)

        if submitted:
            user = get_user(username.strip())
            if user and verify_password(password, user["salt"], user["password_hash"]):
                st.session_state.authenticated = True
                st.session_state.user_id = int(user["id"])
                st.session_state.display_name = user["display_name"]
                st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新輸入。")

        st.info("教學測試帳號：admin　／　密碼：python123")
        st.caption("本系統為教學展示，不會連線至任何真實銀行。")


# ----------------------------- 儀表板 -----------------------------
def dashboard(account):
    page_header("帳戶總覽", "掌握資產概況與近期帳務動態")
    df = get_transactions(account["id"])
    balance = int(account["balance"])

    if df.empty:
        income = expense = 0
    else:
        income = int(df.loc[df["金額"] > 0, "金額"].sum())
        expense = abs(int(df.loc[df["金額"] < 0, "金額"].sum()))

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("目前帳戶餘額", money(balance), "可用存款餘額")
    with c2:
        metric_card("累計存入／轉入", money(income), "依目前交易紀錄計算")
    with c3:
        metric_card("累計支出／轉出", money(expense), "依目前交易紀錄計算")

    st.write("")
    col_chart, col_recent = st.columns([1.25, 1])
    with col_chart:
        st.markdown('<div class="section-title">收支概況</div>', unsafe_allow_html=True)
        if df.empty:
            st.info("目前尚無交易資料。")
        else:
            chart_df = df.copy()
            chart_df["交易時間"] = pd.to_datetime(chart_df["交易時間"])
            chart_df["月份"] = chart_df["交易時間"].dt.to_period("M").astype(str)
            monthly = (
                chart_df.assign(
                    存入=chart_df["金額"].clip(lower=0),
                    支出=chart_df["金額"].clip(upper=0).abs(),
                )
                .groupby("月份", as_index=False)[["存入", "支出"]]
                .sum()
                .sort_values("月份")
            )
            fig = px.bar(
                monthly, x="月份", y=["存入", "支出"], barmode="group",
                labels={"value": "金額（元）", "月份": "月份", "variable": "類別"},
                color_discrete_sequence=["#C69A45", "#315D89"],
            )
            fig.update_layout(
                paper_bgcolor="white", plot_bgcolor="white",
                margin=dict(l=10, r=10, t=20, b=10),
                legend_title_text="",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_recent:
        st.markdown('<div class="section-title">近期交易</div>', unsafe_allow_html=True)
        if df.empty:
            st.info("尚無交易紀錄。")
        else:
            recent = df.head(5).copy()
            recent["金額"] = recent["金額"].map(money)
            st.dataframe(
                recent[["交易時間", "交易類型", "金額", "摘要"]],
                use_container_width=True,
                hide_index=True,
            )

    st.caption(f"帳戶名稱：{account['account_name']}　｜　帳號：{account['account_no']}")


# ----------------------------- 存提款 -----------------------------
def deposit_withdraw(account):
    page_header("存款與提款", "快速管理帳戶資金")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 存款")
        with st.form("deposit_form"):
            deposit_amount = st.number_input(
                "存款金額（新臺幣）", min_value=100, max_value=2_000_000,
                value=1000, step=100, key="deposit_amount",
            )
            deposit_note = st.text_input("存款備註", value="本人存款")
            deposit_submit = st.form_submit_button(
                "確認存款", type="primary", use_container_width=True
            )
        if deposit_submit:
            try:
                new_balance = add_transaction(
                    account["id"], "存款", int(deposit_amount),
                    deposit_note.strip() or "存款",
                )
                st.success(f"存款成功！目前餘額：{money(new_balance)}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with col2:
        st.markdown("### 提款")
        st.write(f"目前餘額：**{money(account['balance'])}**")
        with st.form("withdraw_form"):
            withdraw_amount = st.number_input(
                "提款金額（新臺幣）", min_value=100, max_value=2_000_000,
                value=1000, step=100, key="withdraw_amount",
            )
            withdraw_note = st.text_input("提款備註", value="生活支出")
            withdraw_submit = st.form_submit_button(
                "確認提款", type="primary", use_container_width=True
            )
        if withdraw_submit:
            try:
                new_balance = add_transaction(
                    account["id"], "提款", int(withdraw_amount),
                    withdraw_note.strip() or "提款",
                )
                st.success(f"提款成功！目前餘額：{money(new_balance)}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


# ----------------------------- 轉帳 -----------------------------
def transfer_page(account):
    page_header("轉帳服務", "將款項轉入 BANK PYTHON 測試收款帳戶")
    st.warning(
        "教學模式：僅能轉入本系統內建的測試收款帳號。"
        "請勿輸入真實銀行帳號或真實個人金融資料。"
    )
    st.markdown(f"**轉出帳戶：** {account['account_no']}　　"
                f"**可用餘額：** {money(account['balance'])}")

    with st.form("transfer_form"):
        recipient = st.text_input(
            "收款帳號", placeholder="測試收款帳號：888800002"
        )
        amount = st.number_input(
            "轉帳金額（新臺幣）", min_value=100, max_value=2_000_000,
            value=1000, step=100,
        )
        memo = st.text_input("轉帳備註", value="一般轉帳")
        confirm = st.checkbox("我已確認收款帳號及轉帳金額")
        submitted = st.form_submit_button(
            "確認轉帳", type="primary", use_container_width=True
        )

    if submitted:
        if not confirm:
            st.error("請先勾選確認事項。")
        else:
            try:
                tx_code, new_balance = transfer_money(
                    account["id"], recipient, int(amount)
                )
                st.success(
                    f"模擬轉帳成功！交易編號：{tx_code}；"
                    f"目前餘額：{money(new_balance)}"
                )
                st.caption(f"備註：{memo}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


# ----------------------------- 交易紀錄 -----------------------------
def history_page(account):
    page_header("交易紀錄", "查詢存款、提款及轉帳明細")
    df = get_transactions(account["id"])

    if df.empty:
        st.info("目前沒有交易紀錄。")
        return

    col1, col2 = st.columns(2)
    with col1:
        tx_types = ["全部"] + sorted(df["交易類型"].dropna().unique().tolist())
        selected_type = st.selectbox("交易類型", tx_types)
    with col2:
        search_text = st.text_input("搜尋摘要或交易編號")

    filtered = df.copy()
    if selected_type != "全部":
        filtered = filtered[filtered["交易類型"] == selected_type]
    if search_text.strip():
        needle = search_text.strip()
        filtered = filtered[
            filtered["摘要"].astype(str).str.contains(needle, case=False)
            | filtered["交易編號"].astype(str).str.contains(needle, case=False)
        ]

    display = filtered.copy()
    display["金額"] = display["金額"].map(money)
    display["交易後餘額"] = display["交易後餘額"].map(money)
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(f"共 {len(filtered)} 筆紀錄")


# ----------------------------- 收支分析 -----------------------------
def analytics_page(account):
    page_header("收支分析", "以圖表檢視帳戶資金流向")
    df = get_transactions(account["id"])
    if df.empty:
        st.info("目前尚無足夠資料可供分析。")
        return

    df["交易時間"] = pd.to_datetime(df["交易時間"])
    df["月份"] = df["交易時間"].dt.to_period("M").astype(str)
    df["收支"] = df["金額"].apply(lambda x: "收入／存入" if x > 0 else "支出／轉出")
    df["絕對金額"] = df["金額"].abs()

    monthly = (
        df.assign(
            收入=df["金額"].clip(lower=0),
            支出=df["金額"].clip(upper=0).abs(),
        )
        .groupby("月份", as_index=False)[["收入", "支出"]]
        .sum()
        .sort_values("月份")
    )

    st.markdown("### 每月收支比較")
    fig1 = px.bar(
        monthly, x="月份", y=["收入", "支出"], barmode="group",
        color_discrete_sequence=["#C69A45", "#315D89"],
        labels={"value": "金額（元）", "月份": "月份", "variable": "收支類別"},
    )
    fig1.update_layout(paper_bgcolor="white", plot_bgcolor="white")
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("### 收入與支出比例")
    totals = df.groupby("收支", as_index=False)["絕對金額"].sum()
    if totals["絕對金額"].sum() > 0:
        fig2 = px.pie(
            totals, names="收支", values="絕對金額", hole=0.58,
            color_discrete_sequence=["#C69A45", "#315D89"],
        )
        fig2.update_layout(paper_bgcolor="white")
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### 每日帳戶餘額變化（依交易紀錄）")
    daily = (
        df.sort_values("交易時間")
        .groupby(df["交易時間"].dt.date, as_index=False)
        .tail(1)
        .sort_values("交易時間")
    )
    fig3 = px.line(
        daily, x="交易時間", y="交易後餘額", markers=True,
        labels={"交易時間": "交易日期", "交易後餘額": "交易後餘額（元）"},
    )
    fig3.update_traces(line=dict(color="#315D89", width=3))
    fig3.update_layout(paper_bgcolor="white", plot_bgcolor="white")
    st.plotly_chart(fig3, use_container_width=True)


# ----------------------------- 主程式 -----------------------------
def main():
    init_db()

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        login_page()
        return

    account = get_account(st.session_state.user_id)
    if not account:
        st.error("找不到會員帳戶，請重新登入。")
        st.session_state.authenticated = False
        st.rerun()
        return

    with st.sidebar:
        st.markdown("## 🏦 BANK PYTHON")
        st.caption("智慧網路銀行")
        st.divider()
        st.write(f"您好，{st.session_state.display_name}")
        st.caption(f"帳號：{account['account_no']}")
        menu = st.radio(
            "功能選單",
            [
                "資產儀表板",
                "存款與提款",
                "轉帳服務",
                "交易紀錄",
                "收支圖表",
            ],
        )
        st.divider()
        if st.button("登出系統", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.pop("user_id", None)
            st.session_state.pop("display_name", None)
            st.rerun()
        st.caption("Demo environment · 僅供教學使用")

    # 每次切換頁面重新讀取帳戶餘額，避免顯示舊資料。
    account = get_account(st.session_state.user_id)

    if menu == "資產儀表板":
        dashboard(account)
    elif menu == "存款與提款":
        deposit_withdraw(account)
    elif menu == "轉帳服務":
        transfer_page(account)
    elif menu == "交易紀錄":
        history_page(account)
    elif menu == "收支圖表":
        analytics_page(account)

    st.divider()
    st.caption(
        "© BANK PYTHON｜Python 教學專案。"
        "本系統為模擬環境，不提供真實金融服務。"
    )


if __name__ == "__main__":
    main()
