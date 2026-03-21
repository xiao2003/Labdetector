from __future__ import annotations

import time


def apply_policies_to_detections(
    frame,
    policies,
    detected_objects,
    boxes_dict,
    *,
    last_triggers=None,
    current_time=None,
):
    detected_set = set(detected_objects or [])
    detected_str = ",".join(sorted(detected_set))
    triggered_events = []
    current_time = float(current_time or time.time())
    trigger_cache = last_triggers if isinstance(last_triggers, dict) else {}

    for policy in policies or []:
        event_name = policy.get("event_name")
        targets = set(policy.get("trigger_classes", []))
        condition = policy.get("condition", "any")
        action = policy.get("action", "full_frame")
        cooldown = float(policy.get("cooldown", 5.0) or 5.0)

        if not event_name or not targets:
            continue
        if current_time - float(trigger_cache.get(event_name, 0.0) or 0.0) < cooldown:
            continue

        is_match = False
        if condition == "all" and targets.issubset(detected_set):
            is_match = True
        elif condition == "any" and not targets.isdisjoint(detected_set):
            is_match = True

        if not is_match:
            continue

        trigger_cache[event_name] = current_time
        if action == "crop_target":
            target_cls = list(targets.intersection(detected_set))[0]
            x1, y1, x2, y2 = boxes_dict[target_cls][0]
            h, w = frame.shape[:2]
            crop_img = frame[max(0, y1 - 20):min(h, y2 + 20), max(0, x1 - 20):min(w, x2 + 20)]
            triggered_events.append(
                (
                    event_name,
                    crop_img,
                    detected_str,
                    {
                        "expert_code": str(policy.get("expert_code", "") or ""),
                        "policy_name": str(policy.get("policy_name", event_name) or event_name),
                        "policy_action": action,
                    },
                )
            )
        else:
            triggered_events.append(
                (
                    event_name,
                    frame.copy(),
                    detected_str,
                    {
                        "expert_code": str(policy.get("expert_code", "") or ""),
                        "policy_name": str(policy.get("policy_name", event_name) or event_name),
                        "policy_action": action,
                    },
                )
            )

    return triggered_events
