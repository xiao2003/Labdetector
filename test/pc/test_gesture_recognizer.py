import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pc.experts.safety.hand_pose_expert import HandPoseExpert


def main() -> None:
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    result = HandPoseExpert().analyze(frame, {"event_name": "hand_pose_analysis"})
    print(result)
    try:
        parsed = json.loads(result)
        print("status:", parsed.get("hand_status"), "reason:", parsed.get("reason"))
    except Exception as exc:
        print("parse_failed:", exc)


if __name__ == "__main__":
    main()
