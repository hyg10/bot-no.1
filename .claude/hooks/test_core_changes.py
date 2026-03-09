"""
PostToolUse Hook: 코어 파일 변경 시 테스트 실행
self_improving_bot.py, risk_manager.py, backpack_client.py 수정 시
임포트 체크 + 핵심 함수 존재 확인
"""
import json
import sys
import subprocess
import os

# 코어 파일 목록 (이 파일이 변경되면 테스트 실행)
CORE_FILES = [
    "self_improving_bot.py",
    "risk_manager.py",
    "backpack_client.py",
    "trade_analyst.py",
    "particle_filter.py",
    "wyckoff_analyzer.py",
]

# 핵심 임포트 테스트
IMPORT_TESTS = [
    ("src.self_improving_bot", "SelfImprovingTradingBot"),
    ("src.risk_management.risk_manager", "RiskManager"),
    ("src.utils.backpack_client", "BackpackClient"),
    ("src.ml.trade_analyst", "TradeAnalyst"),
]

def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # 코어 파일인지 확인
    is_core = any(core in file_path for core in CORE_FILES)
    if not is_core:
        sys.exit(0)

    # 프로젝트 디렉토리
    project_dir = data.get("cwd", "")
    if not project_dir:
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    errors = []
    warnings = []

    # 1. 문법 검사 (변경된 파일)
    if file_path.endswith(".py") and os.path.exists(file_path):
        result = subprocess.run(
            [sys.executable, "-c", f"import py_compile; py_compile.compile(r'{file_path}', doraise=True)"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            errors.append(f"문법 오류: {os.path.basename(file_path)}")
            errors.append(result.stderr.strip()[:200])

    # 2. 핵심 모듈 임포트 테스트
    for module, class_name in IMPORT_TESTS:
        test_code = f"from {module} import {class_name}; print('OK')"
        result = subprocess.run(
            [sys.executable, "-c", test_code],
            capture_output=True, text=True, timeout=15,
            cwd=project_dir, env={**os.environ, "PYTHONPATH": project_dir}
        )
        if result.returncode != 0:
            errors.append(f"임포트 실패: {module}.{class_name}")
            # 에러 메시지 첫 줄만
            err_lines = result.stderr.strip().split("\n")
            if err_lines:
                errors.append(f"  → {err_lines[-1][:150]}")

    # 3. 핵심 상수 존재 확인 (risk_manager 변경 시)
    if "risk_manager" in file_path:
        check_code = """
from src.risk_management.risk_manager import RiskManager
rm = type('C', (), {'trading': type('T', (), {'initial_capital': 100})(), 'risk_management': type('R', (), {'max_position_size_percent': 20, 'stop_loss_percent': 1.5, 'take_profit_percent': 6, 'trailing_stop_percent': 1, 'max_daily_loss_percent': 10})(), 'strategy': type('S', (), {'trade_size': 0.001})()})()
r = RiskManager(rm)
assert hasattr(r, 'TAKER_FEE'), 'TAKER_FEE 없음'
assert hasattr(r, 'ROUND_TRIP_FEE'), 'ROUND_TRIP_FEE 없음'
assert hasattr(r, 'total_fees'), 'total_fees 없음'
assert callable(getattr(r, 'calculate_pnl', None)), 'calculate_pnl 없음'
assert callable(getattr(r, 'calculate_pnl_raw', None)), 'calculate_pnl_raw 없음'
assert callable(getattr(r, 'estimate_round_trip_fee', None)), 'estimate_round_trip_fee 없음'
print('core_check OK')
"""
        result = subprocess.run(
            [sys.executable, "-c", check_code],
            capture_output=True, text=True, timeout=10,
            cwd=project_dir, env={**os.environ, "PYTHONPATH": project_dir}
        )
        if result.returncode != 0:
            errors.append("RiskManager 핵심 속성/메서드 누락")
            err_lines = result.stderr.strip().split("\n")
            if err_lines:
                errors.append(f"  → {err_lines[-1][:150]}")

    # 결과 출력
    if errors:
        msg = f"[Hook] 코어 테스트 실패 ({os.path.basename(file_path)}):\n" + "\n".join(errors)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg + "\n⚠️ 봇 재시작 전 반드시 수정하세요."
            }
        }
        json.dump(output, sys.stdout)
    elif warnings:
        msg = f"[Hook] 코어 테스트 통과 (경고 {len(warnings)}건):\n" + "\n".join(warnings)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg
            }
        }
        json.dump(output, sys.stdout)

    sys.exit(0)

if __name__ == "__main__":
    main()
