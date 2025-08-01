"""
Base processor for data processing.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import hashlib
import json

from ..state import DataProcessingState, ProcessedContent, ProcessingStatus


class BaseProcessor(ABC):
    """기본 데이터 프로세서 추상 클래스"""
    
    def __init__(self, processing_options: Dict[str, Any] = None):
        """
        프로세서 초기화
        
        Args:
            processing_options: 처리 옵션
        """
        self.processing_options = processing_options or {}
    
    @abstractmethod
    def process(self, state: DataProcessingState) -> DataProcessingState:
        """
        데이터 처리 메인 메소드
        
        Args:
            state: 현재 상태
            
        Returns:
            DataProcessingState: 업데이트된 상태
        """
        pass
    
    @abstractmethod
    def extract_content(self, state: DataProcessingState) -> str:
        """
        원본 콘텐츠 추출
        
        Args:
            state: 현재 상태
            
        Returns:
            str: 추출된 텍스트 콘텐츠
        """
        pass
    
    def generate_cache_key(self, input_data: Any) -> str:
        """
        캐시 키 생성
        
        Args:
            input_data: 입력 데이터
            
        Returns:
            str: 캐시 키
        """
        # 입력 데이터를 문자열로 변환
        if isinstance(input_data, dict):
            data_str = json.dumps(input_data, sort_keys=True)
        else:
            data_str = str(input_data)
        
        # 처리 옵션도 포함
        options_str = json.dumps(self.processing_options, sort_keys=True)
        
        # 해시 생성
        combined = f"{data_str}:{options_str}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def preprocess_text(self, text: str) -> str:
        """
        텍스트 전처리
        
        Args:
            text: 원본 텍스트
            
        Returns:
            str: 전처리된 텍스트
        """
        if not text:
            return ""
        
        # 기본 정리
        text = text.strip()
        
        # 연속된 공백 제거
        import re
        text = re.sub(r'\s+', ' ', text)
        
        # 연속된 줄바꿈 정리
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        
        return text
    
    def extract_metadata(self, state: DataProcessingState) -> Dict[str, Any]:
        """
        메타데이터 추출
        
        Args:
            state: 현재 상태
            
        Returns:
            Dict: 메타데이터
        """
        metadata = {
            'processor_type': self.__class__.__name__,
            'input_type': state['input_type'].value if state['input_type'] else 'unknown',
            'processing_options': self.processing_options.copy()
        }
        
        # 텍스트 통계
        if state.get('raw_content'):
            content = state['raw_content']
            metadata.update({
                'character_count': len(content),
                'word_count': len(content.split()),
                'line_count': content.count('\n') + 1
            })
        
        return metadata
    
    def create_processed_content(self, 
                               title: str, 
                               content: str, 
                               state: DataProcessingState) -> ProcessedContent:
        """
        ProcessedContent 객체 생성
        
        Args:
            title: 제목
            content: 내용
            state: 현재 상태
            
        Returns:
            ProcessedContent: 처리된 콘텐츠 객체
        """
        return ProcessedContent(
            title=title,
            content=content,
            sections=self._extract_sections(content),
            metadata=self.extract_metadata(state),
            source_info={
                'input_type': state['input_type'].value if state['input_type'] else 'unknown',
                'input_data': str(state['input_data'])[:200] + '...' if len(str(state['input_data'])) > 200 else str(state['input_data'])
            }
        )
    
    def _extract_sections(self, content: str) -> list:
        """
        콘텐츠에서 섹션 추출
        
        Args:
            content: 텍스트 콘텐츠
            
        Returns:
            list: 섹션 리스트
        """
        import re
        
        sections = []
        
        # 헤딩 패턴으로 섹션 분리
        heading_patterns = [
            r'^#{1,6}\s+(.+)$',  # 마크다운 헤딩
            r'^(.+)\n[=-]{3,}$',  # 밑줄 헤딩
            r'^(\d+\.?\s*.+)$',  # 번호 헤딩
        ]
        
        lines = content.split('\n')
        current_section = {'title': 'Introduction', 'content': '', 'level': 0}
        
        for line in lines:
            is_heading = False
            
            for pattern in heading_patterns:
                match = re.match(pattern, line.strip(), re.MULTILINE)
                if match:
                    # 이전 섹션 저장
                    if current_section['content'].strip():
                        sections.append(current_section.copy())
                    
                    # 새 섹션 시작
                    current_section = {
                        'title': match.group(1).strip(),
                        'content': '',
                        'level': line.count('#') if '#' in line else 1
                    }
                    is_heading = True
                    break
            
            if not is_heading:
                current_section['content'] += line + '\n'
        
        # 마지막 섹션 추가
        if current_section['content'].strip():
            sections.append(current_section)
        
        return sections
    
    def update_progress(self, state: DataProcessingState, progress: float, step: str) -> None:
        """
        진행 상태 업데이트
        
        Args:
            state: 상태 객체
            progress: 진행률 (0.0 ~ 1.0)
            step: 현재 단계
        """
        state['progress'] = min(max(progress, 0.0), 1.0)
        state['current_step'] = step
        
        if progress >= 1.0:
            state['status'] = ProcessingStatus.COMPLETED
        elif progress > 0:
            state['status'] = ProcessingStatus.PROCESSING
    
    def add_error(self, state: DataProcessingState, error_msg: str) -> None:
        """
        에러 추가
        
        Args:
            state: 상태 객체
            error_msg: 에러 메시지
        """
        state['errors'].append(error_msg)
        state['status'] = ProcessingStatus.FAILED
    
    def add_warning(self, state: DataProcessingState, warning_msg: str) -> None:
        """
        경고 추가
        
        Args:
            state: 상태 객체
            warning_msg: 경고 메시지
        """
        state['warnings'].append(warning_msg)
