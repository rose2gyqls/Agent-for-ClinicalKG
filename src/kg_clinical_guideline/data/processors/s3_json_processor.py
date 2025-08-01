"""
AWS S3 JSON file processor.
"""

import json
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from .base_processor import BaseProcessor
from ..state import DataProcessingState
from ...config import config


class S3JsonProcessor(BaseProcessor):
    """AWS S3 JSON 파일 프로세서"""
    
    def __init__(self, processing_options: Dict[str, Any] = None):
        super().__init__(processing_options)
        self.s3_client = None
        self._initialize_s3_client()
    
    def _initialize_s3_client(self):
        """S3 클라이언트 초기화"""
        try:
            # config에서 AWS 설정 가져오기
            aws_profile = getattr(config, 'AWS_PROFILE', None)
            aws_region = getattr(config, 'AWS_REGION', 'ap-northeast-2')
            aws_access_key = getattr(config, 'AWS_ACCESS_KEY_ID', None)
            aws_secret_key = getattr(config, 'AWS_SECRET_ACCESS_KEY', None)
            aws_session_token = getattr(config, 'AWS_SESSION_TOKEN', None)
            
            # 자격 증명 방법 결정
            if aws_access_key and aws_secret_key:
                # 직접 자격 증명 사용
                session_kwargs = {
                    'aws_access_key_id': aws_access_key,
                    'aws_secret_access_key': aws_secret_key,
                    'region_name': aws_region
                }
                if aws_session_token:
                    session_kwargs['aws_session_token'] = aws_session_token
                
                session = boto3.Session(**session_kwargs)
                self.s3_client = session.client('s3')
                print(f"AWS S3 연결 성공: 직접 자격 증명 사용, 리전={aws_region}")
                
            elif aws_profile:
                # AWS 프로필 사용
                session = boto3.Session(profile_name=aws_profile, region_name=aws_region)
                self.s3_client = session.client('s3')
                print(f"AWS S3 연결 성공: 프로필={aws_profile}, 리전={aws_region}")
                
            else:
                # 기본 자격 증명 사용 (환경 변수 또는 IAM 역할)
                self.s3_client = boto3.client('s3', region_name=aws_region)
                print(f"AWS S3 연결 성공: 기본 자격 증명 사용, 리전={aws_region}")
            
            # 자격 증명 테스트
            self.s3_client.list_buckets()
            
        except NoCredentialsError:
            self.s3_client = None
            print("AWS 자격 증명을 찾을 수 없습니다. AWS 프로필 또는 환경 변수를 확인하세요.")
        except Exception as e:
            self.s3_client = None
            print(f"AWS S3 클라이언트 초기화 실패: {str(e)}")
    
    def process(self, state: DataProcessingState) -> DataProcessingState:
        """
        S3 JSON 파일 처리
        
        Args:
            state: 현재 상태
            
        Returns:
            DataProcessingState: 업데이트된 상태
        """
        try:
            self.update_progress(state, 0.1, "s3_connecting")
            
            # S3 연결 확인
            if not self.s3_client:
                aws_profile = getattr(config, 'AWS_PROFILE', None)
                error_msg = f"AWS S3 연결을 할 수 없습니다.\n"
                error_msg += f"현재 설정: 프로필={aws_profile}, 리전={getattr(config, 'AWS_REGION', 'ap-northeast-2')}\n"
                error_msg += "확인사항:\n"
                error_msg += "1. AWS CLI가 설치되어 있는지 확인\n"
                error_msg += "2. aws configure로 자격 증명 설정\n"
                error_msg += "3. .env 파일에 AWS_PROFILE, AWS_REGION 확인"
                self.add_error(state, error_msg)
                return state
            
            self.update_progress(state, 0.3, "s3_downloading")
            
            # S3에서 JSON 데이터 다운로드
            json_data = self._download_from_s3(state)
            state['raw_data'] = json_data
            
            self.update_progress(state, 0.6, "s3_extracting")
            
            # JSON에서 텍스트 추출
            raw_content = self.extract_content(state)
            state['raw_content'] = raw_content
            
            self.update_progress(state, 0.8, "s3_processing")
            
            # 텍스트 전처리
            processed_text = self.preprocess_text(raw_content)
            
            # 제목 추출
            title = self._extract_title_from_json(json_data, state)
            
            # ProcessedContent 생성
            processed_content = self.create_processed_content(
                title=title,
                content=processed_text,
                state=state
            )
            
            state['processed_content'] = processed_content
            state['cache_key'] = self.generate_cache_key(f"s3://{state['s3_bucket']}/{state['s3_key']}")
            
            self.update_progress(state, 1.0, "s3_completed")
            
        except Exception as e:
            self.add_error(state, f"S3 JSON 처리 중 오류 발생: {str(e)}")
        
        return state
    
    def _download_from_s3(self, state: DataProcessingState) -> Dict[str, Any]:
        """
        S3에서 JSON 파일 다운로드
        
        Args:
            state: 현재 상태
            
        Returns:
            Dict: JSON 데이터
        """
        bucket = state['s3_bucket']
        key = state['s3_key']
        
        try:
            # S3 객체 다운로드
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            
            # JSON 파싱
            json_data = json.loads(content)
            
            return json_data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise Exception(f"S3 파일을 찾을 수 없습니다: s3://{bucket}/{key}")
            elif error_code == 'NoSuchBucket':
                raise Exception(f"S3 버킷을 찾을 수 없습니다: {bucket}")
            else:
                raise Exception(f"S3 다운로드 오류: {str(e)}")
        
        except json.JSONDecodeError as e:
            raise Exception(f"JSON 파싱 오류: {str(e)}")
    
    def extract_content(self, state: DataProcessingState) -> str:
        """
        JSON 데이터에서 텍스트 추출
        
        Args:
            state: 현재 상태
            
        Returns:
            str: 추출된 텍스트
        """
        json_data = state['raw_data']
        if not json_data:
            return ""
        
        # 의료 가이드라인 JSON 구조에 맞는 텍스트 추출
        content_parts = []
        
        # 일반적인 필드들에서 텍스트 추출
        text_fields = [
            'content', 'text', 'body', 'description', 'guideline_text',
            'recommendations', 'procedures', 'treatment_guidelines',
            'clinical_content', 'medical_content'
        ]
        
        # 재귀적으로 텍스트 추출
        extracted_text = self._extract_text_recursive(json_data, text_fields)
        
        if extracted_text:
            return extracted_text
        
        # 구조화된 데이터를 텍스트로 변환
        return self._convert_structured_to_text(json_data)
    
    def _extract_text_recursive(self, data: Any, target_fields: list) -> str:
        """
        재귀적으로 JSON에서 텍스트 추출
        
        Args:
            data: JSON 데이터
            target_fields: 대상 필드명 리스트
            
        Returns:
            str: 추출된 텍스트
        """
        text_parts = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in [field.lower() for field in target_fields]:
                    if isinstance(value, str):
                        text_parts.append(value)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                text_parts.append(item)
                            else:
                                text_parts.append(self._extract_text_recursive(item, target_fields))
                else:
                    text_parts.append(self._extract_text_recursive(value, target_fields))
        
        elif isinstance(data, list):
            for item in data:
                text_parts.append(self._extract_text_recursive(item, target_fields))
        
        return '\n'.join(filter(None, text_parts))
    
    def _convert_structured_to_text(self, data: Dict[str, Any]) -> str:
        """
        구조화된 JSON 데이터를 읽기 가능한 텍스트로 변환
        
        Args:
            data: JSON 데이터
            
        Returns:
            str: 변환된 텍스트
        """
        text_parts = []
        
        # 제목/헤더 정보
        if 'title' in data:
            text_parts.append(f"# {data['title']}\n")
        elif 'name' in data:
            text_parts.append(f"# {data['name']}\n")
        
        # 설명/요약
        if 'description' in data:
            text_parts.append(f"## 개요\n{data['description']}\n")
        elif 'summary' in data:
            text_parts.append(f"## 요약\n{data['summary']}\n")
        
        # 가이드라인 내용
        if 'guidelines' in data:
            text_parts.append("## 가이드라인\n")
            guidelines = data['guidelines']
            if isinstance(guidelines, list):
                for i, guideline in enumerate(guidelines, 1):
                    if isinstance(guideline, dict):
                        if 'title' in guideline:
                            text_parts.append(f"### {i}. {guideline['title']}")
                        if 'content' in guideline:
                            text_parts.append(f"{guideline['content']}\n")
                    elif isinstance(guideline, str):
                        text_parts.append(f"{i}. {guideline}\n")
        
        # 권고사항
        if 'recommendations' in data:
            text_parts.append("## 권고사항\n")
            recommendations = data['recommendations']
            if isinstance(recommendations, list):
                for rec in recommendations:
                    if isinstance(rec, str):
                        text_parts.append(f"- {rec}")
                    elif isinstance(rec, dict) and 'text' in rec:
                        text_parts.append(f"- {rec['text']}")
        
        # 기타 텍스트 필드들
        for key, value in data.items():
            if key not in ['title', 'name', 'description', 'summary', 'guidelines', 'recommendations']:
                if isinstance(value, str) and len(value) > 50:
                    text_parts.append(f"## {key.title()}\n{value}\n")
        
        return '\n'.join(text_parts)
    
    def _extract_title_from_json(self, json_data: Dict[str, Any], state: DataProcessingState) -> str:
        """
        JSON 데이터에서 제목 추출
        
        Args:
            json_data: JSON 데이터
            state: 현재 상태
            
        Returns:
            str: 추출된 제목
        """
        # 일반적인 제목 필드들
        title_fields = ['title', 'name', 'guideline_title', 'document_title', 'subject']
        
        for field in title_fields:
            if field in json_data and isinstance(json_data[field], str):
                return json_data[field]
        
        # S3 키에서 제목 추출
        if state.get('s3_key'):
            key = state['s3_key']
            # 파일 확장자 제거하고 경로에서 파일명만 추출
            filename = key.split('/')[-1]
            if filename.endswith('.json'):
                filename = filename[:-5]
            return filename.replace('_', ' ').replace('-', ' ').title()
        
        return "의료 가이드라인"
    
    def extract_metadata(self, state: DataProcessingState) -> Dict[str, Any]:
        """S3 JSON 특화 메타데이터 추출"""
        metadata = super().extract_metadata(state)
        
        # S3 특화 정보 추가
        metadata.update({
            's3_bucket': state.get('s3_bucket'),
            's3_key': state.get('s3_key'),
            's3_region': getattr(config, 'AWS_REGION', 'ap-northeast-2'),
            's3_profile': getattr(config, 'AWS_PROFILE', None),
            's3_url': f"s3://{state.get('s3_bucket')}/{state.get('s3_key')}"
        })
        
        # JSON 구조 정보
        if state.get('raw_data'):
            json_data = state['raw_data']
            metadata.update({
                'json_keys': list(json_data.keys()) if isinstance(json_data, dict) else [],
                'json_type': type(json_data).__name__,
                'json_size': len(str(json_data))
            })
        
        return metadata
