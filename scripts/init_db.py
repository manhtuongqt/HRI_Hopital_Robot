#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "hospital_demo.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- tables ---
    cur.executescript("""
    PRAGMA foreign_keys = ON;

    DROP TABLE IF EXISTS visits;
    DROP TABLE IF EXISTS insurance;
    DROP TABLE IF EXISTS patients;

    CREATE TABLE patients (
        patient_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        dob_year INTEGER NOT NULL,
        phone TEXT UNIQUE NOT NULL
    );

    CREATE TABLE insurance (
        insurance_id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        valid_to TEXT NOT NULL,
        is_valid INTEGER NOT NULL,
        referral_required INTEGER NOT NULL,
        referral_present INTEGER NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
    );

    CREATE TABLE visits (
        visit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        visit_time TEXT NOT NULL,
        department TEXT NOT NULL,
        chief_complaint TEXT,
        assessment TEXT,
        plan TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
    );
    """)

    # --- seed patients (10) ---
    patients = [
        ("BN0001", "Nguyễn Mạnh Tường", 2004, "0961320818"),
        ("BN0002", "Trần Văn A", 1998, "0909123456"),
        ("BN0003", "Lê Thị B", 2001, "0987654321"),
        ("BN0004", "Phạm Minh C", 1985, "0911111111"),
        ("BN0005", "Đặng Thị D", 1992, "0922222222"),
        ("BN0006", "Võ Văn E", 1979, "0933333333"),
        ("BN0007", "Ngô Thị F", 2006, "0944444444"),
        ("BN0008", "Hoàng Văn G", 1968, "0955555555"),
        ("BN0009", "Bùi Thị H", 1999, "0966666666"),
        ("BN0010", "Đỗ Văn I", 2003, "0977777777"),
    ]
    cur.executemany("INSERT INTO patients VALUES (?,?,?,?)", patients)

    # --- seed insurance (ví dụ 10 mã, có 1 mã bạn yêu cầu 123456) ---
    insurance = [
        ("160304", "BN0001", "2025-01-01", "2026-01-01", 1, 1, 0),
        ("111111", "BN0002", "2024-01-01", "2025-01-01", 0, 1, 1),
        ("222222", "BN0003", "2025-03-01", "2026-03-01", 1, 0, 0),
        ("333333", "BN0004", "2025-05-01", "2026-05-01", 1, 1, 1),
        ("444444", "BN0005", "2025-02-01", "2025-12-31", 1, 1, 0),
        ("555555", "BN0006", "2024-12-01", "2025-12-01", 1, 0, 0),
        ("666666", "BN0007", "2025-06-01", "2026-06-01", 1, 1, 1),
        ("777777", "BN0008", "2023-01-01", "2024-01-01", 0, 1, 0),
        ("888888", "BN0009", "2025-07-01", "2026-07-01", 1, 0, 0),
        ("999999", "BN0010", "2025-08-01", "2026-08-01", 1, 1, 0),
    ]
    cur.executemany("INSERT INTO insurance VALUES (?,?,?,?,?,?,?)", insurance)

    # --- seed visits (mỗi người 1-2 lần khám) ---
    visits = [
        ("BN0001", "2025-11-20 09:15", "khoa nội", "Đau họng, ho khan, sốt nhẹ", "Viêm đường hô hấp trên (nghi ngờ). Tình trạng ổn định.", "Theo dõi, tái khám nếu nặng."),
        ("BN0001", "2025-06-03 14:10", "khoa tai mũi họng", "Ù tai, nghẹt mũi", "Viêm mũi dị ứng (nghi ngờ).", "Tái khám nếu kéo dài."),
        ("BN0002", "2025-12-10 08:40", "khoa ngoại", "Đau bụng vùng dưới phải", "Cần loại trừ viêm ruột thừa.", "Khám ngay và xét nghiệm."),
        ("BN0003", "2025-10-01 10:20", "khoa sản", "Đau bụng dưới, trễ kinh", "Cần khám chuyên khoa sản.", "Đăng ký khám và siêu âm theo chỉ định."),
        ("BN0007", "2025-09-15 16:00", "khoa nhi", "Sốt, ho, sổ mũi", "Cảm cúm/viêm hô hấp trên (nghi ngờ).", "Theo dõi, uống nước, tái khám nếu nặng."),
    ]
    cur.executemany(
        "INSERT INTO visits (patient_id, visit_time, department, chief_complaint, assessment, plan) VALUES (?,?,?,?,?,?)",
        visits
    )

    conn.commit()
    conn.close()
    print("Created DB:", DB_PATH)

if __name__ == "__main__":
    main()
