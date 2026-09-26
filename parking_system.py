"""
Smart Parking System - Desktop Edition
----------------------------------------
A single-file desktop app (Tkinter GUI + SQLite) that replicates the
parking entry / fee calculation / payment flow, with no web server,
no browser, and no extra installs needed - everything here ships
with a normal Python installation.

Run with:  python parking_system.py
"""

import os
import math
import sqlite3
import uuid
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, messagebox

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "parking.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS parking_bays (
    bay_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bay_number TEXT UNIQUE NOT NULL,
    zone_code TEXT DEFAULT 'ZONE-A',
    status TEXT CHECK (status IN ('AVAILABLE', 'OCCUPIED')) DEFAULT 'AVAILABLE'
);

CREATE TABLE IF NOT EXISTS parking_tariffs (
    tariff_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tariff_name TEXT NOT NULL,
    min_duration_minutes INTEGER NOT NULL,
    max_duration_minutes INTEGER,
    flat_rate_kes REAL NOT NULL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS vehicle_sessions (
    session_id TEXT PRIMARY KEY,
    plate_number TEXT NOT NULL,
    bay_id INTEGER REFERENCES parking_bays(bay_id),
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    duration_minutes INTEGER,
    total_amount_due REAL DEFAULT 0.00,
    status TEXT CHECK (status IN ('PARKED', 'COMPLETED')) DEFAULT 'PARKED'
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES vehicle_sessions(session_id),
    payment_method TEXT NOT NULL,
    transaction_reference TEXT,
    amount_paid REAL NOT NULL,
    vat_amount REAL NOT NULL,
    payment_status TEXT DEFAULT 'SUCCESSFUL',
    paid_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

SEED_TARIFFS = [
    ("Free Tier", 0, 30, 0.00),
    ("Up to 2 Hours", 31, 120, 50.00),
    ("Up to 4 Hours", 121, 240, 100.00),
    ("Up to 6 Hours", 241, 360, 300.00),
    ("Over 6 Hours", 361, None, 500.00),
]

SEED_BAYS = [
    ("A1", "ZONE-A"), ("A2", "ZONE-A"),
    ("B1", "ZONE-B"), ("B2", "ZONE-B"),
]


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM parking_tariffs;")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO parking_tariffs (tariff_name, min_duration_minutes, max_duration_minutes, flat_rate_kes) VALUES (?, ?, ?, ?);",
            SEED_TARIFFS,
        )

    cur.execute("SELECT COUNT(*) FROM parking_bays;")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO parking_bays (bay_number, zone_code) VALUES (?, ?);",
            SEED_BAYS,
        )

    conn.commit()
    conn.close()


def compute_fee(entry_time: datetime, exit_time: datetime):
    duration_minutes = math.ceil((exit_time - entry_time).total_seconds() / 60.0)
    conn = get_connection()
    row = conn.execute(
        """
        SELECT flat_rate_kes FROM parking_tariffs
        WHERE is_active = 1
          AND ? >= min_duration_minutes
          AND (? <= max_duration_minutes OR max_duration_minutes IS NULL)
        ORDER BY min_duration_minutes DESC LIMIT 1;
        """,
        (duration_minutes, duration_minutes),
    ).fetchone()
    conn.close()
    fee = float(row["flat_rate_kes"]) if row else 500.00
    return duration_minutes, fee


class ParkingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Parking System")
        self.geometry("760x560")
        self.resizable(False, False)
        self.current_quote_session_id = None
        self.current_quote_amount = None

        self._build_ui()
        self.refresh_bays()

    # ---------- UI construction ----------
    def _build_ui(self):
        style = ttk.Style(self)
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 11, "bold"))

        outer = ttk.Frame(self, padding=15)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Smart Parking System", style="Header.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Local desktop demo - SQLite backed, no server required").pack(anchor="w", pady=(0, 10))

        main = ttk.Frame(outer)
        main.pack(fill="both", expand=True)

        # ---- Left column: bay availability ----
        left = ttk.LabelFrame(main, text="Bay Availability", padding=10)
        left.pack(side="left", fill="y", padx=(0, 10))

        self.bay_tree = ttk.Treeview(left, columns=("bay", "zone", "status"), show="headings", height=14)
        self.bay_tree.heading("bay", text="Bay")
        self.bay_tree.heading("zone", text="Zone")
        self.bay_tree.heading("status", text="Status")
        self.bay_tree.column("bay", width=70, anchor="center")
        self.bay_tree.column("zone", width=90, anchor="center")
        self.bay_tree.column("status", width=90, anchor="center")
        self.bay_tree.pack()

        ttk.Button(left, text="Refresh", command=self.refresh_bays).pack(pady=(8, 0), fill="x")

        # ---- Right column: actions ----
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        # Entry section
        entry_frame = ttk.LabelFrame(right, text="1. Vehicle Entry", padding=10)
        entry_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(entry_frame, text="Plate number:").grid(row=0, column=0, sticky="w")
        self.entry_plate_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.entry_plate_var, width=20).grid(row=0, column=1, padx=8)
        ttk.Button(entry_frame, text="Record Entry", command=self.record_entry).grid(row=0, column=2)

        # Exit / quote section
        quote_frame = ttk.LabelFrame(right, text="2. Exit - Get Fee Quote", padding=10)
        quote_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(quote_frame, text="Plate number:").grid(row=0, column=0, sticky="w")
        self.quote_plate_var = tk.StringVar()
        ttk.Entry(quote_frame, textvariable=self.quote_plate_var, width=20).grid(row=0, column=1, padx=8)
        ttk.Button(quote_frame, text="Get Quote", command=self.get_quote).grid(row=0, column=2)

        self.quote_result_var = tk.StringVar(value="No quote yet.")
        ttk.Label(quote_frame, textvariable=self.quote_result_var, style="SubHeader.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        # Payment section
        pay_frame = ttk.LabelFrame(right, text="3. Confirm Payment & Open Barrier", padding=10)
        pay_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(pay_frame, text="Payment method:").grid(row=0, column=0, sticky="w")
        self.payment_method_var = tk.StringVar(value="CASH")
        ttk.Combobox(
            pay_frame, textvariable=self.payment_method_var,
            values=["CASH", "CARD", "M-PESA"], width=12, state="readonly"
        ).grid(row=0, column=1, padx=8, sticky="w")

        ttk.Label(pay_frame, text="Amount paid (Kshs):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.amount_paid_var = tk.StringVar()
        ttk.Entry(pay_frame, textvariable=self.amount_paid_var, width=15).grid(row=1, column=1, padx=8, pady=(6, 0), sticky="w")

        ttk.Button(pay_frame, text="Confirm Payment & Open Barrier", command=self.confirm_payment).grid(
            row=2, column=0, columnspan=2, pady=(10, 0), sticky="ew"
        )

        # Log
        log_frame = ttk.LabelFrame(outer, text="Activity Log", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.log_text = tk.Text(log_frame, height=7, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

    # ---------- Helpers ----------
    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def refresh_bays(self):
        for row in self.bay_tree.get_children():
            self.bay_tree.delete(row)
        conn = get_connection()
        bays = conn.execute("SELECT bay_number, zone_code, status FROM parking_bays ORDER BY bay_number;").fetchall()
        conn.close()
        for b in bays:
            self.bay_tree.insert("", "end", values=(b["bay_number"], b["zone_code"], b["status"]))

    # ---------- Actions ----------
    def record_entry(self):
        plate = self.entry_plate_var.get().strip().upper()
        if not plate:
            messagebox.showwarning("Missing plate", "Please enter a plate number.")
            return

        conn = get_connection()
        bay = conn.execute("SELECT bay_id, bay_number FROM parking_bays WHERE status = 'AVAILABLE' LIMIT 1;").fetchone()
        if not bay:
            conn.close()
            messagebox.showerror("Lot full", "No available bays right now.")
            return

        session_id = str(uuid.uuid4())
        entry_time = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO vehicle_sessions (session_id, plate_number, bay_id, entry_time, status) VALUES (?, ?, ?, ?, 'PARKED');",
            (session_id, plate, bay["bay_id"], entry_time.isoformat()),
        )
        conn.execute("UPDATE parking_bays SET status = 'OCCUPIED' WHERE bay_id = ?;", (bay["bay_id"],))
        conn.commit()
        conn.close()

        self.log(f"Entry recorded: {plate} -> bay {bay['bay_number']} (session {session_id[:8]}...)")
        self.entry_plate_var.set("")
        self.refresh_bays()

    def get_quote(self):
        plate = self.quote_plate_var.get().strip().upper()
        if not plate:
            messagebox.showwarning("Missing plate", "Please enter a plate number.")
            return

        conn = get_connection()
        session = conn.execute(
            "SELECT session_id, entry_time FROM vehicle_sessions WHERE plate_number = ? AND status = 'PARKED';",
            (plate,),
        ).fetchone()
        conn.close()

        if not session:
            messagebox.showerror("Not found", f"No parked vehicle found for plate {plate}.")
            self.quote_result_var.set("No quote yet.")
            self.current_quote_session_id = None
            return

        entry_dt = datetime.fromisoformat(session["entry_time"])
        now = datetime.now(timezone.utc)
        duration_mins, amount_due = compute_fee(entry_dt, now)

        self.current_quote_session_id = session["session_id"]
        self.current_quote_amount = amount_due
        self.quote_result_var.set(f"{plate}: {duration_mins} min parked -> Kshs {amount_due:.2f} due")
        self.amount_paid_var.set(f"{amount_due:.2f}")
        self.log(f"Quote generated: {plate} - {duration_mins} min - Kshs {amount_due:.2f}")

    def confirm_payment(self):
        if not self.current_quote_session_id:
            messagebox.showwarning("No quote", "Get a fee quote first before confirming payment.")
            return

        try:
            amount_paid = float(self.amount_paid_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid numeric amount.")
            return

        if amount_paid < self.current_quote_amount:
            messagebox.showerror(
                "Insufficient payment",
                f"Amount paid (Kshs {amount_paid:.2f}) is less than the amount due (Kshs {self.current_quote_amount:.2f})."
            )
            return

        session_id = self.current_quote_session_id
        payment_method = self.payment_method_var.get()
        vat_amount = round(amount_paid * 0.16 / 1.16, 2)
        now = datetime.now(timezone.utc)

        conn = get_connection()
        session = conn.execute("SELECT bay_id, entry_time FROM vehicle_sessions WHERE session_id = ?;", (session_id,)).fetchone()
        entry_dt = datetime.fromisoformat(session["entry_time"])
        duration_mins, amount_due = compute_fee(entry_dt, now)

        conn.execute(
            "INSERT INTO payments (session_id, payment_method, transaction_reference, amount_paid, vat_amount, payment_status) VALUES (?, ?, ?, ?, ?, 'SUCCESSFUL');",
            (session_id, payment_method, f"DEMO-{uuid.uuid4().hex[:8].upper()}", amount_paid, vat_amount),
        )
        conn.execute(
            "UPDATE vehicle_sessions SET exit_time = ?, duration_minutes = ?, total_amount_due = ?, status = 'COMPLETED' WHERE session_id = ?;",
            (now.isoformat(), duration_mins, amount_due, session_id),
        )
        conn.execute("UPDATE parking_bays SET status = 'AVAILABLE' WHERE bay_id = ?;", (session["bay_id"],))
        conn.commit()
        conn.close()

        messagebox.showinfo("Barrier Opened", "Payment confirmed. Exit barrier raised.")
        self.log(f"Payment confirmed via {payment_method} - Kshs {amount_paid:.2f} - barrier opened")

        self.current_quote_session_id = None
        self.current_quote_amount = None
        self.quote_result_var.set("No quote yet.")
        self.quote_plate_var.set("")
        self.amount_paid_var.set("")
        self.refresh_bays()


if __name__ == "__main__":
    init_db()
    app = ParkingApp()
    app.mainloop()
