"""
LangGraph State definitions for data processing.
"""

from typing import Dict, Any, Optional, List, Union
from typing_extensions import TypedDict
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path


class InputType(Enum):
    """입력 데이터 타입"""
    PDF = "pdf"
    S3_JSON = "s3_json"
    LOCAL_JSON = "local_json"
    URL = "url"
    TEXT = "text"
    UNKNOWN = "unknown"


class ProcessingStatus(Enum):
    """처리 상태"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessedContent:
    """처리된 콘텐츠"""
    title: str
    content: str
    sections: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_info: Dict[str, Any] = field(default_factory=dict)


class DataProcessingState(TypedDict):
    """데이터 처리를 위한 LangGraph State"""
    
    # 입력 정보
    input_data: Union[str, Path, Dict[str, Any]]  # 입력 데이터 (파일경로, URL, 직접 데이터 등)
    input_type: Optional[InputType]  # 감지된 입력 타입
    input_metadata: Dict[str, Any]  # 입력 관련 메타데이터
    
    # AWS S3 관련
    s3_bucket: Optional[str]  # S3 버킷 이름
    s3_key: Optional[str]  # S3 객체 키
    aws_region: Optional[str]  # AWS 리전
    
    # 처리 상태
    status: ProcessingStatus  # 현재 처리 상태
    current_step: Optional[str]  # 현재 처리 단계
    progress: float  # 진행률 (0.0 ~ 1.0)
    
    # 원본 콘텐츠
    raw_content: Optional[str]  # 원본 텍스트 콘텐츠
    raw_data: Optional[Dict[str, Any]]  # 원본 구조화된 데이터
    
    # 처리된 콘텐츠
    processed_content: Optional[ProcessedContent]  # 처리된 콘텐츠
    markdown_content: Optional[str]  # 최종 마크다운 결과
    
    # 에러 처리
    errors: List[str]  # 발생한 에러 목록
    warnings: List[str]  # 경고 메시지 목록
    
    # 처리 설정
    processing_options: Dict[str, Any]  # 처리 옵션 (추출 레벨, 언어 등)
    
    # 캐싱
    cache_key: Optional[str]  # 캐시 키
    use_cache: bool  # 캐시 사용 여부

