import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sachivalayam.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Sachivalayams Table (Secretariats)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sachivalayams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT NOT NULL UNIQUE,
        mandal TEXT NOT NULL,
        district TEXT NOT NULL,
        pincode TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 2. Users Table (Admin, Officers, Citizens)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL,
        aadhaar TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'officer', 'citizen')),
        sachivalayam_id INTEGER,
        designation TEXT,
        employee_id TEXT,
        approval_status TEXT NOT NULL DEFAULT 'pending' CHECK(approval_status IN ('pending', 'approved', 'rejected')),
        rejection_reason TEXT,
        approved_at TIMESTAMP,
        approved_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sachivalayam_id) REFERENCES sachivalayams (id),
        FOREIGN KEY (approved_by) REFERENCES users (id)
    )
    ''')

    # 3. Complaints Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id TEXT NOT NULL UNIQUE,
        citizen_id INTEGER NOT NULL,
        sachivalayam_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        location TEXT NOT NULL,
        assigned_officer_id INTEGER,
        status TEXT NOT NULL DEFAULT 'SUBMITTED' 
            CHECK(status IN ('SUBMITTED', 'IN_PROGRESS', 'WORK_COMPLETED_PENDING_CONFIRMATION', 'DONE', 'REWORK_REQUESTED')),
        officer_resolution_notes TEXT,
        citizen_feedback TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (citizen_id) REFERENCES users (id),
        FOREIGN KEY (sachivalayam_id) REFERENCES sachivalayams (id),
        FOREIGN KEY (assigned_officer_id) REFERENCES users (id)
    )
    ''')

    # 4. Certificate Applications Table (New & Renewal)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS certificate_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_no TEXT NOT NULL UNIQUE,
        citizen_id INTEGER NOT NULL,
        sachivalayam_id INTEGER NOT NULL,
        service_type TEXT NOT NULL CHECK(service_type IN ('new', 'renewal')),
        certificate_type TEXT NOT NULL,
        applicant_name TEXT NOT NULL,
        relation_name TEXT,
        relation_type TEXT DEFAULT 'Father',
        annual_income REAL,
        caste_category TEXT,
        previous_cert_no TEXT,
        previous_issue_date TEXT,
        purpose TEXT NOT NULL,
        address TEXT NOT NULL,
        applicant_photo TEXT,
        income_proof_doc TEXT,
        caste_proof_doc TEXT,
        supporting_doc TEXT,
        assigned_officer_id INTEGER,
        status TEXT NOT NULL DEFAULT 'SUBMITTED' 
            CHECK(status IN ('SUBMITTED', 'IN_PROGRESS', 'WORK_COMPLETED_PENDING_CONFIRMATION', 'DONE', 'REWORK_REQUESTED')),
        officer_remarks TEXT,
        certificate_payload_json TEXT,
        citizen_feedback TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (citizen_id) REFERENCES users (id),
        FOREIGN KEY (sachivalayam_id) REFERENCES sachivalayams (id),
        FOREIGN KEY (assigned_officer_id) REFERENCES users (id)
    )
    ''')

    # Migration check for existing SQLite database
    for col in ['applicant_photo', 'income_proof_doc', 'caste_proof_doc', 'supporting_doc']:
        try:
            cursor.execute(f"ALTER TABLE certificate_applications ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    # 5. Activity Logs (Audit trail for timeline)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL CHECK(entity_type IN ('complaint', 'certificate', 'officer_approval')),
        entity_id INTEGER NOT NULL,
        actor_id INTEGER,
        action TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (actor_id) REFERENCES users (id)
    )
    ''')

    # Auto-bootstrap default secretariats if table is empty
    sec_count = cursor.execute("SELECT COUNT(*) FROM sachivalayams").fetchone()[0]
    if sec_count == 0:
        default_secs = [
            ("Pedakakani Grama Sachivalayam 1", "GS-GNT-0101", "Pedakakani", "Guntur", "522509"),
            ("Benz Circle Ward Sachivalayam 12", "WS-VJA-1204", "Vijayawada Urban", "NTR Krishna", "520010"),
            ("Madhurawada Ward Sachivalayam 5", "WS-VZG-0502", "Visakhapatnam Rural", "Visakhapatnam", "530048"),
            ("Chandragiri Grama Sachivalayam 2", "GS-TPT-0205", "Chandragiri", "Tirupati", "517101")
        ]
        cursor.executemany('''
            INSERT INTO sachivalayams (name, code, mandal, district, pincode)
            VALUES (?, ?, ?, ?, ?)
        ''', default_secs)

    # Auto-bootstrap default Admin if no admin exists
    admin_exists = cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if not admin_exists:
        from werkzeug.security import generate_password_hash
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@sachivalayam.gov.in')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        admin_pw_hash = generate_password_hash(admin_pass)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, designation, employee_id, approval_status, approved_at)
            VALUES (?, ?, ?, ?, ?, 'admin', 'District Nodal Officer', 'AP-ADM-001', 'approved', ?)
        ''', ('District Nodal Admin', admin_email, '9988776655', '1111-2222-3333', admin_pw_hash, now_str))

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Sachivalayam database schema initialized successfully at:", DB_PATH)
