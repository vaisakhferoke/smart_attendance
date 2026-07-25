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
    """
    # Accept JSON or Form Data
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    login_identifier = data.get('username') or data.get('emp_code') or data.get('email') or ''
    login_identifier = login_identifier.strip()
    raw_password = data.get('password', '').strip()

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
                   e.address, e.photo_path, e.status, e.created_at,
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

        # Verify hashed password using Werkzeug check_password_hash
        if not check_password_hash(stored_password_hash, raw_password):
            return jsonify({
                'status': 'error',
                'code': 401,
                'message': 'Invalid password.'
            }), 401

        # Generate access auth token
        auth_token = secrets.token_hex(24)

        # Build clean employee response object (excluding password hash)
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
                   e.photo_path, e.status, e.created_at,
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
                'photo_url': clean_photo_url,
                'registered_at': str(emp['created_at']) if emp.get('created_at') else None
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()
