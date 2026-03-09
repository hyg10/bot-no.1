"""
PostToolUse Hook: 수정 후 포맷터 실행
Edit/Write 후 Python 파일 문법 검사 + 포맷 확인
"""
import json
import sys
import subprocess
import os

def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Python 파일만 처리
    if not file_path.endswith(".py"):
        sys.exit(0)

    if not os.path.exists(file_path):
        sys.exit(0)

    # 1. 문법 검사 (py_compile)
    result = subprocess.run(
        [sys.executable, "-c", f"import py_compile; py_compile.compile(r'{file_path}', doraise=True)"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        # PostToolUse에서는 additionalContext로 Claude에게 알림
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"[Hook] 문법 오류 발견: {file_path}\n{error_msg}\n즉시 수정이 필요합니다."
            }
        }
        json.dump(output, sys.stdout)
        sys.exit(0)

    # 2. 기본 코드 품질 체크 (긴 줄, trailing whitespace)
    warnings = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines, 1):
            if len(line.rstrip("\n")) > 120:
                warnings.append(f"  L{i}: 줄 길이 {len(line.rstrip())}자 (120자 초과)")
            if line != "\n" and line.rstrip("\n") != line.rstrip("\n").rstrip():
                warnings.append(f"  L{i}: trailing whitespace")
    except Exception:
        pass

    if warnings and len(warnings) <= 5:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"[Hook] 코드 스타일 경고 ({file_path}):\n" + "\n".join(warnings[:5])
            }
        }
        json.dump(output, sys.stdout)

    sys.exit(0)

if __name__ == "__main__":
    main()
