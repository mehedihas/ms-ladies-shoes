import os
import ssl
import smtplib
import logging
import threading
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from config import Config
import db

logger = logging.getLogger('mailer')
logger.setLevel(logging.INFO)


def _get_smtp_config():
    """Retrieves SMTP configuration, checking database settings first, then Config."""
    server = db.get_setting('smtp_server', Config.__dict__.get('SMTP_SERVER', 'smtp.gmail.com')).strip()
    port_val = db.get_setting('smtp_port', str(Config.__dict__.get('SMTP_PORT', 465))).strip()
    try:
        port = int(port_val)
    except (ValueError, TypeError):
        port = 465

    user = db.get_setting('smtp_user', Config.__dict__.get('SMTP_USER', 'msshoescol@gmail.com')).strip()
    raw_pass = db.get_setting('smtp_pass', Config.__dict__.get('SMTP_PASS', 'dgixyujdnocoxxgl')).strip()
    # Google App Passwords often have spaces; remove whitespace for reliable login
    password = raw_pass.replace(' ', '')

    sender_name = db.get_setting('smtp_sender_name', Config.__dict__.get('SMTP_SENDER_NAME', Config.SHOP_NAME)).strip()

    # Recipients
    recipients_str = db.get_setting(
        'order_notify_emails',
        ','.join(Config.__dict__.get('ORDER_NOTIFY_EMAILS', ['mehedi6674@gmail.com', 'siratunm@gmail.com']))
    )
    recipients = [e.strip() for e in recipients_str.split(',') if e.strip() and '@' in e]
    if not recipients:
        recipients = ['mehedi6674@gmail.com', 'siratunm@gmail.com']

    return {
        'server': server,
        'port': port,
        'user': user,
        'password': password,
        'sender_name': sender_name,
        'recipients': recipients,
    }


def send_email(subject, html_content, text_content=None, to_emails=None, cfg=None):
    """
    Sends an email using SMTP with SSL/TLS and automatic fallback.
    Returns True if sent successfully, False otherwise.
    """
    cfg = cfg or _get_smtp_config()
    recipients = to_emails or cfg['recipients']
    if not recipients:
        logger.warning("No recipient email specified for outgoing email: %s", subject)
        return False

    sender_email = cfg['user']
    sender_name = cfg['sender_name']
    password = cfg['password']
    server_host = cfg['server']
    primary_port = cfg['port']

    # Construct multipart alternative email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f'{sender_name} <{sender_email}>'
    msg['To'] = ', '.join(recipients)
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=sender_email.split('@')[-1] if '@' in sender_email else 'gmail.com')

    if text_content:
        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
    if html_content:
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    raw_msg = msg.as_string()

    # Strategy: Try primary port first. If it fails or times out, try alternate port (465 <-> 587)
    ports_to_try = [primary_port]
    alt_port = 587 if primary_port == 465 else 465
    if alt_port not in ports_to_try:
        ports_to_try.append(alt_port)

    last_error = None
    for port in ports_to_try:
        try:
            logger.info("Connecting to %s:%s for email '%s'...", server_host, port, subject)
            if port == 465:
                # SSL connection
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(server_host, port, context=ctx, timeout=15) as s:
                    s.login(sender_email, password)
                    s.sendmail(sender_email, recipients, raw_msg)
            else:
                # STARTTLS connection (usually 587)
                with smtplib.SMTP(server_host, port, timeout=15) as s:
                    s.ehlo()
                    ctx = ssl.create_default_context()
                    s.starttls(context=ctx)
                    s.ehlo()
                    s.login(sender_email, password)
                    s.sendmail(sender_email, recipients, raw_msg)

            logger.info("Email '%s' successfully delivered to %s via port %s", subject, recipients, port)
            return True
        except Exception as ex:
            last_error = ex
            logger.warning("Failed sending email via %s:%s: %s", server_host, port, ex)

    logger.error("All SMTP attempts failed for '%s'. Last error: %s", subject, last_error)
    return False


def _build_order_email_content(order):
    """Constructs HTML and plain text email notifications for a newly placed order."""
    oid = order['id']
    title = order.get('product_title') or 'Ladies Shoe'
    sku = order.get('product_sku') or 'N/A'
    size = order.get('shoe_size') or 'Standard'
    qty = order.get('quantity') or 1
    price = order.get('unit_price') or 0.0
    charge = order.get('delivery_charge') or 0.0
    total = order.get('total_amount') or (price * qty + charge)
    payment_method = (order.get('payment_method') or 'bkash').upper()

    name = order.get('customer_name') or 'Valued Customer'
    mobile = order.get('mobile_number') or ''
    wa = order.get('whatsapp_number') or mobile
    email = order.get('email') or 'Not provided'
    address = order.get('full_address') or order.get('road_house') or 'Bangladesh'
    division = order.get('division') or ''
    district = order.get('district') or ''
    notes = order.get('notes') or ''
    thash = order.get('tracking_hash') or ''

    # Time formatting in BST (UTC+6)
    bst = timezone(timedelta(hours=Config.TZ_OFFSET_HOURS))
    now_str = datetime.now(bst).strftime('%d %b %Y, %I:%M %p')

    # Links
    base_url = Config.SITE_URL if Config.SITE_URL else ''
    track_url = f"{base_url}/track/{thash}" if base_url else f"/track/{thash}"
    admin_order_url = f"{base_url}/admin/order/{oid}" if base_url else f"/admin/order/{oid}"
    wa_digits = ''.join(c for c in wa if c.isdigit())
    if wa_digits.startswith('0'):
        wa_digits = '88' + wa_digits
    elif not wa_digits.startswith('88') and len(wa_digits) == 10:
        wa_digits = '880' + wa_digits
    wa_chat_link = f"https://wa.me/{wa_digits}?text=Hello%20{name},%20we%20received%20your%20order%20#{oid}%20at%20{Config.SHOP_NAME}."

    # Product image absolute url if available
    img_rel = order.get('product_image')
    img_html = ""
    if img_rel and base_url:
        img_url = f"{base_url}/static/{img_rel}"
        img_html = f'''<div style="text-align:center; margin-bottom:16px;">
            <img src="{img_url}" alt="{title}" style="max-width:220px; max-height:220px; border-radius:10px; border:1px solid #E2E8F0; object-fit:contain; background:#F8FAFC;">
        </div>'''

    subject = f"👠 [New Order #{oid}] {name} ordered {title} - ৳{total:.0f}"

    # Plain text version
    text_content = f"""======================================================
NEW ORDER ALERT #{oid} - {Config.SHOP_NAME}
======================================================
Order Placed: {now_str} (BST)
Total Amount: ৳{total:.0f} ({payment_method})

CUSTOMER DETAILS:
------------------------------------------------------
Name: {name}
Mobile: {mobile}
WhatsApp: {wa}
Email: {email}
Address: {address}
Region: {division} {f'({district})' if district else ''}
Special Notes: {notes if notes else 'None'}

PRODUCT DETAILS:
------------------------------------------------------
Item: {title}
SKU: {sku}
Size: {size}
Quantity: {qty}
Unit Price: ৳{price:.0f}
Delivery Charge: ৳{charge:.0f}
Grand Total: ৳{total:.0f}
Payment Method: {payment_method}

QUICK ACTION LINKS:
------------------------------------------------------
Admin Order Management: {admin_order_url}
Customer WhatsApp Chat: {wa_chat_link}
Customer Tracking Page: {track_url}

======================================================
MS Ladies Shoes Collection Automated Order System
"""

    # Rich responsive HTML version
    payment_badge_color = "#E2136E" if payment_method == 'BKASH' else "#D97706"
    payment_badge_bg = "#FCE7F3" if payment_method == 'BKASH' else "#FEF3C7"
    payment_label = "bKash Send Money" if payment_method == 'BKASH' else "Cash on Delivery (COD)"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>New Order #{oid}</title>
</head>
<body style="margin:0; padding:0; background-color:#F1F5F9; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color:#1E293B;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F1F5F9; padding:24px 12px;">
    <tr>
      <td align="center">
        <!-- Main Email Container -->
        <table role="presentation" width="100%" style="max-width:600px; background:#FFFFFF; border-radius:16px; overflow:hidden; box-shadow:0 8px 24px rgba(15,23,42,0.08); border:1px solid #E2E8F0;" cellpadding="0" cellspacing="0">
          
          <!-- Header Banner -->
          <tr>
            <td style="background:linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding:28px 24px; text-align:center;">
              <div style="font-size:26px; font-weight:800; color:#FFFFFF; letter-spacing:0.5px; margin-bottom:6px;">
                👠 {Config.SHOP_NAME}
              </div>
              <div style="display:inline-block; background:rgba(252,99,10,0.2); border:1px solid #FC630A; color:#FF8A4C; font-size:12px; font-weight:800; letter-spacing:1px; padding:4px 14px; border-radius:20px; text-transform:uppercase;">
                🔥 New Order Received
              </div>
              <div style="margin-top:12px; color:#94A3B8; font-size:13px;">
                Order ID: <b style="color:#FFFFFF;">#{oid}</b> &middot; Placed: {now_str}
              </div>
            </td>
          </tr>

          <!-- Summary Highlights Bar -->
          <tr>
            <td style="background:#F8FAFC; border-bottom:1px solid #E2E8F0; padding:16px 24px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="left">
                    <span style="font-size:12px; color:#64748B; font-weight:600; text-transform:uppercase;">Payment:</span><br>
                    <span style="display:inline-block; margin-top:4px; font-size:12px; font-weight:800; color:{payment_badge_color}; background:{payment_badge_bg}; padding:3px 10px; border-radius:12px;">
                      {payment_label}
                    </span>
                  </td>
                  <td align="right">
                    <span style="font-size:12px; color:#64748B; font-weight:600; text-transform:uppercase;">Total Amount:</span><br>
                    <span style="font-size:22px; font-weight:900; color:#0F172A;">৳{total:.0f}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body Content -->
          <tr>
            <td style="padding:24px;">
              
              {img_html}

              <!-- Section: Product Details -->
              <div style="background:#F8FAFC; border-radius:12px; padding:16px 18px; margin-bottom:20px; border:1px solid #E2E8F0;">
                <div style="font-size:14px; font-weight:800; color:#0F172A; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; border-bottom:2px solid #E2E8F0; padding-bottom:8px;">
                  🛍️ Product Details
                </div>
                <table width="100%" cellpadding="4" cellspacing="0" style="font-size:14px;">
                  <tr>
                    <td style="color:#64748B; width:35%;">Product Title:</td>
                    <td style="font-weight:700; color:#0F172A;">{title}</td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">SKU:</td>
                    <td style="font-weight:700; color:#0F172A;"><code>{sku}</code></td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Shoe Size:</td>
                    <td style="font-weight:800; color:#FC630A; font-size:15px;">Size {size}</td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Quantity:</td>
                    <td style="font-weight:700; color:#0F172A;">{qty} pair</td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Unit Price:</td>
                    <td style="font-weight:700; color:#0F172A;">৳{price:.0f}</td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Delivery Charge:</td>
                    <td style="font-weight:700; color:{'#16A34A' if charge == 0 else '#0F172A'};">
                      {'FREE' if charge == 0 else f'৳{charge:.0f}'}
                    </td>
                  </tr>
                  <tr style="border-top:1px dashed #CBD5E1;">
                    <td style="font-weight:800; color:#0F172A; padding-top:8px;">Grand Total:</td>
                    <td style="font-weight:900; color:#FC630A; font-size:18px; padding-top:8px;">৳{total:.0f}</td>
                  </tr>
                </table>
              </div>

              <!-- Section: Customer Details -->
              <div style="background:#F8FAFC; border-radius:12px; padding:16px 18px; margin-bottom:24px; border:1px solid #E2E8F0;">
                <div style="font-size:14px; font-weight:800; color:#0F172A; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; border-bottom:2px solid #E2E8F0; padding-bottom:8px;">
                  👤 Customer & Delivery Information
                </div>
                <table width="100%" cellpadding="4" cellspacing="0" style="font-size:14px;">
                  <tr>
                    <td style="color:#64748B; width:35%;">Customer Name:</td>
                    <td style="font-weight:700; color:#0F172A;">{name}</td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Mobile Number:</td>
                    <td style="font-weight:700;">
                      <a href="tel:{mobile}" style="color:#0284C7; text-decoration:none;">📞 {mobile}</a>
                    </td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">WhatsApp:</td>
                    <td style="font-weight:700;">
                      <a href="{wa_chat_link}" target="_blank" style="color:#16A34A; text-decoration:none; font-weight:800;">
                        💬 {wa} (Click to Chat)
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Email:</td>
                    <td style="color:#0F172A;">{email}</td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Delivery Address:</td>
                    <td style="font-weight:600; color:#0F172A;">{address}</td>
                  </tr>
                  <tr>
                    <td style="color:#64748B;">Division & District:</td>
                    <td style="font-weight:600; color:#0F172A;">{division} {f'({district})' if district else ''}</td>
                  </tr>
                  {f'<tr><td style="color:#64748B;">Customer Note:</td><td style="font-style:italic; color:#D97706;">"{notes}"</td></tr>' if notes else ''}
                </table>
              </div>

              <!-- Quick Action Buttons -->
              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
                <tr>
                  <td align="center" style="padding-bottom:10px;">
                    <a href="{admin_order_url}" target="_blank" style="display:block; width:90%; background:linear-gradient(135deg, #FC630A 0%, #EA580C 100%); color:#FFFFFF; text-decoration:none; font-weight:800; font-size:15px; padding:14px 20px; border-radius:10px; text-align:center; box-shadow:0 4px 12px rgba(252,99,10,0.35);">
                      ⚡ Manage Order #{oid} in Admin Panel
                    </a>
                  </td>
                </tr>
                <tr>
                  <td align="center">
                    <table width="90%" cellpadding="0" cellspacing="0">
                      <tr>
                        <td width="48%" align="center">
                          <a href="{wa_chat_link}" target="_blank" style="display:block; background:#16A34A; color:#FFFFFF; text-decoration:none; font-weight:700; font-size:13px; padding:10px 14px; border-radius:8px; text-align:center;">
                            💬 Open WhatsApp
                          </a>
                        </td>
                        <td width="4%"></td>
                        <td width="48%" align="center">
                          <a href="{track_url}" target="_blank" style="display:block; background:#0F172A; color:#FFFFFF; text-decoration:none; font-weight:700; font-size:13px; padding:10px 14px; border-radius:8px; text-align:center;">
                            📍 Track Order Link
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#F8FAFC; border-top:1px solid #E2E8F0; padding:16px 24px; text-align:center; color:#94A3B8; font-size:12px;">
              This notification was generated automatically by <b>{Config.SHOP_NAME}</b>.<br>
              Order Tracking Hash: <code>{thash}</code>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return subject, html_content, text_content


def notify_new_order(order_or_id, async_send=True):
    """
    Sends email notification to the shop owners when a new order is placed.
    Accepts either an order dict or an order ID.
    If async_send=True, sends in a background daemon thread so checkout is never delayed.
    """
    if isinstance(order_or_id, (int, str)):
        order = db.get_order(int(order_or_id))
    else:
        order = order_or_id

    if not order:
        logger.error("Cannot send order notification: Order %s not found", order_or_id)
        return False

    def _worker():
        try:
            subject, html, text = _build_order_email_content(order)
            cfg = _get_smtp_config()
            logger.info("Sending new order notification for #%s to %s", order['id'], cfg['recipients'])
            send_email(subject, html, text, to_emails=cfg['recipients'], cfg=cfg)
        except Exception as ex:
            logger.exception("Unexpected error sending new order notification for #%s: %s", order.get('id'), ex)

    if async_send:
        t = threading.Thread(target=_worker, name=f"order-mail-{order.get('id')}", daemon=True)
        t.start()
        return True
    else:
        _worker()
        return True

