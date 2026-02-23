#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launcher.py - 极简项目启动器 (含预加载提示与纯净输出优化)
"""
import sys
import os
import logging

# ==========================================
# ★ 核心优化 1：在所有模块导入前，全局屏蔽啰嗦的底层日志
# ==========================================
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"  # 屏蔽 BertModel 的加载表格
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# 进一步压制第三方库的警告
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


def main():
    # ==========================================
    # ★ 核心优化 2：在执行耗时的 Import 之前，先给用户展示界面
    # ==========================================
    print("=" * 60)
    print("[INFO] 正在启动 LabDetector 实验室多模态管家...")
    print("[INFO] 正在将 RAG 知识库与本地向量模型载入内存...")
    print("[INFO] 这通常需要十几秒钟，请稍候...")
    print("=" * 60)

    # 动态将项目根目录加入环境变量
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        # 当执行下面这句 import 时，系统才会开始真正的耗时卡顿
        from pcside.main import main as pcside_main
        pcside_main()
    except Exception as e:
        print(f"\n[ERROR] 启动失败: {e}")
        print("请确保已在项目根目录运行过: pip install -e .")


if __name__ == "__main__":
    main()