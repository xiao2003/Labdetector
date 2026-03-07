from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_RULE_PATH = Path(__file__).with_name("risk_rules.json")


class RiskRuleBook:
    def __init__(self, rule_path: Path | None = None) -> None:
        self.rule_path = rule_path or _RULE_PATH
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        if not self.rule_path.exists():
            return {"rules": [], "thresholds": {"high": 60, "medium": 30}}
        return json.loads(self.rule_path.read_text(encoding="utf-8-sig"))

    def evaluate(self, semantics: Dict[str, Any]) -> Dict[str, Any]:
        score = 0
        reasons: List[str] = []
        for rule in self.rules.get("rules", []):
            if self._match_rule(rule, semantics):
                score += int(rule.get("score", 0))
                reason = str(rule.get("reason") or "").strip()
                if reason:
                    reasons.append(reason)
        thresholds = self.rules.get("thresholds", {})
        high = int(thresholds.get("high", 60))
        medium = int(thresholds.get("medium", 30))
        if score >= high:
            level = "high"
        elif score >= medium:
            level = "medium"
        else:
            level = "low"
        return {"score": score, "risk_level": level, "reasons": reasons}

    @staticmethod
    def _match_rule(rule: Dict[str, Any], semantics: Dict[str, Any]) -> bool:
        conditions = rule.get("all") or []
        for condition in conditions:
            field = str(condition.get("field") or "")
            expected = condition.get("equals")
            contains = condition.get("contains")
            value = semantics.get(field)
            if contains is not None:
                if isinstance(value, list):
                    if contains not in value:
                        return False
                elif contains not in str(value):
                    return False
            elif value != expected:
                return False
        return True


risk_rulebook = RiskRuleBook()

