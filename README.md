# MS Ladies Shoes Collection (SQLite version – no XAMPP / MySQL needed)

1. Install Python 3.9+ (python.org)
2. `pip install -r requirements.txt`
3. `python init_db.py`  -> creates shop.db and your admin login
4. `python app.py`  -> http://localhost:3570  (admin: /admin/login)
5. **Share Publicly with Custom Subdomain**:
   - Double click `run_mscollection.bat` to host your site at `https://mscollection.loca.lt` (LocalTunnel).
   - Or double click `run_online.bat` to pick between LocalTunnel (`mscollection.loca.lt`) or SSH (`localhost.run`).

Optional: set SITE_URL (e.g. https://yourdomain.com) and SECRET_KEY as environment variables.
Back up by copying shop.db and the static/uploads folder.
