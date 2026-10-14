import os
import json
import random
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import get_db, init_db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sachivalayam_secret_token_key_2026')

# Uploads Configuration
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf'}

def save_uploaded_file(file_obj, prefix):
    if not file_obj or file_obj.filename == '':
        return None
    filename = secure_filename(file_obj.filename)
    if not filename:
        return None
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return None
    safe_name = f"{prefix}_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}.{ext}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    file_obj.save(save_path)
    return f"uploads/{safe_name}"

# ----------------- Decorators & Middleware ----------------- #

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login as Admin.", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def officer_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in as a Sachivalayam Officer.", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'officer':
            flash("Access restricted to Sachivalayam Officers.", "danger")
            return redirect(url_for('index'))
        
        # Verify approval status directly from database to prevent stale session
        conn = get_db()
        user = conn.execute("SELECT approval_status FROM users WHERE id = ?", (session['user_id'],)).fetchone()
        conn.close()

        if not user or user['approval_status'] != 'approved':
            session['approval_status'] = user['approval_status'] if user else 'pending'
            return redirect(url_for('officer_pending'))

        session['approval_status'] = 'approved'
        return f(*args, **kwargs)
    return decorated_function

def citizen_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in as Citizen to access services.", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'citizen':
            flash("Access restricted to Citizens.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Context processor for secretariats & user status
@app.context_processor
def inject_global_data():
    conn = get_db()
    sachivalayams = conn.execute("SELECT * FROM sachivalayams ORDER BY name ASC").fetchall()
    conn.close()
    return dict(sachivalayams=sachivalayams)

# ----------------- Public & Home Routes ----------------- #

@app.route('/')
def index():
    conn = get_db()
    stats = {
        'secretariats': conn.execute("SELECT COUNT(*) FROM sachivalayams").fetchone()[0],
        'total_complaints': conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0],
        'resolved_complaints': conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'DONE'").fetchone()[0],
        'certificates_issued': conn.execute("SELECT COUNT(*) FROM certificate_applications WHERE status = 'DONE'").fetchone()[0],
        'active_officers': conn.execute("SELECT COUNT(*) FROM users WHERE role = 'officer' AND approval_status = 'approved'").fetchone()[0],
    }
    conn.close()
    return render_template('index.html', stats=stats)

@app.route('/track', methods=['GET', 'POST'])
def track():
    query = request.args.get('q', '').strip() or request.form.get('q', '').strip()
    result = None
    item_type = None
    logs = []

    if query:
        conn = get_db()
        # Check complaints
        complaint = conn.execute('''
            SELECT c.*, s.name as sachivalayam_name, u.name as citizen_name, o.name as officer_name, o.designation as officer_designation
            FROM complaints c
            JOIN sachivalayams s ON c.sachivalayam_id = s.id
            JOIN users u ON c.citizen_id = u.id
            LEFT JOIN users o ON c.assigned_officer_id = o.id
            WHERE c.ticket_id = ?
        ''', (query,)).fetchone()

        if complaint:
            result = complaint
            item_type = 'complaint'
            logs = conn.execute('''
                SELECT l.*, u.name as actor_name, u.role as actor_role
                FROM activity_logs l
                LEFT JOIN users u ON l.actor_id = u.id
                WHERE l.entity_type = 'complaint' AND l.entity_id = ?
                ORDER BY l.created_at DESC
            ''', (complaint['id'],)).fetchall()
        else:
            # Check certificate applications
            cert = conn.execute('''
                SELECT c.*, s.name as sachivalayam_name, u.name as citizen_name, o.name as officer_name, o.designation as officer_designation
                FROM certificate_applications c
                JOIN sachivalayams s ON c.sachivalayam_id = s.id
                JOIN users u ON c.citizen_id = u.id
                LEFT JOIN users o ON c.assigned_officer_id = o.id
                WHERE c.application_no = ?
            ''', (query,)).fetchone()

            if cert:
                result = cert
                item_type = 'certificate'
                logs = conn.execute('''
                    SELECT l.*, u.name as actor_name, u.role as actor_role
                    FROM activity_logs l
                    LEFT JOIN users u ON l.actor_id = u.id
                    WHERE l.entity_type = 'certificate' AND l.entity_id = ?
                    ORDER BY l.created_at DESC
                ''', (cert['id'],)).fetchall()

        conn.close()

    return render_template('track.html', query=query, result=result, item_type=item_type, logs=logs)

# ----------------- Auth Routes ----------------- #

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_db()
        user = conn.execute('''
            SELECT u.*, s.name as sachivalayam_name 
            FROM users u
            LEFT JOIN sachivalayams s ON u.sachivalayam_id = s.id
            WHERE LOWER(u.email) = ?
        ''', (email,)).fetchone()
        conn.close()

        if not user or not check_password_hash(user['password_hash'], password):
            flash("Invalid email or password. Please try again.", "danger")
            return render_template('login.html')

        # Set session
        session['user_id'] = user['id']
        session['name'] = user['name']
        session['email'] = user['email']
        session['role'] = user['role']
        session['approval_status'] = user['approval_status']
        session['sachivalayam_id'] = user['sachivalayam_id']
        session['sachivalayam_name'] = user['sachivalayam_name'] or 'All Secretariats'
        session['designation'] = user['designation']

        flash(f"Welcome back, {user['name']}!", "success")

        # Route to respective dashboard
        if user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user['role'] == 'officer':
            if user['approval_status'] == 'approved':
                return redirect(url_for('officer_dashboard'))
            else:
                return redirect(url_for('officer_pending'))
        else:
            return redirect(url_for('citizen_dashboard'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role', 'citizen')
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        aadhaar = request.form.get('aadhaar', '').strip()
        password = request.form.get('password', '')
        sachivalayam_id = request.form.get('sachivalayam_id')
        designation = request.form.get('designation', '').strip() if role == 'officer' else None
        employee_id = request.form.get('employee_id', '').strip() if role == 'officer' else None

        if not name or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template('register.html')

        # Officers default to PENDING; Citizens and Admins default to APPROVED
        approval_status = 'pending' if role == 'officer' else 'approved'

        conn = get_db()
        # Check if email already registered
        existing = conn.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,)).fetchone()
        if existing:
            conn.close()
            flash("An account with this email address already exists. Please log in.", "warning")
            return render_template('register.html')

        password_hash = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, designation, employee_id, approval_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, email, phone, aadhaar, password_hash, role, sachivalayam_id, designation, employee_id, approval_status))
        
        user_id = cursor.lastrowid

        # Log event
        if role == 'officer':
            cursor.execute('''
                INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
                VALUES ('officer_approval', ?, ?, 'OFFICER_REGISTERED', NULL, 'pending', 'Officer registered. Awaiting Admin authorization.')
            ''', (user_id, user_id))

        conn.commit()
        conn.close()

        if role == 'officer':
            flash("Registration successful! Your officer account has been created with status 'PENDING'. You will be able to access your dashboard once an Administrator approves your request.", "info")
            return redirect(url_for('login'))
        else:
            flash("Citizen registration successful! You can now log in.", "success")
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/quick-login/<role>')
def quick_login(role):
    """Demo logins disabled for production deployment"""
    flash("One-click demo logins are disabled for security. Please sign in with your official credentials.", "info")
    return redirect(url_for('login'))

# ----------------- Admin Routes ----------------- #

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db()
    
    # Counts
    pending_officers_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'officer' AND approval_status = 'pending'").fetchone()[0]
    approved_officers_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'officer' AND approval_status = 'approved'").fetchone()[0]
    citizens_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'citizen'").fetchone()[0]
    complaints_total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    complaints_done = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'DONE'").fetchone()[0]
    complaints_pending_citizen = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'WORK_COMPLETED_PENDING_CONFIRMATION'").fetchone()[0]
    certs_total = conn.execute("SELECT COUNT(*) FROM certificate_applications").fetchone()[0]
    certs_done = conn.execute("SELECT COUNT(*) FROM certificate_applications WHERE status = 'DONE'").fetchone()[0]
    certs_pending_citizen = conn.execute("SELECT COUNT(*) FROM certificate_applications WHERE status = 'WORK_COMPLETED_PENDING_CONFIRMATION'").fetchone()[0]

    # Officers awaiting approval
    pending_officers = conn.execute('''
        SELECT u.*, s.name as sachivalayam_name, s.mandal, s.district
        FROM users u
        LEFT JOIN sachivalayams s ON u.sachivalayam_id = s.id
        WHERE u.role = 'officer' AND u.approval_status = 'pending'
        ORDER BY u.created_at DESC
    ''').fetchall()

    # All officers
    all_officers = conn.execute('''
        SELECT u.*, s.name as sachivalayam_name, s.mandal, s.district,
               (SELECT COUNT(*) FROM complaints c WHERE c.assigned_officer_id = u.id) as assigned_complaints,
               (SELECT COUNT(*) FROM certificate_applications a WHERE a.assigned_officer_id = u.id) as assigned_certs
        FROM users u
        LEFT JOIN sachivalayams s ON u.sachivalayam_id = s.id
        WHERE u.role = 'officer'
        ORDER BY u.approval_status ASC, u.name ASC
    ''').fetchall()

    # Recent complaints
    recent_complaints = conn.execute('''
        SELECT c.*, s.name as sachivalayam_name, u.name as citizen_name, o.name as officer_name
        FROM complaints c
        JOIN sachivalayams s ON c.sachivalayam_id = s.id
        JOIN users u ON c.citizen_id = u.id
        LEFT JOIN users o ON c.assigned_officer_id = o.id
        ORDER BY c.created_at DESC LIMIT 10
    ''').fetchall()

    # Recent certificate applications
    recent_certificates = conn.execute('''
        SELECT c.*, s.name as sachivalayam_name, u.name as citizen_name, o.name as officer_name
        FROM certificate_applications c
        JOIN sachivalayams s ON c.sachivalayam_id = s.id
        JOIN users u ON c.citizen_id = u.id
        LEFT JOIN users o ON c.assigned_officer_id = o.id
        ORDER BY c.created_at DESC LIMIT 10
    ''').fetchall()

    conn.close()

    metrics = {
        'pending_officers': pending_officers_count,
        'approved_officers': approved_officers_count,
        'citizens': citizens_count,
        'complaints_total': complaints_total,
        'complaints_done': complaints_done,
        'complaints_pending_citizen': complaints_pending_citizen,
        'certs_total': certs_total,
        'certs_done': certs_done,
        'certs_pending_citizen': certs_pending_citizen
    }

    return render_template('admin_dashboard.html', metrics=metrics, pending_officers=pending_officers,
                           all_officers=all_officers, recent_complaints=recent_complaints,
                           recent_certificates=recent_certificates)

@app.route('/admin/officers/<int:officer_id>/approve', methods=['POST'])
@admin_required
def admin_approve_officer(officer_id):
    conn = get_db()
    cursor = conn.cursor()
    officer = cursor.execute("SELECT * FROM users WHERE id = ? AND role = 'officer'", (officer_id,)).fetchone()
    
    if not officer:
        flash("Officer not found.", "danger")
        conn.close()
        return redirect(url_for('admin_dashboard'))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE users 
        SET approval_status = 'approved', approved_at = ?, approved_by = ?, rejection_reason = NULL
        WHERE id = ?
    ''', (now, session['user_id'], officer_id))

    cursor.execute('''
        INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
        VALUES ('officer_approval', ?, ?, 'OFFICER_APPROVED', ?, 'approved', 'Admin granted dashboard access permission.')
    ''', (officer_id, session['user_id'], officer['approval_status']))

    conn.commit()
    conn.close()

    flash(f"Officer {officer['name']} has been approved! They can now log in and access their dashboard.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/officers/<int:officer_id>/reject', methods=['POST'])
@admin_required
def admin_reject_officer(officer_id):
    reason = request.form.get('reason', 'Verification credentials did not match department records.')
    conn = get_db()
    cursor = conn.cursor()
    officer = cursor.execute("SELECT * FROM users WHERE id = ? AND role = 'officer'", (officer_id,)).fetchone()
    
    if not officer:
        flash("Officer not found.", "danger")
        conn.close()
        return redirect(url_for('admin_dashboard'))

    cursor.execute('''
        UPDATE users 
        SET approval_status = 'rejected', rejection_reason = ?, approved_at = NULL, approved_by = ?
        WHERE id = ?
    ''', (reason, session['user_id'], officer_id))

    cursor.execute('''
        INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
        VALUES ('officer_approval', ?, ?, 'OFFICER_REJECTED', ?, 'rejected', ?)
    ''', (officer_id, session['user_id'], officer['approval_status'], reason))

    conn.commit()
    conn.close()

    flash(f"Officer {officer['name']} registration was rejected.", "warning")
    return redirect(url_for('admin_dashboard'))

# ----------------- Sachivalayam Officer Routes ----------------- #

@app.route('/officer/pending')
@login_required
def officer_pending():
    if session.get('role') != 'officer':
        return redirect(url_for('index'))
    
    # Check if officer got approved in the meantime
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    conn.close()

    if user and user['approval_status'] == 'approved':
        session['approval_status'] = 'approved'
        flash("Your account has been approved by the Admin! Welcome to your dashboard.", "success")
        return redirect(url_for('officer_dashboard'))

    return render_template('officer_pending.html', user=user)

@app.route('/officer/dashboard')
@officer_access_required
def officer_dashboard():
    officer_id = session['user_id']
    sachivalayam_id = session.get('sachivalayam_id')

    conn = get_db()
    # Complaints assigned to officer or within officer's secretariat
    complaints = conn.execute('''
        SELECT c.*, s.name as sachivalayam_name, u.name as citizen_name, u.phone as citizen_phone
        FROM complaints c
        JOIN sachivalayams s ON c.sachivalayam_id = s.id
        JOIN users u ON c.citizen_id = u.id
        WHERE c.assigned_officer_id = ? OR (c.assigned_officer_id IS NULL AND c.sachivalayam_id = ?)
        ORDER BY 
            CASE c.status 
                WHEN 'REWORK_REQUESTED' THEN 1 
                WHEN 'SUBMITTED' THEN 2 
                WHEN 'IN_PROGRESS' THEN 3 
                WHEN 'WORK_COMPLETED_PENDING_CONFIRMATION' THEN 4 
                WHEN 'DONE' THEN 5 
            END, c.created_at DESC
    ''', (officer_id, sachivalayam_id)).fetchall()

    # Certificates assigned to officer or within secretariat
    certificates = conn.execute('''
        SELECT c.*, s.name as sachivalayam_name, u.name as citizen_name, u.phone as citizen_phone
        FROM certificate_applications c
        JOIN sachivalayams s ON c.sachivalayam_id = s.id
        JOIN users u ON c.citizen_id = u.id
        WHERE c.assigned_officer_id = ? OR (c.assigned_officer_id IS NULL AND c.sachivalayam_id = ?)
        ORDER BY 
            CASE c.status 
                WHEN 'REWORK_REQUESTED' THEN 1 
                WHEN 'SUBMITTED' THEN 2 
                WHEN 'IN_PROGRESS' THEN 3 
                WHEN 'WORK_COMPLETED_PENDING_CONFIRMATION' THEN 4 
                WHEN 'DONE' THEN 5 
            END, c.created_at DESC
    ''', (officer_id, sachivalayam_id)).fetchall()

    # Summary counts
    metrics = {
        'total_complaints': len(complaints),
        'pending_complaints': sum(1 for c in complaints if c['status'] in ('SUBMITTED', 'IN_PROGRESS', 'REWORK_REQUESTED')),
        'awaiting_citizen_complaints': sum(1 for c in complaints if c['status'] == 'WORK_COMPLETED_PENDING_CONFIRMATION'),
        'done_complaints': sum(1 for c in complaints if c['status'] == 'DONE'),
        'total_certificates': len(certificates),
        'pending_certificates': sum(1 for c in certificates if c['status'] in ('SUBMITTED', 'IN_PROGRESS', 'REWORK_REQUESTED')),
        'awaiting_citizen_certs': sum(1 for c in certificates if c['status'] == 'WORK_COMPLETED_PENDING_CONFIRMATION'),
        'done_certificates': sum(1 for c in certificates if c['status'] == 'DONE'),
    }

    conn.close()
    return render_template('officer_dashboard.html', complaints=complaints, certificates=certificates, metrics=metrics)

@app.route('/officer/complaints/<int:complaint_id>/update', methods=['POST'])
@officer_access_required
def officer_update_complaint(complaint_id):
    target_status = request.form.get('status')
    notes = request.form.get('notes', '').strip()
    officer_id = session['user_id']

    conn = get_db()
    cursor = conn.cursor()
    complaint = cursor.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()

    if not complaint:
        flash("Complaint not found.", "danger")
        conn.close()
        return redirect(url_for('officer_dashboard'))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # If marking work as completed, it transitions to WORK_COMPLETED_PENDING_CONFIRMATION
    # It CANNOT directly jump to DONE from the officer!
    if target_status == 'WORK_COMPLETED':
        new_status = 'WORK_COMPLETED_PENDING_CONFIRMATION'
        log_action = 'OFFICER_MARKED_WORK_COMPLETED'
        flash("Work marked as completed! Request is now awaiting confirmation from the Citizen before it is officially closed.", "info")
    elif target_status == 'IN_PROGRESS':
        new_status = 'IN_PROGRESS'
        log_action = 'STATUS_UPDATED_IN_PROGRESS'
        flash("Complaint status updated to In Progress.", "success")
    else:
        new_status = target_status
        log_action = f"STATUS_UPDATED_{new_status}"

    cursor.execute('''
        UPDATE complaints 
        SET status = ?, assigned_officer_id = ?, officer_resolution_notes = ?, updated_at = ?
        WHERE id = ?
    ''', (new_status, officer_id, notes or complaint['officer_resolution_notes'], now, complaint_id))

    cursor.execute('''
        INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
        VALUES ('complaint', ?, ?, ?, ?, ?, ?)
    ''', (complaint_id, officer_id, log_action, complaint['status'], new_status, notes))

    conn.commit()
    conn.close()
    return redirect(url_for('officer_dashboard'))

@app.route('/officer/certificates/<int:cert_id>/update', methods=['POST'])
@officer_access_required
def officer_update_certificate(cert_id):
    target_status = request.form.get('status')
    remarks = request.form.get('remarks', '').strip()
    officer_id = session['user_id']
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_disp = datetime.now().strftime("%d-%b-%Y")

    conn = get_db()
    cursor = conn.cursor()
    cert = cursor.execute("SELECT * FROM certificate_applications WHERE id = ?", (cert_id,)).fetchone()

    if not cert:
        flash("Certificate application not found.", "danger")
        conn.close()
        return redirect(url_for('officer_dashboard'))

    cert_payload = cert['certificate_payload_json']

    if target_status == 'WORK_COMPLETED':
        new_status = 'WORK_COMPLETED_PENDING_CONFIRMATION'
        log_action = 'CERTIFICATE_PROCESSED_AWAITING_CITIZEN_ACCEPTANCE'
        
        # Prepare generated certificate payload
        prefix = "AP-REN" if cert['service_type'] == 'renewal' else "AP-CRT"
        cert_id_code = f"{prefix}-2026-{random.randint(10000, 99999)}"
        payload = {
            "certificate_id": cert_id_code,
            "qr_hash": f"APGS-{cert['sachivalayam_id']}-{cert_id_code}",
            "digital_signer": f"{session.get('name', 'Sachivalayam Officer')}, {session.get('designation', 'Authorized Signatory')}",
            "date_of_issue": today_disp,
            "valid_until": "VALID PERMANENTLY" if "Caste" in cert['certificate_type'] else f"Valid for 1 Year (Till {datetime.now().year + 1})",
            "annual_income": cert['annual_income'],
            "caste_category": cert['caste_category']
        }
        cert_payload = json.dumps(payload)
        flash("Certificate prepared and marked as Completed! Sent to citizen for verification and acceptance.", "info")
    elif target_status == 'IN_PROGRESS':
        new_status = 'IN_PROGRESS'
        log_action = 'CERTIFICATE_IN_VERIFICATION'
        flash("Certificate marked as Under Verification.", "success")
    else:
        new_status = target_status
        log_action = f"STATUS_UPDATED_{new_status}"

    cursor.execute('''
        UPDATE certificate_applications 
        SET status = ?, assigned_officer_id = ?, officer_remarks = ?, certificate_payload_json = ?, updated_at = ?
        WHERE id = ?
    ''', (new_status, officer_id, remarks or cert['officer_remarks'], cert_payload, now_str, cert_id))

    cursor.execute('''
        INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
        VALUES ('certificate', ?, ?, ?, ?, ?, ?)
    ''', (cert_id, officer_id, log_action, cert['status'], new_status, remarks))

    conn.commit()
    conn.close()
    return redirect(url_for('officer_dashboard'))

# ----------------- Citizen Routes ----------------- #

@app.route('/citizen/dashboard')
@citizen_required
def citizen_dashboard():
    citizen_id = session['user_id']
    conn = get_db()

    complaints = conn.execute('''
        SELECT c.*, s.name as sachivalayam_name, o.name as officer_name, o.designation as officer_designation
        FROM complaints c
        JOIN sachivalayams s ON c.sachivalayam_id = s.id
        LEFT JOIN users o ON c.assigned_officer_id = o.id
        WHERE c.citizen_id = ?
        ORDER BY 
            CASE c.status 
                WHEN 'WORK_COMPLETED_PENDING_CONFIRMATION' THEN 1 
                WHEN 'REWORK_REQUESTED' THEN 2 
                WHEN 'IN_PROGRESS' THEN 3 
                WHEN 'SUBMITTED' THEN 4 
                WHEN 'DONE' THEN 5 
            END, c.created_at DESC
    ''', (citizen_id,)).fetchall()

    certificates = conn.execute('''
        SELECT c.*, s.name as sachivalayam_name, o.name as officer_name, o.designation as officer_designation
        FROM certificate_applications c
        JOIN sachivalayams s ON c.sachivalayam_id = s.id
        LEFT JOIN users o ON c.assigned_officer_id = o.id
        WHERE c.citizen_id = ?
        ORDER BY 
            CASE c.status 
                WHEN 'WORK_COMPLETED_PENDING_CONFIRMATION' THEN 1 
                WHEN 'REWORK_REQUESTED' THEN 2 
                WHEN 'IN_PROGRESS' THEN 3 
                WHEN 'SUBMITTED' THEN 4 
                WHEN 'DONE' THEN 5 
            END, c.created_at DESC
    ''', (citizen_id,)).fetchall()

    # Find items awaiting citizen action (KEY FEATURE)
    pending_acceptance_complaints = [c for c in complaints if c['status'] == 'WORK_COMPLETED_PENDING_CONFIRMATION']
    pending_acceptance_certs = [c for c in certificates if c['status'] == 'WORK_COMPLETED_PENDING_CONFIRMATION']

    metrics = {
        'total_complaints': len(complaints),
        'pending_action_complaints': len(pending_acceptance_complaints),
        'done_complaints': sum(1 for c in complaints if c['status'] == 'DONE'),
        'total_certs': len(certificates),
        'pending_action_certs': len(pending_acceptance_certs),
        'done_certs': sum(1 for c in certificates if c['status'] == 'DONE')
    }

    conn.close()
    return render_template('citizen_dashboard.html', complaints=complaints, certificates=certificates,
                           pending_acceptance_complaints=pending_acceptance_complaints,
                           pending_acceptance_certs=pending_acceptance_certs,
                           metrics=metrics)

@app.route('/citizen/complaints/new', methods=['POST'])
@citizen_required
def citizen_new_complaint():
    citizen_id = session['user_id']
    category = request.form.get('category')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    location = request.form.get('location', '').strip()
    sachivalayam_id = request.form.get('sachivalayam_id') or session.get('sachivalayam_id')

    if not title or not description or not location or not sachivalayam_id:
        flash("Please provide all required grievance details.", "danger")
        return redirect(url_for('citizen_dashboard'))

    ticket_id = f"GS-CMP-2026-{random.randint(1000, 9999)}"

    conn = get_db()
    cursor = conn.cursor()

    # Auto-assign to an approved officer in this secretariat if available
    officer = cursor.execute('''
        SELECT id FROM users 
        WHERE role = 'officer' AND approval_status = 'approved' AND sachivalayam_id = ?
        LIMIT 1
    ''', (sachivalayam_id,)).fetchone()
    assigned_officer_id = officer['id'] if officer else None

    cursor.execute('''
        INSERT INTO complaints (ticket_id, citizen_id, sachivalayam_id, category, title, description, location, assigned_officer_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED')
    ''', (ticket_id, citizen_id, sachivalayam_id, category, title, description, location, assigned_officer_id))

    complaint_id = cursor.lastrowid
    cursor.execute('''
        INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
        VALUES ('complaint', ?, ?, 'COMPLAINT_FILED', NULL, 'SUBMITTED', 'Citizen lodged complaint through Sachivalayam Portal.')
    ''', (complaint_id, citizen_id))

    conn.commit()
    conn.close()

    flash(f"Your grievance has been successfully lodged with Ticket ID: {ticket_id}", "success")
    return redirect(url_for('citizen_dashboard'))

@app.route('/citizen/certificates/new', methods=['POST'])
@citizen_required
def citizen_new_certificate():
    citizen_id = session['user_id']
    cert_type = request.form.get('certificate_type')
    applicant_name = request.form.get('applicant_name', '').strip()
    relation_name = request.form.get('relation_name', '').strip()
    relation_type = request.form.get('relation_type', 'Father')
    annual_income = request.form.get('annual_income') or None
    caste_category = request.form.get('caste_category') or None
    purpose = request.form.get('purpose', '').strip()
    address = request.form.get('address', '').strip()
    sachivalayam_id = request.form.get('sachivalayam_id') or session.get('sachivalayam_id')

    if not applicant_name or not purpose or not address or not sachivalayam_id:
        flash("Please fill in all mandatory application fields.", "danger")
        return redirect(url_for('citizen_dashboard'))

    applicant_photo = save_uploaded_file(request.files.get('applicant_photo'), 'photo')
    income_proof_doc = save_uploaded_file(request.files.get('income_proof_doc'), 'income_doc')
    caste_proof_doc = save_uploaded_file(request.files.get('caste_proof_doc'), 'caste_doc')
    supporting_doc = save_uploaded_file(request.files.get('supporting_doc'), 'other_doc')

    app_no = f"GS-CRT-2026-{random.randint(1000, 9999)}"

    conn = get_db()
    cursor = conn.cursor()

    officer = cursor.execute('''
        SELECT id FROM users 
        WHERE role = 'officer' AND approval_status = 'approved' AND sachivalayam_id = ?
        LIMIT 1
    ''', (sachivalayam_id,)).fetchone()
    assigned_officer_id = officer['id'] if officer else None

    cursor.execute('''
        INSERT INTO certificate_applications 
        (application_no, citizen_id, sachivalayam_id, service_type, certificate_type, applicant_name, relation_name, relation_type, annual_income, caste_category, purpose, address, applicant_photo, income_proof_doc, caste_proof_doc, supporting_doc, assigned_officer_id, status)
        VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED')
    ''', (app_no, citizen_id, sachivalayam_id, cert_type, applicant_name, relation_name, relation_type, annual_income, caste_category, purpose, address, applicant_photo, income_proof_doc, caste_proof_doc, supporting_doc, assigned_officer_id))

    cert_id = cursor.lastrowid
    cursor.execute('''
        INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
        VALUES ('certificate', ?, ?, 'APPLICATION_SUBMITTED', NULL, 'SUBMITTED', 'Applied for new certificate with document photos.')
    ''', (cert_id, citizen_id))

    conn.commit()
    conn.close()

    flash(f"Application for {cert_type} submitted successfully with No: {app_no}", "success")
    return redirect(url_for('citizen_dashboard'))

@app.route('/citizen/certificates/renew', methods=['POST'])
@citizen_required
def citizen_renew_certificate():
    citizen_id = session['user_id']
    cert_type = request.form.get('certificate_type')
    applicant_name = request.form.get('applicant_name', '').strip()
    previous_cert_no = request.form.get('previous_cert_no', '').strip()
    previous_issue_date = request.form.get('previous_issue_date', '').strip()
    annual_income = request.form.get('annual_income') or None
    caste_category = request.form.get('caste_category') or None
    purpose = request.form.get('purpose', '').strip()
    address = request.form.get('address', '').strip()
    sachivalayam_id = request.form.get('sachivalayam_id') or session.get('sachivalayam_id')

    if not applicant_name or not previous_cert_no or not purpose or not address or not sachivalayam_id:
        flash("Please provide previous certificate number and all renewal details.", "danger")
        return redirect(url_for('citizen_dashboard'))

    applicant_photo = save_uploaded_file(request.files.get('applicant_photo'), 'photo_ren')
    income_proof_doc = save_uploaded_file(request.files.get('income_proof_doc'), 'income_ren')
    caste_proof_doc = save_uploaded_file(request.files.get('caste_proof_doc'), 'caste_ren')
    supporting_doc = save_uploaded_file(request.files.get('previous_cert_doc'), 'prevcert_doc') or save_uploaded_file(request.files.get('supporting_doc'), 'ren_doc')

    app_no = f"GS-REN-2026-{random.randint(1000, 9999)}"

    conn = get_db()
    cursor = conn.cursor()

    officer = cursor.execute('''
        SELECT id FROM users 
        WHERE role = 'officer' AND approval_status = 'approved' AND sachivalayam_id = ?
        LIMIT 1
    ''', (sachivalayam_id,)).fetchone()
    assigned_officer_id = officer['id'] if officer else None

    cursor.execute('''
        INSERT INTO certificate_applications 
        (application_no, citizen_id, sachivalayam_id, service_type, certificate_type, applicant_name, previous_cert_no, previous_issue_date, annual_income, caste_category, purpose, address, applicant_photo, income_proof_doc, caste_proof_doc, supporting_doc, assigned_officer_id, status)
        VALUES (?, ?, ?, 'renewal', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED')
    ''', (app_no, citizen_id, sachivalayam_id, cert_type, applicant_name, previous_cert_no, previous_issue_date, annual_income, caste_category, purpose, address, applicant_photo, income_proof_doc, caste_proof_doc, supporting_doc, assigned_officer_id))

    cert_id = cursor.lastrowid
    cursor.execute('''
        INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
        VALUES ('certificate', ?, ?, 'RENEWAL_APPLIED', NULL, 'SUBMITTED', 'Applied for certificate renewal with updated proof photos.')
    ''', (cert_id, citizen_id))

    conn.commit()
    conn.close()

    flash(f"Renewal application submitted successfully! Application No: {app_no}", "success")
    return redirect(url_for('citizen_dashboard'))

# ----------------- Two-Party Completion Confirmation Routes (KEY REQUIREMENT) ----------------- #

@app.route('/citizen/complaints/<int:complaint_id>/action', methods=['POST'])
@citizen_required
def citizen_complaint_action(complaint_id):
    decision = request.form.get('decision') # 'accept' or 'dispute'
    feedback = request.form.get('feedback', '').strip()
    citizen_id = session['user_id']
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    complaint = cursor.execute("SELECT * FROM complaints WHERE id = ? AND citizen_id = ?", (complaint_id, citizen_id)).fetchone()

    if not complaint:
        flash("Complaint record not found.", "danger")
        conn.close()
        return redirect(url_for('citizen_dashboard'))

    if complaint['status'] != 'WORK_COMPLETED_PENDING_CONFIRMATION':
        flash("This request is not currently waiting for your confirmation.", "warning")
        conn.close()
        return redirect(url_for('citizen_dashboard'))

    if decision == 'accept':
        # Citizen accepts -> Status becomes DONE
        cursor.execute('''
            UPDATE complaints 
            SET status = 'DONE', citizen_feedback = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
        ''', (feedback or 'Work completion confirmed and accepted by Citizen.', now, now, complaint_id))

        cursor.execute('''
            INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
            VALUES ('complaint', ?, ?, 'CITIZEN_ACCEPTED_DONE', 'WORK_COMPLETED_PENDING_CONFIRMATION', 'DONE', ?)
        ''', (complaint_id, citizen_id, feedback or 'Citizen accepted work resolution.'))

        conn.commit()
        conn.close()
        flash("Thank you! You have confirmed the work completion. The grievance is now marked as DONE.", "success")
    
    elif decision == 'dispute':
        # Citizen disputes -> Status transitions back to REWORK_REQUESTED
        cursor.execute('''
            UPDATE complaints 
            SET status = 'REWORK_REQUESTED', citizen_feedback = ?, updated_at = ?
            WHERE id = ?
        ''', (feedback or 'Citizen indicated that the issue is still unresolved.', now, complaint_id))

        cursor.execute('''
            INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
            VALUES ('complaint', ?, ?, 'CITIZEN_DISPUTED_REWORK', 'WORK_COMPLETED_PENDING_CONFIRMATION', 'REWORK_REQUESTED', ?)
        ''', (complaint_id, citizen_id, feedback or 'Rework requested by citizen.'))

        conn.commit()
        conn.close()
        flash("Your rework request has been forwarded to the Sachivalayam Officer with your comments.", "warning")
    
    else:
        conn.close()
        flash("Invalid action specified.", "danger")

    return redirect(url_for('citizen_dashboard'))

@app.route('/citizen/certificates/<int:cert_id>/action', methods=['POST'])
@citizen_required
def citizen_certificate_action(cert_id):
    decision = request.form.get('decision') # 'accept' or 'dispute'
    feedback = request.form.get('feedback', '').strip()
    citizen_id = session['user_id']
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    cert = cursor.execute("SELECT * FROM certificate_applications WHERE id = ? AND citizen_id = ?", (cert_id, citizen_id)).fetchone()

    if not cert:
        flash("Certificate application record not found.", "danger")
        conn.close()
        return redirect(url_for('citizen_dashboard'))

    if cert['status'] != 'WORK_COMPLETED_PENDING_CONFIRMATION':
        flash("This certificate application is not awaiting confirmation.", "warning")
        conn.close()
        return redirect(url_for('citizen_dashboard'))

    if decision == 'accept':
        # Citizen verifies details -> Status becomes DONE
        cursor.execute('''
            UPDATE certificate_applications 
            SET status = 'DONE', citizen_feedback = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
        ''', (feedback or 'Certificate details verified and accepted by citizen.', now, now, cert_id))

        cursor.execute('''
            INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
            VALUES ('certificate', ?, ?, 'CITIZEN_ACCEPTED_CERTIFICATE', 'WORK_COMPLETED_PENDING_CONFIRMATION', 'DONE', ?)
        ''', (cert_id, citizen_id, feedback or 'Citizen confirmed certificate.'))

        conn.commit()
        conn.close()
        flash(f"Certificate accepted! Status is now DONE. You can now download and print your official certificate.", "success")

    elif decision == 'dispute':
        # Citizen disputes details -> Returns for REWORK_REQUESTED
        cursor.execute('''
            UPDATE certificate_applications 
            SET status = 'REWORK_REQUESTED', citizen_feedback = ?, updated_at = ?
            WHERE id = ?
        ''', (feedback or 'Details incorrect or incomplete. Revision requested.', now, cert_id))

        cursor.execute('''
            INSERT INTO activity_logs (entity_type, entity_id, actor_id, action, old_status, new_status, notes)
            VALUES ('certificate', ?, ?, 'CITIZEN_DISPUTED_CERTIFICATE', 'WORK_COMPLETED_PENDING_CONFIRMATION', 'REWORK_REQUESTED', ?)
        ''', (cert_id, citizen_id, feedback or 'Revision requested by citizen.'))

        conn.commit()
        conn.close()
        flash("Revision requested! The officer has been alerted to update the certificate details.", "warning")

    return redirect(url_for('citizen_dashboard'))

# ----------------- Certificate View / Print Route ----------------- #

@app.route('/certificate/<application_no>/view')
def view_certificate(application_no):
    conn = get_db()
    cert = conn.execute('''
        SELECT c.*, s.name as sachivalayam_name, s.mandal, s.district, s.pincode,
               u.phone as citizen_phone, u.aadhaar as citizen_aadhaar,
               o.name as officer_name, o.designation as officer_designation
        FROM certificate_applications c
        JOIN sachivalayams s ON c.sachivalayam_id = s.id
        JOIN users u ON c.citizen_id = u.id
        LEFT JOIN users o ON c.assigned_officer_id = o.id
        WHERE c.application_no = ?
    ''', (application_no,)).fetchone()
    conn.close()

    if not cert:
        flash("Certificate record not found.", "danger")
        return redirect(url_for('index'))

    # If not done yet and not admin/officer, restrict full view
    if cert['status'] != 'DONE' and session.get('role') not in ('admin', 'officer'):
        flash("Certificate is not yet finalized. It must be approved and accepted first.", "warning")
        return redirect(url_for('citizen_dashboard'))

    payload = json.loads(cert['certificate_payload_json']) if cert['certificate_payload_json'] else {}

    return render_template('certificate_view.html', cert=cert, payload=payload)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1')
    host = os.environ.get('HOST', '0.0.0.0')
    app.run(debug=debug_mode, host=host, port=port)
