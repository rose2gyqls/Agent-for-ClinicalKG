from dotenv import load_dotenv
import os
from pathlib import Path


# 프로젝트 루트의 .env 파일 강제 로드
project_root = Path(__file__).parent.parent.parent
env_file = project_root / ".env"

if env_file.exists():
    # 기존 환경 변수 클리어하고 새로 로드
    os.environ.pop('GEMINI_API_KEY', None)
    load_dotenv(env_file, override=True)
    print(f"✅ .env 파일 로드됨: {env_file}")
else:
    print("❌ .env 파일을 찾을 수 없습니다.")
    # 기본 .env 파일 로드 시도
    load_dotenv(override=True)

class Config:
    """설정 클래스 - 속성 접근 방식 사용"""
    # API 키에서 따옴표 제거
    _raw_api_key = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_KEY = _raw_api_key.strip().strip('"').strip("'")
    
    # 디버깅을 위한 API 키 상태 출력
    if GEMINI_API_KEY:
        print(f"✅ GEMINI_API_KEY 로드됨 (길이: {len(GEMINI_API_KEY)})")
        print(f"🔑 API 키 시작: {GEMINI_API_KEY[:15]}...")
        print(f"✅ 따옴표 제거됨: {chr(34) not in GEMINI_API_KEY and chr(39) not in GEMINI_API_KEY}")
    else:
        print("❌ GEMINI_API_KEY를 찾을 수 없습니다.")

    # 선택적 설정들 (없어도 에러 발생하지 않음)
    ES_SERVER_HOST = os.getenv("ES_SERVER_HOST", "").strip().strip('"').strip("'")
    ES_SERVER_PORT = os.getenv("ES_SERVER_PORT", "").strip().strip('"').strip("'")
    ES_SERVER_USERNAME = os.getenv("ES_SERVER_USERNAME", "").strip().strip('"').strip("'")
    ES_SERVER_PASSWORD = os.getenv("ES_SERVER_PASSWORD", "").strip().strip('"').strip("'")
    GRPC_SERVER_PORT = os.getenv("GRPC_SERVER_PORT", "").strip().strip('"').strip("'")
    
    # NEO4J 설정
    NEO4J_SERVER_URI = os.getenv("NEO4J_SERVER_URI", "").strip().strip('"').strip("'")
    NEO4J_SERVER_USER = os.getenv("NEO4J_SERVER_USER", "").strip().strip('"').strip("'")
    NEO4J_SERVER_PASSWORD = os.getenv("NEO4J_SERVER_PASSWORD", "").strip().strip('"').strip("'")
    NEO4J_SERVER_DATABASE = os.getenv("NEO4J_SERVER_DATABASE", "").strip().strip('"').strip("'")

    # AWS S3 관련 설정
    AWS_PROFILE = os.getenv("AWS_PROFILE", "boaz-snuh").strip().strip('"').strip("'")  # 기본값 boaz-snuh 프로필    
    AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2").strip().strip('"').strip("'")  # 기본값 서울 리전
    AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "source-to-kg").strip().strip('"').strip("'")  # 기본 버킷명 (필요시 사용)
    
    # AWS 자격 증명 (프로필이 없는 경우 사용)
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip().strip('"').strip("'")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip().strip('"').strip("'")
    AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "").strip().strip('"').strip("'")  # 임시 자격 증명용


# 전역 설정 인스턴스 생성
config = Config()