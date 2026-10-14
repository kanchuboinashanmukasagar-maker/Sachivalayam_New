# Grama & Ward Sachivalayam Citizen Services & Grievance Portal

A decentralized citizen-services web application inspired by the **Government of Andhra Pradesh Grama / Ward Sachivalayam System**.

---

## 🔐 Official Administrator Credentials

The application initializes the Master Administrator account automatically upon first startup:

| Field | Production Value | Notes |
| :--- | :--- | :--- |
| **Login URL** | `/login` | Secure Single Sign-On |
| **Admin Email** | `admin@sachivalayam.gov.in` | Configurable via `ADMIN_EMAIL` env variable |
| **Admin Password** | `admin123` | Configurable via `ADMIN_PASSWORD` env variable |
| **Designation** | District Nodal Officer | Full authority over all Secretariats & Staff approvals |
| **Permissions** | Master Superadmin | Grant/Revoke Officer permissions, District-wide oversight |

---

## 🌟 Key Highlights

1. **Three Dedicated Roles**:
   - **Admin (District Nodal Officer / Superadmin)**: Sole authority who can approve or reject registered Sachivalayam officers.
   - **Sachivalayam Officer**: Registers with secretariat designation (Panchayat Secretary, Digital Assistant, Welfare Assistant, etc.). **Dashboard access is locked until the Admin verifies and approves the registration.**
   - **Citizen / Public User**: Can lodge grievances, apply for new certificates, renew expiring certificates, upload verification photos, and track requests.

2. **Citizen-Confirmed "DONE" Workflow**:
   - When an officer marks work as completed, the request transitions to **`WORK_COMPLETED_PENDING_CONFIRMATION`**.
   - An alert appears on the Citizen's Dashboard.
   - **Only when the citizen verifies and clicks "Accept Completion" does the status officially transition to `DONE`**.
   - If the citizen disputes the work, the status transitions to **`REWORK_REQUESTED`** with citizen remarks.

3. **Photo & Document Uploads**:
   - Supports **Applicant Passport Photos**, **Caste Certificate Proof Photos**, and **Income Proof / Ration Card Photos**.
   - Officers inspect uploaded photos before issuing draft certificates.
   - The citizen's passport photo is framed directly onto the official downloadable/printable government certificate.

---

## 🚀 Deployment Guide

### Option 1: Docker Container Deployment (Recommended)

1. Build the Docker image:
   ```bash
   docker build -t sachivalayam-portal:latest .
   ```

2. Run the container:
   ```bash
   docker run -d -p 5000:5000 \
     -e SECRET_KEY="your-strong-production-secret-key" \
     -e ADMIN_EMAIL="admin@sachivalayam.gov.in" \
     -e ADMIN_PASSWORD="your-secure-password" \
     --name sachivalayam-app sachivalayam-portal:latest
   ```
   Open **`http://localhost:5000`**.

---

### Option 2: Linux / VPS Deployment with Gunicorn

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Launch production server with Gunicorn:
   ```bash
   gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 3 --threads 4 --timeout 120
   ```

---

### Option 3: Cloud / PaaS Deployment (Render, Railway, Fly.io, Heroku)

This repository includes a native `Procfile` configured for cloud web services:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4`
- Set environment variables in your cloud dashboard (see `.env.example`).

---

### Option 4: Local / Windows Server

1. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Start the server:
   ```powershell
   python wsgi.py
   # Or directly:
   python app.py
   ```

---

## ⚙️ Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `SECRET_KEY` | `sachivalayam_secret_token_key_2026` | Cryptographic secret for signing session cookies |
| `ADMIN_EMAIL` | `admin@sachivalayam.gov.in` | Master Admin login email |
| `ADMIN_PASSWORD`| `admin123` | Master Admin login password |
| `PORT` | `5000` | HTTP listen port |
| `FLASK_DEBUG` | `false` | Enable/disable Flask debug mode |

---

## 🧪 Automated Integration Tests

Run the 9-scenario test suite verifying access boundaries, security policies, and photo uploads:
```powershell
python test_portal.py
```
```text
Ran 9 tests in 1.644s

OK
```
