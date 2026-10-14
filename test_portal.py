import unittest
import json
from app import app
from database import get_db, init_db
from seed_data import seed

class SachivalayamPortalTestCase(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        self.client = app.test_client()
        # Seed fresh database
        seed()

    def test_1_officer_registration_defaults_to_pending(self):
        """Verify that newly registered officers are set to PENDING status"""
        response = self.client.post('/register', data={
            'role': 'officer',
            'name': 'Srikanth Reddy',
            'email': 'srikanth.officer@sachivalayam.gov.in',
            'phone': '9876500000',
            'aadhaar': '9999-8888-7777',
            'password': 'password123',
            'sachivalayam_id': '1',
            'designation': 'Village Revenue Officer (VRO)',
            'employee_id': 'APGS-2026-9999'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        # Check DB
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = 'srikanth.officer@sachivalayam.gov.in'").fetchone()
        conn.close()

        self.assertIsNotNone(user)
        self.assertEqual(user['role'], 'officer')
        self.assertEqual(user['approval_status'], 'pending')

    def test_2_pending_officer_blocked_from_officer_dashboard(self):
        """Verify that an unapproved (pending) officer cannot access the officer dashboard"""
        # Login as pending officer
        login_resp = self.client.post('/login', data={
            'email': 'officer.pending@sachivalayam.gov.in',
            'password': 'officer123'
        }, follow_redirects=False)

        # Should redirect to /officer/pending, NOT /officer/dashboard
        self.assertIn('/officer/pending', login_resp.location)

        # Attempt directly requesting /officer/dashboard
        dash_resp = self.client.get('/officer/dashboard', follow_redirects=False)
        self.assertIn('/officer/pending', dash_resp.location)

    def test_3_admin_approves_officer_and_unlocks_dashboard(self):
        """Verify that Admin can approve a pending officer and unlock their dashboard access"""
        # 1. Login as Admin
        self.client.post('/login', data={
            'email': 'admin@sachivalayam.gov.in',
            'password': 'admin123'
        }, follow_redirects=True)

        # Get pending officer id (Praveen Kumar, ID 3)
        conn = get_db()
        officer = conn.execute("SELECT id FROM users WHERE email = 'officer.pending@sachivalayam.gov.in'").fetchone()
        officer_id = officer['id']
        conn.close()

        # Admin approves the officer
        approve_resp = self.client.post(f'/admin/officers/{officer_id}/approve', follow_redirects=True)
        self.assertEqual(approve_resp.status_code, 200)

        # Verify DB updated to approved
        conn = get_db()
        officer_after = conn.execute("SELECT approval_status FROM users WHERE id = ?", (officer_id,)).fetchone()
        conn.close()
        self.assertEqual(officer_after['approval_status'], 'approved')

        # Logout Admin
        self.client.get('/logout')

        # Login as the newly approved officer
        login_resp = self.client.post('/login', data={
            'email': 'officer.pending@sachivalayam.gov.in',
            'password': 'officer123'
        }, follow_redirects=False)

        # Should now successfully redirect to /officer/dashboard!
        self.assertIn('/officer/dashboard', login_resp.location)

        # Verify dashboard renders with HTTP 200
        dash_resp = self.client.get('/officer/dashboard')
        self.assertEqual(dash_resp.status_code, 200)
        self.assertIn(b'Sachivalayam Officer Desk', dash_resp.data)

    def test_4_citizen_can_lodge_complaint_and_renew_certificate(self):
        """Verify citizen can lodge complaints and request certificate renewals"""
        # Login as Citizen
        self.client.post('/login', data={
            'email': 'citizen@example.com',
            'password': 'citizen123'
        }, follow_redirects=True)

        # Lodge a new complaint
        comp_resp = self.client.post('/citizen/complaints/new', data={
            'category': 'Drinking Water',
            'title': 'Low water pressure on 5th cross',
            'description': 'Water arrives with extremely low pressure for only 15 minutes in the morning.',
            'location': '5th Cross, Near Water Tank',
            'sachivalayam_id': '1'
        }, follow_redirects=True)
        self.assertEqual(comp_resp.status_code, 200)

        # Apply for certificate renewal
        renew_resp = self.client.post('/citizen/certificates/renew', data={
            'certificate_type': 'Income Certificate',
            'previous_cert_no': 'AP-INC-2024-8812',
            'applicant_name': 'K. Venkateswara Rao',
            'annual_income': '92000',
            'purpose': 'Scholarship renewal for daughter',
            'address': 'D.No 4-21, Main Bazaar, Pedakakani',
            'sachivalayam_id': '1'
        }, follow_redirects=True)
        self.assertEqual(renew_resp.status_code, 200)

        # Verify in DB
        conn = get_db()
        complaint = conn.execute("SELECT * FROM complaints WHERE title = 'Low water pressure on 5th cross'").fetchone()
        cert = conn.execute("SELECT * FROM certificate_applications WHERE previous_cert_no = 'AP-INC-2024-8812'").fetchone()
        conn.close()

        self.assertIsNotNone(complaint)
        self.assertEqual(complaint['status'], 'SUBMITTED')
        self.assertIsNotNone(cert)
        self.assertEqual(cert['service_type'], 'renewal')
        self.assertEqual(cert['status'], 'SUBMITTED')

    def test_5_officer_marks_work_completed_sets_pending_confirmation(self):
        """Verify officer marking work completed transitions to WORK_COMPLETED_PENDING_CONFIRMATION (NOT directly DONE)"""
        # Login as Approved Officer
        self.client.post('/login', data={
            'email': 'officer.approved@sachivalayam.gov.in',
            'password': 'officer123'
        }, follow_redirects=True)

        # Find complaint 1 (Street light, currently IN_PROGRESS)
        conn = get_db()
        comp = conn.execute("SELECT id FROM complaints WHERE ticket_id = 'GS-CMP-2026-101'").fetchone()
        comp_id = comp['id']
        conn.close()

        # Officer marks work completed
        update_resp = self.client.post(f'/officer/complaints/{comp_id}/update', data={
            'status': 'WORK_COMPLETED',
            'notes': 'Replaced defective 70W LED driver and photocell sensor. Illumination tested and verified on site.'
        }, follow_redirects=True)
        self.assertEqual(update_resp.status_code, 200)

        # Check status in DB - it MUST NOT be DONE! It must be WORK_COMPLETED_PENDING_CONFIRMATION
        conn = get_db()
        comp_after = conn.execute("SELECT status, officer_resolution_notes FROM complaints WHERE id = ?", (comp_id,)).fetchone()
        conn.close()

        self.assertEqual(comp_after['status'], 'WORK_COMPLETED_PENDING_CONFIRMATION')
        self.assertIn('Replaced defective 70W LED driver', comp_after['officer_resolution_notes'])

    def test_6_citizen_accepts_work_completion_transitions_to_done(self):
        """Verify that when Citizen accepts work completion, status officially becomes DONE"""
        # Login as Citizen
        self.client.post('/login', data={
            'email': 'citizen@example.com',
            'password': 'citizen123'
        }, follow_redirects=True)

        # Seeded Complaint 2 (GS-CMP-2026-102) is in WORK_COMPLETED_PENDING_CONFIRMATION
        conn = get_db()
        comp = conn.execute("SELECT id, status FROM complaints WHERE ticket_id = 'GS-CMP-2026-102'").fetchone()
        comp_id = comp['id']
        conn.close()
        self.assertEqual(comp['status'], 'WORK_COMPLETED_PENDING_CONFIRMATION')

        # Citizen reviews and clicks ACCEPT
        action_resp = self.client.post(f'/citizen/complaints/{comp_id}/action', data={
            'decision': 'accept',
            'feedback': 'Inspected site today. Water pipe leak has been completely repaired. Excellent job!'
        }, follow_redirects=True)
        self.assertEqual(action_resp.status_code, 200)

        # Check DB: status MUST now be DONE
        conn = get_db()
        comp_done = conn.execute("SELECT status, citizen_feedback, completed_at FROM complaints WHERE id = ?", (comp_id,)).fetchone()
        conn.close()

        self.assertEqual(comp_done['status'], 'DONE')
        self.assertIsNotNone(comp_done['completed_at'])
        self.assertIn('Inspected site today', comp_done['citizen_feedback'])

    def test_7_citizen_disputes_work_completion_transitions_to_rework(self):
        """Verify that when Citizen disputes work, status transitions to REWORK_REQUESTED"""
        # Login as Citizen
        self.client.post('/login', data={
            'email': 'citizen@example.com',
            'password': 'citizen123'
        }, follow_redirects=True)

        # Seeded Certificate 1 (GS-CRT-2026-201) is in WORK_COMPLETED_PENDING_CONFIRMATION
        conn = get_db()
        cert = conn.execute("SELECT id, status FROM certificate_applications WHERE application_no = 'GS-CRT-2026-201'").fetchone()
        cert_id = cert['id']
        conn.close()
        self.assertEqual(cert['status'], 'WORK_COMPLETED_PENDING_CONFIRMATION')

        # Citizen disputes details (e.g. spelling or income discrepancy)
        dispute_resp = self.client.post(f'/citizen/certificates/{cert_id}/action', data={
            'decision': 'dispute',
            'feedback': 'My father name spelling in the draft is slightly incorrect. Please change to Ranga Rao K.'
        }, follow_redirects=True)
        self.assertEqual(dispute_resp.status_code, 200)

        # Check DB: status MUST now be REWORK_REQUESTED
        conn = get_db()
        cert_rework = conn.execute("SELECT status, citizen_feedback FROM certificate_applications WHERE id = ?", (cert_id,)).fetchone()
        conn.close()

        self.assertEqual(cert_rework['status'], 'REWORK_REQUESTED')
        self.assertIn('spelling in the draft is slightly incorrect', cert_rework['citizen_feedback'])

    def test_8_pending_officer_page_has_no_direct_admin_access(self):
        """Verify that pending officer page has NO backdoor access or shortcut link to admin dashboard"""
        # Login as pending officer
        self.client.post('/login', data={
            'email': 'officer.pending@sachivalayam.gov.in',
            'password': 'officer123'
        }, follow_redirects=True)

        resp = self.client.get('/officer/pending')
        self.assertEqual(resp.status_code, 200)
        # Ensure no direct shortcut or link to admin dashboard exists in the pending view
        self.assertNotIn(b'Switch to Admin Account', resp.data)
        self.assertNotIn(b'/admin/dashboard', resp.data)
        self.assertIn(b'Security & Verification Policy', resp.data)

    def test_9_citizen_uploads_caste_and_income_photos(self):
        """Verify that citizen can upload applicant photo, caste proof photo, and income proof photo"""
        import io
        # Login as Citizen
        self.client.post('/login', data={
            'email': 'citizen@example.com',
            'password': 'citizen123'
        }, follow_redirects=True)

        # Create dummy image bytes
        photo_file = (io.BytesIO(b'fake_photo_bytes_data'), 'applicant_photo.jpg')
        income_file = (io.BytesIO(b'fake_income_cert_bytes'), 'income_proof.png')
        caste_file = (io.BytesIO(b'fake_caste_cert_bytes'), 'caste_proof.png')

        resp = self.client.post('/citizen/certificates/new', data={
            'certificate_type': 'Income Certificate',
            'applicant_name': 'K. Venkateswara Rao',
            'relation_name': 'K. Ranga Rao',
            'relation_type': 'Father',
            'annual_income': '88000',
            'purpose': 'College Fee Reimbursement 2026',
            'address': 'D.No 4-21, Main Bazaar, Pedakakani',
            'sachivalayam_id': '1',
            'applicant_photo': photo_file,
            'income_proof_doc': income_file,
            'caste_proof_doc': caste_file
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(resp.status_code, 200)

        # Check DB
        conn = get_db()
        cert = conn.execute("SELECT * FROM certificate_applications WHERE purpose = 'College Fee Reimbursement 2026'").fetchone()
        conn.close()

        self.assertIsNotNone(cert)
        self.assertIsNotNone(cert['applicant_photo'])
        self.assertTrue(cert['applicant_photo'].startswith('uploads/photo_'))
        self.assertIsNotNone(cert['income_proof_doc'])
        self.assertTrue(cert['income_proof_doc'].startswith('uploads/income_doc_'))
        self.assertIsNotNone(cert['caste_proof_doc'])
        self.assertTrue(cert['caste_proof_doc'].startswith('uploads/caste_doc_'))

if __name__ == '__main__':
    unittest.main()
