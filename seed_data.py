import os
import sqlite3
import json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from database import get_db, init_db

# Pre-generate hashes once at module load to optimize speed
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@sachivalayam.gov.in')
ADMIN_PASS = os.environ.get('ADMIN_PASSWORD', 'admin123')
ADMIN_PW = generate_password_hash(ADMIN_PASS)
OFFICER_PW = generate_password_hash("officer123")
CITIZEN_PW = generate_password_hash("citizen123")

def seed():
    init_db()
    conn = get_db()
    try:
        cursor = conn.cursor()

        # Temporarily disable foreign keys for clean wipe & sequence reset
        cursor.execute("PRAGMA foreign_keys = OFF")
        cursor.execute("DELETE FROM activity_logs")
        cursor.execute("DELETE FROM certificate_applications")
        cursor.execute("DELETE FROM complaints")
        cursor.execute("DELETE FROM users")
        cursor.execute("DELETE FROM sachivalayams")
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('activity_logs', 'certificate_applications', 'complaints', 'users', 'sachivalayams')")
        except sqlite3.OperationalError:
            pass
        cursor.execute("PRAGMA foreign_keys = ON")

        # 1. Seed Sachivalayams
        sachivalayams = [
            ("Pedakakani Grama Sachivalayam 1", "GS-GNT-0101", "Pedakakani", "Guntur", "522509"),
            ("Benz Circle Ward Sachivalayam 12", "WS-VJA-1204", "Vijayawada Urban", "NTR Krishna", "520010"),
            ("Madhurawada Ward Sachivalayam 5", "WS-VZG-0502", "Visakhapatnam Rural", "Visakhapatnam", "530048"),
            ("Chandragiri Grama Sachivalayam 2", "GS-TPT-0205", "Chandragiri", "Tirupati", "517101")
        ]
        cursor.executemany('''
            INSERT INTO sachivalayams (name, code, mandal, district, pincode)
            VALUES (?, ?, ?, ?, ?)
        ''', sachivalayams)

        # 2. Seed Users
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Admin
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, designation, employee_id, approval_status, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("District Nodal Admin", ADMIN_EMAIL, "9988776655", "1111-2222-3333", 
              ADMIN_PW, "admin", None, "District Nodal Officer", "AP-ADM-001", "approved", now_str))
        admin_id = cursor.lastrowid

        # Approved Officer
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, designation, employee_id, approval_status, approved_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("Suresh Babu (PS)", "officer.approved@sachivalayam.gov.in", "9848022338", "2222-3333-4444", 
              OFFICER_PW, "officer", 1, "Panchayat Secretary (Grade-V)", "APGS-2023-8891", "approved", now_str, admin_id))
        approved_officer_id = cursor.lastrowid

        # Pending Officer (Waiting for Admin approval)
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, designation, employee_id, approval_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("Praveen Kumar (DA)", "officer.pending@sachivalayam.gov.in", "9440123456", "3333-4444-5555", 
              OFFICER_PW, "officer", 2, "Digital Assistant", "APWS-2024-4102", "pending"))

        # Second Approved Officer for Ward 12
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, designation, employee_id, approval_status, approved_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("K. Anitha (Welfare)", "officer.anitha@sachivalayam.gov.in", "9123456789", "4444-5555-6666",
              OFFICER_PW, "officer", 2, "Welfare & Education Assistant", "APWS-2023-7721", "approved", now_str, admin_id))

        # Citizen 1
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, approval_status, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'approved', ?)
        ''', ("K. Venkateswara Rao", "citizen@example.com", "9876543210", "4512-8890-3321", 
              CITIZEN_PW, "citizen", 1, now_str))
        citizen_id = cursor.lastrowid

        # Citizen 2
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, approval_status, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'approved', ?)
        ''', ("Lakshmi Devi", "lakshmi@example.com", "9876543211", "5623-9901-4432", 
              CITIZEN_PW, "citizen", 2, now_str))

        # 3. Seed Complaints
        complaints = [
            # In progress complaint
            ("GS-CMP-2026-101", citizen_id, 1, "Street Lighting", "Street light non-functional on Temple Street", 
             "Pole #14 near Sri Rama Temple is completely dark for 5 days. Causing difficulties for pedestrians at night.", 
             "Temple Street, Ward 3, Pedakakani", approved_officer_id, "IN_PROGRESS", 
             "Dispatched electrical linesman for ballast & LED bulb replacement.", None,
             (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), now_str, None),

            # Work completed - Pending citizen confirmation!
            ("GS-CMP-2026-102", citizen_id, 1, "Drinking Water", "Drinking water pipeline leak near Community Hall", 
             "Severe pipeline rupture wasting potable water and flooding adjacent lane.", 
             "Opposite Community Hall, Main Road, Pedakakani", approved_officer_id, "WORK_COMPLETED_PENDING_CONFIRMATION", 
             "Replaced 2-inch PVC coupling and checked water pressure. Leakage completely plugged. Please verify on site.", None,
             (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"), now_str, None),

            # Done complaint (citizen accepted)
            ("GS-CMP-2026-103", citizen_id, 1, "Sanitation", "Open drain silt accumulation & blockage", 
             "Drain overflow during morning hours near bus stand.", 
             "Bus Stand Road, Pedakakani", approved_officer_id, "DONE", 
             "Sanitation squad desilted 60 meters of drainage canal.", "Inspected site. Drain is flowing clear now. Thank you for the quick action!",
             (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"), now_str, 
             (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"))
        ]

        cursor.executemany('''
            INSERT INTO complaints (ticket_id, citizen_id, sachivalayam_id, category, title, description, location, assigned_officer_id, status, officer_resolution_notes, citizen_feedback, created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', complaints)

        # 4. Seed Certificate Applications
        cert_done_payload = json.dumps({
            "certificate_id": "AP-RES-2026-90421",
            "qr_hash": "APGS-SEC1-RES-90421-VALIDATED",
            "digital_signer": "Suresh Babu, Panchayat Secretary",
            "valid_until": "PERMANENT / 5 YEARS",
            "date_of_issue": (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        })

        cert_renewal_payload = json.dumps({
            "certificate_id": "AP-INC-2026-30219",
            "qr_hash": "APGS-SEC1-INC-30219-PROVISIONAL",
            "digital_signer": "Suresh Babu, Panchayat Secretary",
            "verified_annual_income": "95,000",
            "valid_until": (datetime.now() + timedelta(days=365)).strftime("%d-%b-%Y"),
            "date_of_issue": datetime.now().strftime("%d-%b-%Y")
        })

        certificates = [
            # Certificate Renewal - WORK_COMPLETED_PENDING_CONFIRMATION
            ("GS-CRT-2026-201", citizen_id, 1, "renewal", "Income Certificate", "K. Venkateswara Rao", "K. Ranga Rao", "Father",
             95000.0, "BC-A", "AP-INC-2025-11048", "2025-03-10", "College fee reimbursement renewal for son", 
             "D.No 4-21, Main Bazaar, Pedakakani, Guntur", approved_officer_id, "WORK_COMPLETED_PENDING_CONFIRMATION",
             "Field revenue inquiry completed. Annual household income assessed at Rs. 95,000/-. New certificate generated. Please review details and accept to finalize.",
             cert_renewal_payload, None,
             (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S"), now_str, None),

            # New Certificate - SUBMITTED
            ("GS-CRT-2026-202", citizen_id, 1, "new", "Integrated Caste & Nativity Certificate", "K. Sai Kumar", "K. Venkateswara Rao", "Father",
             None, "BC-A", None, None, "Application for Govt Competitive Examination / Polytechnic Admission", 
             "D.No 4-21, Main Bazaar, Pedakakani, Guntur", approved_officer_id, "SUBMITTED",
             None, None, None,
             (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), now_str, None),

            # New Certificate - DONE (Already accepted by citizen)
            ("GS-CRT-2026-203", citizen_id, 1, "new", "Residence Certificate", "K. Venkateswara Rao", "K. Ranga Rao", "Father",
             None, None, None, None, "Bank Loan Address Verification", 
             "D.No 4-21, Main Bazaar, Pedakakani, Guntur", approved_officer_id, "DONE",
             "Physical residence verified with local electricity bill and voter ID. Certificate officially released.",
             cert_done_payload, "All details match correctly. Downloaded certificate successfully.",
             (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S"), now_str,
             (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"))
        ]

        cursor.executemany('''
            INSERT INTO certificate_applications (application_no, citizen_id, sachivalayam_id, service_type, certificate_type, applicant_name, relation_name, relation_type, annual_income, caste_category, previous_cert_no, previous_issue_date, purpose, address, assigned_officer_id, status, officer_remarks, certificate_payload_json, citizen_feedback, created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', certificates)

        conn.commit()
    finally:
        conn.close()

if __name__ == '__main__':
    seed()
    print("Database seeded successfully with resilient dynamic keys.")
