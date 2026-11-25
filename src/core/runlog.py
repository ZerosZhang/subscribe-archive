#!/usr/bin/env python3
"""
运行日志落盘

一次归档一个日期一份 `result/logs/YYYY年MM月DD日.log`（追加写），
同一天多次执行会按执行分段接在后面，方便事后排查「当时到底报了什么错」。

捕获两类输出：
- 流程自己调用的 `log()` 回调
- 底层模块（render_html / summarize / save_webpages）直接 `print()` 的内容
  通过替换 `sys.stdout` 实现，退出时恢复原样

同一行不会写两遍：`log` 回调在 CLI 下就是 print（会经过 stdout 的分身），
此时改为直接写原始流，绕开分身。
"""

import sys
from datetime import datetime

from utils import LOGS_DIR


class RunLog:
    """日期级日志文件（追加模式，线程内串行写）"""

    def __init__(self, today):
        self.path = LOGS_DIR / f"{today}.log"
        self._stream = None
        self._partial = ""
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            self._stream = open(self.path, "a", encoding="utf-8")
        except OSError as exc:
            print(f"⚠️  日志文件无法写入：{exc}")

    def _write(self, text):
        if self._stream is None:
            return
        try:
            self._stream.write(text)
            self._stream.flush()
        except OSError:
            pass

    def header(self, steps):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write(f"\n{'=' * 60}\n[{stamp}] 开始执行，步骤 {list(steps)}\n{'=' * 60}\n")

    def footer(self, ok=True):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state = "结束" if ok else "异常结束"
        self._write(f"[{stamp}] {state}\n")

    def line(self, message):
        """写一行（带时间戳，多行消息逐行加）"""
        stamp = datetime.now().strftime("%H:%M:%S")
        for text in str(message).splitlines() or [""]:
            self._write(f"[{stamp}] {text}\n")

    def stream_write(self, text):
        """接收 print() 的原始写入，按行补时间戳后落盘"""
        if not text:
            return
        self._partial += text
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            self.line(line)

    def close(self):
        if self._partial:
            self.line(self._partial)
            self._partial = ""
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
            self._stream = None


class _StreamTee:
    """把 stdout 的写入同时送到原流与日志文件（其余属性透传）"""

    def __init__(self, inner, runlog):
        self._inner = inner
        self._runlog = runlog

    def write(self, text):
        if self._inner is not None:
            try:
                self._inner.write(text)
            except (OSError, ValueError):
                pass
        self._runlog.stream_write(text)
        return len(text) if text else 0

    def flush(self):
        if self._inner is not None:
            try:
                self._inner.flush()
            except (OSError, ValueError):
                pass

    def __getattr__(self, name):
        if self._inner is None:
            raise AttributeError(name)
        return getattr(self._inner, name)


def make_logger(user_log, runlog, base_stream):
    """包一层日志回调：先落盘，再交给原有出口

    base_stream 是接管前的 sys.stdout —— CLI 传进来的 log 就是 print，
    直接写原始流，避免被 _StreamTee 再写一遍日志。
    """
    def logger(message):
        runlog.line(message)
        if user_log is print and base_stream is not None:
            try:
                base_stream.write(f"{message}\n")
            except (OSError, ValueError):
                pass
        else:
            user_log(message)

    return logger


def install_stdout_tee(runlog):
    """接管 sys.stdout，返回 (原流, tee)；恢复时用 restore_stdout_tee(原流)"""
    original = sys.stdout
    tee = _StreamTee(original, runlog)
    sys.stdout = tee
    return original, tee


def restore_stdout_tee(original):
    sys.stdout = original
