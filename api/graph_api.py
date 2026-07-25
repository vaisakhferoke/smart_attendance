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
    
    # Check for loginEmployee query/mutation
    if 'loginEmployee' in query_str:
        operation = 'loginEmployee'
        # Extract arguments from query string like loginEmployee(username: "foo", password: "bar")
        un_match = re.search(r'username\s*:\s*["\']([^"\']+)["\']', query_str)
        pw_match = re.search(r'password\s*:\s*["\']([^"\']+)["\']', query_str)
        if un_match: args['username'] = un_match.group(1)
        if pw_match: args['password'] = pw_match.group(1)
        
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
    Accepts GraphQL query string payload:
      { "query": "mutation { loginEmployee(username: \"...\", password: \"...\") { success employee { id emp_code full_name email branch } } }" }
    Or Graph API JSON payload:
      { "operation": "loginEmployee", "variables": { "username": "...", "password": "..." } }
    """
    if request.method == 'GET':
        return jsonify({
            'name': 'Smart Attendance Employee Graph API',
            'version': '1.0',
            'endpoints': ['/api/graph', '/api/graphql'],
            'supported_queries': ['loginEmployee', 'getEmployee', 'listEmployees']
        })

    payload = request.get_json(silent=True) or {}
    query_str = payload.get('query', '')
    operation = payload.get('operation')
    variables = payload.get('variables', {})

    if not operation and query_str:
        operation, parsed_args = parse_graphql_query(query_str)
        variables.update(parsed_args)

    if not operation:
        operation = 'loginEmployee' # default graph operation

    # 1. GRAPH OPERATION: loginEmployee
    if operation == 'loginEmployee':
        username = variables.get('username') or variables.get('emp_code') or variables.get('email') or ''
        password = variables.get('password') or ''
        username = str(username).strip()

        if not username or not password:
            return jsonify({
                'errors': [{'message': 'loginEmployee requires username and password parameters.'}],
                'data': {'loginEmployee': None}
            }), 400

        conn = get_db_connection()
        if conn is None:
            return jsonify({
                'errors': [{'message': 'Database Connection Failure.'}],
                'data': {'loginEmployee': None}
            }), 500

        try:
            cursor = conn.cursor(dictionary=True)
            sql = """
                SELECT e.id, e.emp_code, e.username, e.password, e.full_name, e.email, e.phone,
                       e.address, e.photo_path, e.status, e.created_at,
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
                    'errors': [{'message': 'Invalid password authentication failed.'}],
                    'data': {'loginEmployee': {'success': False, 'employee': None}}
                }), 200

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
                            'photo_url': clean_photo_url
                        }
                    }
                }
            }), 200
        except Exception as err:
            return jsonify({
                'errors': [{'message': f"Graph Exception: {str(err)}"}],
                'data': {'loginEmployee': None}
            }), 500
        finally:
            conn.close()

    # 2. GRAPH OPERATION: getEmployee
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

            return jsonify({'data': {'employee': emp}}), 200
        except Exception as err:
            return jsonify({'errors': [{'message': str(err)}], 'data': {'employee': None}}), 500
        finally:
            conn.close()

    # 3. GRAPH OPERATION: listEmployees
    elif operation == 'listEmployees':
        conn = get_db_connection()
        if conn is None:
            return jsonify({'errors': [{'message': 'DB Connection Error'}], 'data': {'employees': []}}), 500
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT e.id, e.emp_code, e.username, e.full_name, e.email, e.status,
                       d.department_name, dg.designation_name, b.branch_name
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                LEFT JOIN designations dg ON e.designation_id = dg.id
                LEFT JOIN branches b ON e.branch_id = b.id
                ORDER BY e.id DESC
            """)
            employees = cursor.fetchall()
            return jsonify({'data': {'employees': employees}}), 200
        except Exception as err:
            return jsonify({'errors': [{'message': str(err)}], 'data': {'employees': []}}), 500
        finally:
            conn.close()

    return jsonify({'errors': [{'message': f"Unsupported Graph operation: '{operation}'"}]}), 400
