from typing import Dict, List

from pcside.core.base_expert import BaseExpert
from pcside.experts.nanofluidics_models import run_nanofluidics_suite


class NanoFluidicsMultiModelExpert(BaseExpert):
    """微纳流体实验多模型专家（接触角/弯月面/粒子速度）。"""

    @property
    def expert_name(self) -> str:
        return "微纳流体多模型专家"

    @property
    def expert_version(self) -> str:
        return "2.6"

    def supported_events(self) -> List[str]:
        return ["接触角检测", "microfluidic_contact_angle", "微纳流体多模型巡检"]

    def get_edge_policy(self) -> List[Dict]:
        return [
            {
                "event_name": "微纳流体多模型巡检",
                "trigger_classes": ["slide", "droplet", "chip"],
                "condition": "any",
                "action": "crop_target",
                "cooldown": 2.0,
            }
        ]

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        if frame is None:
            return ""
        prev_frame = context.get("prev_frame")
        metrics = run_nanofluidics_suite(frame, prev_frame=prev_frame)
        if not metrics:
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

        if tips:
            return "微纳流体异常：" + "；".join(tips)
        return "微纳流体指标正常。"
