#!/usr/bin/env python3
"""解析策略清单与删除（订阅配置页「未使用的策略」板块使用）

- `inventory(used_names)`：把已注册策略分成「有订阅匹配」与「没有订阅匹配」两组，
  并标出纯结构型策略（detect 只看页面结构，可能仍在服务「按格式」的源）。
- `delete_strategies(names, used_names)`：删除策略源文件，并从 strategies/__init__.py
  去掉对应导入。删除后**必须重启服务**——Python 常驻进程不会重新扫描 strategies 包。

只动 src/strategies/ 下的文件，删文件前先在 __init__.py 里摘掉导入，
写 __init__.py 失败或删文件失败都会回滚，避免包导入直接坏掉。
"""

import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies import _STRATEGIES, strategy_domains  # noqa: E402

STRATEGIES_DIR = Path(__file__).resolve().parent.parent / "strategies"
INIT_PATH = STRATEGIES_DIR / "__init__.py"


def _module_name(strategy):
    return strategy.__module__.rsplit(".", 1)[-1]


def _file_path(strategy):
    try:
        return Path(inspect.getsourcefile(strategy)).resolve()
    except (OSError, TypeError):
        return None


def _is_structural(strategy):
    """detect() 不依赖域名、也不看文件名提示 → 纯按页面结构识别

    这类策略（如 Hexo博客）不会被「订阅 → 策略」的近似匹配命中，
    但转换时仍可能命中「按格式」的源，删除后这些源会转换失败。
    """
    if strategy_domains(strategy):
        return False
    try:
        source = inspect.getsource(strategy.detect)
    except (OSError, TypeError):
        return False
    # 去掉 def 签名（可能跨行），只看函数体
    match = re.search(r"\)\s*:\s*\n", source)
    body = source[match.end():] if match else source
    return "filename_hint" not in body


def inventory(used_names):
    """返回 (used, unused) 两个列表，供配置页渲染

    used_names: 当前有订阅匹配到的策略名集合
    """
    used, unused = [], []
    for strategy in _STRATEGIES:
        path = _file_path(strategy)
        # 源文件已被删除（等待重启）的策略不再列出
        if path is None or not path.exists():
            continue
        item = {
            "name": strategy.name,
            "module": _module_name(strategy),
            "file": path.name if path else "",
            "structural": _is_structural(strategy),
        }
        (used if strategy.name in used_names else unused).append(item)
    return used, unused


def _drop_import_line(text, module):
    """从 __init__.py 文本里删掉 `from . import <module>` 这一行"""
    lines = text.splitlines(keepends=True)
    kept = [line for line in lines
            if line.strip() not in (f"from . import {module}",)]
    return "".join(kept) if len(kept) != len(lines) else None


def delete_strategies(names, used_names):
    """删除指定策略。返回 (ok, 消息, 已删除列表, 跳过列表)

    安全约束：有订阅在用的策略拒绝删除；文件必须落在 strategies/ 目录内；
    先改 __init__.py 摘导入，再删文件，任一失败都回滚。
    """
    wanted = [str(name) for name in (names or []) if str(name).strip()]
    if not wanted:
        return False, "没有选中要删除的策略", [], []

    registry = {strategy.name: strategy for strategy in _STRATEGIES}
    deleted, skipped = [], []
    init_text = INIT_PATH.read_text(encoding="utf-8") if INIT_PATH.exists() else None

    for name in wanted:
        strategy = registry.get(name)
        if strategy is None:
            skipped.append(f"{name}：策略不存在")
            continue
        if name in used_names:
            skipped.append(f"{name}：仍有订阅在用")
            continue
        path = _file_path(strategy)
        module = _module_name(strategy)
        if path is None or path.parent != STRATEGIES_DIR or path.name != f"{module}.py":
            skipped.append(f"{name}：源文件位置异常，已跳过")
            continue

        new_init = _drop_import_line(init_text, module) if init_text else None
        if init_text is not None and new_init is None:
            skipped.append(f"{name}：__init__.py 里没找到导入行，已跳过")
            continue

        try:
            if new_init is not None:
                tmp = INIT_PATH.with_suffix(".py.tmp")
                tmp.write_text(new_init, encoding="utf-8")
                tmp.replace(INIT_PATH)
            path.unlink()
        except OSError as exc:
            # 删文件失败就把 __init__.py 恢复回去，避免导入断链
            if new_init is not None and init_text is not None:
                try:
                    INIT_PATH.write_text(init_text, encoding="utf-8")
                except OSError:
                    pass
            skipped.append(f"{name}：删除失败（{exc}）")
            continue

        init_text = new_init if new_init is not None else init_text
        deleted.append(name)

    if not deleted:
        return False, "；".join(skipped) or "没有删除任何策略", [], skipped
    message = f"已删除 {len(deleted)} 个：{'、'.join(deleted)}（重启服务后生效）"
    if skipped:
        message += "；" + "；".join(skipped)
    return True, message, deleted, skipped
