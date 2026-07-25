# pyrefly: ignore [missing-import]
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os, sys, cv2, numpy as np, json, base64, urllib.request, time
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)
from db_config import get_db_connection
import face_utils

# Run database encoding auto-migration
face_utils.auto_migrate_legacy_encodings()

app = Flask(__name__)
app.secret_key = 'smart_attendance_super_secret_key_2026'

# Ensure uploads directory exists
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'web', 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_company():
    company = None
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM company LIMIT 1")
            company = cursor.fetchone()
        except Exception as err:
            print(f"Company context error: {err}")
        finally:
            conn.close()
    return dict(company_info=company)

def fetch_metadata():
    departments, designations, branches = [], [], []
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, department_name FROM departments ORDER BY department_name ASC")
            departments = cursor.fetchall()
            cursor.execute("SELECT id, designation_name FROM designations ORDER BY designation_name ASC")
            designations = cursor.fetchall()
            cursor.execute("SELECT id, branch_name, branch_code FROM branches ORDER BY branch_name ASC")
            branches = cursor.fetchall()
        except Exception as err:
            print(f"Metadata error: {err}")
        finally:
            conn.close()
    return departments, designations, branches

def compute_similarity(enc1, enc2):
    dot = np.dot(enc1, enc2)
    norm1 = np.linalg.norm(enc1)
    norm2 = np.linalg.norm(enc2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            return jsonify({'status': 'error', 'msg': 'Username and password are required.'}), 400

        conn = get_db_connection()
        if conn is None:
            return jsonify({'status': 'error', 'msg': 'Database connection failed.'}), 500

        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT id, username, email, password, role FROM users WHERE username = %s OR email = %s"
            cursor.execute(query, (username, username))
            user = cursor.fetchone()

            if user and user['password'] == password:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                return jsonify({'status': 'success', 'msg': 'Login successful', 'redirect': '/dashboard'})
            else:
                return jsonify({'status': 'error', 'msg': 'Invalid username or password.'}), 401
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            conn.close()

    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    today_date_str = datetime.now().strftime('%Y-%m-%d')
    current_date_display = datetime.now().strftime('%B %d, %Y')
    
    total_employees, total_departments, today_attendance = 0, 0, 0
    recent_attendance = []

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) AS total FROM employees WHERE status = 'ACTIVE'")
            res_emp = cursor.fetchone()
            total_employees = res_emp['total'] if res_emp else 0

            cursor.execute("SELECT COUNT(*) AS total FROM departments")
            res_dept = cursor.fetchone()
            total_departments = res_dept['total'] if res_dept else 0

            cursor.execute("SELECT COUNT(*) AS total FROM attendance WHERE attendance_date = %s", (today_date_str,))
            res_att = cursor.fetchone()
            today_attendance = res_att['total'] if res_att else 0

            cursor.execute("""
                SELECT a.id, a.emp_code, a.in_time, a.status, 
                       e.full_name, d.department_name, dg.designation_name, b.branch_name
                FROM attendance a
                LEFT JOIN employees e ON a.emp_code = e.emp_code
                LEFT JOIN departments d ON e.department_id = d.id
                LEFT JOIN designations dg ON e.designation_id = dg.id
                LEFT JOIN branches b ON e.branch_id = b.id
                WHERE a.attendance_date = %s
                ORDER BY a.id DESC LIMIT 20
            """, (today_date_str,))
            recent_attendance = cursor.fetchall()

            for row in recent_attendance:
                if row.get('in_time'):
                    row['in_time'] = str(row['in_time'])
        except Exception as err:
            print(f"Dashboard error: {err}")
        finally:
            conn.close()

    attendance_rate = round((today_attendance / total_employees) * 100) if total_employees > 0 else 0

    return render_template('dashboard.html',
                           username=session.get('username', 'Admin'),
                           total_employees=total_employees,
                           total_departments=total_departments,
                           today_attendance=today_attendance,
                           attendance_rate=attendance_rate,
                           current_date=current_date_display,
                           recent_attendance=recent_attendance)

# ==================== EMPLOYEES DIRECTORY ====================
@app.route('/employees')
@login_required
def employees_page():
    employees = []
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT e.id, e.emp_code, e.full_name, e.email, e.phone, e.photo_path,
                       e.status, e.created_at, d.department_name, dg.designation_name,
                       b.branch_name, b.branch_code
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                LEFT JOIN designations dg ON e.designation_id = dg.id
                LEFT JOIN branches b ON e.branch_id = b.id
                ORDER BY e.id DESC
            """
            cursor.execute(query)
            employees = cursor.fetchall()
            for emp in employees:
                emp['created_at_display'] = emp['created_at'].strftime('%Y-%m-%d') if emp.get('created_at') else 'N/A'
        except Exception as err:
            print(f"Fetch employees error: {err}")
        finally:
            conn.close()
    return render_template('employees.html', employees=employees)

@app.route('/employees/toggle_status/<int:emp_id>', methods=['POST'])
@login_required
def toggle_employee_status(emp_id):
    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM employees WHERE id = %s", (emp_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'status': 'error', 'msg': 'Employee not found'}), 404
        
        new_status = 'INACTIVE' if row['status'] == 'ACTIVE' else 'ACTIVE'
        cursor.execute("UPDATE employees SET status = %s WHERE id = %s", (new_status, emp_id))
        conn.commit()
        return jsonify({'status': 'success', 'msg': f"Status updated to {new_status}"})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500
    finally:
        conn.close()

@app.route('/employees/delete/<int:emp_id>', methods=['POST'])
@login_required
def delete_employee(emp_id):
    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM employees WHERE id = %s", (emp_id,))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Employee deleted successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500
    finally:
        conn.close()

# ==================== SETTINGS HUB ====================
@app.route('/settings')
@app.route('/settings/<tab>')
@login_required
def settings_page(tab='company'):
    company = None
    branches, departments, designations, system_users = [], [], [], []
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Company Profile
            cursor.execute("SELECT * FROM company ORDER BY id ASC LIMIT 1")
            company = cursor.fetchone()

            # Branches
            cursor.execute("""
                SELECT b.id, b.branch_name, b.branch_code, b.location, b.created_at, COUNT(e.id) AS employee_count
                FROM branches b
                LEFT JOIN employees e ON b.id = e.branch_id AND e.status = 'ACTIVE'
                GROUP BY b.id ORDER BY b.id ASC
            """)
            branches = cursor.fetchall()
            for b in branches:
                b['created_at_display'] = b['created_at'].strftime('%Y-%m-%d') if b.get('created_at') else 'N/A'

            # Departments
            cursor.execute("""
                SELECT d.id, d.department_name, d.created_at, COUNT(e.id) AS employee_count
                FROM departments d
                LEFT JOIN employees e ON d.id = e.department_id AND e.status = 'ACTIVE'
                GROUP BY d.id ORDER BY d.id ASC
            """)
            departments = cursor.fetchall()
            for d in departments:
                d['created_at_display'] = d['created_at'].strftime('%Y-%m-%d') if d.get('created_at') else 'N/A'

            # Designations
            cursor.execute("""
                SELECT dg.id, dg.designation_name, dg.created_at, COUNT(e.id) AS employee_count
                FROM designations dg
                LEFT JOIN employees e ON dg.id = e.designation_id AND e.status = 'ACTIVE'
                GROUP BY dg.id ORDER BY dg.id ASC
            """)
            designations = cursor.fetchall()
            for d in designations:
                d['created_at_display'] = d['created_at'].strftime('%Y-%m-%d') if d.get('created_at') else 'N/A'

            # Users
            cursor.execute("SELECT id, username, email, role, created_at FROM users ORDER BY id ASC")
            system_users = cursor.fetchall()
            for u in system_users:
                u['created_at_display'] = u['created_at'].strftime('%Y-%m-%d') if u.get('created_at') else 'N/A'
        except Exception as err:
            print(f"Settings fetch error: {err}")
        finally:
            conn.close()

    return render_template('settings.html',
                           active_tab=tab,
                           company=company,
                           branches=branches,
                           departments=departments,
                           designations=designations,
                           system_users=system_users)

# ==================== COMPANY UPDATE ====================
@app.route('/company/update', methods=['POST'])
@login_required
def update_company():
    company_name = request.form.get('company_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()

    if not company_name:
        return jsonify({'status': 'error', 'msg': 'Company name is required.'}), 400

    logo_file = request.files.get('logo')
    logo_rel_path = None

    if logo_file and logo_file.filename:
        filename = secure_filename(logo_file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        logo_file.save(save_path)
        logo_rel_path = f"uploads/{filename}"

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM company LIMIT 1")
        row = cursor.fetchone()

        if row:
            if logo_rel_path:
                cursor.execute("""
                    UPDATE company SET company_name=%s, email=%s, phone=%s, address=%s, logo_path=%s WHERE id=%s
                """, (company_name, email, phone, address, logo_rel_path, row['id']))
            else:
                cursor.execute("""
                    UPDATE company SET company_name=%s, email=%s, phone=%s, address=%s WHERE id=%s
                """, (company_name, email, phone, address, row['id']))
        else:
            cursor.execute("""
                INSERT INTO company (company_name, email, phone, address, logo_path) VALUES (%s, %s, %s, %s, %s)
            """, (company_name, email, phone, address, logo_rel_path or ''))

        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Company profile updated successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500
    finally:
        conn.close()

# ==================== BRANCHES CRUD ====================
@app.route('/branches/add', methods=['POST'])
@login_required
def add_branch():
    branch_name = request.form.get('branch_name', '').strip()
    branch_code = request.form.get('branch_code', '').strip()
    location = request.form.get('location', '').strip()

    if not branch_name or not branch_code:
        return jsonify({'status': 'error', 'msg': 'Branch Name and Branch Code are required.'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed'}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO branches (branch_name, branch_code, location) VALUES (%s, %s, %s)",
                       (branch_name, branch_code, location))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Branch created successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': f"Branch Name or Code already exists: {e}"}), 400
    finally:
        conn.close()

@app.route('/branches/edit/<int:branch_id>', methods=['POST'])
@login_required
def edit_branch(branch_id):
    branch_name = request.form.get('branch_name', '').strip()
    branch_code = request.form.get('branch_code', '').strip()
    location = request.form.get('location', '').strip()

    if not branch_name or not branch_code:
        return jsonify({'status': 'error', 'msg': 'Branch Name and Branch Code are required.'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed'}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE branches SET branch_name=%s, branch_code=%s, location=%s WHERE id=%s",
                       (branch_name, branch_code, location, branch_id))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Branch updated successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally:
        conn.close()

@app.route('/branches/delete/<int:branch_id>', methods=['POST'])
@login_required
def delete_branch(branch_id):
    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM employees WHERE branch_id = %s", (branch_id,))
        count_res = cursor.fetchone()
        if count_res and count_res['total'] > 0:
            return jsonify({'status': 'error', 'msg': f"Cannot delete: {count_res['total']} employee(s) assigned to this branch."}), 400

        cursor.execute("DELETE FROM branches WHERE id = %s", (branch_id,))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Branch deleted successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally:
        conn.close()

# ==================== USER MANAGEMENT ====================
@app.route('/users/add', methods=['POST'])
@login_required
def add_user():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'admin').strip()

    if not username or not email or not password:
        return jsonify({'status': 'error', 'msg': 'All user fields are required.'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed.'}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
                       (username, email, password, role))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'User created successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': f"Username or Email already exists: {e}"}), 400
    finally:
        conn.close()

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        return jsonify({'status': 'error', 'msg': 'Cannot delete your own active session account.'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'DB connection failed.'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        u = cursor.fetchone()
        if u and u['username'] == 'admin':
            return jsonify({'status': 'error', 'msg': 'Main admin account is protected and cannot be deleted.'}), 400

        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'User deleted successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500
    finally:
        conn.close()

# ==================== DEPARTMENTS & DESIGNATIONS ====================
@app.route('/departments')
@login_required
def departments_page():
    return redirect('/settings/departments')

@app.route('/departments/add', methods=['POST'])
@login_required
def add_department():
    dept_name = request.form.get('department_name', '').strip()
    if not dept_name:
        return jsonify({'status': 'error', 'msg': 'Department name required'}), 400
    conn = get_db_connection()
    if conn is None: return jsonify({'status': 'error', 'msg': 'DB failed'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO departments (department_name) VALUES (%s)", (dept_name,))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Department added.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally: conn.close()

@app.route('/departments/edit/<int:dept_id>', methods=['POST'])
@login_required
def edit_department(dept_id):
    dept_name = request.form.get('department_name', '').strip()
    conn = get_db_connection()
    if conn is None: return jsonify({'status': 'error', 'msg': 'DB failed'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE departments SET department_name = %s WHERE id = %s", (dept_name, dept_id))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Department updated.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally: conn.close()

@app.route('/departments/delete/<int:dept_id>', methods=['POST'])
@login_required
def delete_department(dept_id):
    conn = get_db_connection()
    if conn is None: return jsonify({'status': 'error', 'msg': 'DB failed'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM employees WHERE department_id = %s", (dept_id,))
        count_res = cursor.fetchone()
        if count_res and count_res['total'] > 0:
            return jsonify({'status': 'error', 'msg': f"Cannot delete: {count_res['total']} employee(s) assigned."}), 400
        cursor.execute("DELETE FROM departments WHERE id = %s", (dept_id,))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Department deleted.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally: conn.close()

@app.route('/designations')
@login_required
def designations_page():
    return redirect('/settings/designations')

@app.route('/designations/add', methods=['POST'])
@login_required
def add_designation():
    desig_name = request.form.get('designation_name', '').strip()
    conn = get_db_connection()
    if conn is None: return jsonify({'status': 'error', 'msg': 'DB failed'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO designations (designation_name) VALUES (%s)", (desig_name,))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Designation added.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally: conn.close()

@app.route('/designations/edit/<int:desig_id>', methods=['POST'])
@login_required
def edit_designation(desig_id):
    desig_name = request.form.get('designation_name', '').strip()
    conn = get_db_connection()
    if conn is None: return jsonify({'status': 'error', 'msg': 'DB failed'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE designations SET designation_name = %s WHERE id = %s", (desig_name, desig_id))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Designation updated.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally: conn.close()

@app.route('/designations/delete/<int:desig_id>', methods=['POST'])
@login_required
def delete_designation(desig_id):
    conn = get_db_connection()
    if conn is None: return jsonify({'status': 'error', 'msg': 'DB failed'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM employees WHERE designation_id = %s", (desig_id,))
        count_res = cursor.fetchone()
        if count_res and count_res['total'] > 0:
            return jsonify({'status': 'error', 'msg': f"Cannot delete: {count_res['total']} employee(s) assigned."}), 400
        cursor.execute("DELETE FROM designations WHERE id = %s", (desig_id,))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Designation deleted.'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    finally: conn.close()

# ==================== OTHER ROUTES ====================
@app.route('/register-employee')
@login_required
def register_employee_page():
    departments, designations, branches = fetch_metadata()
    return render_template('register.html', departments=departments, designations=designations, branches=branches)

@app.route('/attendance')
@login_required
def attendance_page():
    return render_template('attendance.html')

@app.route('/api/metadata', methods=['GET'])
@login_required
def api_metadata():
    departments, designations, branches = fetch_metadata()
    return jsonify({'departments': departments, 'designations': designations, 'branches': branches})

@app.route('/register', methods=['POST'])
@login_required
def register():
    data = request.form
    emp_code = data.get('emp_code', '').strip()
    full_name = data.get('full_name', '').strip()
    img_data = data.get('photo')
    
    if not emp_code or not full_name:
        return jsonify({'status': 'error', 'msg': 'Employee Code and Full Name are required.'}), 400

    dept_id = data.get('dept_id')
    desig_id = data.get('desig_id')
    branch_id = data.get('branch_id')

    if not dept_id or not desig_id:
        return jsonify({'status': 'error', 'msg': 'Please select Department and Designation.'}), 400

    photo_path = None
    face_encoding_str = "[]"

    if img_data:
        try:
            header, encoded = img_data.split(',', 1)
            img_bytes = base64.b64decode(encoded)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            photos_dir = os.path.join(PROJECT_ROOT, 'captured_photos')
            os.makedirs(photos_dir, exist_ok=True)
            rel_photo_path = os.path.join('captured_photos', f"{emp_code}.jpg")
            abs_photo_path = os.path.join(PROJECT_ROOT, rel_photo_path)
            cv2.imwrite(abs_photo_path, img)
            photo_path = rel_photo_path

            encoding = face_utils.extract_face_encoding(img)
            if encoding is not None:
                face_encoding_str = json.dumps(encoding.tolist())
            else:
                face_encoding_str = "[]"

        except Exception as img_err:
            print(f"Image error: {img_err}")

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'Database connection failed'}), 500

    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO employees 
            (emp_code, full_name, email, phone, address, branch_id, department_id, designation_id, face_encoding, photo_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            emp_code,
            full_name,
            data.get('email', '').strip(),
            data.get('phone', '').strip(),
            data.get('address', '').strip(),
            int(branch_id) if branch_id else None,
            int(dept_id),
            int(desig_id),
            face_encoding_str,
            photo_path
        )
        cursor.execute(query, values)
        conn.commit()
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500
    finally:
        conn.close()

    return jsonify({'status': 'success', 'msg': f"Employee {full_name} ({emp_code}) registered successfully!"})

@app.route('/api/scan_attendance', methods=['POST'])
@login_required
def scan_attendance():
    req_json = request.get_json(silent=True) or {}
    img_data = req_json.get('photo') or request.form.get('photo')

    if not img_data:
        return jsonify({'status': 'error', 'msg': 'No image data received.'}), 400

    try:
        header, encoded = img_data.split(',', 1)
        img_bytes = base64.b64decode(encoded)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        boxes, yunet_faces = face_utils.detect_faces(img)

        if len(boxes) == 0:
            return jsonify({'status': 'success', 'recognized': False, 'msg': 'Scanning... Position face clearly in camera.'})

        yunet_face = yunet_faces[0] if yunet_faces is not None and len(yunet_faces) > 0 else None
        current_encoding = face_utils.extract_face_encoding(img, bbox=boxes[0], yunet_face=yunet_face)

    except Exception as err:
        return jsonify({'status': 'error', 'msg': f"Image decoding error: {err}"}), 400

    if current_encoding is None:
        return jsonify({'status': 'success', 'recognized': False, 'msg': 'Scanning... Position face clearly.'})

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'msg': 'Database connection failed.'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT e.id, e.emp_code, e.full_name, e.face_encoding, e.photo_path,
                   d.department_name, dg.designation_name
            FROM employees e
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN designations dg ON e.designation_id = dg.id
            WHERE e.status = 'ACTIVE'
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        matched_emp = None
        best_similarity = -1.0

        for r in rows:
            if r['face_encoding']:
                try:
                    vec = np.array(json.loads(r['face_encoding']), dtype=np.float32)
                    if len(vec) == 128:
                        sim = face_utils.compute_similarity(vec, current_encoding)
                        if sim > best_similarity:
                            best_similarity = sim
                            if sim >= face_utils.MATCH_THRESHOLD:
                                matched_emp = r
                except Exception:
                    pass

        if not matched_emp:
            return jsonify({'status': 'success', 'recognized': False, 'msg': 'Face detected, searching database...'})

        emp_code = matched_emp['emp_code']
        emp_name = matched_emp['full_name']
        today_date = datetime.now().strftime('%Y-%m-%d')
        current_time_str = datetime.now().strftime('%H:%M:%S')

        check_query = "SELECT id, in_time FROM attendance WHERE emp_code = %s AND attendance_date = %s"
        cursor.execute(check_query, (emp_code, today_date))
        record = cursor.fetchone()

        already_marked = False
        in_time_display = current_time_str

        if record:
            already_marked = True
            if record.get('in_time'):
                in_time_display = str(record['in_time'])
            msg = f"Already Checked In Today at {in_time_display}"
        else:
            insert_query = """
                INSERT INTO attendance (emp_code, attendance_date, in_time, status)
                VALUES (%s, %s, %s, 'PRESENT')
            """
            cursor.execute(insert_query, (emp_code, today_date, current_time_str))
            conn.commit()
            msg = f"Attendance Marked Successfully for {emp_name}!"

        return jsonify({
            'status': 'success',
            'recognized': True,
            'already_marked': already_marked,
            'msg': msg,
            'employee': {
                'emp_code': emp_code,
                'full_name': emp_name,
                'department_name': matched_emp.get('department_name') or 'N/A',
                'designation_name': matched_emp.get('designation_name') or 'N/A',
                'in_time': in_time_display,
                'photo_path': matched_emp.get('photo_path')
            }
        })

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
