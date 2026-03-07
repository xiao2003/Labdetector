from typing import Dict, List

from pc.core.base_expert import BaseExpert
from pc.experts.nanofluidics.nanofluidics_models import run_nanofluidics_suite, run_nanomechanics_bubble_suite


class NanoFluidicsMultiModelExpert(BaseExpert):
    """微纳力学多模型专家（气泡追踪/接触线/钉扎 + 接触角/弯月面/粒子速度）。"""

    @property
    def expert_name(self) -> str:
        return "微纳力学多模型专家"

    @property
    def expert_version(self) -> str:
        return "2.6"

    def supported_events(self) -> List[str]:
        return [
            "接触角检测",
            "microfluidic_contact_angle",
            "微纳流体多模型巡检",
            "纳米力学气泡巡检",
            "电渗电泳气泡跟踪",
        ]

    def get_edge_policy(self) -> List[Dict]:
        return [
            {
                "event_name": "微纳流体多模型巡检",
                "trigger_classes": ["slide", "droplet", "chip"],
                "condition": "any",
                "action": "crop_target",
                "cooldown": 2.0,
            },
            {
                "event_name": "纳米力学气泡巡检",
                "trigger_classes": ["bubble", "capillary", "microchannel", "chip"],
                "condition": "any",
                "action": "crop_target",
                "cooldown": 1.0,
            },
        ]

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        if frame is None:
            return ""
        prev_frame = context.get("prev_frame")
        metrics = run_nanofluidics_suite(frame, prev_frame=prev_frame)
        bubble_metrics = run_nanomechanics_bubble_suite(frame, prev_frame=prev_frame)
        if not metrics and not bubble_metrics:
            return "微纳流体分析：当前帧特征不足，建议提升照明与对焦。"

        tips = []
        angle = metrics.get("contact_angle_deg")
        if angle is not None:
            low = float(context.get("angle_low", 60))
            high = float(context.get("angle_high", 110))
            if angle < low or angle > high:
                tips.append(f"接触角={angle:.1f}°超出[{low:.0f},{high:.0f}]°")
        curv = metrics.get("meniscus_curvature")
        if curv is not None and curv > float(context.get("curvature_high", 0.08)):
            tips.append(f"弯月面曲率偏大({curv:.4f})")
        vel = metrics.get("particle_velocity_px_per_frame")
        if vel is not None and vel > float(context.get("velocity_high", 10.0)):
            tips.append(f"粒子速度偏高({vel:.2f}px/frame)")

        if bubble_metrics:
            bubbles = bubble_metrics.get("bubbles", [])
            if isinstance(bubbles, list):
                for idx, bubble in enumerate(bubbles[:2], start=1):
                    speed = bubble.get("velocity_px_per_frame")
                    direction = bubble.get("direction_deg")
                    cang = bubble.get("contact_angle_deg")
                    if speed is not None and direction is not None:
                        tips.append(f"气泡{idx}速度={speed:.2f}px/frame 方向={direction:.1f}°")
                    if cang is not None:
                        tips.append(f"气泡{idx}接触角≈{cang:.1f}°")
                    if bubble.get("pinning_suspected"):
                        tips.append(f"气泡{idx}疑似接触线钉扎")

            if bubble_metrics.get("bubble_split_detected"):
                tips.append("检测到气泡分裂，已分别输出前两个子气泡参数")

        if tips:
            return "微纳力学研判：" + "；".join(tips)
        return "微纳力学指标正常。"
