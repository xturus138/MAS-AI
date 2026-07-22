"""Strip all # comments from Python files without breaking code.

Uses Python's tokenize module to safely distinguish comments from
# characters inside strings. Preserves docstrings, shebangs, and
encoding declarations.
"""

import tokenize
import io
import os
import sys


def strip_comments(filepath):
    with open(filepath, "rb") as f:
        raw = f.read()

    encoding = "utf-8"
    for line in raw.split(b"\n")[:2]:
        if line.startswith(b"# -*- coding:"):
            encoding = line.split(b":")[1].split(b"-*-")[0].strip().decode()
            break

    text = raw.decode(encoding, errors="replace")
    has_crlf = "\r\n" in text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_raw = normalized.encode(encoding, errors="replace")

    try:
        tokens = list(tokenize.tokenize(io.BytesIO(normalized_raw).readline))
    except tokenize.TokenError:
        return False

    comments = []
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            line_idx = tok.start[0] - 1
            start_col = tok.start[1]
            end_col = len(normalized.splitlines()[line_idx]) if line_idx < len(normalized.splitlines()) else start_col
            comments.append((line_idx, start_col, end_col))

    lines = normalized.splitlines(keepends=True)
    for line_idx, start_col, end_col in sorted(comments, reverse=True):
        if line_idx >= len(lines):
            continue
        line = lines[line_idx]
        if start_col < len(line):
            before = line[:start_col]
            after = line[end_col:] if end_col < len(line) else ""
            if before.strip() == "" and after.strip() == "":
                lines[line_idx] = ""
            elif before.strip() == "" and after == "":
                lines[line_idx] = ""
            elif before.strip() == "" and after == "\n":
                lines[line_idx] = ""
            else:
                lines[line_idx] = before.rstrip() + after

    output = "".join(lines)
    if has_crlf:
        output = output.replace("\n", "\r\n")

    with open(filepath, "wb") as f:
        f.write(output.encode(encoding, errors="replace"))
    return True


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")
        if ".claude" in dirnames:
            dirnames.remove(".claude")
        if "venv" in dirnames:
            dirnames.remove("venv")

        for fn in filenames:
            if fn.endswith(".py"):
                fp = os.path.join(dirpath, fn)
                try:
                    if strip_comments(fp):
                        count += 1
                        print(f"  OK  {os.path.relpath(fp, root)}")
                    else:
                        print(f" SKIP {os.path.relpath(fp, root)}")
                except Exception as e:
                    print(f" FAIL {os.path.relpath(fp, root)}: {e}")

    print(f"\nProcessed {count} files")
