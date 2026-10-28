import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'ms_ladies_shoes_sec_key_2026_987654321_x9f8e7d6c5b4a3')
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    IS_VERCEL = bool(os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))

    if IS_VERCEL:
        DB_PATH = os.environ.get('DB_PATH', '/tmp/shop.db')
        bundled_db = os.path.join(BASE_DIR, 'shop.db')
        if not os.path.exists(DB_PATH) and os.path.exists(bundled_db):
            try:
                import shutil
                shutil.copy2(bundled_db, DB_PATH)
            except Exception:
                pass
        UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', '/tmp/uploads')
    else:
        DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'shop.db'))
        UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'static', 'uploads'))
    MAX_CONTENT_LENGTH = 35 * 1024 * 1024  # 35 MB (video)
    ALLOWED_IMAGES = {'jpg', 'jpeg', 'png', 'webp'}
    ALLOWED_VIDEOS = {'mp4', 'webm'}

    # Public site URL used in tracking links sent to customers
    # e.g. https://yourdomain.com  (empty = use current host)
    SITE_URL = os.environ.get('SITE_URL', '').rstrip('/')

    SHOP_NAME = "MS Ladies Shoes Collection"
    BKASH_NUMBER = "01638431515"
    SUPPORT_WHATSAPP = "01638431515"

    TZ_OFFSET_HOURS = 6
    DELIVERY_INSIDE_DHAKA = 70
    DELIVERY_OUTSIDE_DHAKA = 130
    MAX_QTY = 10
    NOTES_MAX = 200

    STEPS = ['Order Placed', 'Payment Pending', 'Payment Verified', 'Packaging', 'Out for Delivery', 'Received', 'Completed']
    COURIERS = ['Steadfast', 'Pathao', 'RedX', 'Paperfly', 'Sundarban', 'SA Paribahan', 'Other']

    # Bangladeshi women's shoe sizes & divisions
    BD_SIZES = ['35', '36', '37', '38', '39', '40', '41']
    DIVISIONS = ['Dhaka', 'Chattogram', 'Rajshahi', 'Khulna', 'Barishal',
                 'Sylhet', 'Rangpur', 'Mymensingh']


