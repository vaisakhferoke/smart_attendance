import re, os, sys
from flask import request, jsonify
from werkzeug.security import check_password_hash
from . import api_bp

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)
from db_config import get_db_connection

def parse_graphql_query(query_str):
    """Simple parser for Graph query operations and parameters"""
    operation = None
    args = {}
    
    if 'updateEmployeeFcm' in query_str or 'updateFcm' in query_str:
        operation = 'updateEmployeeFcm'
        un_match = re.search(r'(?:username|emp_id|emp_code)\s*:\s*["\']?([^"\',\s)]+)["\']?', query_str)
        fcm_match = re.search(r'fcm_token\s*:\s*["\']([^"\']+)["\']', query_str)
        ver_match = re.search(r'app_version\s*:\s*["\']([^"\']+)["\']', query_str)
        plat_match = re.search(r'app_platform\s*:\s*["\']([^"\']+)["\']', query_str)
        if un_match: args['identifier'] = un_match.group(1)
        if fcm_match: args['fcm_token'] = fcm_match.group(1)
        if ver_match: args['app_version'] = ver_match.group(1)
        if plat_match: args['app_platform'] = plat_match.group(1)

    elif 'loginEmployee' in query_str:
        operation = 'loginEmployee'
        un_match = re.search(r'username\s*:\s*["\']([^"\']+)["\']', query_str)
        pw_match = re.search(r'password\s*:\s*["\']([^"\']+)["\']', query_str)
        fcm_match = re.search(r'fcm_token\s*:\s*["\']([^"\']+)["\']', query_str)
        ver_match = re.search(r'app_version\s*:\s*["\']([^"\']+)["\']', query_str)
        plat_match = re.search(r'app_platform\s*:\s*["\']([^"\']+)["\']', query_str)
        if un_match: args['username'] = un_match.group(1)
        if pw_match: args['password'] = pw_match.group(1)
        if fcm_match: args['fcm_token'] = fcm_match.group(1)
        if ver_match: args['app_version'] = ver_match.group(1)
        if plat_match: args['app_platform'] = plat_match.group(1)
        
    elif 'getEmployee' in query_str or 'employee(' in query_str or 'employee {' in query_str:
        operation = 'getEmployee'
        id_match = re.search(r'id\s*:\s*(\d+)', query_str)
        code_match = re.search(r'emp_code\s*:\s*["\']([^"\']+)["\']', query_str)
        if id_match: args['id'] = int(id_match.group(1))
        if code_match: args['emp_code'] = code_match.group(1)
        
    elif 'employees' in query_str:
        operation = 'listEmployees'
        
    return operation, args

@api_bp.route('/graph', methods=['POST', 'GET'])
@api_bp.route('/graphql', methods=['POST', 'GET'])
def graph_api_endpoint():
    """
    Employee Graph API / GraphQL Endpoint.
    Accepts GraphQL query string payload or Graph API JSON payload.
    """
    if request.method == 'GET':
        return jsonify({
            'name': 'Smart Attendance Employee Graph API',
            'version': '1.1',
            'endpoints': ['/api/graph', '/api/graphql'],
            'supported_queries': ['loginEmployee', 'updateEmployeeFcm', 'getEmployee', 'listEmployees']
        })

    payload = request.get_json(silent=True) or {}
    query_str = payload.get('query', '')
    operation = payload.get('operation')
    variables = payload.get('variables', {})

    if not operation and query_str:
        operation, parsed_args = parse_graphql_query(query_str)
        variables.update(parsed_args)

    if not operation:
        operation = 'loginEmployee'

    # 1. GRAPH OPERATION: updateEmployeeFcm
    if operation == 'updateEmployeeFcm' or operation == 'updateFcmToken':
        identifier = variables.get('identifier') or variables.get('emp_id') or variables.get('emp_code') or variables.get('username')
        identifier = str(identifier or '').strip()
        fcm_token = variables.get('fcm_token', '').strip()
        app_version = variables.get('app_version', '').strip() or None
        app_platform = variables.get('app_platform', '').strip() or None

        if not identifier or not fcm_token:
            return jsonify({
                'errors': [{'message': 'updateEmployeeFcm requires identifier and fcm_token.'}],
                'data': {'updateEmployeeFcm': None}
            }), 400

        conn = get_db_connection()
        if conn is None:
            return jsonify({'errors': [{'message': 'DB Connection Error'}], 'data': {'updateEmployeeFcm': None}}), 500

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, emp_code, username, full_name FROM employees WHERE id = %s OR emp_code = %s OR username = %s LIMIT 1",
                           (identifier, identifier, identifier))
            emp = cursor.fetchone()

            if not emp:
                return jsonify({'errors': [{'message': 'Employee not found'}], 'data': {'updateEmployeeFcm': None}}), 404

            emp_id = emp['id']
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
            updated = cursor.fetchone() or {}

            return jsonify({
                'data': {
                    'updateEmployeeFcm': {
                        'success': True,
                        'message': f"FCM Token and App Info updated for {emp['full_name']}",
                        'emp_id': emp_id,
                        'emp_code': emp['emp_code'],
                        'fcm_token': updated.get('fcm_token'),
                        'app_version': updated.get('app_version'),
                        'app_platform': updated.get('app_platform'),
                        'last_logged_date': str(updated['last_login_date']) if updated.get('last_login_date') else None
                    }
                }
            }), 200
        except Exception as err:
            return jsonify({'errors': [{'message': str(err)}], 'data': {'updateEmployeeFcm': None}}), 500
        finally:
            conn.close()

    # 2. GRAPH OPERATION: loginEmployee
    elif operation == 'loginEmployee':
        username = variables.get('username') or variables.get('emp_code') or variables.get('email') or ''
        password = variables.get('password') or ''
        fcm_token = variables.get('fcm_token')
        app_version = variables.get('app_version')
        app_platform = variables.get('app_platform')
        username = str(username).strip()

        if not username or not password:
            return jsonify({
                'errors': [{'message': 'loginEmployee requires username and password.'}],
                'data': {'loginEmployee': None}
            }), 400

        conn = get_db_connection()
        if conn is None:
            return jsonify({'errors': [{'message': 'Database Connection Failure.'}], 'data': {'loginEmployee': None}}), 500

        try:
            cursor = conn.cursor(dictionary=True)
            sql = """
                SELECT e.id, e.emp_code, e.username, e.password, e.full_name, e.email, e.phone,
                       e.address, e.photo_path, e.status, e.fcm_token, e.app_version, e.app_platform,
                       e.last_login_date, e.created_at,
                       d.department_name, dg.designation_name, b.branch_name
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                LEFT JOIN designations dg ON e.designation_id = dg.id
                LEFT JOIN branches b ON e.branch_id = b.id
                WHERE e.username = %s OR e.emp_code = %s OR e.email = %s
                LIMIT 1
            """
            cursor.execute(sql, (username, username, username))
            emp = cursor.fetchone()

            if not emp:
                return jsonify({
                    'errors': [{'message': f"No employee found matching username: '{username}'"}],
                    'data': {'loginEmployee': {'success': False, 'employee': None}}
                }), 200

            if emp.get('status') != 'ACTIVE':
                return jsonify({
                    'errors': [{'message': 'Employee account is INACTIVE.'}],
                    'data': {'loginEmployee': {'success': False, 'employee': None}}
                }), 200

            stored_hash = emp.get('password')
            if not stored_hash or not check_password_hash(stored_hash, password):
                return jsonify({
                    'errors': [{'message': 'Invalid password.'}],
                    'data': {'loginEmployee': {'success': False, 'employee': None}}
                }), 200

            # Update last_login_date and optional device/fcm info on graph login
            emp_id = emp['id']
            cursor.execute("""
                UPDATE employees
                SET last_login_date = NOW(),
                    fcm_token = COALESCE(%s, fcm_token),
                    app_version = COALESCE(%s, app_version),
                    app_platform = COALESCE(%s, app_platform)
                WHERE id = %s
            """, (fcm_token, app_version, app_platform, emp_id))
            conn.commit()

            cursor.execute("SELECT fcm_token, app_version, app_platform, last_login_date FROM employees WHERE id = %s", (emp_id,))
            updated = cursor.fetchone() or {}

            photo_rel = emp.get('photo_path') or ''
            clean_photo_url = f"/{photo_rel.replace('\\', '/')}" if photo_rel else None

            return jsonify({
                'data': {
                    'loginEmployee': {
                        'success': True,
                        'message': f"Authentication successful for {emp['full_name']}",
                        'employee': {
                            'id': emp['id'],
                            'emp_code': emp['emp_code'],
                            'username': emp['username'],
                            'full_name': emp['full_name'],
                            'email': emp['email'],
                            'phone': emp['phone'],
                            'status': emp['status'],
                            'branch': emp.get('branch_name') or 'Main HQ',
                            'department': emp.get('department_name') or 'General',
                            'designation': emp.get('designation_name') or 'Staff',
                            'fcm_token': updated.get('fcm_token') or emp.get('fcm_token'),
                            'app_version': updated.get('app_version') or emp.get('app_version'),
                            'app_platform': updated.get('app_platform') or emp.get('app_platform'),
                            'last_logged_date': str(updated['last_login_date']) if updated.get('last_login_date') else None,
                            'photo_url': clean_photo_url
                        }
                    }
                }
            }), 200
        except Exception as err:
            return jsonify({'errors': [{'message': f"Graph Exception: {str(err)}"}], 'data': {'loginEmployee': None}}), 500
        finally:
            conn.close()

    # 3. GRAPH OPERATION: getEmployee
    elif operation == 'getEmployee':
        emp_id = variables.get('id')
        emp_code = variables.get('emp_code')

        conn = get_db_connection()
        if conn is None:
            return jsonify({'errors': [{'message': 'DB Connection Error'}], 'data': {'employee': None}}), 500

        try:
            cursor = conn.cursor(dictionary=True)
            sql = """
                SELECT e.id, e.emp_code, e.username, e.full_name, e.email, e.phone, e.status,
                       e.fcm_token, e.app_version, e.app_platform, e.last_login_date,
                       d.department_name, dg.designation_name, b.branch_name
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                LEFT JOIN designations dg ON e.designation_id = dg.id
                LEFT JOIN branches b ON e.branch_id = b.id
                WHERE e.id = %s OR e.emp_code = %s
                LIMIT 1
            """
            cursor.execute(sql, (emp_id, emp_code))
            emp = cursor.fetchone()

            if emp and emp.get('last_login_date'):
                emp['last_logged_date'] = str(emp['last_login_date'])

            return jsonify({'data': {'employee': emp}}), 200
        except Exception as err:
            return jsonify({'errors': [{'message': str(err)}], 'data': {'employee': None}}), 500
        finally:
            conn.close()

    # 4. GRAPH OPERATION: listEmployees
    elif operation == 'listEmployees':
        conn = get_db_connection()
        if conn is None:
            return jsonify({'errors': [{'message': 'DB Connection Error'}], 'data': {'employees': []}}), 500
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT e.id, e.emp_code, e.username, e.full_name, e.email, e.status,
                       e.fcm_token, e.app_version, e.app_platform, e.last_login_date,
                       d.department_name, dg.designation_name, b.branch_name
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                LEFT JOIN designations dg ON e.designation_id = dg.id
                LEFT JOIN branches b ON e.branch_id = b.id
                ORDER BY e.id DESC
            """)
            employees = cursor.fetchall()
            for emp in employees:
                if emp.get('last_login_date'):
                    emp['last_logged_date'] = str(emp['last_login_date'])
            return jsonify({'data': {'employees': employees}}), 200
        except Exception as err:
            return jsonify({'errors': [{'message': str(err)}], 'data': {'employees': []}}), 500
        finally:
            conn.close()

    return jsonify({'errors': [{'message': f"Unsupported Graph operation: '{operation}'"}]}), 400
