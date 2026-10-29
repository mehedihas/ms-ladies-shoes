"""
routes.py  -  every URL of the shop. No SQL here: all database work is in db.py.

CUSTOMER   /  /product/<id>  /order/create  /track  /track/<hash>  /order/pay|cancel|received|feedback
ADMIN      /admin/login  /admin  /admin/order/<id>  /admin/products  /admin/feedbacks ...
"""
import csv
import io
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote
import requests

from flask import (Blueprint, Response, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import db
from config import Config

try:  # Pillow is optional: it shrinks big phone photos so the shop loads fast on mobile data
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None

main_bp = Blueprint('main', __name__)

MOBILE_RE = re.compile(r'^01[3-9]\d{8}$')
TRX_RE = re.compile(r'^[A-Z0-9]{6,20}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# =============================================================================== helpers
def today_bd():
    return (datetime.now(timezone.utc) + timedelta(hours=Config.TZ_OFFSET_HOURS)).date()


def norm_mobile(raw):
    """'+8801712-345678' -> '01712345678'. Returns '' if it is not a valid BD mobile."""
    d = ''.join(c for c in (raw or '') if c.isdigit())
    if d.startswith('880'):
        d = d[2:]
    if not d.startswith('0') and len(d) == 10:
        d = '0' + d
    return d if MOBILE_RE.match(d) else ''


def intl(num):
    d = norm_mobile(num) or ''.join(c for c in (num or '') if c.isdigit())
    if d.startswith('880'):
        return d
    return '88' + d if d.startswith('0') else '880' + d


def wa_url(num, text):
    return "https://wa.me/%s?text=%s" % (intl(num), quote(text))


def sms_url(num, text):
    return "sms:+%s?body=%s" % (intl(num), quote(text))


def track_link(h):
    if Config.SITE_URL:
        return "%s/track/%s" % (Config.SITE_URL, h)
    return url_for('main.track_order', tracking_hash=h, _external=True)


def delivery_charge(division, is_free=False, payment_method='bkash'):
    if payment_method == 'bkash' and is_free:
        return 0
    return Config.DELIVERY_INSIDE_DHAKA if division == 'Dhaka' else Config.DELIVERY_OUTSIDE_DHAKA


def to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def to_float(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


_hits = {}


def too_many(bucket, limit, window):
    """Tiny in-memory rate limiter (per client IP). Returns True when the limit is exceeded."""
    key = (bucket, request.headers.get('X-Forwarded-For', request.remote_addr))
    now = time.time()
    hits = [t for t in _hits.get(key, []) if now - t < window]
    hits.append(now)
    _hits[key] = hits
    return len(hits) > limit


def save_upload(file, kind):
    """kind = 'images' | 'videos'. Returns 'uploads/<kind>/<name>' or None."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in (Config.ALLOWED_IMAGES if kind == 'images' else Config.ALLOWED_VIDEOS):
        return None
    folder = os.path.join(Config.UPLOAD_FOLDER, kind)
    os.makedirs(folder, exist_ok=True)
    if kind == 'images' and Image:
        try:
            img = ImageOps.exif_transpose(Image.open(file.stream))
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGBA')
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            else:
                img = img.convert('RGB')
            img.thumbnail((1200, 1200))
            name = uuid.uuid4().hex[:16] + '.jpg'
            img.save(os.path.join(folder, name), 'JPEG', quality=84, optimize=True, progressive=True)
            return "uploads/%s/%s" % (kind, name)
        except Exception:
            try:
                file.stream.seek(0)
            except Exception:
                pass
    name = "%s_%s" % (uuid.uuid4().hex[:12], secure_filename(file.filename or 'upload.jpg'))
    file.save(os.path.join(folder, name))
    return "uploads/%s/%s" % (kind, name)


def remove_upload(rel):
    if rel:
        try:
            os.remove(os.path.join(Config.BASE_DIR, 'static', rel))
        except OSError:
            pass


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('admin'):
            return redirect(url_for('main.admin_login', next=request.path))
        return fn(*a, **kw)
    return wrapper


def date_range():
    """Reads ?from_date & ?to_date. Defaults: whole history up to today."""
    from_date = request.args.get('from_date') or '2020-01-01'
    to_date = request.args.get('to_date') or today_bd().isoformat()
    return from_date, to_date, from_date + ' 00:00:00', to_date + ' 23:59:59'


def build_messages(o, link):
    """Ready-to-send SMS / WhatsApp texts for every step of the order."""
    name, title = o['customer_name'], o['product_title']
    courier = ''
    if o.get('courier_name'):
        courier = " Courier: %s%s." % (o['courier_name'],
                                       (", Consignment " + o['consignment_id']) if o.get('consignment_id') else '')
    is_cod = o.get('payment_method') == 'cod'
    if is_cod:
        created_text = ("Hello %s, thank you for ordering %s (ID %s) from %s via Cash on Delivery. "
                        "Total payable on delivery: BDT %.0f. Track your order here: %s"
                        % (name, title, o['product_id'], Config.SHOP_NAME, o['total_amount'], link))
    else:
        created_text = ("Hello %s, thank you for ordering %s (ID %s) from %s. "
                        "Track your order and pay via bKash Send Money here: %s"
                        % (name, title, o['product_id'], Config.SHOP_NAME, link))

    texts = [
        ('created', 'Tracking link', created_text),
        ('reminder', 'Payment reminder', "Hello %s, your order for %s is waiting for payment (BDT %.0f). "
         "Send money to bKash %s and submit the TrxID here: %s" % (name, title, o['total_amount'], Config.BKASH_NUMBER, link)),
        ('approved', 'Payment verified', "Hello %s, your bKash payment is VERIFIED. We are preparing your order. "
         "Track: %s" % (name, link)),
        ('packaged', 'Shoes packaged', "Hello %s, your order for %s has been packed and boxed! It is ready at our dispatch gate for courier pickup. Track: %s"
         % (name, title, link)),
        ('rejected', 'Payment rejected', "Hello %s, we could not verify your payment%s. Please re-submit the correct "
         "TrxID here: %s" % (name, (" (" + o['pay_note'] + ")") if o.get('pay_note') else '', link)),
        ('delivery', 'Out for delivery', "Hello %s, your order is OUT FOR DELIVERY.%s Track: %s" % (name, courier, link)),
        ('received', 'Thanks + review', "Hello %s, thank you for shopping with %s! Please rate your shoes here: %s"
         % (name, Config.SHOP_NAME, link)),
        ('completed', 'Order completed', "Hello %s, thank you for ordering from %s! Your order has been completed and verified. Hope you love your new shoes!"
         % (name, Config.SHOP_NAME)),
        ('cancelled', 'Order cancelled', "Hello %s, your order for %s has been cancelled. "
         "Contact us on WhatsApp %s if you need help." % (name, title, Config.SUPPORT_WHATSAPP)),
    ]
    num = o['whatsapp_number'] or o['mobile_number']
    return {k: dict(key=k, label=lab, text=t, wa=wa_url(num, t), sms=sms_url(o['mobile_number'], t))
            for k, lab, t in texts}


SUGGESTED_MESSAGE = {'Order Placed': 'created', 'Payment Pending': None, 'Payment Verified': 'approved',
                     'Packaging': 'packaged', 'Payment Rejected': 'rejected', 'Out for Delivery': 'delivery',
                     'Received': 'received', 'Completed': 'completed', 'Cancelled': 'cancelled'}


# =============================================================================== meta messenger integration
def send_meta_messenger(psid, message_text, tag='CONFIRMED_CUSTOMER_UPDATE'):
    """
    Sends message to customer's Facebook Messenger via Meta Graph API.
    Uses 'CONFIRMED_CUSTOMER_UPDATE' tag for order status notifications outside 24h window (free of charge).
    """
    token = db.get_setting('messenger_page_token', '').strip()
    enabled = db.get_setting('messenger_enabled', '0') == '1'
    if not enabled or not token or not psid:
        return {'success': False, 'error': 'Messenger not configured or recipient missing'}

    url = "https://graph.facebook.com/v19.0/me/messages"
    params = {"access_token": token}
    headers = {"Content-Type": "application/json"}

    payload = {
        "recipient": {"id": psid},
        "message": {"text": message_text}
    }
    if tag:
        payload["messaging_type"] = "MESSAGE_TAG"
        payload["tag"] = tag
    else:
        payload["messaging_type"] = "RESPONSE"

    try:
        resp = requests.post(url, params=params, headers=headers, json=payload, timeout=8)
        data = resp.json()
        if resp.status_code == 200 and 'message_id' in data:
            return {'success': True, 'message_id': data['message_id']}
        err = data.get('error', {}).get('message', str(data))
        return {'success': False, 'error': err}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def notify_order_messenger(order_id, stage, extra_note=None):
    """
    Automatically sends step completion notifications to the customer in Messenger
    if the order has a linked messenger_psid.
    """
    order = db.get_order(order_id)
    if not order or not order.get('messenger_psid'):
        return None
    psid = order['messenger_psid']
    name = order['customer_name']
    title = order['product_title']
    link = track_link(order['tracking_hash'])

    msg_map = {
        'payment_approved': (
            f"✅ Hello {name}! Your payment for Order #{order['id']} ({title}) has been VERIFIED!\n"
            f"Our team is now packaging your shoes for courier dispatch.\n"
            f"📍 Track live progress: {link}"
        ),
        'payment_rejected': (
            f"⚠️ Hello {name}, your payment for Order #{order['id']} could not be verified"
            f"{': ' + extra_note if extra_note else '.'} Please re-submit the correct TrxID here:\n"
            f"📍 {link}"
        ),
        'packaged': (
            f"📦 Hello {name}! Great news! Your shoes (Order #{order['id']}) have been packaged and boxed!\n"
            f"They are now ready at our dispatch gate for courier pickup.\n"
            f"📍 Track live: {link}"
        ),
        'dispatched': (
            f"🚚 Hello {name}! Your parcel (Order #{order['id']}) is OUT FOR DELIVERY via "
            f"{order.get('courier_name') or 'Courier'}"
            f"{( ' (Consignment: ' + order['consignment_id'] + ')') if order.get('consignment_id') else ''}!\n"
            f"The delivery rider will contact you soon.\n"
            f"📍 Track live: {link}"
        ),
        'received': (
            f"🎉 Hello {name}! Courier confirms that your shoes have been delivered! "
            f"We hope you love them!\n"
            f"Please take 30 seconds to rate and review your shoes:\n"
            f"⭐️ Rate your shoes: {link}"
        ),
        'completed': (
            f"🌟 Hello {name}! Thank you for shopping with {Config.SHOP_NAME}!\n"
            f"Your order #{order['id']} is marked completed and verified. "
            f"Feel free to message us here anytime if you need more pairs!"
        )
    }

    text = msg_map.get(stage)
    if not text:
        return None

    res = send_meta_messenger(psid, text, tag='CONFIRMED_CUSTOMER_UPDATE')
    if res.get('success'):
        db.save_messenger_message(psid, 'outbound', text, order_id=order['id'])
        db.add_event(order['id'], 'message_sent', f"Automated Messenger update sent: {stage}", public=0)
    return res


def handle_inbound_messenger(sender_id, text):
    """
    Smart Chatbot Engine:
    1. Looks for tracking ID, order #, or mobile number in customer message.
    2. Links the order to the customer's Messenger PSID.
    3. Auto-replies with live order tracking & status.
    """
    matched_order = db.find_order_by_text(text)
    if not matched_order:
        contact = db.get_messenger_contact(sender_id)
        if contact and contact.get('linked_order_id'):
            matched_order = db.get_order(contact['linked_order_id'])

    order_id = matched_order['id'] if matched_order else None
    db.save_messenger_message(sender_id, 'inbound', text, order_id=order_id)

    auto_reply = db.get_setting('messenger_auto_reply', '1') == '1'
    if not auto_reply:
        return

    if matched_order:
        if matched_order.get('messenger_psid') != sender_id:
            db.link_order_messenger(matched_order['id'], sender_id)
        link = track_link(matched_order['tracking_hash'])
        reply = (
            f"✅ Assalamu Alaikum! Found your Order #{matched_order['id']} ({matched_order['product_title']}).\n"
            f"• Shoe Size: {matched_order['shoe_size']} ({matched_order['quantity']} pair)\n"
            f"• Current Status: {matched_order['status']}\n"
            f"• Total Payable: BDT {matched_order['total_amount']:.0f}\n"
            f"📍 Live Tracking: {link}\n\n"
            f"🔔 Your Messenger is now connected! You will automatically receive updates here for every step."
        )
    else:
        reply = (
            f"🌸 Welcome to {Config.SHOP_NAME}!\n"
            f"How can we help you today?\n\n"
            f"🔍 To track your shoe order live, please reply with your:\n"
            f"• Tracking ID (e.g. A0368762965B) or\n"
            f"• Mobile Number (e.g. 01XXXXXXXXX)\n\n"
            f"Our team will also assist you shortly! 💬"
        )

    res = send_meta_messenger(sender_id, reply, tag=None)
    if res.get('success'):
        db.save_messenger_message(sender_id, 'outbound', reply, order_id=order_id)


# =============================================================================== meta whatsapp cloud api integration
def format_wa_destination(phone):
    """Formats phone number to Meta WhatsApp E.164 without plus (8801XXXXXXXXX)."""
    if not phone:
        return ''
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if digits.startswith('8801') and len(digits) == 13:
        return digits
    if digits.startswith('01') and len(digits) == 11:
        return '88' + digits
    if len(digits) == 10 and digits.startswith('1'):
        return '880' + digits
    return digits


def send_whatsapp_cloud_api(to_num, message_text):
    """
    Sends WhatsApp message to customer via Meta WhatsApp Business Cloud API.
    Endpoint: POST https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages
    """
    enabled = db.get_setting('whatsapp_enabled', '0') == '1'
    token = db.get_setting('whatsapp_access_token', '').strip()
    phone_id = db.get_setting('whatsapp_phone_number_id', '').strip()

    wa_to = format_wa_destination(to_num)
    if not enabled or not token or not phone_id or not wa_to:
        return {'success': False, 'error': 'WhatsApp Cloud API not configured or recipient invalid'}

    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": wa_to,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": message_text
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        data = resp.json()
        if resp.status_code in (200, 201) and 'messages' in data and data['messages']:
            return {'success': True, 'message_id': data['messages'][0].get('id')}
        err = data.get('error', {}).get('message', str(data))
        return {'success': False, 'error': err}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def notify_order_whatsapp(order_id, stage, extra_note=None):
    """
    Automatically sends step completion notifications to the customer via WhatsApp Cloud API
    if the order has a whatsapp_number or mobile_number.
    """
    order = db.get_order(order_id)
    if not order:
        return None
    raw_num = order.get('whatsapp_number') or order.get('mobile_number')
    if not raw_num:
        return None

    wa_to = format_wa_destination(raw_num)
    if not wa_to:
        return None

    name = order['customer_name']
    title = order['product_title']
    link = track_link(order['tracking_hash'])

    msg_map = {
        'payment_approved': (
            f"✅ Hello {name}! Your payment for Order #{order['id']} ({title}) has been VERIFIED!\n"
            f"Our team is now packaging your shoes for courier dispatch.\n"
            f"📍 Track live progress: {link}"
        ),
        'payment_rejected': (
            f"⚠️ Hello {name}, your payment for Order #{order['id']} could not be verified"
            f"{': ' + extra_note if extra_note else '.'} Please re-submit the correct TrxID here:\n"
            f"📍 {link}"
        ),
        'packaged': (
            f"📦 Hello {name}! Great news! Your shoes (Order #{order['id']}) have been packaged and boxed!\n"
            f"They are now ready at our dispatch gate for courier pickup.\n"
            f"📍 Track live: {link}"
        ),
        'dispatched': (
            f"🚚 Hello {name}! Your parcel (Order #{order['id']}) is OUT FOR DELIVERY via "
            f"{order.get('courier_name') or 'Courier'}"
            f"{( ' (Consignment: ' + order['consignment_id'] + ')') if order.get('consignment_id') else ''}!\n"
            f"The delivery rider will contact you soon.\n"
            f"📍 Track live: {link}"
        ),
        'received': (
            f"🎉 Hello {name}! Courier confirms that your shoes have been delivered! "
            f"We hope you love them!\n"
            f"Please take 30 seconds to rate and review your shoes:\n"
            f"⭐️ Rate your shoes: {link}"
        ),
        'completed': (
            f"🌟 Hello {name}! Thank you for shopping with {Config.SHOP_NAME}!\n"
            f"Your order #{order['id']} is marked completed and verified. "
            f"Feel free to message us on WhatsApp anytime if you need more pairs!"
        )
    }

    text = msg_map.get(stage)
    if not text:
        return None

    res = send_whatsapp_cloud_api(wa_to, text)
    if res.get('success'):
        db.save_whatsapp_message(wa_to, 'outbound', text, order_id=order['id'], customer_name=name)
        db.add_event(order['id'], 'message_sent', f"Automated WhatsApp update sent: {stage}", public=0)
    return res


def handle_inbound_whatsapp(wa_id, text, customer_name=None):
    """
    Smart WhatsApp Bot Engine:
    1. Looks for tracking ID, order #, or phone number in customer message.
    2. Links the order to the customer's WhatsApp wa_id.
    3. Auto-replies with live order tracking & status.
    """
    clean_wa_id = format_wa_destination(wa_id)
    local_mobile = clean_wa_id[2:] if clean_wa_id.startswith('8801') else clean_wa_id

    # 1. Match order by text content (Tracking ID, #Order, mobile)
    matched_order = db.find_order_by_text(text)
    # 2. Match order by sender's phone number
    if not matched_order:
        matched_order = db.find_order_by_phone(clean_wa_id) or db.find_order_by_phone(local_mobile)
    # 3. Match by previously linked contact
    if not matched_order:
        contact = db.get_whatsapp_contact(clean_wa_id)
        if contact and contact.get('linked_order_id'):
            matched_order = db.get_order(contact['linked_order_id'])

    order_id = matched_order['id'] if matched_order else None
    disp_name = customer_name or (matched_order['customer_name'] if matched_order else None)
    db.save_whatsapp_message(clean_wa_id, 'inbound', text, order_id=order_id, customer_name=disp_name)

    if matched_order:
        db.link_order_whatsapp(matched_order['id'], clean_wa_id, disp_name)

    auto_reply = db.get_setting('whatsapp_auto_reply', '1') == '1'
    if not auto_reply:
        return

    if matched_order:
        link = track_link(matched_order['tracking_hash'])
        reply = (
            f"✅ Assalamu Alaikum {disp_name or ''}! Found your Order #{matched_order['id']} ({matched_order['product_title']}).\n"
            f"• Shoe Size: {matched_order['shoe_size']} ({matched_order['quantity']} pair)\n"
            f"• Current Status: {matched_order['status']}\n"
            f"• Total Payable: BDT {matched_order['total_amount']:.0f}\n"
            f"📍 Live Tracking: {link}\n\n"
            f"🔔 Your WhatsApp is now connected! You will automatically receive updates here for every step."
        )
    else:
        reply = (
            f"🌸 Welcome to {Config.SHOP_NAME}!\n"
            f"How can we help you today?\n\n"
            f"🔍 To track your shoe order live, please reply with your:\n"
            f"• Tracking ID (e.g. A0368762965B) or\n"
            f"• Mobile Number (e.g. 01XXXXXXXXX)\n\n"
            f"Our team will also assist you shortly! 💬"
        )

    res = send_whatsapp_cloud_api(clean_wa_id, reply)
    if res.get('success'):
        db.save_whatsapp_message(clean_wa_id, 'outbound', reply, order_id=order_id, customer_name=disp_name)


# =============================================================================== android airtel sim sms gateway integration
def send_sms_gateway(to_num, message_text, order_id=None):
    """
    Sends SMS to customer via Android Phone SMS Gateway (e.g. personal Airtel SIM) or HTTP Gateway.
    Compatible with:
    - Android SMS Gateway (F-Droid/GitHub)
    - SMS Gateway API / TextBee / SmsSync / Traccar
    - Generic HTTP SMS Endpoints
    """
    enabled = db.get_setting('sms_enabled', '0') == '1'
    gateway_url = db.get_setting('sms_gateway_url', '').strip()
    api_key = db.get_setting('sms_api_key', '').strip()
    sim_slot = db.get_setting('sms_sim_slot', '1')

    if not enabled:
        return {'success': False, 'error': 'SMS Gateway is disabled in settings'}
    if not gateway_url:
        return {'success': False, 'error': 'SMS Gateway URL not configured'}

    # Normalize phone number to 11-digit Bangladeshi mobile format (01XXXXXXXXX)
    digits = ''.join(c for c in str(to_num) if c.isdigit())
    if digits.startswith('8801') and len(digits) == 13:
        clean_num = digits[2:]
    else:
        clean_num = digits

    if not clean_num or len(clean_num) < 10:
        return {'success': False, 'error': 'Recipient phone number is invalid'}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-API-Key"] = api_key

    # Broadly compatible payload covering multiple Android gateway app formats
    payload = {
        "phone": clean_num,
        "to": clean_num,
        "recipient": clean_num,
        "message": message_text,
        "text": message_text,
        "sim": int(sim_slot) if str(sim_slot).isdigit() else 1
    }

    try:
        resp = requests.post(gateway_url, headers=headers, json=payload, timeout=10)
        status = 'sent' if resp.status_code in (200, 201, 202) else 'failed'
        err_msg = None if status == 'sent' else f"HTTP {resp.status_code}: {resp.text[:150]}"
        db.log_sms(clean_num, message_text, order_id=order_id, status=status,
                   error_message=err_msg, gateway_response=resp.text[:300])

        if status == 'sent':
            if order_id:
                db.add_event(order_id, 'message_sent', 'SMS sent via Android Airtel SIM Gateway', public=0)
            return {'success': True, 'response': resp.text}
        return {'success': False, 'error': err_msg}
    except Exception as e:
        err = str(e)
        db.log_sms(clean_num, message_text, order_id=order_id, status='failed',
                   error_message=err, gateway_response=None)
        return {'success': False, 'error': err}


def notify_order_sms(order_id, stage, extra_note=None):
    """
    Sends automatic SMS update to customer's mobile number via Android Airtel SIM Gateway
    if sms_enabled and sms_auto_notify are active.
    """
    if db.get_setting('sms_enabled', '0') != '1' or db.get_setting('sms_auto_notify', '1') != '1':
        return None

    order = db.get_order(order_id)
    if not order or not order.get('mobile_number'):
        return None

    name = order['customer_name']
    title = order['product_title']
    link = track_link(order['tracking_hash'])
    courier = order.get('courier_name') or 'Courier'
    consignment = f" (Consignment: {order['consignment_id']})" if order.get('consignment_id') else ""

    msg_map = {
        'created': f"Hello {name}, order #{order['id']} for {title} placed with {Config.SHOP_NAME}! Track: {link}",
        'payment_approved': f"Hello {name}, payment for Order #{order['id']} ({title}) is VERIFIED! We are packing your shoes. Track: {link}",
        'payment_rejected': f"Hello {name}, payment for Order #{order['id']} could not be verified{': ' + extra_note if extra_note else ''}. Please resubmit: {link}",
        'packaged': f"Hello {name}, Order #{order['id']} ({title}) is packed and ready at gate for courier handover. Track: {link}",
        'dispatched': f"Hello {name}, Order #{order['id']} is OUT FOR DELIVERY via {courier}{consignment}! Rider will contact you. Track: {link}",
        'received': f"Hello {name}, your shoes (Order #{order['id']}) have been delivered! Please rate your shoes: {link}",
        'completed': f"Hello {name}, thank you for ordering from {Config.SHOP_NAME}! Your order #{order['id']} is completed."
    }

    text = msg_map.get(stage)
    if not text:
        return None

    return send_sms_gateway(order['mobile_number'], text, order_id=order['id'])


# =============================================================================== customer side
@main_bp.route('/')
def home():
    q = request.args.get('q', '').strip()
    size = request.args.get('size', '').strip()
    products = db.list_products(search=q or None, size=size or None)
    return render_template('index.html', products=products, q=q, size=size, sizes=Config.BD_SIZES)


def render_product(pid, form=None):
    product = db.get_product(pid)
    if not product or not product['is_active']:
        return render_template('404.html', msg="This product is not available."), 404
    feedbacks = db.product_feedbacks(pid)
    sizes = [s.strip() for s in product['available_sizes'].split(',') if s.strip()]
    avg = round(sum(f['rating'] for f in feedbacks) / len(feedbacks), 1) if feedbacks else None
    is_free = bool(product.get('is_free_delivery'))
    charge_in = 0 if is_free else Config.DELIVERY_INSIDE_DHAKA
    charge_out = 0 if is_free else Config.DELIVERY_OUTSIDE_DHAKA
    return render_template('product_detail.html', product=product, feedbacks=feedbacks, sizes=sizes,
                           avg=avg, divisions=Config.DIVISIONS, form=form or {}, open_modal=bool(form),
                           charge_in=charge_in, charge_out=charge_out, is_free_delivery=is_free)


@main_bp.route('/product/<int:product_id>')
def product_view(product_id):
    return render_product(product_id)


@main_bp.route('/order/create', methods=['POST'])
def create_order():
    f = request.form
    if f.get('website'):                        # honeypot: bots fill hidden fields
        return redirect(url_for('main.home'))
    prod = db.get_product(to_int(f.get('product_id')))
    if not prod or not prod['is_active']:
        flash("Product not found.", "error")
        return redirect(url_for('main.home'))
    if too_many('order', 6, 600):
        flash("Too many orders from this device. Please wait a few minutes or chat with us on WhatsApp.", "error")
        return render_product(prod['id'], form=f)

    sizes = [s.strip() for s in prod['available_sizes'].split(',')]
    size = f.get('shoe_size', '')
    qty = to_int(f.get('quantity'), 1)
    name = f.get('customer_name', '').strip()
    mobile = norm_mobile(f.get('mobile_number'))
    wa_raw = f.get('whatsapp_number', '').strip()
    wa = norm_mobile(wa_raw) if wa_raw else ''
    email = f.get('email', '').strip()
    division = f.get('division', '')
    district = f.get('district', '').strip()
    village = f.get('village_town', '').strip()
    road = f.get('road_house', '').strip()

    errors = []
    if size not in sizes:
        errors.append("Please choose an available size.")
    if not 1 <= qty <= Config.MAX_QTY:
        errors.append("Quantity must be between 1 and %d." % Config.MAX_QTY)
    if len(name) < 2:
        errors.append("Please enter your name.")
    if not mobile:
        errors.append("Enter a valid Bangladeshi mobile number (01XXXXXXXXX).")
    if wa_raw and not wa:
        errors.append("WhatsApp number is not valid (01XXXXXXXXX) - or leave it empty.")
    if email and not EMAIL_RE.match(email):
        errors.append("Email address is not valid - or leave it empty.")
    if division not in Config.DIVISIONS:
        errors.append("Please choose your division.")
    if not village or not road:
        errors.append("Village/Town and Road/House no are required.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_product(prod['id'], form=f)

    payment_method = f.get('payment_method', 'bkash').strip().lower()
    if payment_method not in ('bkash', 'cod'):
        payment_method = 'bkash'

    is_free = bool(prod.get('is_free_delivery'))
    charge = delivery_charge(division, is_free=is_free, payment_method=payment_method)
    parts = [road, village, district, division]
    data = dict(product_id=prod['id'], product_sku=prod['sku'], product_title=prod['title'],
                product_image=prod['image_1'], shoe_size=size, quantity=qty,
                unit_price=prod['price'], delivery_charge=charge,
                total_amount=prod['price'] * qty + charge,
                payment_method=payment_method,
                notes=f.get('notes', '').strip()[:Config.NOTES_MAX] or None,
                customer_name=name, email=email or None, mobile_number=mobile,
                whatsapp_number=wa or None, division=division, district=district or None,
                village_town=village, road_house=road,
                full_address=", ".join(p for p in parts if p))
    for _ in range(5):
        data['tracking_hash'] = secrets.token_hex(6).upper()
        try:
            new_oid = db.create_order(data)
            notify_order_sms(new_oid, 'created')
            break
        except sqlite3.IntegrityError:
            continue
    else:
        flash("Could not create order, please try again.", "error")
        return render_product(prod['id'], form=f)
    flash("Order placed! Your personal tracking link is ready. Save it - the shop will also send it to you.", "success")
    return redirect(url_for('main.track_order', tracking_hash=data['tracking_hash'], new=1))


@main_bp.route('/track', methods=['GET', 'POST'])
def track_lookup():
    """Customer lost the link? Tracking ID + mobile number brings it back."""
    if request.method == 'POST':
        if too_many('lookup', 10, 600):
            flash("Too many attempts. Please try again later.", "error")
            return render_template('track_lookup.html')
        h = request.form.get('tracking_id', '').strip().upper()
        o = db.get_order_by_hash(h) if h else None
        if o and norm_mobile(request.form.get('mobile')) == o['mobile_number']:
            return redirect(url_for('main.track_order', tracking_hash=h))
        flash("No order matches that Tracking ID and mobile number.", "error")
    return render_template('track_lookup.html')


@main_bp.route('/track/<tracking_hash>')
def track_order(tracking_hash):
    order = db.get_order_by_hash(tracking_hash)
    if not order:
        return render_template('404.html', msg="This order tracking link is not valid."), 404
    st = order['status']
    is_cod = order.get('payment_method') == 'cod'
    if is_cod:
        steps = ['Order Placed', 'Packaging', 'Out for Delivery', 'Received', 'Completed']
    else:
        steps = ['Order Placed', 'Payment Verified', 'Packaging', 'Out for Delivery', 'Received', 'Completed']

    rejected = st == 'Payment Rejected'
    if rejected:
        idx = 1
    elif st == 'Payment Pending':
        idx = 0
    elif st in steps:
        idx = steps.index(st)
    else:
        idx = 0

    return render_template('order_tracking.html', order=order, steps=steps, idx=idx, rejected=rejected,
                           events=db.list_events(order['id'], public_only=True),
                           bkash_no=Config.BKASH_NUMBER, is_new=bool(request.args.get('new')),
                           link=track_link(tracking_hash),
                           messenger_enabled=db.get_setting('messenger_enabled', '0') == '1',
                           messenger_page_id=db.get_setting('messenger_page_id', ''))


@main_bp.route('/order/status/<tracking_hash>')
def order_status_json(tracking_hash):
    """Polled by tracker.js so the page refreshes only when something changed."""
    o = db.get_order_by_hash(tracking_hash)
    if not o:
        return jsonify(status=None), 404
    return jsonify(status=o['status'], updated=str(o['updated_at']))


@main_bp.route('/order/pay', methods=['POST'])
def submit_payment():
    h = request.form.get('tracking_hash', '')
    back = redirect(url_for('main.track_order', tracking_hash=h))
    order = db.get_order_by_hash(h)
    if not order or order['status'] not in ('Order Placed', 'Payment Rejected'):
        flash("Payment cannot be submitted for this order now.", "error")
        return back
    trx = request.form.get('transaction_id', '').strip().upper().replace(' ', '')
    bk = norm_mobile(request.form.get('bkash_number'))
    address = request.form.get('full_address', '').strip()[:300] or order['full_address']
    if not TRX_RE.match(trx):
        flash("Transaction ID looks wrong. It is 8-12 letters/numbers, e.g. 9AB3C4D5EF.", "error")
        return back
    if not bk:
        flash("Enter the bKash number you paid from (01XXXXXXXXX).", "error")
        return back
    try:
        db.submit_payment(order['id'], bk, trx, order['total_amount'], address)
    except sqlite3.IntegrityError:
        flash("This Transaction ID was already submitted. Please check it and try again.", "error")
        return back
    flash("Payment submitted. The shop will verify it shortly and message you.", "success")
    return back


@main_bp.route('/order/cancel', methods=['POST'])
def customer_cancel():
    h = request.form.get('tracking_hash', '')
    order = db.get_order_by_hash(h)
    if order and db.cancel_order(order['id'], 'customer', '', db.CANCEL_BY_CUSTOMER):
        flash("Your order has been cancelled.", "success")
    else:
        flash("This order can no longer be cancelled online. Please chat with us on WhatsApp.", "error")
    return redirect(url_for('main.track_order', tracking_hash=h))


@main_bp.route('/order/received', methods=['POST'])
def mark_received():
    h = request.form.get('tracking_hash', '')
    order = db.get_order_by_hash(h)
    if order and db.mark_received(order['id']):
        notify_order_messenger(order['id'], 'received')
        notify_order_whatsapp(order['id'], 'received')
        notify_order_sms(order['id'], 'received')
        flash("Thank you! Please rate your shoes below.", "success")
    return redirect(url_for('main.track_order', tracking_hash=h))


@main_bp.route('/order/feedback', methods=['POST'])
def submit_feedback():
    h = request.form.get('tracking_hash', '')
    order = db.get_order_by_hash(h)
    if not order or order['status'] != 'Received' or order['feedback_id']:
        flash("Feedback is not available for this order.", "error")
        return redirect(url_for('main.track_order', tracking_hash=h))
    rating = min(5, max(1, to_int(request.form.get('rating'), 5)))
    first_name = order['customer_name'].split()[0]          # privacy: show first name only
    db.add_feedback(dict(order, customer_name=first_name), rating,
                    request.form.get('comment', '').strip()[:500])
    flash("Thank you! Your review now appears on the product page.", "success")
    return redirect(url_for('main.track_order', tracking_hash=h))


# =============================================================================== admin: auth & localhost protection
@main_bp.before_request
def restrict_admin_access():
    """Restricts all /admin routes so that admin management is strictly local (localhost only)."""
    if request.path.startswith('/admin'):
        host_no_port = request.host.split(':')[0].lower()
        is_local = host_no_port in ('localhost', '127.0.0.1', '0.0.0.0')
        if Config.IS_VERCEL or not is_local:
            emergency_key = os.environ.get('ADMIN_REMOTE_KEY')
            if emergency_key and request.args.get('key') == emergency_key:
                return None
            return render_template('404.html', msg="Admin portal is restricted to local server maintenance. Please manage your shop via http://localhost:3570/admin/login"), 404


@main_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if too_many('login', 8, 300):
            flash("Too many login attempts. Wait 5 minutes.", "error")
            return render_template('admin/login.html')
        u = db.get_admin(request.form.get('username', '').strip())
        if u and check_password_hash(u['password_hash'], request.form.get('password', '')):
            session.clear()
            session['admin'] = u['username']
            session.permanent = True
            nxt = request.args.get('next', '')
            return redirect(nxt if nxt.startswith('/admin') else url_for('main.admin_dashboard'))
        flash("Wrong username or password.", "error")
    return render_template('admin/login.html')


@main_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('main.admin_login'))


@main_bp.route('/admin/password', methods=['GET', 'POST'])
@login_required
def admin_password():
    if request.method == 'POST':
        u = db.get_admin(session['admin'])
        new = request.form.get('new_password', '')
        if not check_password_hash(u['password_hash'], request.form.get('current_password', '')):
            flash("Current password is wrong.", "error")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new != request.form.get('confirm_password', ''):
            flash("New passwords do not match.", "error")
        else:
            db.upsert_admin(u['username'], generate_password_hash(new))
            flash("Password changed.", "success")
            return redirect(url_for('main.admin_dashboard'))
    return render_template('admin/password.html')


# =============================================================================== admin: dashboard & orders
def _filters():
    from_date, to_date, f, t = date_range()
    queue = request.args.get('queue', '').strip()
    all_time = request.args.get('all_time', '0') == '1'
    use_f = None if all_time else f
    use_t = None if all_time else t
    return dict(from_date=from_date, to_date=to_date, f=use_f, t=use_t,
                f_metrics=f, t_metrics=t,
                stage=request.args.get('stage', ''), status=request.args.get('status', ''),
                queue=queue, all_time=all_time,
                q=request.args.get('q', '').strip())


@main_bp.route('/admin')
@main_bp.route('/admin/dashboard')
@login_required
def admin_dashboard():
    fl = _filters()
    today = today_bd()
    quick = [('Today', today, today), ('Last 7 days', today - timedelta(days=6), today),
             ('Last 30 days', today - timedelta(days=29), today),
             ('This month', today.replace(day=1), today)]
    orders = db.list_orders(fl['f'], fl['t'], fl['stage'], fl['status'], fl['q'], fl['queue'])
    return render_template(
        'admin/dashboard.html', m=db.dashboard_metrics(fl['f_metrics'], fl['t_metrics']), todo=db.action_needed(),
        customer_metrics=db.get_customer_metrics(),
        orders=orders, order_count=len(orders),
        top=db.top_products(fl['f_metrics'], fl['t_metrics']), quick=quick,
        couriers=Config.COURIERS,
        statuses=Config.STEPS + ['Payment Rejected', 'Cancelled'], **fl)


@main_bp.route('/admin/export.csv')
@login_required
def admin_export():
    fl = _filters()
    rows = db.list_orders(fl['f'], fl['t'], fl['stage'], fl['status'], fl['q'], fl['queue'])
    out = io.StringIO()
    out.write('\ufeff')                                   # Excel-friendly UTF-8
    w = csv.writer(out)
    w.writerow(['Order #', 'Date', 'Tracking ID', 'Customer', 'Mobile', 'WhatsApp', 'Product ID', 'SKU',
                'Title', 'Size', 'Qty', 'Unit price', 'Delivery', 'Total', 'Payment Method', 'bKash no', 'TrxID',
                'Payment', 'Status', 'Courier', 'Consignment', 'Address', 'Notes'])
    for o in rows:
        w.writerow([o['id'], o['created_at'], o['tracking_hash'], o['customer_name'], o['mobile_number'],
                    o['whatsapp_number'] or '', o['product_id'] or '', o['product_sku'], o['product_title'],
                    o['shoe_size'], o['quantity'], o['unit_price'], o['delivery_charge'], o['total_amount'],
                    o.get('payment_method', 'bkash').upper(),
                    o['bkash_number'] or '', o['transaction_id'] or '', o['verification_status'] or '',
                    o['status'], o['courier_name'] or '', o['consignment_id'] or '', o['full_address'],
                    o['notes'] or ''])
    return Response(out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=orders_%s_to_%s.csv'
                             % (fl['from_date'], fl['to_date'])})


def _order_or_404(order_id):
    return db.get_order(order_id)


@main_bp.route('/admin/order/<int:order_id>')
@login_required
def admin_order(order_id):
    o = _order_or_404(order_id)
    if not o:
        return render_template('404.html', msg="Order not found."), 404
    link = track_link(o['tracking_hash'])
    return render_template('admin/order_detail.html', o=o, link=link, total=o['total_amount'],
                           msgs=build_messages(o, link),
                           suggested=SUGGESTED_MESSAGE.get(o['status']), events=db.list_events(order_id),
                           couriers=Config.COURIERS, can_cancel=o['status'] in db.CANCEL_BY_ADMIN)


@main_bp.route('/admin/order/<int:order_id>/print')
@login_required
def admin_order_print(order_id):
    o = _order_or_404(order_id)
    if not o:
        return render_template('404.html', msg="Order not found."), 404
    return render_template('admin/order_print.html', o=o)


@main_bp.route('/admin/order/<int:order_id>/notify/<kind>/<channel>')
@login_required
def admin_notify(order_id, kind, channel):
    """Logs that the admin sent a message, then opens WhatsApp / the SMS app with the text ready."""
    o = _order_or_404(order_id)
    msgs = build_messages(o, track_link(o['tracking_hash'])) if o else {}
    msg = msgs.get(kind)
    if not msg or channel not in ('wa', 'sms'):
        return render_template('404.html', msg="Message not found."), 404
    db.add_event(order_id, 'message_sent', "%s sent via %s" % (msg['label'], 'WhatsApp' if channel == 'wa' else 'SMS'),
                 public=0)
    return redirect(msg[channel])


@main_bp.route('/admin/order/<int:order_id>/payment', methods=['POST'])
@login_required
def admin_payment(order_id):
    action = request.form.get('action')
    note = request.form.get('admin_notes', '').strip()[:255]
    if action in ('approve', 'reject') and db.decide_payment(order_id, action == 'approve', note):
        notify_order_messenger(order_id, 'payment_approved' if action == 'approve' else 'payment_rejected', note)
        notify_order_whatsapp(order_id, 'payment_approved' if action == 'approve' else 'payment_rejected', note)
        notify_order_sms(order_id, 'payment_approved' if action == 'approve' else 'payment_rejected', note)
        flash("Payment %s for Order #%d. Now ready for packaging." %
              ('approved' if action == 'approve' else 'rejected', order_id), "success")
    else:
        flash("No pending payment to decide on this order.", "error")
    return redirect(request.referrer or url_for('main.admin_order', order_id=order_id))


@main_bp.route('/admin/order/<int:order_id>/pack', methods=['POST'])
@login_required
def admin_pack(order_id):
    note = request.form.get('note', '').strip()[:150]
    if db.mark_packaging(order_id, note):
        notify_order_messenger(order_id, 'packaged', note)
        notify_order_whatsapp(order_id, 'packaged', note)
        notify_order_sms(order_id, 'packaged', note)
        flash("Order #%d marked as Packaged! Ready at gate for courier handover." % order_id, "success")
    else:
        flash("Cannot mark order as packaged. Ensure payment is verified or COD is placed.", "error")
    return redirect(request.referrer or url_for('main.admin_order', order_id=order_id))


@main_bp.route('/admin/order/<int:order_id>/dispatch', methods=['POST'])
@login_required
def admin_dispatch(order_id):
    courier = request.form.get('courier', '').strip()[:60]
    consignment = request.form.get('consignment_id', '').strip()[:60]
    note = request.form.get('note', '').strip()[:150]
    if db.dispatch_order(order_id, courier, consignment, note):
        notify_order_messenger(order_id, 'dispatched', note)
        notify_order_whatsapp(order_id, 'dispatched', note)
        notify_order_sms(order_id, 'dispatched', note)
        flash("Order #%d Gate Out completed: Handed over to %s and Out for Delivery!" % (order_id, courier or 'Courier'), "success")
    else:
        flash("Only packaged, verified or Cash on Delivery orders can go out for delivery.", "error")
    return redirect(request.referrer or url_for('main.admin_order', order_id=order_id))


@main_bp.route('/admin/order/<int:order_id>/received', methods=['POST'])
@login_required
def admin_received(order_id):
    if db.mark_received(order_id, by='admin'):
        notify_order_messenger(order_id, 'received')
        notify_order_whatsapp(order_id, 'received')
        notify_order_sms(order_id, 'received')
        flash("Order #%d marked as Delivered! Now awaiting customer feedback / closure." % order_id, "success")
    else:
        flash("Only orders out for delivery can be marked as delivered.", "error")
    return redirect(request.referrer or url_for('main.admin_order', order_id=order_id))


@main_bp.route('/admin/order/<int:order_id>/complete', methods=['POST'])
@login_required
def admin_complete(order_id):
    note = request.form.get('note', '').strip()[:150]
    if db.complete_order(order_id, note):
        notify_order_messenger(order_id, 'completed', note)
        notify_order_whatsapp(order_id, 'completed', note)
        notify_order_sms(order_id, 'completed', note)
        flash("Order #%d verified and closed as Completed!" % order_id, "success")
    else:
        flash("Only delivered or in-transit orders can be closed as completed.", "error")
    return redirect(request.referrer or url_for('main.admin_order', order_id=order_id))


@main_bp.route('/admin/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def admin_cancel(order_id):
    if db.cancel_order(order_id, 'admin', request.form.get('reason', '').strip()[:150], db.CANCEL_BY_ADMIN):
        flash("Order cancelled.", "success")
    else:
        flash("This order can no longer be cancelled.", "error")
    return redirect(url_for('main.admin_order', order_id=order_id))


# =============================================================================== admin: products
@main_bp.route('/admin/products')
@login_required
def admin_products():
    return render_template('admin/products.html', products=db.list_products(include_inactive=True))


@main_bp.route('/admin/product/new', methods=['GET', 'POST'])
@main_bp.route('/admin/product/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
def admin_product_form(pid=None):
    p = db.get_product(pid) if pid else None
    if pid and not p:
        return render_template('404.html', msg="Product not found."), 404

    def show(form=None):
        return render_template('admin/product_form.html', p=p, all_sizes=Config.BD_SIZES, form=form)

    if request.method == 'GET':
        return show()
    f = request.form
    sizes = ', '.join(s for s in Config.BD_SIZES if s in f.getlist('sizes'))
    price, old_price = to_float(f.get('price')), to_float(f.get('old_price'))
    sku, title = f.get('sku', '').strip(), f.get('title', '').strip()
    if not sku or not title or price is None or price < 0:
        flash("SKU, title and a valid price are required.", "error")
        return show(f)
    if not sizes:
        flash("Select at least one size.", "error")
        return show(f)
    new_files, data = [], dict(sku=sku, title=title, description=f.get('description', '').strip(),
                               price=price, old_price=old_price, sizes=sizes,
                               is_free_delivery=1 if f.get('is_free_delivery') else 0,
                               is_active=1 if f.get('is_active') else 0)
    for i in (1, 2, 3):
        key = 'image_%d' % i
        up = save_upload(request.files.get(key), 'images')
        if up:
            new_files.append(up)
            data[key] = up
        elif p and (i == 1 or not f.get('remove_' + key)):    # keep current (image 1 can't be removed)
            data[key] = p[key]
        else:
            data[key] = None
    up_video = save_upload(request.files.get('video'), 'videos')
    if up_video:
        new_files.append(up_video)
    data['video_url'] = up_video or (p['video_url'] if p and not f.get('remove_video') else None)
    if not data['image_1']:
        for n in new_files:
            remove_upload(n)
        flash("Image 1 is required (jpg / png / webp).", "error")
        return show(f)
    try:
        db.save_product(pid, data)
    except sqlite3.IntegrityError:
        for n in new_files:
            remove_upload(n)
        flash("This SKU already exists. Use a different SKU.", "error")
        return show(f)
    if p:                                                  # delete files that were replaced / removed
        for key in ('image_1', 'image_2', 'image_3', 'video_url'):
            if p[key] and p[key] != data[key]:
                remove_upload(p[key])
    flash("Product saved.", "success")
    return redirect(url_for('main.admin_products'))


@main_bp.route('/admin/product/<int:pid>/toggle', methods=['POST'])
@login_required
def admin_product_toggle(pid):
    p = db.get_product(pid)
    if p:
        db.set_product_active(pid, not p['is_active'])
        flash("Product is now %s." % ('hidden' if p['is_active'] else 'visible in the shop'), "success")
    return redirect(url_for('main.admin_products'))


@main_bp.route('/admin/product/<int:pid>/delete', methods=['POST'])
@login_required
def admin_product_delete(pid):
    p = db.get_product(pid)
    if not p:
        return redirect(url_for('main.admin_products'))
    if db.product_order_count(pid):
        db.set_product_active(pid, False)
        flash("This product has orders, so it was hidden instead of deleted (order history is kept).", "success")
    else:
        db.delete_product(pid)
        for key in ('image_1', 'image_2', 'image_3', 'video_url'):
            remove_upload(p[key])
        flash("Product deleted.", "success")
    return redirect(url_for('main.admin_products'))


# =============================================================================== admin: feedback
@main_bp.route('/admin/feedbacks')
@login_required
def admin_feedbacks():
    from_date, to_date, f, t = date_range()
    return render_template('admin/feedbacks.html', feedbacks=db.admin_feedbacks(f, t),
                           from_date=from_date, to_date=to_date)


@main_bp.route('/admin/feedback/<int:fid>/toggle', methods=['POST'])
@login_required
def admin_feedback_toggle(fid):
    db.set_feedback_visible(fid, request.form.get('visible') == '1')
    flash("Review updated.", "success")
    return redirect(request.referrer or url_for('main.admin_feedbacks'))


# =============================================================================== meta messenger & whatsapp webhook & admin
@main_bp.route('/webhook', methods=['GET', 'POST'])
def messenger_webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        expected_messenger = db.get_setting('messenger_verify_token', 'ms_ladies_shoes_meta_verify_2026')
        expected_whatsapp = db.get_setting('whatsapp_verify_token', 'ms_ladies_shoes_meta_verify_2026')
        if mode == 'subscribe' and token in (expected_messenger, expected_whatsapp):
            return challenge, 200
        return "Verification token mismatch", 403

    data = request.get_json(silent=True) or {}
    obj = data.get('object')

    # 1. Meta Messenger Event
    if obj == 'page':
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event.get('sender', {}).get('id')
                message = event.get('message', {})
                if sender_id and message and not message.get('is_echo'):
                    msg_text = message.get('text', '').strip()
                    if msg_text:
                        handle_inbound_messenger(sender_id, msg_text)

    # 2. WhatsApp Business Cloud API Event
    elif obj == 'whatsapp_business_account':
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                val = change.get('value', {})
                contacts = val.get('contacts', [])
                name_by_wa = {}
                for c in contacts:
                    wa = c.get('wa_id')
                    cname = c.get('profile', {}).get('name')
                    if wa and cname:
                        name_by_wa[wa] = cname

                for msg in val.get('messages', []):
                    from_num = msg.get('from')
                    msg_type = msg.get('type')
                    if msg_type == 'text':
                        text_body = msg.get('text', {}).get('body', '').strip()
                        if from_num and text_body:
                            cname = name_by_wa.get(from_num)
                            handle_inbound_whatsapp(from_num, text_body, customer_name=cname)

    return "EVENT_RECEIVED", 200


@main_bp.route('/admin/messenger')
@login_required
def admin_messenger():
    channel = request.args.get('channel', '').strip()

    # Messenger contacts & thread
    active_psid = request.args.get('psid', '').strip()
    contacts = db.list_messenger_contacts()
    if not active_psid and contacts:
        active_psid = contacts[0]['psid']
    active_contact = db.get_messenger_contact(active_psid) if active_psid else None
    messages = db.get_messenger_messages(active_psid) if active_psid else []

    # WhatsApp contacts & thread
    active_wa_id = request.args.get('wa_id', '').strip()
    wa_contacts = db.list_whatsapp_contacts()
    if not active_wa_id and wa_contacts:
        active_wa_id = wa_contacts[0]['wa_id']
    active_wa_contact = db.get_whatsapp_contact(active_wa_id) if active_wa_id else None
    wa_messages = db.get_whatsapp_messages(active_wa_id) if active_wa_id else []

    if not channel:
        if active_wa_id and request.args.get('wa_id'):
            channel = 'whatsapp'
        else:
            channel = 'messenger'

    settings = db.get_all_settings()
    webhook_url = request.host_url.rstrip('/') + '/webhook'
    recent_orders = db.list_orders(limit=25)
    sms_logs = db.list_sms_logs(limit=40)

    return render_template(
        'admin/messenger.html',
        channel=channel,
        contacts=contacts,
        active_psid=active_psid,
        active_contact=active_contact,
        messages=messages,
        wa_contacts=wa_contacts,
        active_wa_id=active_wa_id,
        active_wa_contact=active_wa_contact,
        wa_messages=wa_messages,
        sms_logs=sms_logs,
        settings=settings,
        webhook_url=webhook_url,
        recent_orders=recent_orders
    )


@main_bp.route('/admin/messenger/settings', methods=['POST'])
@login_required
def admin_messenger_settings():
    f = request.form
    db.set_setting('messenger_enabled', '1' if f.get('messenger_enabled') else '0')
    db.set_setting('messenger_page_token', f.get('messenger_page_token', '').strip())
    db.set_setting('messenger_verify_token', f.get('messenger_verify_token', '').strip() or 'ms_ladies_shoes_meta_verify_2026')
    db.set_setting('messenger_page_id', f.get('messenger_page_id', '').strip())
    db.set_setting('messenger_auto_reply', '1' if f.get('messenger_auto_reply') else '0')
    flash("Meta Messenger settings saved successfully!", "success")
    return redirect(url_for('main.admin_messenger', channel='settings'))


@main_bp.route('/admin/messenger/<psid>/send', methods=['POST'])
@login_required
def admin_messenger_send(psid):
    text = request.form.get('message_text', '').strip()
    if not text:
        flash("Message cannot be empty.", "error")
        return redirect(url_for('main.admin_messenger', channel='messenger', psid=psid))

    contact = db.get_messenger_contact(psid)
    order_id = contact['linked_order_id'] if contact else None

    res = send_meta_messenger(psid, text, tag=None)
    if res.get('success'):
        db.save_messenger_message(psid, 'outbound', text, order_id=order_id)
        flash("Message sent to customer on Facebook Messenger!", "success")
    else:
        db.save_messenger_message(psid, 'outbound', text, order_id=order_id)
        flash("Meta API response: %s" % res.get('error', 'Unknown error'), "error")
    return redirect(url_for('main.admin_messenger', channel='messenger', psid=psid))


@main_bp.route('/admin/messenger/<psid>/link_order', methods=['POST'])
@login_required
def admin_messenger_link_order(psid):
    oid = to_int(request.form.get('order_id'))
    if oid and db.link_order_messenger(oid, psid):
        flash("Conversation successfully linked to Order #%d!" % oid, "success")
    else:
        flash("Invalid Order ID.", "error")
    return redirect(url_for('main.admin_messenger', channel='messenger', psid=psid))


@main_bp.route('/admin/order/<int:order_id>/link_messenger', methods=['POST'])
@login_required
def admin_order_link_messenger(order_id):
    psid = request.form.get('messenger_psid', '').strip()
    if psid and db.link_order_messenger(order_id, psid):
        flash("Order #%d linked to Messenger PSID %s!" % (order_id, psid), "success")
    else:
        flash("Please enter a valid Messenger PSID.", "error")
    return redirect(url_for('main.admin_order', order_id=order_id))


@main_bp.route('/admin/order/<int:order_id>/messenger_test', methods=['POST'])
@login_required
def admin_order_messenger_test(order_id):
    order = db.get_order(order_id)
    if not order or not order.get('messenger_psid'):
        flash("No Messenger PSID linked to this order.", "error")
        return redirect(url_for('main.admin_order', order_id=order_id))

    psid = order['messenger_psid']
    msg = f"🔔 Test ping from {Config.SHOP_NAME} for Order #{order['id']}: Your Messenger is active and connected for automatic tracking updates!"
    res = send_meta_messenger(psid, msg, tag='CONFIRMED_CUSTOMER_UPDATE')
    if res.get('success'):
        db.save_messenger_message(psid, 'outbound', msg, order_id=order['id'])
        flash("Test notification sent successfully to customer's Messenger!", "success")
    else:
        flash("Meta API response: %s" % res.get('error', 'Failed to send ping'), "error")
    return redirect(url_for('main.admin_order', order_id=order_id))


# =============================================================================== admin: whatsapp cloud api routes
@main_bp.route('/admin/whatsapp/settings', methods=['POST'])
@login_required
def admin_whatsapp_settings():
    f = request.form
    db.set_setting('whatsapp_enabled', '1' if f.get('whatsapp_enabled') else '0')
    db.set_setting('whatsapp_phone_number_id', f.get('whatsapp_phone_number_id', '').strip())
    db.set_setting('whatsapp_business_account_id', f.get('whatsapp_business_account_id', '').strip())
    db.set_setting('whatsapp_access_token', f.get('whatsapp_access_token', '').strip())
    db.set_setting('whatsapp_verify_token', f.get('whatsapp_verify_token', '').strip() or 'ms_ladies_shoes_meta_verify_2026')
    db.set_setting('whatsapp_auto_reply', '1' if f.get('whatsapp_auto_reply') else '0')
    flash("WhatsApp Business Cloud API settings saved successfully!", "success")
    return redirect(url_for('main.admin_messenger', channel='wa_settings'))


@main_bp.route('/admin/whatsapp/<wa_id>/send', methods=['POST'])
@login_required
def admin_whatsapp_send(wa_id):
    text = request.form.get('message_text', '').strip()
    if not text:
        flash("Message cannot be empty.", "error")
        return redirect(url_for('main.admin_messenger', channel='whatsapp', wa_id=wa_id))

    contact = db.get_whatsapp_contact(wa_id)
    order_id = contact['linked_order_id'] if contact else None

    res = send_whatsapp_cloud_api(wa_id, text)
    if res.get('success'):
        db.save_whatsapp_message(wa_id, 'outbound', text, order_id=order_id)
        flash("Message sent to customer on WhatsApp!", "success")
    else:
        db.save_whatsapp_message(wa_id, 'outbound', text, order_id=order_id)
        flash("WhatsApp Cloud API response: %s" % res.get('error', 'Unknown error'), "error")
    return redirect(url_for('main.admin_messenger', channel='whatsapp', wa_id=wa_id))


@main_bp.route('/admin/whatsapp/<wa_id>/link_order', methods=['POST'])
@login_required
def admin_whatsapp_link_order(wa_id):
    oid = to_int(request.form.get('order_id'))
    if oid and db.link_order_whatsapp(oid, wa_id):
        flash("WhatsApp conversation successfully linked to Order #%d!" % oid, "success")
    else:
        flash("Invalid Order ID.", "error")
    return redirect(url_for('main.admin_messenger', channel='whatsapp', wa_id=wa_id))


@main_bp.route('/admin/order/<int:order_id>/link_whatsapp', methods=['POST'])
@login_required
def admin_order_link_whatsapp(order_id):
    wa_num = request.form.get('whatsapp_number', '').strip()
    formatted = format_wa_destination(wa_num)
    if formatted and db.link_order_whatsapp(order_id, formatted):
        flash("Order #%d linked to WhatsApp number %s!" % (order_id, formatted), "success")
    else:
        flash("Please enter a valid WhatsApp phone number.", "error")
    return redirect(url_for('main.admin_order', order_id=order_id))


@main_bp.route('/admin/order/<int:order_id>/whatsapp_test', methods=['POST'])
@login_required
def admin_order_whatsapp_test(order_id):
    order = db.get_order(order_id)
    raw_num = (order.get('whatsapp_number') or order.get('mobile_number')) if order else None
    if not order or not raw_num:
        flash("No WhatsApp number or mobile number found for this order.", "error")
        return redirect(url_for('main.admin_order', order_id=order_id))

    wa_to = format_wa_destination(raw_num)
    msg = f"🔔 Test ping from {Config.SHOP_NAME} for Order #{order['id']}: Your WhatsApp is connected for automatic tracking updates!"
    res = send_whatsapp_cloud_api(wa_to, msg)
    if res.get('success'):
        db.save_whatsapp_message(wa_to, 'outbound', msg, order_id=order['id'], customer_name=order['customer_name'])
        flash("Test notification ping sent successfully to customer's WhatsApp (%s)!" % wa_to, "success")
    else:
        flash("WhatsApp Cloud API response: %s" % res.get('error', 'Failed to send ping'), "error")
    return redirect(url_for('main.admin_order', order_id=order_id))


# =============================================================================== admin: android airtel sim sms routes
@main_bp.route('/admin/sms/settings', methods=['POST'])
@login_required
def admin_sms_settings():
    f = request.form
    db.set_setting('sms_enabled', '1' if f.get('sms_enabled') else '0')
    db.set_setting('sms_gateway_url', f.get('sms_gateway_url', '').strip())
    db.set_setting('sms_api_key', f.get('sms_api_key', '').strip())
    db.set_setting('sms_sim_slot', f.get('sms_sim_slot', '1').strip())
    db.set_setting('sms_sim_operator', f.get('sms_sim_operator', 'Airtel').strip())
    db.set_setting('sms_auto_notify', '1' if f.get('sms_auto_notify') else '0')
    flash("Android SMS Gateway (Airtel SIM) settings saved successfully!", "success")
    return redirect(url_for('main.admin_messenger', channel='sms'))


@main_bp.route('/admin/sms/send', methods=['POST'])
@login_required
def admin_sms_send():
    phone = request.form.get('recipient_number', '').strip()
    text = request.form.get('message_text', '').strip()
    order_id = to_int(request.form.get('order_id'))

    if not phone or not text:
        flash("Recipient phone and message text are required.", "error")
        return redirect(url_for('main.admin_messenger', channel='sms'))

    res = send_sms_gateway(phone, text, order_id=order_id)
    if res.get('success'):
        flash("SMS successfully dispatched via Android Airtel SIM Gateway to %s!" % phone, "success")
    else:
        flash("SMS Gateway error: %s" % res.get('error', 'Failed to send SMS'), "error")
    return redirect(url_for('main.admin_messenger', channel='sms'))


@main_bp.route('/admin/order/<int:order_id>/sms_test', methods=['POST'])
@login_required
def admin_order_sms_test(order_id):
    order = db.get_order(order_id)
    if not order or not order.get('mobile_number'):
        flash("No mobile number found for this order.", "error")
        return redirect(url_for('main.admin_order', order_id=order_id))

    phone = order['mobile_number']
    msg = f"Test SMS from {Config.SHOP_NAME} for Order #{order['id']}: Your phone is connected for automated delivery SMS alerts!"
    res = send_sms_gateway(phone, msg, order_id=order['id'])
    if res.get('success'):
        flash("Test SMS sent successfully to %s via Android Airtel SIM Gateway!" % phone, "success")
    else:
        flash("SMS Gateway response: %s" % res.get('error', 'Failed to send SMS'), "error")
    return redirect(url_for('main.admin_order', order_id=order_id))


# =============================================================================== admin: customer master & mass messaging
@main_bp.route('/admin/customers')
@login_required
def admin_customers():
    q = request.args.get('q', '').strip()
    tier = request.args.get('tier', 'all').strip()
    sort = request.args.get('sort', 'orders_desc').strip()
    
    tier_filter = tier if tier in ('vip', 'repeat', 'single') else None
    customers = db.list_customer_master(search=q or None, tier=tier_filter, sort=sort)
    metrics = db.get_customer_metrics()
    
    sms_enabled = db.get_setting('sms_enabled', '0') == '1'
    wa_enabled = db.get_setting('whatsapp_enabled', '0') == '1'
    operator = db.get_setting('sms_sim_operator', 'Airtel')
    
    return render_template(
        'admin/customers.html',
        customers=customers,
        metrics=metrics,
        q=q,
        tier=tier,
        sort=sort,
        sms_enabled=sms_enabled,
        wa_enabled=wa_enabled,
        operator=operator
    )


@main_bp.route('/admin/customer/<mobile>/history')
@login_required
def admin_customer_history(mobile):
    history = db.get_customer_history(mobile)
    if not history:
        return jsonify({'success': False, 'error': 'Customer not found'}), 404
        
    serialized_orders = []
    for o in history['orders']:
        serialized_orders.append({
            'id': o['id'],
            'tracking_hash': o['tracking_hash'],
            'product_title': o['product_title'],
            'product_sku': o['product_sku'],
            'product_image': o['product_image'],
            'shoe_size': o['shoe_size'],
            'quantity': o['quantity'],
            'total_amount': o['total_amount'],
            'status': o['status'],
            'payment_method': o['payment_method'],
            'created_at': o['created_at'].strftime('%Y-%m-%d %H:%M') if hasattr(o['created_at'], 'strftime') else str(o['created_at']),
            'track_url': url_for('main.track_order', tracking_hash=o['tracking_hash']),
            'admin_order_url': url_for('main.admin_order', order_id=o['id'])
        })
        
    return jsonify({
        'success': True,
        'customer': {
            'customer_name': history['customer_name'],
            'mobile_number': history['mobile_number'],
            'email': history['email'],
            'whatsapp_number': history['whatsapp_number'],
            'division': history['division'],
            'district': history['district'],
            'full_address': history['full_address'],
            'total_orders': history['total_orders'],
            'completed_orders': history['completed_orders'],
            'total_spent': history['total_spent'],
            'tier': history['tier'],
            'tier_label': history['tier_label'],
            'first_purchase_date': str(history['first_purchase_date']),
            'last_purchase_date': str(history['last_purchase_date']),
            'orders': serialized_orders
        }
    })


@main_bp.route('/admin/customers/mass_message', methods=['POST'])
@login_required
def admin_customers_mass_message():
    channel = request.form.get('channel', 'sms').strip()
    target_tier = request.form.get('target_tier', 'all').strip()
    selected_mobiles_raw = request.form.getlist('selected_mobiles')
    message_tpl = request.form.get('message_template', '').strip()
    
    if not message_tpl:
        flash("Message content cannot be empty for mass sending.", "error")
        return redirect(url_for('main.admin_customers', tier=target_tier))
        
    if target_tier == 'selected' and selected_mobiles_raw:
        all_custs = db.list_customer_master(limit=500)
        selected_set = set(selected_mobiles_raw)
        recipients = [c for c in all_custs if c['mobile_number'] in selected_set]
    else:
        tier_filter = target_tier if target_tier in ('vip', 'repeat', 'single') else None
        recipients = db.list_customer_master(tier=tier_filter, limit=500)
        
    if not recipients:
        flash("No customers found for the selected recipient group.", "error")
        return redirect(url_for('main.admin_customers', tier=target_tier))
        
    sent_count = 0
    fail_count = 0
    
    for c in recipients:
        name = c.get('customer_name') or 'Valued Customer'
        msg = message_tpl.replace('{name}', name)
        msg = msg.replace('{shop_name}', Config.SHOP_NAME)
        msg = msg.replace('{last_product}', c.get('last_product_title') or 'shoes')
        msg = msg.replace('{total_orders}', str(c.get('total_orders') or 1))
        
        if channel == 'whatsapp':
            target_wa = c.get('whatsapp_number') or c.get('mobile_number')
            wa_to = format_wa_destination(target_wa)
            res = send_whatsapp_cloud_api(wa_to, msg)
            if res.get('success'):
                db.save_whatsapp_message(wa_to, 'outbound', msg, order_id=c.get('last_order_id'), customer_name=name)
                sent_count += 1
            else:
                fail_count += 1
        else:
            res = send_sms_gateway(c['mobile_number'], msg, order_id=c.get('last_order_id'))
            if res.get('success'):
                sent_count += 1
            else:
                fail_count += 1
                
        time.sleep(0.08)
        
    channel_name = "Android Airtel SIM SMS Gateway" if channel == 'sms' else "Meta WhatsApp Cloud API"
    if sent_count > 0:
        flash(f"Mass Broadcast Finished via {channel_name}: {sent_count} sent successfully, {fail_count} failed.", "success")
    else:
        flash(f"Mass Broadcast Result via {channel_name}: {sent_count} sent, {fail_count} failed. Please verify gateway settings.", "error")
        
    return redirect(url_for('main.admin_customers', tier=target_tier))




