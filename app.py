import os
from urllib.parse import quote
from flask import Flask
from werkzeug.security import generate_password_hash
from config import Config
from routes import main_bp
import db

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload folders exist
os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'images'), exist_ok=True)
os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'videos'), exist_ok=True)

# Ensure database tables exist and default admin is seeded if empty
db.init_db()
try:
    if db.count_admins() == 0:
        db.upsert_admin('Mehedi', generate_password_hash('Mehedi%123'))
except Exception:
    pass

app.register_blueprint(main_bp)


@app.context_processor
def inject_globals():
    chat = "https://wa.me/88%s?text=%s" % (
        Config.SUPPORT_WHATSAPP.lstrip('0'),
        quote("Hello MS Ladies Shoes, I need assistance"))
    return dict(shop_name=Config.SHOP_NAME, chat_url=chat)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3570))
    app.run(debug=True, host='0.0.0.0', port=port)
