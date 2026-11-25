#!/usr/bin/env python3
"""
订阅文章一键归档脚本（CLI）
连续执行：获取订阅更新列表 → 下载网页到本地 → 优化文件名 → HTML 转 Markdown
核心流程见 archive_core.py

用法:
    python archive.py                # 完整执行所有步骤
    python archive.py --start-step 4 # 从第 4 步开始（跳过 1-3）
    python archive.py --only-step 4  # 只执行第 4 步
    python archive.py --list-steps   # 列出所有步骤
    python archive.py --reindex "2026年11月14日,2026年11月15日"  # 只重建索引页（不联网、不调 AI）
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# 源码根（本文件在 src/ 下）
sys.path.insert(0, str(Path(__file__).parent))
# 功能模块目录 src/core/（utils、watch_export 等）
sys.path.insert(0, str(Path(__file__).parent / "core"))

# Windows 终端编码修复（必须在导入其他模块之前执行）
from utils import fix_encoding, OUTPUT_BASE_DIR
fix_encoding()

from archive_core import STEPS, reindex_dates, run_archive

_DATE_RE = re.compile(r"^\d{4}年\d{2}月\d{2}日$")


def _is_date(text):
    """校验 YYYY年MM月DD日 形式的日期，含真实日期检查"""
    if not _DATE_RE.match(text or ""):
        return False
    try:
        datetime.strptime(text, "%Y年%m月%d日")
    except ValueError:
        return False
    return True


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="订阅文章一键归档脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python archive.py                # 完整执行所有步骤
  python archive.py --start-step 4 # 从第 4 步开始（跳过 1-3）
  python archive.py --only-step 4  # 只执行第 4 步
  python archive.py --list-steps   # 列出所有步骤"""
    )
    parser.add_argument("--start-step", type=int, metavar="N",
                        help="从第 N 步开始执行（跳过前面的步骤）")
    parser.add_argument("--only-step", type=int, metavar="N",
                        help="只执行第 N 步")
    parser.add_argument("--list-steps", action="store_true",
                        help="列出所有步骤及编号")
    parser.add_argument("--date", type=str, metavar="YYYY年MM月DD日",
                        help="指定日期（默认为今天）")
    parser.add_argument("--reindex", nargs="?", const="", metavar="日期1,日期2",
                        help="只重建索引页（不联网、不调 AI）：可给逗号分隔的日期，"
                             "省略日期则重建 result/ 下所有日期")
    parser.add_argument("--refresh", action="store_true",
                        help="强制重新下载：步骤 2 覆盖已有原始 HTML、步骤 3 重下已有图片"
                             "（默认只补缺失，避免重复抓站点）")
    parser.add_argument("--only-feed", type=str, metavar="名字",
                        help="只检查这一个订阅源（名字或订阅地址），且不改写当天文章列表；"
                             "有新增条目时并入已有列表。常与 --only-step 1 搭配")
    return parser.parse_args()


def notify_failures(today, result):
    """归档存在失败时发送通知邮件（复用 core/notify.py；未配置则只提示，不影响退出码）"""
    failures = list(result.get("failures") or [])
    if not failures:
        return

    try:
        from notify import load_mail_config, send_failure_mail, format_failure_report
    except Exception as exc:
        print(f"⚠️  无法加载邮件模块，跳过失败通知: {exc}")
        return

    mail_config = load_mail_config()
    if not mail_config:
        print("⚠️  本次存在失败，但未配置邮件通知（config.json 的 mail 段缺失或未启用）")
        return

    subject = f"[订阅归档失败] {today} 共 {len(failures)} 项"
    body = format_failure_report(today, failures, result.get("step_times") or {})
    ok, message = send_failure_mail(mail_config, subject, body)
    if ok:
        print(f"✉️  失败通知邮件已发送: {', '.join(mail_config.get('to', []))}")
    else:
        print(f"✗ 失败通知邮件发送失败: {message}")


def main():
    args = parse_args()

    # 列出所有步骤
    if args.list_steps:
        print("订阅归档步骤：")
        print()
        for num, name, desc in STEPS:
            print(f"  {num}. {desc}")
        print()
        print("用法:")
        print("  python archive.py --start-step 4  # 从第 4 步开始")
        print("  python archive.py --only-step 4   # 只执行第 4 步")
        return

    # 确定日期
    today = args.date or datetime.now().strftime("%Y年%m月%d日")

    # 只重建索引页（补正被旧代码生成错的索引）
    if args.reindex is not None:
        if args.reindex.strip():
            dates = [item.strip() for item in args.reindex.split(",") if item.strip()]
            invalid = [item for item in dates if not _is_date(item)]
            if invalid:
                print(f"❌ 日期格式无效: {', '.join(invalid)}（应为 YYYY年MM月DD日）")
                sys.exit(1)
        else:
            dates = sorted(path.name for path in OUTPUT_BASE_DIR.iterdir()
                           if path.is_dir() and _is_date(path.name))
        if not dates:
            print("❌ 没有可重建的日期")
            sys.exit(1)
        results = reindex_dates(dates, log=lambda message: print(message, flush=True))
        failed = [item for item in results if item["error"]]
        print(f"\n共 {len(results)} 天，成功 {len(results) - len(failed)} 天"
              + (f"，失败 {len(failed)} 天" if failed else ""))
        if failed:
            sys.exit(1)
        return

    # 确定要执行的步骤范围
    if args.only_step is not None and args.start_step is not None:
        print("❌ 不能同时使用 --start-step 和 --only-step")
        sys.exit(1)

    if args.only_feed and args.only_step is None and args.start_step is None:
        # 单源刷新默认只跑步骤 1，避免顺带把 2/3/4 跑起来
        start_step = end_step = 1
    elif args.only_step is not None:
        if args.only_step < 1 or args.only_step > len(STEPS):
            print(f"❌ 无效的步骤编号: {args.only_step}（有效范围: 1-{len(STEPS)}）")
            sys.exit(1)
        start_step = args.only_step
        end_step = args.only_step
    elif args.start_step is not None:
        if args.start_step < 1 or args.start_step > len(STEPS):
            print(f"❌ 无效的步骤编号: {args.start_step}（有效范围: 1-{len(STEPS)}）")
            sys.exit(1)
        start_step = args.start_step
        end_step = len(STEPS)
    else:
        start_step = 1
        end_step = len(STEPS)

    if start_step > 1:
        print(f"⏭️  从第 {start_step} 步开始执行（跳过步骤 1-{start_step - 1}）")
        print()

    selected_steps = list(range(start_step, end_step + 1))
    if args.only_feed and 1 not in selected_steps:
        print("❌ --only-feed 只作用于步骤 1，请配合 --only-step 1（或包含步骤 1 的范围）使用")
        sys.exit(1)
    result = run_archive(
        selected_steps,
        today,
        log=lambda message: print(message, flush=True),
        refresh=args.refresh,
        only_feed=args.only_feed,
    )

    notify_failures(today, result)

    # 单源刷新后顺手重建索引页（纯本地，不联网），让索引页的「仅链接」区块同步
    if args.only_feed:
        print()
        print("正在用本地数据重建索引页...")
        reindex_dates([today], log=lambda message: print(message, flush=True))

    if result["error"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
