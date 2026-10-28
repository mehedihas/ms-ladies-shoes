"""
db.py  -  ALL SQL of the project lives here (SQLite via the built-in sqlite3 module).
routes.py never writes SQL; it only calls the functions below.

Dates are stored in Bangladesh time (UTC + Config.TZ_OFFSET_HOURS) so that the
admin date filter ("from - to") matches the real calendar day in Bangladesh.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import Config

NOW = "datetime('now','%+d hours')" % Config.TZ_OFFSET_HOURS


def _parse_ts(raw):
    s = raw.decode()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return s


sqlite3.register_converter("TIMESTAMP", _parse_ts)

# --------------------------------------------------------------------------- schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT ({now})
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT,
    price           REAL NOT NULL DEFAULT 0,
    old_price       REAL,                       -- optional strike-through price
    available_sizes TEXT NOT NULL,              -- "36, 37, 38"
    image_1         TEXT NOT NULL,
    image_2         TEXT,
    image_3         TEXT,
    video_url       TEXT,
    is_free_delivery INTEGER NOT NULL DEFAULT 0, -- 1 = free delivery nationwide
    is_active       INTEGER NOT NULL DEFAULT 1, -- 0 = hidden from shop
    created_at      TIMESTAMP DEFAULT ({now}),
    updated_at      TIMESTAMP DEFAULT ({now})
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_hash   TEXT NOT NULL UNIQUE,
    product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_sku     TEXT NOT NULL,              -- snapshots: survive later product edits
    product_title   TEXT NOT NULL,
    product_image   TEXT,
    shoe_size       TEXT NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      REAL NOT NULL,
    delivery_charge REAL NOT NULL DEFAULT 0,
    total_amount    REAL NOT NULL,
    notes           TEXT,
    customer_name   TEXT NOT NULL,
    email           TEXT,
    mobile_number   TEXT NOT NULL,
    whatsapp_number TEXT,
    division        TEXT NOT NULL,
    district        TEXT,
    village_town    TEXT NOT NULL,
    road_house      TEXT NOT NULL,
    full_address    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'Order Placed',
    payment_method  TEXT NOT NULL DEFAULT 'bkash', -- bkash | cod
    courier_name    TEXT,
    consignment_id  TEXT,
    messenger_psid  TEXT,
    created_at      TIMESTAMP DEFAULT ({now}),
    updated_at      TIMESTAMP DEFAULT ({now})
);
CREATE INDEX IF NOT EXISTS ix_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS ix_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS ix_orders_mobile  ON orders(mobile_number);
CREATE INDEX IF NOT EXISTS ix_orders_psid    ON orders(messenger_psid);

CREATE TABLE IF NOT EXISTS payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id            INTEGER NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
    bkash_number        TEXT NOT NULL,
    transaction_id      TEXT NOT NULL UNIQUE,
    amount              REAL,
    verification_status TEXT NOT NULL DEFAULT 'Pending',   -- Pending | Approved | Rejected
    admin_notes         TEXT,
    submitted_at        TIMESTAMP DEFAULT ({now}),
    verified_at         TIMESTAMP
);

-- Every step of an order is logged here: this is what makes the project fully trackable
CREATE TABLE IF NOT EXISTS order_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,   -- order_placed payment_submitted payment_approved payment_rejected
                                -- dispatched received cancelled feedback message_sent
    detail     TEXT,
    is_public  INTEGER NOT NULL DEFAULT 1,  -- 1 = customer can see it on the tracking page
    created_at TIMESTAMP DEFAULT ({now})
);
CREATE INDEX IF NOT EXISTS ix_events_order ON order_events(order_id, event_type);

CREATE TABLE IF NOT EXISTS feedbacks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
    product_id    INTEGER REFERENCES products(id) ON DELETE CASCADE,
    customer_name TEXT NOT NULL,
    rating        INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    is_visible    INTEGER NOT NULL DEFAULT 1,  -- admin can hide abusive reviews
    created_at    TIMESTAMP DEFAULT ({now})
);

CREATE TABLE IF NOT EXISTS site_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS messenger_contacts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    psid              TEXT NOT NULL UNIQUE,
    first_name        TEXT,
    last_name         TEXT,
    profile_pic       TEXT,
    mobile_number     TEXT,
    linked_order_id   INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    last_message_text TEXT,
    last_message_at   TIMESTAMP DEFAULT ({now}),
    created_at        TIMESTAMP DEFAULT ({now})
);
CREATE INDEX IF NOT EXISTS ix_messenger_psid ON messenger_contacts(psid);
CREATE INDEX IF NOT EXISTS ix_messenger_order ON messenger_contacts(linked_order_id);

CREATE TABLE IF NOT EXISTS messenger_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    psid         TEXT NOT NULL,
    direction    TEXT NOT NULL, -- inbound | outbound
    message_text TEXT NOT NULL,
    order_id     INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    created_at   TIMESTAMP DEFAULT ({now})
);
CREATE INDEX IF NOT EXISTS ix_msg_psid ON messenger_messages(psid);
CREATE INDEX IF NOT EXISTS ix_msg_order ON messenger_messages(order_id);

CREATE TABLE IF NOT EXISTS whatsapp_contacts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_id             TEXT NOT NULL UNIQUE,       -- e.g. 88017XXXXXXXX
    customer_name     TEXT,
    mobile_number     TEXT,
    linked_order_id   INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    last_message_text TEXT,
    last_message_at   TIMESTAMP DEFAULT ({now}),
    created_at        TIMESTAMP DEFAULT ({now})
);
CREATE INDEX IF NOT EXISTS ix_wa_contact_wa_id ON whatsapp_contacts(wa_id);
CREATE INDEX IF NOT EXISTS ix_wa_contact_order ON whatsapp_contacts(linked_order_id);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_id        TEXT NOT NULL,
    direction    TEXT NOT NULL, -- inbound | outbound
    message_text TEXT NOT NULL,
    order_id     INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    status       TEXT DEFAULT 'sent',
    created_at   TIMESTAMP DEFAULT ({now})
);
CREATE INDEX IF NOT EXISTS ix_wa_msg_wa_id ON whatsapp_messages(wa_id);
CREATE INDEX IF NOT EXISTS ix_wa_msg_order ON whatsapp_messages(order_id);

CREATE TABLE IF NOT EXISTS sms_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_number  TEXT NOT NULL,
    message_text      TEXT NOT NULL,
    order_id          INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    status            TEXT DEFAULT 'sent',  -- sent | failed
    error_message     TEXT,
    gateway_response  TEXT,
    created_at        TIMESTAMP DEFAULT ({now})
);
CREATE INDEX IF NOT EXISTS ix_sms_recipient ON sms_logs(recipient_number);
CREATE INDEX IF NOT EXISTS ix_sms_order ON sms_logs(order_id);
CREATE INDEX IF NOT EXISTS ix_sms_created ON sms_logs(created_at);
""".format(now=NOW)

# Statuses from which an order may still be cancelled
CANCEL_BY_CUSTOMER = ('Order Placed', 'Payment Rejected')
CANCEL_BY_ADMIN = ('Order Placed', 'Payment Pending', 'Payment Rejected', 'Payment Verified', 'Packaging')
EVENT_STAGES = ('payment_submitted', 'payment_approved', 'payment_rejected',
                'packaged', 'dispatched', 'received', 'completed', 'cancelled', 'feedback')


# --------------------------------------------------------------------------- plumbing
def get_connection():
    conn = sqlite3.connect(Config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, timeout=15)
    conn.row_factory = lambda cur, row: {d[0]: row[i] for i, d in enumerate(cur.description)}
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def tx():
    """One transaction: commits on success, rolls back on any error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _q(sql, args=(), one=False):
    conn = get_connection()
    try:
        rows = conn.execute(sql, args).fetchall()
        if one:
            return rows[0] if rows else None
        return rows
    finally:
        conn.close()


def _x(sql, args=()):
    with tx() as c:
        return c.execute(sql, args).lastrowid


def ensure_schema():
    """Migrates any missing columns for backwards compatibility."""
    try:
        conn = sqlite3.connect(Config.DB_PATH)
        # Check products table
        cur = conn.execute("PRAGMA table_info(products)")
        p_cols = [r[1] for r in cur.fetchall()]
        if p_cols and 'is_free_delivery' not in p_cols:
            conn.execute("ALTER TABLE products ADD COLUMN is_free_delivery INTEGER NOT NULL DEFAULT 0")
        # Check orders table
        cur = conn.execute("PRAGMA table_info(orders)")
        o_cols = [r[1] for r in cur.fetchall()]
        if o_cols and 'payment_method' not in o_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'bkash'")
        if o_cols and 'messenger_psid' not in o_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN messenger_psid TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_orders_psid ON orders(messenger_psid)")
        
        # Ensure site_settings, messenger_contacts, messenger_messages tables exist
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS site_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS messenger_contacts (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                psid              TEXT NOT NULL UNIQUE,
                first_name        TEXT,
                last_name         TEXT,
                profile_pic       TEXT,
                mobile_number     TEXT,
                linked_order_id   INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                last_message_text TEXT,
                last_message_at   TIMESTAMP DEFAULT (""" + NOW + """),
                created_at        TIMESTAMP DEFAULT (""" + NOW + """)
            );
            CREATE INDEX IF NOT EXISTS ix_messenger_psid ON messenger_contacts(psid);
            CREATE INDEX IF NOT EXISTS ix_messenger_order ON messenger_contacts(linked_order_id);

            CREATE TABLE IF NOT EXISTS messenger_messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                psid         TEXT NOT NULL,
                direction    TEXT NOT NULL,
                message_text TEXT NOT NULL,
                order_id     INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                created_at   TIMESTAMP DEFAULT (""" + NOW + """)
            );
            CREATE INDEX IF NOT EXISTS ix_msg_psid ON messenger_messages(psid);
            CREATE INDEX IF NOT EXISTS ix_msg_order ON messenger_messages(order_id);

            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('messenger_verify_token', 'ms_ladies_shoes_meta_verify_2026');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('messenger_enabled', '0');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('messenger_auto_reply', '1');

            CREATE TABLE IF NOT EXISTS whatsapp_contacts (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_id             TEXT NOT NULL UNIQUE,
                customer_name     TEXT,
                mobile_number     TEXT,
                linked_order_id   INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                last_message_text TEXT,
                last_message_at   TIMESTAMP DEFAULT (""" + NOW + """),
                created_at        TIMESTAMP DEFAULT (""" + NOW + """)
            );
            CREATE INDEX IF NOT EXISTS ix_wa_contact_wa_id ON whatsapp_contacts(wa_id);
            CREATE INDEX IF NOT EXISTS ix_wa_contact_order ON whatsapp_contacts(linked_order_id);

            CREATE TABLE IF NOT EXISTS whatsapp_messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_id        TEXT NOT NULL,
                direction    TEXT NOT NULL,
                message_text TEXT NOT NULL,
                order_id     INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                status       TEXT DEFAULT 'sent',
                created_at   TIMESTAMP DEFAULT (""" + NOW + """)
            );
            CREATE INDEX IF NOT EXISTS ix_wa_msg_wa_id ON whatsapp_messages(wa_id);
            CREATE INDEX IF NOT EXISTS ix_wa_msg_order ON whatsapp_messages(order_id);

            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('whatsapp_verify_token', 'ms_ladies_shoes_meta_verify_2026');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('whatsapp_enabled', '0');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('whatsapp_phone_number_id', '');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('whatsapp_access_token', '');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('whatsapp_business_account_id', '');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('whatsapp_auto_reply', '1');

            CREATE TABLE IF NOT EXISTS sms_logs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_number  TEXT NOT NULL,
                message_text      TEXT NOT NULL,
                order_id          INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                status            TEXT DEFAULT 'sent',
                error_message     TEXT,
                gateway_response  TEXT,
                created_at        TIMESTAMP DEFAULT (""" + NOW + """)
            );
            CREATE INDEX IF NOT EXISTS ix_sms_recipient ON sms_logs(recipient_number);
            CREATE INDEX IF NOT EXISTS ix_sms_order ON sms_logs(order_id);
            CREATE INDEX IF NOT EXISTS ix_sms_created ON sms_logs(created_at);

            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('sms_enabled', '0');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('sms_provider', 'android_gateway');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('sms_gateway_url', '');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('sms_api_key', '');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('sms_sim_slot', '1');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('sms_auto_notify', '1');
            INSERT OR IGNORE INTO site_settings (key, value) VALUES ('sms_sim_operator', 'Airtel');
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


def init_db():
    conn = sqlite3.connect(Config.DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    ensure_schema()


ensure_schema()


# --------------------------------------------------------------------------- admins
def get_admin(username):
    return _q("SELECT * FROM admins WHERE username=?", (username,), one=True)


def count_admins():
    return _q("SELECT COUNT(*) AS c FROM admins", one=True)['c']


def upsert_admin(username, password_hash):
    _x("""INSERT INTO admins (username, password_hash) VALUES (?, ?)
          ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash""",
       (username, password_hash))


# --------------------------------------------------------------------------- products
def list_products(search=None, size=None, include_inactive=False):
    sql = """
        SELECT p.*, ROUND(AVG(f.rating),1) AS avg_rating, COUNT(f.id) AS review_count
        FROM products p
        LEFT JOIN feedbacks f ON f.product_id = p.id AND f.is_visible = 1
        WHERE 1=1
    """
    args = []
    if not include_inactive:
        sql += " AND p.is_active = 1"
    if search:
        sql += " AND (p.sku LIKE ? OR p.title LIKE ? OR p.description LIKE ?)"
        like = "%" + search + "%"
        args += [like, like, like]
    if size:
        sql += " AND (',' || REPLACE(p.available_sizes,' ','') || ',') LIKE ?"
        args.append("%," + size + ",%")
    sql += " GROUP BY p.id ORDER BY p.id DESC"
    return _q(sql, args)


def get_product(pid):
    return _q("SELECT * FROM products WHERE id=?", (pid,), one=True)


def save_product(pid, d):
    """Insert (pid=None) or update. Raises sqlite3.IntegrityError when SKU already exists."""
    cols = (d['sku'], d['title'], d['description'], d['price'], d['old_price'], d['sizes'],
            d['image_1'], d['image_2'], d['image_3'], d['video_url'],
            d.get('is_free_delivery', 0), d['is_active'])
    if pid:
        _x("""UPDATE products SET sku=?, title=?, description=?, price=?, old_price=?,
              available_sizes=?, image_1=?, image_2=?, image_3=?, video_url=?,
              is_free_delivery=?, is_active=?,
              updated_at=""" + NOW + " WHERE id=?", cols + (pid,))
        return pid
    return _x("""INSERT INTO products (sku, title, description, price, old_price, available_sizes,
                 image_1, image_2, image_3, video_url, is_free_delivery, is_active)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", cols)


def set_product_active(pid, flag):
    _x("UPDATE products SET is_active=?, updated_at=" + NOW + " WHERE id=?", (1 if flag else 0, pid))


def product_order_count(pid):
    return _q("SELECT COUNT(*) AS c FROM orders WHERE product_id=?", (pid,), one=True)['c']


def delete_product(pid):
    _x("DELETE FROM products WHERE id=?", (pid,))


# --------------------------------------------------------------------------- orders
_ORDER_SELECT = """
    SELECT o.*,
           p.bkash_number, p.transaction_id, p.verification_status,
           p.admin_notes AS pay_note, p.amount AS paid_amount, p.submitted_at,
           f.id AS feedback_id
    FROM orders o
    LEFT JOIN payments  p ON p.order_id = o.id
    LEFT JOIN feedbacks f ON f.order_id = o.id
"""


def get_order_by_hash(h):
    return _q(_ORDER_SELECT + " WHERE o.tracking_hash=?", (h,), one=True)


def get_order(order_id):
    return _q(_ORDER_SELECT + " WHERE o.id=?", (order_id,), one=True)


def _event(conn, order_id, etype, detail=None, public=1):
    conn.execute("INSERT INTO order_events (order_id, event_type, detail, is_public) VALUES (?,?,?,?)",
                 (order_id, etype, detail, public))
    conn.execute("UPDATE orders SET updated_at=" + NOW + " WHERE id=?", (order_id,))


def add_event(order_id, etype, detail=None, public=0):
    with tx() as c:
        _event(c, order_id, etype, detail, public)


def list_events(order_id, public_only=False):
    sql = "SELECT * FROM order_events WHERE order_id=?"
    if public_only:
        sql += " AND is_public=1"
    return _q(sql + " ORDER BY id", (order_id,))


def create_order(d):
    """Insert a new order + first event. Raises sqlite3.IntegrityError on duplicate tracking hash."""
    method = d.get('payment_method', 'bkash')
    with tx() as c:
        oid = c.execute("""
            INSERT INTO orders (tracking_hash, product_id, product_sku, product_title, product_image,
                shoe_size, quantity, unit_price, delivery_charge, total_amount, notes,
                customer_name, email, mobile_number, whatsapp_number, division, district,
                village_town, road_house, full_address, status, payment_method)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'Order Placed', ?)""",
                        (d['tracking_hash'], d['product_id'], d['product_sku'], d['product_title'],
                         d['product_image'], d['shoe_size'], d['quantity'], d['unit_price'],
                         d['delivery_charge'], d['total_amount'], d['notes'], d['customer_name'],
                         d['email'], d['mobile_number'], d['whatsapp_number'], d['division'],
                         d['district'], d['village_town'], d['road_house'], d['full_address'], method)).lastrowid
        if method == 'cod':
            _event(c, oid, 'order_placed', 'Order placed via Cash on Delivery (COD). Total payable on delivery: BDT %.0f' % d['total_amount'])
        else:
            _event(c, oid, 'order_placed', 'Order placed via bKash Send Money. Tracking link created.')
    return oid


def submit_payment(order_id, bkash_number, trx_id, amount, address):
    """Customer step 1. Raises sqlite3.IntegrityError when the TrxID was already used."""
    with tx() as c:
        c.execute("""
            INSERT INTO payments (order_id, bkash_number, transaction_id, amount, verification_status, submitted_at)
            VALUES (?,?,?,?, 'Pending', """ + NOW + """)
            ON CONFLICT(order_id) DO UPDATE SET bkash_number=excluded.bkash_number,
                transaction_id=excluded.transaction_id, amount=excluded.amount,
                verification_status='Pending', admin_notes=NULL, verified_at=NULL,
                submitted_at=""" + NOW,
                  (order_id, bkash_number, trx_id, amount))
        c.execute("UPDATE orders SET status='Payment Pending', full_address=? WHERE id=?", (address, order_id))
        _event(c, order_id, 'payment_submitted',
               "Payment submitted: TrxID %s from %s (BDT %.0f)" % (trx_id, bkash_number, amount))


def decide_payment(order_id, approve, note):
    """Admin step 2. Returns False if there is no pending payment."""
    with tx() as c:
        cur = c.execute("""UPDATE payments SET verification_status=?, admin_notes=?, verified_at=""" + NOW +
                        " WHERE order_id=? AND verification_status='Pending'",
                        ('Approved' if approve else 'Rejected', note, order_id))
        if cur.rowcount == 0:
            return False
        c.execute("UPDATE orders SET status=? WHERE id=?",
                  ('Payment Verified' if approve else 'Payment Rejected', order_id))
        if approve:
            _event(c, order_id, 'payment_approved', 'Payment verified by admin.')
        else:
            _event(c, order_id, 'payment_rejected',
                   'Payment rejected' + (': ' + note if note else '.') + ' Please re-submit correct details.')
        return True


def mark_packaging(order_id, note=None):
    with tx() as c:
        cur = c.execute("""UPDATE orders SET status='Packaging', updated_at=""" + NOW + """
                           WHERE id=? AND (status='Payment Verified' OR (payment_method='cod' AND status='Order Placed'))""",
                        (order_id,))
        if cur.rowcount == 0:
            return False
        detail = "Shoes packaged and boxed with shipping label. Ready at gate for courier pickup."
        if note:
            detail += " " + note
        _event(c, order_id, 'packaged', detail)
        return True


def dispatch_order(order_id, courier, consignment, note=None):
    with tx() as c:
        cur = c.execute("""UPDATE orders SET status='Out for Delivery', courier_name=?, consignment_id=?, updated_at=""" + NOW + """
                           WHERE id=? AND (status IN ('Packaging', 'Payment Verified') OR (payment_method='cod' AND status='Order Placed'))""",
                        (courier, consignment, order_id))
        if cur.rowcount == 0:
            return False
        detail = "Gate out completed: Handed over to courier"
        if courier:
            detail += " via %s" % courier
        if consignment:
            detail += " (Consignment %s)" % consignment
        if note:
            detail += ". " + note
        _event(c, order_id, 'dispatched', detail)
        return True


def mark_received(order_id, by='customer'):
    with tx() as c:
        cur = c.execute("UPDATE orders SET status='Received', updated_at=" + NOW + " WHERE id=? AND status='Out for Delivery'", (order_id,))
        if cur.rowcount == 0:
            return False
        detail = 'Customer confirmed the parcel is received.' if by == 'customer' else 'Parcel delivery confirmed by admin/courier.'
        _event(c, order_id, 'received', detail)
        return True


def complete_order(order_id, note=None):
    with tx() as c:
        cur = c.execute("UPDATE orders SET status='Completed', updated_at=" + NOW + """
                         WHERE id=? AND status IN ('Received', 'Out for Delivery')""", (order_id,))
        if cur.rowcount == 0:
            return False
        detail = "Order verified and closed as Completed by admin."
        if note:
            detail += " " + note
        _event(c, order_id, 'completed', detail)
        return True


def cancel_order(order_id, by, reason, allowed):
    with tx() as c:
        marks = ",".join("?" * len(allowed))
        cur = c.execute("UPDATE orders SET status='Cancelled' WHERE id=? AND status IN (%s)" % marks,
                        (order_id,) + tuple(allowed))
        if cur.rowcount == 0:
            return False
        _event(c, order_id, 'cancelled', "Cancelled by %s%s" % (by, (": " + reason) if reason else "."))
        return True


# --------------------------------------------------------------------------- admin lists & stats
def list_orders(f=None, t=None, stage=None, status=None, search=None, queue=None, limit=None):
    sql = _ORDER_SELECT + " WHERE 1=1"
    args = []
    if f and t:
        sql += " AND o.created_at BETWEEN ? AND ?"
        args += [f, t]
    if queue == 'payment_pending':
        sql += " AND o.status = 'Payment Pending'"
    elif queue == 'packaging_pending':
        sql += " AND (o.status = 'Payment Verified' OR (o.status = 'Order Placed' AND o.payment_method = 'cod'))"
    elif queue == 'gate_out_pending':
        sql += " AND o.status = 'Packaging'"
    elif queue == 'delivery_pending':
        sql += " AND o.status = 'Out for Delivery'"
    elif queue == 'feedback_pending':
        sql += " AND o.status = 'Received' AND f.id IS NULL"
    elif queue == 'completed':
        sql += " AND (o.status = 'Completed' OR (o.status = 'Received' AND f.id IS NOT NULL))"
    elif queue == 'cancelled_rejected':
        sql += " AND o.status IN ('Payment Rejected', 'Cancelled')"

    if stage in EVENT_STAGES:
        sql += " AND EXISTS (SELECT 1 FROM order_events e WHERE e.order_id=o.id AND e.event_type=?)"
        args.append(stage)
    if status:
        sql += " AND o.status=?"
        args.append(status)
    if search:
        like = "%" + search + "%"
        sql += """ AND (o.customer_name LIKE ? OR o.mobile_number LIKE ? OR o.whatsapp_number LIKE ?
                   OR o.tracking_hash LIKE ? OR o.product_sku LIKE ? OR p.transaction_id LIKE ?
                   OR o.courier_name LIKE ? OR o.consignment_id LIKE ?)"""
        args += [like] * 8
    sql += " ORDER BY o.id DESC"
    if limit:
        sql += " LIMIT %d" % int(limit)
    return _q(sql, args)


def dashboard_metrics(f, t):
    """Funnel counted per ORDER created in the period (each order counted once per stage)."""
    def stage(name, alias):
        return "COUNT(DISTINCT CASE WHEN e.event_type='%s' THEN o.id END) AS %s" % (name, alias)
    m = _q("""SELECT COUNT(DISTINCT o.id) AS total_requests, %s, %s, %s, %s, %s, %s, %s, %s, %s
              FROM orders o LEFT JOIN order_events e ON e.order_id = o.id
              WHERE o.created_at BETWEEN ? AND ?""" % (
        stage('payment_submitted', 'payment_requests'), stage('payment_approved', 'verified'),
        stage('payment_rejected', 'rejected'), stage('packaged', 'packaged'),
        stage('dispatched', 'out_for_delivery'), stage('received', 'received'),
        stage('completed', 'completed'), stage('feedback', 'feedbacks'),
        stage('cancelled', 'cancelled')), (f, t), one=True)
    money = _q("""SELECT
        COALESCE(SUM(CASE WHEN status IN ('Payment Verified','Packaging','Out for Delivery','Received','Completed')
                          THEN total_amount END),0) AS revenue,
        COALESCE(SUM(CASE WHEN status='Payment Pending' THEN total_amount END),0) AS awaiting_amount,
        COALESCE(SUM(CASE WHEN payment_method='cod' THEN total_amount END),0) AS cod_amount,
        COALESCE(SUM(CASE WHEN payment_method='bkash' THEN total_amount END),0) AS bkash_amount
        FROM orders WHERE created_at BETWEEN ? AND ?""", (f, t), one=True)
    m.update(money)
    return m


def action_needed():
    """Live to-do counters for the Smart Tracking Dashboard."""
    row = _q("""SELECT
        COALESCE(SUM(CASE WHEN o.status = 'Payment Pending' THEN 1 ELSE 0 END), 0) AS payment_pending,
        COALESCE(SUM(CASE WHEN (o.status = 'Payment Verified' OR (o.status = 'Order Placed' AND o.payment_method = 'cod')) THEN 1 ELSE 0 END), 0) AS packaging_pending,
        COALESCE(SUM(CASE WHEN o.status = 'Packaging' THEN 1 ELSE 0 END), 0) AS gate_out_pending,
        COALESCE(SUM(CASE WHEN o.status = 'Out for Delivery' THEN 1 ELSE 0 END), 0) AS delivery_pending,
        COALESCE(SUM(CASE WHEN o.status = 'Received' AND f.id IS NULL THEN 1 ELSE 0 END), 0) AS feedback_pending,
        COALESCE(SUM(CASE WHEN (o.status = 'Completed' OR (o.status = 'Received' AND f.id IS NOT NULL)) THEN 1 ELSE 0 END), 0) AS completed,
        COALESCE(SUM(CASE WHEN o.status IN ('Payment Rejected', 'Cancelled') THEN 1 ELSE 0 END), 0) AS cancelled_rejected,
        COUNT(o.id) AS total_orders
    FROM orders o
    LEFT JOIN feedbacks f ON f.order_id = o.id""", one=True)
    if not row:
        row = dict(payment_pending=0, packaging_pending=0, gate_out_pending=0,
                   delivery_pending=0, feedback_pending=0, completed=0,
                   cancelled_rejected=0, total_orders=0)
    # Backward compatibility aliases
    row['to_verify'] = row['payment_pending']
    row['to_dispatch'] = row['packaging_pending'] + row['gate_out_pending']
    row['in_transit'] = row['delivery_pending']
    row['unpaid'] = _q("SELECT COUNT(*) AS c FROM orders WHERE status='Order Placed' AND payment_method='bkash'", one=True)['c']
    return row


def top_products(f, t, limit=5):
    return _q("""SELECT product_sku, product_title, COUNT(*) AS orders, SUM(quantity) AS pairs
                 FROM orders WHERE created_at BETWEEN ? AND ? AND status != 'Cancelled'
                 GROUP BY product_sku, product_title ORDER BY pairs DESC LIMIT ?""", (f, t, limit))


# --------------------------------------------------------------------------- feedback
def add_feedback(order, rating, comment):
    with tx() as c:
        c.execute("""INSERT INTO feedbacks (order_id, product_id, customer_name, rating, comment)
                     VALUES (?,?,?,?,?)""",
                  (order['id'], order['product_id'], order['customer_name'], rating, comment))
        _event(c, order['id'], 'feedback', 'Customer rated %d/5.' % rating)


def product_feedbacks(pid):
    return _q("""SELECT customer_name, rating, comment, created_at FROM feedbacks
                 WHERE product_id=? AND is_visible=1 ORDER BY id DESC""", (pid,))


def admin_feedbacks(f, t):
    return _q("""SELECT f.*, o.product_sku, o.product_title, o.tracking_hash
                 FROM feedbacks f JOIN orders o ON o.id = f.order_id
                 WHERE f.created_at BETWEEN ? AND ? ORDER BY f.id DESC""", (f, t))


def set_feedback_visible(fid, flag):
    _x("UPDATE feedbacks SET is_visible=? WHERE id=?", (1 if flag else 0, fid))


# --------------------------------------------------------------------------- site settings
def get_setting(key, default=''):
    row = _q("SELECT value FROM site_settings WHERE key=?", (key,), one=True)
    return row['value'] if row and row['value'] is not None else default


def set_setting(key, value):
    _x("""INSERT INTO site_settings (key, value) VALUES (?, ?)
          ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, str(value) if value is not None else ''))


def get_all_settings():
    rows = _q("SELECT key, value FROM site_settings")
    return {r['key']: r['value'] for r in rows}


# --------------------------------------------------------------------------- messenger chats & contacts
def save_messenger_message(psid, direction, message_text, order_id=None):
    """Saves message and updates or inserts contact."""
    with tx() as c:
        mid = c.execute("""INSERT INTO messenger_messages (psid, direction, message_text, order_id)
                           VALUES (?, ?, ?, ?)""", (psid, direction, message_text, order_id)).lastrowid
        c.execute("""INSERT INTO messenger_contacts (psid, last_message_text, last_message_at)
                     VALUES (?, ?, """ + NOW + """)
                     ON CONFLICT(psid) DO UPDATE SET last_message_text=excluded.last_message_text,
                                                     last_message_at=""" + NOW + """
                     WHERE psid=excluded.psid""", (psid, message_text))
        if order_id:
            c.execute("UPDATE messenger_contacts SET linked_order_id=? WHERE psid=?", (order_id, psid))
            c.execute("UPDATE orders SET messenger_psid=? WHERE id=?", (psid, order_id))
    return mid


def list_messenger_contacts():
    return _q("""SELECT c.*, o.tracking_hash, o.customer_name, o.status AS order_status, o.total_amount
                 FROM messenger_contacts c
                 LEFT JOIN orders o ON o.id = c.linked_order_id
                 ORDER BY c.last_message_at DESC""")


def get_messenger_contact(psid):
    return _q("""SELECT c.*, o.tracking_hash, o.customer_name, o.mobile_number AS order_mobile,
                        o.status AS order_status, o.total_amount, o.product_title, o.shoe_size, o.quantity
                 FROM messenger_contacts c
                 LEFT JOIN orders o ON o.id = c.linked_order_id
                 WHERE c.psid=?""", (psid,), one=True)


def get_messenger_messages(psid, limit=60):
    return _q("""SELECT m.*, o.tracking_hash
                 FROM messenger_messages m
                 LEFT JOIN orders o ON o.id = m.order_id
                 WHERE m.psid=? ORDER BY m.id ASC LIMIT ?""", (psid, int(limit)))


def link_order_messenger(order_id, psid):
    with tx() as c:
        c.execute("UPDATE orders SET messenger_psid=? WHERE id=?", (psid, order_id))
        c.execute("""INSERT INTO messenger_contacts (psid, linked_order_id, last_message_at)
                     VALUES (?, ?, """ + NOW + """)
                     ON CONFLICT(psid) DO UPDATE SET linked_order_id=excluded.linked_order_id""",
                  (psid, order_id))
        return True


def find_order_by_text(query_text):
    """
    Intelligently extracts and matches tracking hash, order ID, or mobile number from user message.
    """
    if not query_text:
        return None
    import re
    raw = query_text.strip().upper()

    # 1. Direct match on 12-char tracking hash (or word containing it)
    hashes = re.findall(r'[A-Z0-9]{10,14}', raw)
    for h in hashes:
        order = _q(_ORDER_SELECT + " WHERE UPPER(o.tracking_hash)=?", (h,), one=True)
        if order:
            return order

    # 2. Check for order ID like #3 or Order 3
    order_ids = re.findall(r'(?:#|ORDER\s*|ID\s*)(\d+)', raw, re.IGNORECASE)
    for oid in order_ids:
        order = _q(_ORDER_SELECT + " WHERE o.id=?", (int(oid),), one=True)
        if order:
            return order

    # 3. Check for mobile number (01XXXXXXXXX or 8801XXXXXXXXX)
    mobiles = re.findall(r'(?:88)?01[3-9]\d{8}', query_text.replace(' ', '').replace('-', ''))
    for mob in mobiles:
        clean_11 = mob if not mob.startswith('88') else mob[2:]
        clean_13 = mob if mob.startswith('88') else '88' + mob
        order = _q(_ORDER_SELECT + """ WHERE o.mobile_number IN (?, ?) 
                                      OR o.whatsapp_number IN (?, ?) 
                                      ORDER BY o.id DESC""", 
                   (clean_11, clean_13, clean_11, clean_13), one=True)
        if order:
            return order

    return None


def find_order_by_phone(phone):
    """Matches an order by 11-digit or 13-digit (8801...) phone number."""
    if not phone:
        return None
    raw = str(phone).replace(' ', '').replace('-', '').replace('+', '')
    clean_11 = raw[2:] if raw.startswith('8801') else raw
    clean_13 = '88' + raw if raw.startswith('01') else raw
    return _q(_ORDER_SELECT + """ WHERE o.mobile_number IN (?, ?) 
                                  OR o.whatsapp_number IN (?, ?) 
                                  ORDER BY o.id DESC""",
              (clean_11, clean_13, clean_11, clean_13), one=True)


# --------------------------------------------------------------------------- whatsapp chats & contacts
def save_whatsapp_message(wa_id, direction, message_text, order_id=None, customer_name=None):
    """Saves WhatsApp message and updates or inserts contact."""
    with tx() as c:
        mid = c.execute("""INSERT INTO whatsapp_messages (wa_id, direction, message_text, order_id)
                           VALUES (?, ?, ?, ?)""", (wa_id, direction, message_text, order_id)).lastrowid
        if customer_name:
            c.execute("""INSERT INTO whatsapp_contacts (wa_id, customer_name, last_message_text, last_message_at)
                         VALUES (?, ?, ?, """ + NOW + """)
                         ON CONFLICT(wa_id) DO UPDATE SET customer_name=coalesce(excluded.customer_name, whatsapp_contacts.customer_name),
                                                          last_message_text=excluded.last_message_text,
                                                          last_message_at=""" + NOW + """
                         WHERE wa_id=excluded.wa_id""", (wa_id, customer_name, message_text))
        else:
            c.execute("""INSERT INTO whatsapp_contacts (wa_id, last_message_text, last_message_at)
                         VALUES (?, ?, """ + NOW + """)
                         ON CONFLICT(wa_id) DO UPDATE SET last_message_text=excluded.last_message_text,
                                                          last_message_at=""" + NOW + """
                         WHERE wa_id=excluded.wa_id""", (wa_id, message_text))
        if order_id:
            c.execute("UPDATE whatsapp_contacts SET linked_order_id=? WHERE wa_id=?", (order_id, wa_id))
            c.execute("UPDATE orders SET whatsapp_number=coalesce(nullif(whatsapp_number, ''), ?) WHERE id=?", (wa_id, order_id))
    return mid


def list_whatsapp_contacts():
    return _q("""SELECT c.*, o.tracking_hash, o.customer_name AS order_customer_name,
                        o.status AS order_status, o.total_amount, o.product_title
                 FROM whatsapp_contacts c
                 LEFT JOIN orders o ON o.id = c.linked_order_id
                 ORDER BY c.last_message_at DESC""")


def get_whatsapp_contact(wa_id):
    return _q("""SELECT c.*, o.tracking_hash, o.customer_name AS order_customer_name, o.mobile_number AS order_mobile,
                        o.status AS order_status, o.total_amount, o.product_title, o.shoe_size, o.quantity
                 FROM whatsapp_contacts c
                 LEFT JOIN orders o ON o.id = c.linked_order_id
                 WHERE c.wa_id=?""", (wa_id,), one=True)


def get_whatsapp_messages(wa_id, limit=60):
    return _q("""SELECT m.*, o.tracking_hash
                 FROM whatsapp_messages m
                 LEFT JOIN orders o ON o.id = m.order_id
                 WHERE m.wa_id=? ORDER BY m.id ASC LIMIT ?""", (wa_id, int(limit)))


def link_order_whatsapp(order_id, wa_id, customer_name=None):
    with tx() as c:
        c.execute("UPDATE orders SET whatsapp_number=? WHERE id=?", (wa_id, order_id))
        c.execute("""INSERT INTO whatsapp_contacts (wa_id, linked_order_id, customer_name, last_message_at)
                     VALUES (?, ?, ?, """ + NOW + """)
                     ON CONFLICT(wa_id) DO UPDATE SET linked_order_id=excluded.linked_order_id,
                                                      customer_name=coalesce(excluded.customer_name, whatsapp_contacts.customer_name)""",
                  (wa_id, order_id, customer_name))
        return True


# --------------------------------------------------------------------------- sms logs & helpers
def log_sms(recipient_number, message_text, order_id=None, status='sent', error_message=None, gateway_response=None):
    """Logs sent or failed SMS into database."""
    with tx() as c:
        return c.execute("""
            INSERT INTO sms_logs (recipient_number, message_text, order_id, status, error_message, gateway_response)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (recipient_number, message_text, order_id, status, error_message, str(gateway_response) if gateway_response else None)).lastrowid


def list_sms_logs(limit=50, order_id=None):
    """Retrieves recent SMS logs with order context."""
    if order_id:
        return _q("""
            SELECT s.*, o.tracking_hash, o.customer_name
            FROM sms_logs s
            LEFT JOIN orders o ON o.id = s.order_id
            WHERE s.order_id=?
            ORDER BY s.id DESC LIMIT ?
        """, (order_id, int(limit)))
    return _q("""
        SELECT s.*, o.tracking_hash, o.customer_name
        FROM sms_logs s
        LEFT JOIN orders o ON o.id = s.order_id
        ORDER BY s.id DESC LIMIT ?
    """, (int(limit),))


# --------------------------------------------------------------------------- customer master & analytics
def get_customer_metrics():
    """Returns high-level customer master metrics for the dashboard & customer directory."""
    row = _q("""
        SELECT
            COUNT(DISTINCT mobile_number) AS total_customers,
            COALESCE(SUM(CASE WHEN order_count >= 3 OR total_spent >= 5000 THEN 1 ELSE 0 END), 0) AS vip_customers,
            COALESCE(SUM(CASE WHEN order_count = 2 THEN 1 ELSE 0 END), 0) AS repeat_customers,
            COALESCE(SUM(CASE WHEN order_count = 1 THEN 1 ELSE 0 END), 0) AS single_customers,
            COALESCE(SUM(total_spent), 0) AS total_spent_all,
            COALESCE(SUM(order_count), 0) AS total_orders_all
        FROM (
            SELECT 
                mobile_number,
                COUNT(id) AS order_count,
                COALESCE(SUM(CASE WHEN status NOT IN ('Cancelled', 'Payment Rejected') THEN total_amount ELSE 0 END), 0) AS total_spent
            FROM orders
            WHERE mobile_number IS NOT NULL AND mobile_number != ''
            GROUP BY mobile_number
        )
    """, one=True)
    if not row:
        row = dict(total_customers=0, vip_customers=0, repeat_customers=0,
                   single_customers=0, total_spent_all=0, total_orders_all=0)
    
    total_cust = row['total_customers'] or 0
    row['avg_orders'] = round((row['total_orders_all'] / total_cust), 1) if total_cust > 0 else 0
    row['avg_spend'] = round((row['total_spent_all'] / total_cust), 0) if total_cust > 0 else 0
    return row


def list_customer_master(search=None, tier=None, sort='orders_desc', limit=100, offset=0):
    """
    Returns aggregated customer master records grouped by mobile_number.
    Calculates buy history, total orders, completed orders, total spent, and last purchase date.
    """
    base_sql = """
        SELECT
            o.mobile_number,
            MAX(o.customer_name) AS customer_name,
            MAX(o.email) AS email,
            MAX(o.whatsapp_number) AS whatsapp_number,
            MAX(o.division) AS division,
            MAX(o.district) AS district,
            MAX(o.full_address) AS full_address,
            COUNT(o.id) AS total_orders,
            COALESCE(SUM(CASE WHEN o.status IN ('Received', 'Completed') THEN 1 ELSE 0 END), 0) AS completed_orders,
            COALESCE(SUM(CASE WHEN o.status NOT IN ('Cancelled', 'Payment Rejected') THEN o.total_amount ELSE 0 END), 0) AS total_spent,
            MIN(o.created_at) AS first_purchase_date,
            MAX(o.created_at) AS last_purchase_date,
            (SELECT id FROM orders WHERE mobile_number = o.mobile_number ORDER BY id DESC LIMIT 1) AS last_order_id,
            (SELECT tracking_hash FROM orders WHERE mobile_number = o.mobile_number ORDER BY id DESC LIMIT 1) AS last_tracking_hash,
            (SELECT product_title FROM orders WHERE mobile_number = o.mobile_number ORDER BY id DESC LIMIT 1) AS last_product_title,
            (SELECT status FROM orders WHERE mobile_number = o.mobile_number ORDER BY id DESC LIMIT 1) AS last_order_status
        FROM orders o
        WHERE o.mobile_number IS NOT NULL AND o.mobile_number != ''
    """
    args = []
    
    if search:
        s = f"%{search.strip()}%"
        base_sql += " AND (o.customer_name LIKE ? OR o.mobile_number LIKE ? OR o.email LIKE ? OR o.district LIKE ? OR o.full_address LIKE ?)"
        args.extend([s, s, s, s, s])

    base_sql += " GROUP BY o.mobile_number"

    having_clauses = []
    if tier == 'vip':
        having_clauses.append("(COUNT(o.id) >= 3 OR SUM(CASE WHEN o.status NOT IN ('Cancelled', 'Payment Rejected') THEN o.total_amount ELSE 0 END) >= 5000)")
    elif tier == 'repeat':
        having_clauses.append("COUNT(o.id) >= 2")
    elif tier == 'single':
        having_clauses.append("COUNT(o.id) = 1")

    if having_clauses:
        base_sql += " HAVING " + " AND ".join(having_clauses)

    order_by_map = {
        'orders_desc': " ORDER BY total_orders DESC, total_spent DESC, last_purchase_date DESC",
        'spent_desc': " ORDER BY total_spent DESC, total_orders DESC, last_purchase_date DESC",
        'recent_desc': " ORDER BY last_purchase_date DESC, total_orders DESC",
        'name_asc': " ORDER BY customer_name COLLATE NOCASE ASC"
    }
    base_sql += order_by_map.get(sort, order_by_map['orders_desc'])

    if limit is not None:
        base_sql += " LIMIT ? OFFSET ?"
        args.extend([int(limit), int(offset)])

    rows = _q(base_sql, tuple(args))
    
    # Enrich with tier classification label
    for r in rows:
        orders_cnt = r['total_orders'] or 0
        spent = r['total_spent'] or 0
        if orders_cnt >= 3 or spent >= 5000:
            r['tier'] = 'vip'
            r['tier_label'] = '💎 VIP / Elite'
            r['tier_badge'] = 'badge-vip'
        elif orders_cnt >= 2:
            r['tier'] = 'repeat'
            r['tier_label'] = '⭐ Loyal / Repeat'
            r['tier_badge'] = 'badge-repeat'
        else:
            r['tier'] = 'single'
            r['tier_label'] = '🌱 New Customer'
            r['tier_badge'] = 'badge-new'
            
    return rows


def get_customer_history(mobile_number):
    """Fetches full order history and aggregate summary for a specific customer mobile number."""
    orders = _q("""
        SELECT * FROM orders
        WHERE mobile_number=?
        ORDER BY id DESC
    """, (mobile_number,))
    
    if not orders:
        return None
        
    latest = orders[0]
    total_spent = sum(o['total_amount'] for o in orders if o['status'] not in ('Cancelled', 'Payment Rejected'))
    completed_orders = sum(1 for o in orders if o['status'] in ('Received', 'Completed'))
    
    tier = 'vip' if (len(orders) >= 3 or total_spent >= 5000) else ('repeat' if len(orders) >= 2 else 'single')
    
    return {
        'mobile_number': mobile_number,
        'customer_name': latest['customer_name'],
        'email': latest['email'],
        'whatsapp_number': latest['whatsapp_number'],
        'division': latest['division'],
        'district': latest['district'],
        'full_address': latest['full_address'],
        'total_orders': len(orders),
        'completed_orders': completed_orders,
        'total_spent': total_spent,
        'tier': tier,
        'tier_label': '💎 VIP / Elite' if tier == 'vip' else ('⭐ Loyal / Repeat' if tier == 'repeat' else '🌱 New Customer'),
        'first_purchase_date': orders[-1]['created_at'],
        'last_purchase_date': orders[0]['created_at'],
        'orders': orders
    }




