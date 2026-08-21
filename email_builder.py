from __future__ import annotations

import time
from html import escape


def format_mail_value(value, default: str = "-") -> str:
    """Chuyen gia tri hien thi trong email ve dang ngan gon, de doc."""

    if value in (None, ""):
        return default

    if isinstance(value, float):
        return f"{value:g}"

    return str(value)


def format_metric_value(value, unit) -> str:
    """Dinh dang gia tri do kem don vi."""

    formatted_value = format_mail_value(value)
    unit = str(unit or "").strip()

    if formatted_value == "-":
        return formatted_value

    return f"{formatted_value} {unit}".strip()


def escape_mail_html(value) -> str:
    """Escape gia tri dong de chen vao HTML email."""

    return escape(format_mail_value(value), quote=True)


def build_email_subject(config: dict, exceeded_tags: list[dict]) -> str:
    """Tao subject canh bao ngan gon, ro muc dich bao cao."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    config_name = format_mail_value(config.get("Name"))
    ip_iolink = format_mail_value(sensor_config.get("ip_iolink"))
    tag_count = len(exceeded_tags)

    return f"[CANH BAO] {tag_count} thong so vuot nguong - {config_name} ({ip_iolink})"


def build_email_body(config: dict, exceeded_tags: list[dict]) -> str:
    """Tao noi dung text fallback tu cau hinh sensor dang doc duoc."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    exceeded_lines = []

    for index, tag in enumerate(exceeded_tags, start=1):
        exceeded_lines.append(
            f"{index}. {tag['TagKey']} ({tag['TagName']}): "
            f"gia tri hien tai {format_metric_value(tag.get('Value'), tag.get('Unit'))}; "
            f"nguong cai dat {format_metric_value(tag.get('Threshold'), tag.get('Unit'))}; "
            f"cap nhat luc {format_mail_value(tag.get('LastUpdated'))}"
        )

    return (
        "Kinh gui Anh/Chi,\n\n"
        "He thong giam sat ghi nhan mot hoac nhieu thong so cua thiet bi dang vuot "
        "nguong cai dat. Kinh de nghi Anh/Chi xem thong tin duoi day va chi dao xu ly.\n\n"
        "THONG TIN CANH BAO\n"
        f"- Ten cau hinh: {format_mail_value(config.get('Name'))}\n"
        f"- IP IO-Link: {format_mail_value(sensor_config.get('ip_iolink'))}\n"
        f"- Port: {format_mail_value(sensor_config.get('port'))}\n"
        f"- Chu ky/nguong thoi gian: {format_mail_value(sensor_config.get('time_threshold'))} giay\n"
        f"- So thong so vuot nguong: {len(exceeded_tags)}\n"
        f"- Thoi gian gui bao cao: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "CHI TIET THONG SO VUOT NGUONG\n"
        f"{chr(10).join(exceeded_lines)}\n\n"
        "KIEN NGHI XU LY\n"
        "- Kiem tra tinh trang thiet bi/cam bien va cac dieu kien van hanh lien quan.\n"
        "- Xu ly theo quy trinh bao tri neu gia tri tiep tuc duy tri tren nguong.\n\n"
        "Tran trong,\n"
        "He thong giam sat tu dong\n\n"
        "Email nay duoc tao tu script send_mail.py."
    )


def build_email_html_body(config: dict, exceeded_tags: list[dict]) -> str:
    """Tao HTML email de hien thi chuyen nghiep hon trong Gmail/Outlook."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    report_time = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = []

    for index, tag in enumerate(exceeded_tags, start=1):
        rows.append(
            "<tr>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:center;\">{index}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;font-weight:600;color:#111827;\">"
            f"{escape_mail_html(tag.get('TagKey'))}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#374151;\">"
            f"{escape_mail_html(tag.get('TagName'))}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#b91c1c;font-weight:700;\">"
            f"{escape(format_metric_value(tag.get('Value'), tag.get('Unit')), quote=True)}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#374151;\">"
            f"{escape(format_metric_value(tag.get('Threshold'), tag.get('Unit')), quote=True)}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;\">"
            f"{escape_mail_html(tag.get('LastUpdated'))}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#111827;">
    <div style="max-width:760px;margin:0 auto;padding:24px;">
      <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
        <div style="background:#991b1b;color:#ffffff;padding:18px 22px;">
          <div style="font-size:13px;letter-spacing:.4px;text-transform:uppercase;font-weight:700;">Bao cao canh bao thiet bi</div>
          <div style="font-size:22px;font-weight:700;margin-top:6px;">Thong so vuot nguong cai dat</div>
        </div>
        <div style="padding:22px;">
          <p style="margin:0 0 12px 0;font-size:15px;line-height:1.6;">Kinh gui Anh/Chi,</p>
          <p style="margin:0 0 18px 0;font-size:15px;line-height:1.6;">
            He thong giam sat ghi nhan thiet bi co thong so dang vuot nguong cai dat.
            Kinh de nghi Anh/Chi xem thong tin duoi day va chi dao xu ly kip thoi.
          </p>

          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 20px 0;background:#f9fafb;border:1px solid #e5e7eb;">
            <tr>
              <td style="padding:10px 12px;color:#6b7280;width:190px;">Ten cau hinh</td>
              <td style="padding:10px 12px;font-weight:700;">{escape_mail_html(config.get('Name'))}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;color:#6b7280;border-top:1px solid #e5e7eb;">IP IO-Link</td>
              <td style="padding:10px 12px;border-top:1px solid #e5e7eb;">{escape_mail_html(sensor_config.get('ip_iolink'))}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;color:#6b7280;border-top:1px solid #e5e7eb;">Port</td>
              <td style="padding:10px 12px;border-top:1px solid #e5e7eb;">{escape_mail_html(sensor_config.get('port'))}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;color:#6b7280;border-top:1px solid #e5e7eb;">Chu ky/nguong thoi gian</td>
              <td style="padding:10px 12px;border-top:1px solid #e5e7eb;">{escape_mail_html(sensor_config.get('time_threshold'))} giay</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;color:#6b7280;border-top:1px solid #e5e7eb;">So thong so vuot nguong</td>
              <td style="padding:10px 12px;border-top:1px solid #e5e7eb;color:#b91c1c;font-weight:700;">{len(exceeded_tags)}</td>
            </tr>
            <tr>
              <td style="padding:10px 12px;color:#6b7280;border-top:1px solid #e5e7eb;">Thoi gian gui bao cao</td>
              <td style="padding:10px 12px;border-top:1px solid #e5e7eb;">{escape(report_time, quote=True)}</td>
            </tr>
          </table>

          <div style="font-size:16px;font-weight:700;margin:0 0 10px 0;">Chi tiet thong so vuot nguong</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #e5e7eb;margin-bottom:20px;">
            <thead>
              <tr style="background:#f9fafb;color:#374151;">
                <th align="center" style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">STT</th>
                <th align="left" style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">Tag key</th>
                <th align="left" style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">Ten thong so</th>
                <th align="left" style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">Gia tri hien tai</th>
                <th align="left" style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">Nguong cai dat</th>
                <th align="left" style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">Cap nhat luc</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>

          <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:14px 16px;margin-bottom:18px;">
            <div style="font-weight:700;color:#9a3412;margin-bottom:6px;">Kien nghi xu ly</div>
            <div style="font-size:14px;line-height:1.6;color:#7c2d12;">
              Vui long kiem tra tinh trang thiet bi/cam bien va cac dieu kien van hanh lien quan.
              Neu gia tri tiep tuc duy tri tren nguong, can xu ly theo quy trinh bao tri.
            </div>
          </div>

          <p style="margin:0;font-size:14px;line-height:1.6;">
            Tran trong,<br>
            <strong>He thong giam sat tu dong</strong>
          </p>
        </div>
        <div style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:12px 22px;color:#6b7280;font-size:12px;">
          Email nay duoc tao tu script send_mail.py.
        </div>
      </div>
    </div>
  </body>
</html>"""
