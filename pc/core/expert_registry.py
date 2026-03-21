from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from pc.app_identity import resource_path


@dataclass(frozen=True)
class ExpertDefinition:
    code: str
    module: str
    display_name: str
    category: str
    description: str
    trigger_mode: str = "resident"
    stream_group: str = "default"
    knowledge_required: bool = False
    model_required: bool = False
    model_hint: str = ""
    knowledge_hint: str = ""
    media_types: Tuple[str, ...] = ("text",)
    voice_keywords: Tuple[str, ...] = ()

    @property
    def scope(self) -> str:
        return f"expert.{self.code}"

    @property
    def asset_slug(self) -> str:
        return self.code.replace(".", "__")


_EXPERTS: List[ExpertDefinition] = [
    ExpertDefinition(
        code="equipment_ocr_expert",
        module="pc.experts.equipment_ocr_expert",
        trigger_mode="voice",
        stream_group="ocr_video",
        display_name="设备 OCR 识别专家",
        category="仪表读数",
        description="识别实验仪表、屏幕或铭牌文字，输出读数与状态提示。",
        model_required=True,
        model_hint="建议导入 OCR 识别模型或设备读数数据集。",
        media_types=("image", "video", "text"),
        voice_keywords=("ocr", "读数", "识别设备", "仪表", "读一下", "屏幕内容", "标签内容"),
    ),
    ExpertDefinition(
        code="lab_qa_expert",
        module="pc.experts.lab_qa_expert",
        trigger_mode="voice",
        stream_group="voice_qa",
        display_name="实验室智能问答专家",
        category="问答检索",
        description="结合公共背景知识与实验问答知识库，回答实验流程、制度与历史问题。",
        knowledge_required=True,
        model_required=True,
        model_hint="建议配置本地或云端大模型。",
        knowledge_hint="建议导入实验室制度、SOP、操作手册和问答资料。",
        media_types=("audio", "video", "text"),
        voice_keywords=("问答", "什么", "为什么", "如何", "介绍", "说明", "系统状态", "帮我看"),
    ),
    ExpertDefinition(
        code="nanofluidics.microfluidic_contact_angle_expert",
        module="pc.experts.nanofluidics.microfluidic_contact_angle_expert",
        trigger_mode="voice",
        stream_group="nanofluidics_video",
        display_name="微流控接触角分析专家",
        category="微纳流体",
        description="分析液滴接触角与边界变化，辅助材料润湿性评估。",
        model_required=True,
        model_hint="建议导入接触角分析样本或标定模型。",
        media_types=("image", "video", "text"),
        voice_keywords=("接触角", "润湿", "液滴", "微流控", "微纳", "分析液滴"),
    ),
    ExpertDefinition(
        code="nanofluidics.nanofluidics_multimodel_expert",
        module="pc.experts.nanofluidics.nanofluidics_multimodel_expert",
        trigger_mode="voice",
        stream_group="nanofluidics_video",
        display_name="微纳流体多模态专家",
        category="微纳流体",
        description="对芯片流场、气泡和多物理量变化进行综合研判。",
        model_required=True,
        model_hint="建议导入微流控实验模型或标定参数。",
        media_types=("image", "video", "text"),
        voice_keywords=("微纳", "微流体", "芯片流场", "气泡", "多模态分析"),
    ),
    ExpertDefinition(
        code="safety.chem_safety_expert",
        module="pc.experts.safety.chem_safety_expert",
        trigger_mode="voice",
        stream_group="chem_video",
        display_name="危化品识别提醒专家",
        category="安全合规",
        description="识别危化品容器与标签，输出禁忌、风险和防护建议。",
        knowledge_required=True,
        model_required=True,
        model_hint="建议导入危化品识别模型或标签样本。",
        knowledge_hint="建议导入危化品台账、MSDS 与应急处置资料。",
        media_types=("image", "video", "text"),
        voice_keywords=("化学品", "危化品", "试剂", "药品", "瓶子里是什么", "识别这个化学品", "识别试剂"),
    ),
    ExpertDefinition(
        code="safety.equipment_operation_expert",
        module="pc.experts.safety.equipment_operation_expert",
        trigger_mode="resident",
        stream_group="safety_video",
        display_name="设备操作合规专家",
        category="安全合规",
        description="检查实验设备操作过程是否符合规范。",
        knowledge_required=True,
        model_required=True,
        model_hint="建议导入仪器操作样本、动作识别模型或设备知识文件。",
        knowledge_hint="建议导入设备 SOP、点检单和培训资料。",
        media_types=("video", "image", "text"),
    ),
    ExpertDefinition(
        code="safety.flame_fire_expert",
        module="pc.experts.safety.flame_fire_expert",
        trigger_mode="resident",
        stream_group="safety_video",
        display_name="明火与热源风险专家",
        category="安全合规",
        description="识别明火、热源和烟雾风险，给出处置提醒。",
        model_required=True,
        model_hint="建议导入火焰识别样本或热源检测模型。",
        media_types=("video", "image", "text"),
    ),
    ExpertDefinition(
        code="safety.general_safety_expert",
        module="pc.experts.safety.general_safety_expert",
        trigger_mode="resident",
        stream_group="safety_video",
        display_name="通用安全行为专家",
        category="安全合规",
        description="识别通用实验室违规行为，如分心、误操作和危险接近。",
        model_required=True,
        model_hint="建议导入实验室场景行为识别模型。",
        media_types=("video", "image", "text"),
    ),
    ExpertDefinition(
        code="safety.hand_pose_expert",
        module="pc.experts.safety.hand_pose_expert",
        trigger_mode="resident",
        stream_group="safety_video",
        display_name="手部姿态估计专家",
        category="动作识别",
        description="分析抓取、伸手和精细操作姿态。",
        model_required=True,
        model_hint="建议导入手势识别模型或姿态样本。",
        media_types=("video", "image", "text"),
    ),
    ExpertDefinition(
        code="safety.integrated_lab_safety_expert",
        module="pc.experts.safety.integrated_lab_safety_expert",
        trigger_mode="resident",
        stream_group="safety_video",
        display_name="综合实验室安全专家",
        category="安全合规",
        description="融合 PPE、热源、危化和行为信号，输出综合安全结论。",
        knowledge_required=True,
        model_required=True,
        model_hint="建议导入综合安全模型与规则包。",
        knowledge_hint="建议导入实验室制度、风险分级与应急预案。",
        media_types=("video", "image", "text"),
    ),
    ExpertDefinition(
        code="safety.ppe_expert",
        module="pc.experts.safety.ppe_expert",
        trigger_mode="resident",
        stream_group="safety_video",
        display_name="个体防护装备专家",
        category="安全合规",
        description="检查实验服、护目镜、口罩和手套穿戴情况。",
        model_required=True,
        model_hint="建议导入 PPE 检测模型或样本集。",
        media_types=("video", "image", "text"),
    ),
    ExpertDefinition(
        code="safety.spill_detection_expert",
        module="pc.experts.safety.spill_detection_expert",
        trigger_mode="resident",
        stream_group="safety_video",
        display_name="液体泄漏识别专家",
        category="安全合规",
        description="识别台面、地面液体泄漏与残留，给出清理与隔离建议。",
        model_required=True,
        model_hint="建议导入泄漏检测模型或异常样本。",
        media_types=("video", "image", "text"),
    ),
]

_BY_CODE: Dict[str, ExpertDefinition] = {item.code: item for item in _EXPERTS}
_BY_SCOPE: Dict[str, ExpertDefinition] = {item.scope: item for item in _EXPERTS}


def list_expert_definitions() -> List[ExpertDefinition]:
    return list(_EXPERTS)


def iter_expert_modules() -> Iterable[str]:
    for item in _EXPERTS:
        yield item.module


def get_expert_definition(code: str) -> ExpertDefinition | None:
    return _BY_CODE.get((code or "").strip())


def get_definition_by_scope(scope_name: str) -> ExpertDefinition | None:
    return _BY_SCOPE.get((scope_name or "").strip())


def known_scopes() -> List[str]:
    return [item.scope for item in _EXPERTS]


def scope_title(scope_name: str) -> str:
    scope = (scope_name or "common").strip() or "common"
    if scope == "common":
        return "公共背景知识库"
    definition = get_definition_by_scope(scope)
    if definition is not None:
        return f"{definition.display_name}知识库"
    if scope.startswith("expert."):
        return f"专家知识库 / {scope[len('expert.'):]}"
    return scope


def expert_assets_root() -> Path:
    root = Path(resource_path("pc/models/experts"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def expert_asset_dir(code: str) -> Path:
    definition = get_expert_definition(code)
    slug = definition.asset_slug if definition is not None else (code or "unknown").replace(".", "__")
    path = expert_assets_root() / slug
    path.mkdir(parents=True, exist_ok=True)
    return path
