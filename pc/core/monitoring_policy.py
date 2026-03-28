from __future__ import annotations


def should_speak_monitoring_result(event_name: str, result_text: str) -> bool:
    """仅对必须报警的监控结果自动播报。"""
    text = str(result_text or "").strip()
    if not text:
        return False

    normalized = text.replace(" ", "")
    event_label = str(event_name or "").strip()
    alarm_keywords = (
        "警报",
        "极度危险",
        "严重危险",
        "紧急",
        "应急",
        "立即停止",
        "立即撤离",
        "立即疏散",
        "立即上报",
        "火焰",
        "烟雾",
        "起火",
        "爆炸",
        "泄漏",
        "泄露",
        "中毒",
        "氢氟酸",
        "HF",
    )
    if any(keyword in normalized for keyword in alarm_keywords):
        return True
    if event_label in {"火焰识别", "烟雾识别", "危化品泄漏", "综合风险告警"}:
        return True
    return False
