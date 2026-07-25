import secrets, os, sys
from flask import request, jsonify, session
from werkzeug.security import check_password_hash
from . import api_bp

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)
from db_config import get_db_connection

@api_bp.route('/v1/employee/login', methods=['POST'])
def employee_login_api():
    """
    Employee Authentication REST API.
    Accepts JSON body or Form data with fields:
      - username (or emp_code / email)
      - password
      - fcm_token (optional)
      - app_version (optional)
      - app_platform (optional)
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    login_identifier = data.get('username') or data.get('emp_code') or data.get('email') or ''
    login_identifier = login_identifier.strip()
    raw_password = data.get('password', '').strip()

    fcm_token = data.get('fcm_token', '').strip() or None
    app_version = data.get('app_version', '').strip() or None
    app_platform = data.get('app_platform', '').strip() or None

    if not login_identifier or not raw_password:
        return jsonify({
            'status': 'error',
            'code': 400,
            'message': 'Username/EmpCode/Email and Password are required.'
        }), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({
            'status': 'error',
            'code': 500,
            'message': 'Database connection error.'
        }), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT e.id, e.emp_code, e.username, e.password, e.full_name, e.email, e.phone,
                   e.address, e.photo_path, e.status, e.fcm_token, e.app_version, e.app_platform,
                   e.last_login_date, e.created_at,
                   d.department_name, dg.designation_name, b.branch_name, b.branch_code
            FROM employees e
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN designations dg ON e.designation_id = dg.id
            LEFT JOIN branches b ON e.branch_id = b.id
            WHERE e.username = %s OR e.emp_code = %s OR e.email = %s
            LIMIT 1
        """
        cursor.execute(query, (login_identifier, login_identifier, login_identifier))
        employee = cursor.fetchone()

        if not employee:
            return jsonify({
                'status': 'error',
                'code': 401,
                'message': 'Invalid username or credentials.'
            }), 401

        if employee.get('status') != 'ACTIVE':
            return jsonify({
                'status': 'error',
                'code': 403,
                'message': 'Employee account is INACTIVE. Please contact administration.'
            }), 403

        stored_password_hash = employee.get('password')

        if not stored_password_hash:
            return jsonify({
                'status': 'error',
                'code': 401,
                'message': 'No password set for this employee account. Please request password setup.'
            }), 401

        # Verify hashed password
        if not check_password_hash(stored_password_hash, raw_password):
            return jsonify({
                'status': 'error',
                'code': 401,
                'message': 'Invalid password.'
            }), 401

        # Update last_login_date and optional device/fcm info on login
        emp_id = employee['id']
        cursor.execute("""
            UPDATE employees
            SET last_login_date = NOW(),
                fcm_token = COALESCE(%s, fcm_token),
                app_version = COALESCE(%s, app_version),
                app_platform = COALESCE(%s, app_platform)
            WHERE id = %s
        """, (fcm_token, app_version, app_platform, emp_id))
        conn.commit()

        # Re-fetch updated fields
        cursor.execute("SELECT fcm_token, app_version, app_platform, last_login_date FROM employees WHERE id = %s", (emp_id,))
        updated = cursor.fetchone() or {}

        # Generate access auth token
        auth_token = secrets.token_hex(24)

        photo_rel = employee.get('photo_path') or ''
        clean_photo_url = f"/{photo_rel.replace('\\', '/')}" if photo_rel else None

        employee_data = {
            'id': employee['id'],
            'emp_code': employee['emp_code'],
            'username': employee['username'],
            'full_name': employee['full_name'],
            'email': employee['email'],
            'phone': employee['phone'],
            'address': employee['address'],
            'status': employee['status'],
            'branch': employee.get('branch_name') or 'Main HQ',
            'department': employee.get('department_name') or 'General',
            'designation': employee.get('designation_name') or 'Staff',
            'fcm_token': updated.get('fcm_token') or employee.get('fcm_token'),
            'app_version': updated.get('app_version') or employee.get('app_version'),
            'app_platform': updated.get('app_platform') or employee.get('app_platform'),
            'last_logged_date': str(updated.get('last_login_date')) if updated.get('last_login_date') else None,
            'photo_url': clean_photo_url,
            'registered_at': str(employee['created_at']) if employee.get('created_at') else None
        }

        return jsonify({
            'status': 'success',
            'code': 200,
            'message': f"Welcome back, {employee['full_name']}!",
            'auth_token': auth_token,
            'employee': employee_data
        }), 200

    except Exception as err:
        return jsonify({
            'status': 'error',
            'code': 500,
            'message': f"Server exception during login: {str(err)}"
        }), 500
    finally:
        conn.close()

@api_bp.route('/v1/employee/fcm-update', methods=['POST'])
@api_bp.route('/v1/employee/update-fcm', methods=['POST'])
def update_fcm_token_api():
    """
    Employee FCM Push Notification Token and App Info Update REST API.
    Accepts JSON body or Form data:
      - emp_id / emp_code / username (required)
      - fcm_token (required)
      - app_version (optional, e.g. "1.0.4")
      - app_platform (optional, e.g. "android" / "ios")
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    identifier = data.get('emp_id') or data.get('emp_code') or data.get('username') or ''
    identifier = str(identifier).strip()
    fcm_token = data.get('fcm_token', '').strip()
    app_version = data.get('app_version', '').strip() or None
    app_platform = data.get('app_platform', '').strip() or None

    if not identifier:
        return jsonify({
            'status': 'error',
            'code': 400,
            'message': 'emp_id, emp_code, or username is required.'
        }), 400

    if not fcm_token:
        return jsonify({
            'status': 'error',
            'code': 400,
            'message': 'fcm_token is required.'
        }), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'code': 500, 'message': 'Database Connection Error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, emp_code, username, full_name 
            FROM employees 
            WHERE id = %s OR emp_code = %s OR username = %s
            LIMIT 1
        """, (identifier, identifier, identifier))
        employee = cursor.fetchone()

        if not employee:
            return jsonify({'status': 'error', 'code': 404, 'message': 'Employee not found'}), 404

        emp_id = employee['id']

        cursor.execute("""
            UPDATE employees 
            SET fcm_token = %s,
                app_version = COALESCE(%s, app_version),
                app_platform = COALESCE(%s, app_platform),
                last_login_date = NOW()
            WHERE id = %s
        """, (fcm_token, app_version, app_platform, emp_id))
        conn.commit()

        cursor.execute("SELECT fcm_token, app_version, app_platform, last_login_date FROM employees WHERE id = %s", (emp_id,))
        updated_row = cursor.fetchone()

        return jsonify({
            'status': 'success',
            'code': 200,
            'message': f"FCM token and device information updated successfully for {employee['full_name']}",
            'updated_info': {
                'emp_id': emp_id,
                'emp_code': employee['emp_code'],
                'username': employee['username'],
                'fcm_token': updated_row.get('fcm_token'),
                'app_version': updated_row.get('app_version'),
                'app_platform': updated_row.get('app_platform'),
                'last_logged_date': str(updated_row['last_login_date']) if updated_row.get('last_login_date') else None
            }
        }), 200

    except Exception as err:
        return jsonify({'status': 'error', 'code': 500, 'message': str(err)}), 500
    finally:
        conn.close()

@api_bp.route('/v1/employee/profile/<int:emp_id>', methods=['GET'])
def get_employee_profile_api(emp_id):
    """Fetch Employee Profile details API"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'message': 'DB Connection Error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT e.id, e.emp_code, e.username, e.full_name, e.email, e.phone, e.address,
                   e.photo_path, e.status, e.fcm_token, e.app_version, e.app_platform,
                   e.last_login_date, e.created_at,
                   d.department_name, dg.designation_name, b.branch_name
            FROM employees e
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN designations dg ON e.designation_id = dg.id
            LEFT JOIN branches b ON e.branch_id = b.id
            WHERE e.id = %s
        """
        cursor.execute(query, (emp_id,))
        emp = cursor.fetchone()

        if not emp:
            return jsonify({'status': 'error', 'message': 'Employee not found'}), 404

        photo_rel = emp.get('photo_path') or ''
        clean_photo_url = f"/{photo_rel.replace('\\', '/')}" if photo_rel else None

        return jsonify({
            'status': 'success',
            'employee': {
                'id': emp['id'],
                'emp_code': emp['emp_code'],
                'username': emp['username'],
                'full_name': emp['full_name'],
                'email': emp['email'],
                'phone': emp['phone'],
                'address': emp['address'],
                'status': emp['status'],
                'branch': emp.get('branch_name') or 'Main HQ',
                'department': emp.get('department_name') or 'General',
                'designation': emp.get('designation_name') or 'Staff',
                'fcm_token': emp.get('fcm_token'),
                'app_version': emp.get('app_version'),
                'app_platform': emp.get('app_platform'),
                'last_logged_date': str(emp['last_login_date']) if emp.get('last_login_date') else None,
                'photo_url': clean_photo_url,
                'registered_at': str(emp['created_at']) if emp.get('created_at') else None
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()
