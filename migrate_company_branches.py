import os, sys
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.append(PROJECT_ROOT)
from db_config import get_db_connection

def migrate():
    conn = get_db_connection()
    if conn is None:
        print("Failed to connect to MySQL database.")
        return

    try:
        cursor = conn.cursor()
        
        # 1. Company Table
        print("Creating 'company' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company (
                id INT AUTO_INCREMENT PRIMARY KEY,
                company_name VARCHAR(150) NOT NULL,
                email VARCHAR(100),
                phone VARCHAR(50),
                address TEXT,
                logo_path VARCHAR(255),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("SELECT COUNT(*) FROM company")
        res = cursor.fetchone()
        if res[0] == 0:
            cursor.execute("""
                INSERT INTO company (company_name, email, phone, address)
                VALUES (%s, %s, %s, %s)
            """, ('Smart Biometric Solutions Inc.', 'contact@smartattendance.com', '+1 (800) 555-0199', '100 Innovation Parkway, Suite 400, Tech City'))
            conn.commit()
            print("Seeded default company profile.")

        # 2. Branches Table
        print("Creating 'branches' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS branches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                branch_name VARCHAR(100) NOT NULL UNIQUE,
                branch_code VARCHAR(50) NOT NULL UNIQUE,
                location VARCHAR(150),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("SELECT COUNT(*) FROM branches")
        res_b = cursor.fetchone()
        if res_b[0] == 0:
            cursor.execute("""
                INSERT INTO branches (branch_name, branch_code, location)
                VALUES (%s, %s, %s), (%s, %s, %s)
            """, (
                'Headquarters', 'HQ-01', 'Main Innovation Campus',
                'West Branch', 'BR-02', 'Downtown Financial District'
            ))
            conn.commit()
            print("Seeded default branches.")

        # 3. Add branch_id to employees table
        try:
            cursor.execute("ALTER TABLE employees ADD COLUMN branch_id INT NULL AFTER designation_id")
            conn.commit()
            print("Added 'branch_id' column to 'employees' table.")
        except Exception as e:
            print("Notice regarding 'branch_id' column:", e)

        print("Migration finished successfully!")

    except Exception as err:
        print("Migration error:", err)
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
