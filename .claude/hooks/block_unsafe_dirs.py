"""
PreToolUse Hook: 안전하지 않은 디렉터리 차단
인증, 결제, 마이그레이션 관련 파일 수정 차단
"""
import json
import sys
import os

# 차단할 디렉터리/파일 패턴
BLOCKED_PATTERNS = [
    # 인증 관련
    ("auth", "인증(auth) 디렉터리"),
    ("authentication", "인증(authentication) 디렉터리"),
    ("credentials", "인증정보(credentials) 파일"),
    ("secrets", "시크릿(secrets) 파일"),
    (".env.prod", "프로덕션 환경변수"),
    ("api_key", "API 키 파일"),
    ("private_key", "개인키 파일"),

    # 결제 관련
    ("payment", "결제(payment) 디렉터리"),
    ("billing", "빌링(billing) 디렉터리"),
    ("transaction", "트랜잭션(transaction) 디렉터리"),
    ("wallet", "지갑(wallet) 디렉터리"),

    # 마이그레이션 관련
    ("migration", "마이그레이션(migration) 디렉터리"),
    ("migrate", "마이그레이트(migrate) 파일"),
    ("schema", "스키마(schema) 파일"),
    ("alembic", "Alembic 마이그레이션"),

    # 시스템 설정
    ("systemd", "시스템 서비스 설정"),
    ("crontab", "크론탭 설정"),
    (".ssh", "SSH 설정"),
]

# 절대 수정 불가 파일
BLOCKED_EXACT = [
    ".env.production",
    ".env.mainnet",
]

# 예외: 이 파일들은 허용 (개발 환경)
ALLOWED_PATTERNS = [
    ".env",           # devnet 환경변수는 허용
    "backpack_client.py",  # API 클라이언트는 허용
]


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    # 정규화
    file_path_lower = file_path.replace("\\", "/").lower()
    file_name = os.path.basename(file_path_lower)

    # 예외 목록 체크 (허용된 파일은 통과)
    for allowed in ALLOWED_PATTERNS:
        if file_name == allowed.lower():
            sys.exit(0)

    # 절대 차단 파일
    for blocked in BLOCKED_EXACT:
        if file_name == blocked.lower():
            reason = f"차단: {blocked} 파일은 수정할 수 없습니다 (프로덕션 설정)"
            print(reason, file=sys.stderr)
            sys.exit(2)  # 차단

    # 패턴 매칭 차단
    for pattern, description in BLOCKED_PATTERNS:
        pattern_lower = pattern.lower()
        # 디렉터리명이나 파일명에 패턴이 포함되어 있으면 차단
        if f"/{pattern_lower}/" in file_path_lower or \
           f"\\{pattern_lower}\\" in file_path_lower or \
           file_name.startswith(pattern_lower) or \
           f"/{pattern_lower}." in file_path_lower:
            reason = f"차단: {description} — 이 영역은 직접 수정이 필요합니다.\n파일: {file_path}"
            print(reason, file=sys.stderr)
            sys.exit(2)  # 차단

    # 통과
    sys.exit(0)

if __name__ == "__main__":
    main()
