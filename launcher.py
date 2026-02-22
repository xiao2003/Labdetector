#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import logging
import signal
import importlib.util

# 配置基本日志
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')


def setup_project_path():
    """设置项目路径，确保可以正确导入所有模块"""
    # 获取当前文件的目录（launcher.py所在目录）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logging.info(f"当前工作目录: {current_dir}")

    # 获取项目根目录
    project_root = current_dir
    logging.info(f"项目根目录: {project_root}")

    # 确保项目根目录在sys.path中
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        logging.info(f"已添加项目根目录到sys.path: {project_root}")

    # 检查必要的目录是否存在
    pcside_dir = os.path.join(project_root, '')
    core_dir = os.path.join(project_root, 'pcside/core')

    if not os.path.exists(pcside_dir):
        logging.error(f"错误：缺少pcside目录: {pcside_dir}")
        return False

    if not os.path.exists(core_dir):
        logging.error(f"错误：缺少core目录: {core_dir}")
        return False

    # 检查__init__.py文件
    for directory in [pcside_dir, core_dir]:
        init_file = os.path.join(directory, 'pcside/__init__.py')
        if not os.path.exists(init_file):
            logging.warning(f"警告：缺少{init_file}，创建空文件")
            try:
                with open(init_file, 'w') as f:
                    f.write('# Project package initialization\n')
            except Exception as e:
                logging.error(f"无法创建__init__.py: {str(e)}")

    return True


def import_main_module():
    """安全导入main模块，处理各种可能的导入路径问题"""
    project_root = os.path.dirname(os.path.abspath(__file__))
    pcside_path = os.path.join(project_root, '')

    # 尝试1：直接导入
    try:
        from pcside.main import main
        if callable(main):
            return main
    except (ImportError, AttributeError) as e:
        logging.debug(f"直接导入失败: {str(e)}")

    # 尝试2：通过sys.path导入
    if pcside_path not in sys.path:
        sys.path.insert(0, pcside_path)

    try:
        from pcside.main import main
        if callable(main):
            return main
    except (ImportError, AttributeError) as e:
        logging.debug(f"sys.path导入失败: {str(e)}")

    # 尝试3：使用importlib
    main_module_path = os.path.join(pcside_path, 'pcside/main.py')
    if os.path.exists(main_module_path):
        try:
            spec = importlib.util.spec_from_file_location("main", main_module_path)
            main_module = importlib.util.module_from_spec(spec)
            sys.modules["main"] = main_module
            spec.loader.exec_module(main_module)
            if hasattr(main_module, 'main') and callable(main_module.main):
                return main_module.main
        except Exception as e:
            logging.debug(f"importlib导入失败: {str(e)}")

    # 尝试4：相对导入
    try:
        from pcside.main import main
        if callable(main):
            return main
    except (ImportError, AttributeError, ValueError) as e:
        logging.debug(f"相对导入失败: {str(e)}")

    return None


def signal_handler(sig, frame):
    """处理Ctrl+C信号"""
    # 明确声明我们使用这些参数
    _ = sig
    _ = frame
    logging.info("用户退出")
    sys.exit(0)


def main():
    """主函数"""
    logging.info("===== 启动实验室检测系统 =====")

    # 设置项目路径
    if not setup_project_path():
        logging.error("无法设置项目路径，退出")
        return 1

    # 导入main模块
    main_function = import_main_module()

    if main_function is None:
        logging.error("无法找到可调用的main函数")
        # 尝试直接运行 main.py
        main_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '', 'pcside/main.py')
        if os.path.exists(main_path):
            logging.info(f"尝试直接运行 {main_path}")
            try:
                os.execv(sys.executable, [sys.executable, main_path] + sys.argv[1:])
            except Exception as e:
                logging.error(f"执行 main.py 失败: {str(e)}")
                return 1
        else:
            logging.error(f"找不到 main.py: {main_path}")
            return 1

    logging.info("成功获取main函数")

    try:
        # 运行主程序
        return main_function()
    except Exception as e:
        logging.error(f"程序运行异常: {str(e)}")
        return 1


if __name__ == "__main__":
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)

    # 运行主函数
    exit_code = main()
    sys.exit(exit_code)