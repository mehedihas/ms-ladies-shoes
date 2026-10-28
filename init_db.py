"""Run once: python init_db.py -> creates shop.db, tables and the default admin user."""
import sys
from werkzeug.security import generate_password_hash
import db

def setup():
    db.init_db()
    username = input('Admin username [Mehedi]: ').strip() if sys.stdin.isatty() else 'Mehedi'
    password = 'Mehedi%123'
    if sys.stdin.isatty():
        import getpass
        password = getpass.getpass('Admin password [default: Mehedi%123]: ') or 'Mehedi%123'
    
    db.upsert_admin(username, generate_password_hash(password))
    print(f"Database initialized! Admin username: '{username}'")
    print("Start the server with: python app.py")

if __name__ == '__main__':
    setup()
