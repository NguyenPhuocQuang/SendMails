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


def get_first_text(*values, default: str = "-") -> str:
    """Lay gia tri text dau tien khong rong."""

    for value in values:
        if value not in (None, ""):
            return format_mail_value(value)

    return default


def get_sensor_tag_id_text(sensor_config: dict):
    """Lay tag id tu sensor config de hien thi trong email."""

    for key in ("tag_id", "tagId", "TagId", "tag_ids", "tagIds", "TagIds"):
        value = sensor_config.get(key)
        if isinstance(value, list):
            tag_ids = [str(item).strip() for item in value if str(item).strip()]
            if tag_ids:
                return ", ".join(tag_ids)
            continue

        if value not in (None, ""):
            return value

    return None


def is_condition_sensor_config(sensor_config: dict) -> bool:
    """Nhan dien InstanceConfigJsonSensor schema moi."""

    return bool(sensor_config.get("condition") or sensor_config.get("alert_type") or get_sensor_tag_id_text(sensor_config))


def format_condition_text(sensor_config: dict) -> str:
    """Dinh dang condition trong schema moi de hien thi trong mail."""

    condition = sensor_config.get("condition") or {}
    if not isinstance(condition, dict):
        return "-"

    condition_type = str(condition.get("type") or "").strip().lower()
    operator = str(condition.get("operator") or "").strip().lower()
    params = condition.get("params") or {}

    if condition_type == "threshold":
        target = f"{format_operator_text(operator)} {format_mail_value(params.get('value'))}".strip()
    elif condition_type == "range":
        min_value = format_mail_value(params.get("min"))
        max_value = format_mail_value(params.get("max"))
        target = f"{format_operator_text(operator or 'outside')} {min_value} - {max_value}".strip()
    elif condition_type == "rate":
        target = (
            f"{format_operator_text(operator)} {format_mail_value(params.get('value'))} mỗi "
            f"{format_time_unit_text(params.get('unit'))}, trong "
            f"{format_mail_value(params.get('window'))} {format_mail_value(params.get('unit'))}"
        )
    elif condition_type == "change":
        target = f"{format_operator_text(operator)} {format_mail_value(params.get('percent'))}%"
    else:
        target = format_mail_value(params)

    return f"{format_condition_type_text(condition_type)}: {target}".strip()


def format_condition_type_text(condition_type) -> str:
    """Doi ma loai dieu kien thanh tieng Viet de doc trong email."""

    labels = {
        "threshold": "So sánh ngưỡng",
        "range": "Kiểm tra khoảng giá trị",
        "rate": "Tốc độ biến thiên",
        "change": "Biến động trung bình ngày",
    }
    normalized_type = str(condition_type or "").strip().lower()
    return labels.get(normalized_type, format_mail_value(condition_type))


def format_alert_type_text(alert_type) -> str:
    """Doi alert_type thanh nhan tieng Viet de hien thi."""

    formatted_type = format_condition_type_text(alert_type)
    return formatted_type if formatted_type != "-" else format_mail_value(alert_type)


def format_operator_text(operator) -> str:
    """Doi operator ky thuat thanh mo ta tieng Viet ngan gon."""

    labels = {
        "gt": "lớn hơn",
        "gte": "lớn hơn hoặc bằng",
        "lt": "nhỏ hơn",
        "lte": "nhỏ hơn hoặc bằng",
        "eq": "bằng",
        "ne": "khác",
        "neq": "khác",
        "inside": "nằm trong khoảng",
        "outside": "nằm ngoài khoảng",
        "increase": "tăng tối thiểu",
        "decrease": "giảm tối thiểu",
        "increase_pct": "tăng tối thiểu",
        "decrease_pct": "giảm tối thiểu",
        "change_pct": "thay đổi tối thiểu",
    }
    normalized_operator = str(operator or "").strip().lower()
    return labels.get(normalized_operator, format_mail_value(operator))


def format_status_text(status) -> str:
    """Doi ma trang thai thanh tieng Viet."""

    labels = {
        "VUOT_NGUONG": "Vượt ngưỡng",
        "OK": "Bình thường",
        "CHUA_CO_NGUONG": "Chưa có ngưỡng cảnh báo",
        "CHUA_CO_GIA_TRI_LIVE": "Chưa có giá trị hiện tại",
        "CHUA_DU_LIEU_PHAN_TICH": "Chưa đủ dữ liệu phân tích",
        "CHUA_DU_LIEU_TRUNG_BINH_NGAY": "Chưa đủ dữ liệu trung bình ngày",
        "CHUA_HO_TRO_DIEU_KIEN": "Chưa hỗ trợ điều kiện cảnh báo",
    }
    normalized_status = str(status or "").strip()
    return labels.get(normalized_status, format_mail_value(status))


def format_time_unit_text(unit) -> str:
    """Doi don vi thoi gian thanh tieng Viet."""

    labels = {
        "second": "giây",
        "seconds": "giây",
        "sec": "giây",
        "s": "giây",
        "minute": "phút",
        "minutes": "phút",
        "min": "phút",
        "m": "phút",
        "hour": "giờ",
        "hours": "giờ",
        "h": "giờ",
    }
    normalized_unit = str(unit or "").strip().lower()
    return labels.get(normalized_unit, format_mail_value(unit, "giây"))


def build_text_summary_lines(config: dict, sensor_config: dict) -> list[str]:
    """Tao cac dong thong tin canh bao cho text email."""

    if is_condition_sensor_config(sensor_config):
        return [
            f"- Tên cấu hình: {format_mail_value(config.get('Name'))}",
            f"- MachineId: {format_mail_value(config.get('MachineId'))}",
            f"- TagId trong sensor: {format_mail_value(get_sensor_tag_id_text(sensor_config))}",
            f"- Loại cảnh báo: {format_alert_type_text(sensor_config.get('alert_type'))}",
            f"- Điều kiện cảnh báo: {format_condition_text(sensor_config)}",
            f"- Sự cố ghi nhận: {format_mail_value(sensor_config.get('incident'))}",
            f"- Hướng xử lý cấu hình: {format_mail_value(sensor_config.get('solution'))}",
        ]

    return [
        f"- Tên cấu hình: {format_mail_value(config.get('Name'))}",
        f"- IP IO-Link: {format_mail_value(sensor_config.get('ip_iolink'))}",
        f"- Port: {format_mail_value(sensor_config.get('port'))}",
        f"- Chu kỳ kiểm tra: {format_mail_value(sensor_config.get('time_threshold'))} giây",
    ]


def build_html_summary_rows(config: dict, sensor_config: dict, report_time: str, exceeded_count: int) -> str:
    """Tao bang tom tat cho HTML email."""

    summary_items = [
        ("Tên cấu hình", config.get("Name")),
    ]

    if is_condition_sensor_config(sensor_config):
        summary_items.extend(
            [
                ("MachineId", config.get("MachineId")),
                ("TagId trong sensor", get_sensor_tag_id_text(sensor_config)),
                ("Loại cảnh báo", format_alert_type_text(sensor_config.get("alert_type"))),
                ("Điều kiện cảnh báo", format_condition_text(sensor_config)),
                ("Sự cố ghi nhận", sensor_config.get("incident")),
                ("Hướng xử lý cấu hình", sensor_config.get("solution")),
            ]
        )
    else:
        summary_items.extend(
            [
                ("IP IO-Link", sensor_config.get("ip_iolink")),
                ("Port", sensor_config.get("port")),
                ("Chu kỳ kiểm tra", f"{format_mail_value(sensor_config.get('time_threshold'))} giây"),
            ]
        )

    summary_items.extend(
        [
            ("Số thông số vượt ngưỡng", exceeded_count),
            ("Thời gian gửi báo cáo", report_time),
        ]
    )

    rows = []
    for index, (label, value) in enumerate(summary_items):
        border = "" if index == 0 else "border-top:1px solid #e5e7eb;"
        rows.append(
            "<tr>"
            f"<td style=\"padding:10px 12px;color:#6b7280;width:190px;{border}\">{escape_mail_html(label)}</td>"
            f"<td style=\"padding:10px 12px;font-weight:700;{border}\">{escape_mail_html(value)}</td>"
            "</tr>"
        )

    return "".join(rows)


def format_tag_condition(tag: dict) -> str:
    """Dinh dang condition cua tung tag."""

    condition_type = format_condition_type_text(tag.get("ConditionType"))
    operator = format_operator_text(tag.get("Operator"))
    if operator == "-":
        return condition_type

    return f"{condition_type} ({operator})"


def format_current_value_if_different(tag: dict) -> str:
    """Hien thi gia tri hien tai neu khac gia tri kiem tra."""

    if tag.get("ConditionType") == "change" and (
        tag.get("TodayAverage") is not None or tag.get("YesterdayAverage") is not None
    ):
        return (
            f"; trung bình hôm nay {format_metric_value(tag.get('TodayAverage'), tag.get('CurrentUnit'))}"
            f"; trung bình hôm trước {format_metric_value(tag.get('YesterdayAverage'), tag.get('BaselineUnit'))}"
        )

    if tag.get("CurrentValue") == tag.get("Value") and tag.get("CurrentUnit") == tag.get("Unit"):
        return ""

    return f"; giá trị hiện tại {format_metric_value(tag.get('CurrentValue'), tag.get('CurrentUnit'))}"


def format_change_average_context(tag: dict) -> str:
    """Tao ghi chu trung binh ngay cho condition change."""

    if tag.get("ConditionType") != "change":
        return ""
    if tag.get("TodayAverage") is None and tag.get("YesterdayAverage") is None:
        return ""

    return (
        f"Trung bình hôm nay: {format_metric_value(tag.get('TodayAverage'), tag.get('CurrentUnit'))}; "
        f"trung bình hôm trước: {format_metric_value(tag.get('YesterdayAverage'), tag.get('BaselineUnit'))}"
    )


def format_tag_text_detail(index: int, tag: dict) -> str:
    """Tao block chi tiet mot tag cho text email."""

    incident = get_first_text(tag.get("Incident"), default="-")
    solution = get_first_text(tag.get("Solution"), default="-")
    current_detail = format_current_value_if_different(tag).lstrip("; ").strip()
    current_line = ""
    if current_detail:
        current_line = f"\n   - {current_detail[:1].upper()}{current_detail[1:]}"

    return (
        f"{index}. {format_mail_value(tag.get('TagKey'))} - {format_mail_value(tag.get('TagName'))}\n"
        f"   - Trạng thái: {format_status_text(tag.get('Status'))}\n"
        f"   - Điều kiện: {format_tag_condition(tag)}\n"
        f"   - Giá trị kiểm tra: {format_metric_value(tag.get('Value'), tag.get('Unit'))}\n"
        f"   - Ngưỡng cảnh báo: {format_metric_value(tag.get('Threshold'), tag.get('Unit'))}\n"
        f"   - Thời điểm cập nhật: {format_mail_value(tag.get('LastUpdated'))}"
        f"{current_line}\n"
        f"   - Sự cố: {incident}\n"
        f"   - Hướng xử lý: {solution}"
    )


def get_overall_incident(config: dict, sensor_config: dict, exceeded_tags: list[dict]) -> str:
    """Lay mo ta su co uu tien tu tag, sau do den sensor config."""

    tag_incident = next((tag.get("Incident") for tag in exceeded_tags if tag.get("Incident")), None)
    return get_first_text(tag_incident, sensor_config.get("incident"), config.get("Name"), default="Thông số vượt ngưỡng")


def get_overall_solution(sensor_config: dict, exceeded_tags: list[dict]) -> str:
    """Lay huong xu ly uu tien tu tag, sau do den sensor config."""

    tag_solution = next((tag.get("Solution") for tag in exceeded_tags if tag.get("Solution")), None)
    return get_first_text(
        tag_solution,
        sensor_config.get("solution"),
        "Kiểm tra thiết bị/cảm biến, đối chiếu dữ liệu vận hành và xử lý theo quy trình bảo trì.",
    )


def build_email_subject(config: dict, exceeded_tags: list[dict]) -> str:
    """Tao subject canh bao ngan gon, ro muc dich bao cao."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    config_name = format_mail_value(config.get("Name"))
    sensor_label = format_mail_value(sensor_config.get("ip_iolink") or config.get("MachineId"))
    incident = sensor_config.get("incident")
    tag_count = len(exceeded_tags)

    if incident:
        return f"[CẢNH BÁO] {incident} - {config_name}"

    return f"[CẢNH BÁO] {tag_count} thông số vượt ngưỡng - {config_name} ({sensor_label})"


def build_email_body(config: dict, exceeded_tags: list[dict]) -> str:
    """Tao noi dung text fallback tu cau hinh sensor dang doc duoc."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    exceeded_lines = [
        format_tag_text_detail(index, tag)
        for index, tag in enumerate(exceeded_tags, start=1)
    ]
    summary_lines = build_text_summary_lines(config, sensor_config)
    incident = get_overall_incident(config, sensor_config, exceeded_tags)
    solution = get_overall_solution(sensor_config, exceeded_tags)
    return (
        "Kính gửi Anh/Chị,\n\n"
        "Hệ thống giám sát ghi nhận thiết bị có thông số vượt ngưỡng cảnh báo. "
        "Vui lòng kiểm tra thông tin bên dưới để xử lý kịp thời.\n\n"
        "TÓM TẮT CẢNH BÁO\n"
        f"- Sự cố chính: {incident}\n"
        f"{chr(10).join(summary_lines)}\n"
        f"- Số thông số vượt ngưỡng: {len(exceeded_tags)}\n"
        f"- Thời gian gửi báo cáo: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "CHI TIẾT THÔNG SỐ VƯỢT NGƯỠNG\n"
        f"{chr(10).join(exceeded_lines)}\n\n"
        "KIẾN NGHỊ XỬ LÝ\n"
        f"- {solution}\n"
        "- Theo dõi lại giá trị sau khi xử lý để bảo đảm cảnh báo đã trở về trạng thái an toàn.\n\n"
        "Trân trọng,\n"
        "Hệ thống giám sát tự động\n\n"
        "Email này được tạo tự động từ script send_mail.py."
    )


def build_email_html_body(config: dict, exceeded_tags: list[dict]) -> str:
    """Tao HTML email de hien thi chuyen nghiep hon trong Gmail/Outlook."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    report_time = time.strftime("%Y-%m-%d %H:%M:%S")
    summary_rows = build_html_summary_rows(config, sensor_config, report_time, len(exceeded_tags))
    incident = get_overall_incident(config, sensor_config, exceeded_tags)
    solution = get_overall_solution(sensor_config, exceeded_tags)
    config_name = format_mail_value(config.get("Name"))
    rows = []

    for index, tag in enumerate(exceeded_tags, start=1):
        change_average_context = format_change_average_context(tag)
        change_average_html = (
            f"<div style=\"font-size:12px;color:#6b7280;margin-top:4px;line-height:1.4;\">"
            f"{escape_mail_html(change_average_context)}</div>"
            if change_average_context
            else ""
        )
        current_context = format_current_value_if_different(tag).lstrip("; ").strip()
        current_html = (
            f"<div style=\"font-size:12px;color:#4b5563;margin-top:4px;line-height:1.4;\">"
            f"{escape_mail_html(current_context[:1].upper() + current_context[1:])}</div>"
            if current_context and tag.get("ConditionType") != "change"
            else ""
        )
        incident_html = (
            f"<div style=\"font-size:12px;color:#7f1d1d;margin-top:6px;line-height:1.45;\">"
            f"<strong>Sự cố:</strong> {escape_mail_html(tag.get('Incident'))}</div>"
            if tag.get("Incident")
            else ""
        )
        solution_html = (
            f"<div style=\"font-size:12px;color:#065f46;margin-top:4px;line-height:1.45;\">"
            f"<strong>Hướng xử lý:</strong> {escape_mail_html(tag.get('Solution'))}</div>"
            if tag.get("Solution")
            else ""
        )
        status_html = (
            f"<div style=\"font-size:12px;color:#991b1b;margin-top:5px;line-height:1.45;\">"
            f"<strong>Trạng thái:</strong> {escape_mail_html(format_status_text(tag.get('Status')))}</div>"
        )
        rows.append(
            "<tr>"
            f"<td style=\"padding:12px 10px;border-bottom:1px solid #e5e7eb;text-align:center;color:#6b7280;\">{index}</td>"
            f"<td style=\"padding:12px 10px;border-bottom:1px solid #e5e7eb;font-weight:700;color:#111827;\">"
            f"{escape_mail_html(tag.get('TagKey'))}</td>"
            f"<td style=\"padding:12px 10px;border-bottom:1px solid #e5e7eb;color:#374151;line-height:1.45;\">"
            f"<strong>{escape_mail_html(tag.get('TagName'))}</strong>"
            f"{status_html}{incident_html}{solution_html}{current_html}{change_average_html}</td>"
            f"<td style=\"padding:12px 10px;border-bottom:1px solid #e5e7eb;color:#374151;line-height:1.45;\">"
            f"{escape_mail_html(format_tag_condition(tag))}</td>"
            f"<td style=\"padding:12px 10px;border-bottom:1px solid #e5e7eb;color:#b91c1c;font-weight:800;white-space:nowrap;\">"
            f"{escape(format_metric_value(tag.get('Value'), tag.get('Unit')), quote=True)}</td>"
            f"<td style=\"padding:12px 10px;border-bottom:1px solid #e5e7eb;color:#374151;font-weight:700;white-space:nowrap;\">"
            f"{escape(format_metric_value(tag.get('Threshold'), tag.get('Unit')), quote=True)}</td>"
            f"<td style=\"padding:12px 10px;border-bottom:1px solid #e5e7eb;color:#6b7280;white-space:nowrap;\">"
            f"{escape_mail_html(tag.get('LastUpdated'))}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#eef2f7;font-family:Arial,Helvetica,sans-serif;color:#111827;">
    <div style="max-width:860px;margin:0 auto;padding:24px;">
      <div style="background:#ffffff;border:1px solid #dbe3ef;border-radius:8px;overflow:hidden;">
        <div style="background:#b91c1c;color:#ffffff;padding:20px 24px;">
          <div style="font-size:12px;text-transform:uppercase;font-weight:700;opacity:.92;">Báo cáo cảnh báo thiết bị</div>
          <div style="font-size:24px;font-weight:800;margin-top:6px;line-height:1.25;">Thông số vượt ngưỡng cảnh báo</div>
          <div style="font-size:14px;margin-top:8px;line-height:1.45;opacity:.95;">{escape_mail_html(config_name)}</div>
        </div>
        <div style="padding:24px;">
          <p style="margin:0 0 12px 0;font-size:15px;line-height:1.6;">Kính gửi Anh/Chị,</p>
          <p style="margin:0 0 18px 0;font-size:15px;line-height:1.6;color:#374151;">
            Hệ thống giám sát ghi nhận thiết bị có thông số vượt ngưỡng cảnh báo.
            Vui lòng kiểm tra thông tin bên dưới để xử lý kịp thời.
          </p>

          <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:14px 16px;margin-bottom:18px;">
            <div style="font-size:12px;text-transform:uppercase;font-weight:800;color:#991b1b;margin-bottom:6px;">Sự cố chính</div>
            <div style="font-size:16px;font-weight:800;color:#7f1d1d;line-height:1.45;">{escape_mail_html(incident)}</div>
          </div>

          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 20px 0;background:#f9fafb;border:1px solid #e5e7eb;">
            {summary_rows}
          </table>

          <div style="font-size:16px;font-weight:800;margin:0 0 10px 0;">Chi tiết thông số vượt ngưỡng</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #e5e7eb;margin-bottom:20px;">
            <thead>
              <tr style="background:#f9fafb;color:#374151;">
                <th align="center" style="padding:10px;border-bottom:1px solid #e5e7eb;font-size:12px;">STT</th>
                <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;font-size:12px;">Tag key</th>
                <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;font-size:12px;">Thông số / xử lý</th>
                <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;font-size:12px;">Điều kiện</th>
                <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;font-size:12px;">Giá trị</th>
                <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;font-size:12px;">Ngưỡng</th>
                <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;font-size:12px;">Cập nhật</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>

          <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:6px;padding:14px 16px;margin-bottom:18px;">
            <div style="font-weight:800;color:#065f46;margin-bottom:6px;">Kiến nghị xử lý</div>
            <div style="font-size:14px;line-height:1.6;color:#065f46;">
              {escape_mail_html(solution)}<br>
              Theo dõi lại giá trị sau khi xử lý để bảo đảm cảnh báo đã trở về trạng thái an toàn.
            </div>
          </div>

          <p style="margin:0;font-size:14px;line-height:1.6;">
            Trân trọng,<br>
            <strong>Hệ thống giám sát tự động</strong>
          </p>
        </div>
        <div style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:12px 22px;color:#6b7280;font-size:12px;">
          Email này được tạo tự động từ script send_mail.py. Vui lòng kiểm tra dữ liệu thực tế trước khi thao tác bảo trì.
        </div>
      </div>
    </div>
  </body>
</html>"""
