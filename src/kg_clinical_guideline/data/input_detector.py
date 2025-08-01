"""
Input data type detection module.
"""

import re
import json
from pathlib import Path
from typing import Union, Dict, Any
from urllib.parse import urlparse

from .state import InputType, DataProcessingState, ProcessingStatus


class InputDetector:
    """입력 데이터 타입 감지기"""
    
    @staticmethod
    def detect_input_type(input_data: Union[str, Path, Dict[str, Any]]) -> InputType:
        """
        입력 데이터 타입 감지
        
        Args:
            input_data: 입력 데이터
            
        Returns:
            InputType: 감지된 입력 타입
        """
        
        # 딕셔너리 형태의 직접 데이터
        if isinstance(input_data, dict):
            return InputType.LOCAL_JSON
        
        # 문자열 또는 Path 객체
        if isinstance(input_data, (str, Path)):
            input_str = str(input_data)
            
            # S3 URL 패턴 확인
            if InputDetector._is_s3_url(input_str):
                # JSON 파일인지 확인
                if input_str.lower().endswith('.json'):
                    return InputType.S3_JSON
                return InputType.S3_JSON  # S3의 경우 기본적으로 JSON으로 가정
            
            # HTTP/HTTPS URL 확인
            if InputDetector._is_web_url(input_str):
                return InputType.URL
            
            # 로컬 파일 경로 확인
            if InputDetector._is_file_path(input_str):
                file_path = Path(input_str)
                if file_path.suffix.lower() == '.pdf':
                    return InputType.PDF
                elif file_path.suffix.lower() == '.json':
                    return InputType.LOCAL_JSON
            
            # JSON 문자열인지 확인
            if InputDetector._is_json_string(input_str):
                return InputType.LOCAL_JSON
            
            # 긴 텍스트인지 확인 (100자 이상)
            if len(input_str.strip()) > 100:
                return InputType.TEXT
        
        return InputType.UNKNOWN
    
    @staticmethod
    def _is_s3_url(input_str: str) -> bool:
        """S3 URL인지 확인"""
        s3_patterns = [
            r'^s3://[\w.-]+/.*',  # s3://bucket/key
            r'^https://[\w.-]+\.s3[\w.-]*\.amazonaws\.com/.*',  # HTTPS S3 URL
            r'^https://s3[\w.-]*\.amazonaws\.com/[\w.-]+/.*',  # Alternative S3 URL
        ]
        
        for pattern in s3_patterns:
            if re.match(pattern, input_str, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def _is_web_url(input_str: str) -> bool:
        """웹 URL인지 확인"""
        try:
            parsed = urlparse(input_str)
            return parsed.scheme in ['http', 'https'] and parsed.netloc
        except:
            return False
    
    @staticmethod
    def _is_file_path(input_str: str) -> bool:
        """파일 경로인지 확인"""
        try:
            path = Path(input_str)
            # 절대경로이거나 상대경로 패턴
            return (path.is_absolute() or 
                   '/' in input_str or 
                   '\\' in input_str or 
                   '.' in path.suffix)
        except:
            return False
    
    @staticmethod
    def _is_json_string(input_str: str) -> bool:
        """JSON 문자열인지 확인"""
        try:
            json.loads(input_str)
            return True
        except:
            return False
    
    @staticmethod
    def extract_s3_info(s3_url: str) -> Dict[str, str]:
        """
        S3 URL에서 버킷과 키 정보 추출
        
        Args:
            s3_url: S3 URL
            
        Returns:
            Dict: 버킷, 키, 리전 정보
        """
        s3_info = {
            'bucket': '',
            'key': '',
            'region': 'us-east-1'  # 기본 리전
        }
        
        # s3://bucket/key 형태
        if s3_url.startswith('s3://'):
            parts = s3_url[5:].split('/', 1)
            if len(parts) >= 2:
                s3_info['bucket'] = parts[0]
                s3_info['key'] = parts[1]
        
        # HTTPS S3 URL 형태
        elif 'amazonaws.com' in s3_url:
            # https://bucket.s3.region.amazonaws.com/key
            # https://s3.region.amazonaws.com/bucket/key
            
            if '.s3.' in s3_url:
                # bucket.s3.region.amazonaws.com 형태
                match = re.match(r'https://([^.]+)\.s3\.([^.]+)\.amazonaws\.com/(.*)', s3_url)
                if match:
                    s3_info['bucket'] = match.group(1)
                    s3_info['region'] = match.group(2)
                    s3_info['key'] = match.group(3)
            else:
                # s3.region.amazonaws.com/bucket/key 형태
                match = re.match(r'https://s3\.([^.]+)\.amazonaws\.com/([^/]+)/(.*)', s3_url)
                if match:
                    s3_info['region'] = match.group(1)
                    s3_info['bucket'] = match.group(2)
                    s3_info['key'] = match.group(3)
        
        return s3_info


def detect_and_prepare_state(input_data: Union[str, Path, Dict[str, Any]], 
                           processing_options: Dict[str, Any] = None) -> DataProcessingState:
    """
    입력 데이터를 분석하고 초기 State 생성
    
    Args:
        input_data: 입력 데이터
        processing_options: 처리 옵션
        
    Returns:
        DataProcessingState: 초기화된 상태
    """
    
    # 입력 타입 감지
    input_type = InputDetector.detect_input_type(input_data)
    
    # 기본 상태 생성
    state = DataProcessingState(
        input_data=input_data,
        input_type=input_type,
        input_metadata={},
        s3_bucket=None,
        s3_key=None,
        aws_region=None,
        status=ProcessingStatus.PENDING,
        current_step="input_detection",
        progress=0.1,
        raw_content=None,
        raw_data=None,
        processed_content=None,
        markdown_content=None,
        errors=[],
        warnings=[],
        processing_options=processing_options or {},
        cache_key=None,
        use_cache=True
    )
    
    # S3 정보 추출
    if input_type == InputType.S3_JSON and isinstance(input_data, str):
        s3_info = InputDetector.extract_s3_info(input_data)
        state.update({
            's3_bucket': s3_info['bucket'],
            's3_key': s3_info['key'],
            'aws_region': s3_info['region']
        })
    
    # 입력 메타데이터 설정
    if isinstance(input_data, (str, Path)):
        state['input_metadata'] = {
            'input_string': str(input_data),
            'detected_type': input_type.value,
            'input_length': len(str(input_data))
        }
    elif isinstance(input_data, dict):
        state['input_metadata'] = {
            'detected_type': input_type.value,
            'data_keys': list(input_data.keys()),
            'data_size': len(input_data)
        }
    
    return state