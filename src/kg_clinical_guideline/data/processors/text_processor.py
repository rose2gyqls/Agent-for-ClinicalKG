"""
Plain text processor.
"""

from typing import Dict, Any
import re

from .base_processor import BaseProcessor
from ..state import DataProcessingState


class TextProcessor(BaseProcessor):
    """일반 텍스트 프로세서"""
    
    def process(self, state: DataProcessingState) -> DataProcessingState:
        """
        텍스트 데이터 처리
        
        Args:
            state: 현재 상태
            
        Returns:
            DataProcessingState: 업데이트된 상태
        """
        try:
            self.update_progress(state, 0.2, "text_loading")
            
            # 텍스트 추출
            raw_content = self.extract_content(state)
            state['raw_content'] = raw_content
            
            self.update_progress(state, 0.5, "text_preprocessing")
            
            # 텍스트 전처리
            processed_text = self.preprocess_text(raw_content)
            
            self.update_progress(state, 0.7, "text_analysis")
            
            # 제목 추출
            title = self._extract_title_from_text(processed_text)
            
            self.update_progress(state, 0.9, "text_structuring")
            
            # ProcessedContent 생성
            processed_content = self.create_processed_content(
                title=title,
                content=processed_text,
                state=state
            )
            
            state['processed_content'] = processed_content
            state['cache_key'] = self.generate_cache_key(state['input_data'])
            
            self.update_progress(state, 1.0, "text_completed")
            
        except Exception as e:
            self.add_error(state, f"텍스트 처리 중 오류 발생: {str(e)}")
        
        return state
    
    def extract_content(self, state: DataProcessingState) -> str:
        """
        입력에서 텍스트 추출
        
        Args:
            state: 현재 상태
            
        Returns:
            str: 추출된 텍스트
        """
        input_data = state['input_data']
        
        if isinstance(input_data, str):
            return input_data
        else:
            return str(input_data)
    
    def preprocess_text(self, text: str) -> str:
        """
        의료 텍스트에 특화된 전처리
        
        Args:
            text: 원본 텍스트
            
        Returns:
            str: 전처리된 텍스트
        """
        if not text:
            return ""
        
        # 기본 전처리
        text = super().preprocess_text(text)
        
        # 의료 텍스트 특화 전처리
        text = self._normalize_medical_terms(text)
        text = self._format_medical_lists(text)
        text = self._enhance_readability(text)
        
        return text
    
    def _normalize_medical_terms(self, text: str) -> str:
        """
        의료 용어 정규화
        
        Args:
            text: 입력 텍스트
            
        Returns:
            str: 정규화된 텍스트
        """
        # 일반적인 의료 약어 확장
        medical_abbreviations = {
            'HTN': '고혈압(HTN)',
            'DM': '당뇨병(DM)',
            'MI': '심근경색(MI)',
            'COPD': '만성폐쇄성폐질환(COPD)',
            'CHF': '울혈성심부전(CHF)',
            'CAD': '관상동맥질환(CAD)',
            'CVA': '뇌혈관사고(CVA)',
            'DVT': '심부정맥혈전증(DVT)',
            'PE': '폐색전증(PE)',
            'ARDS': '급성호흡곤란증후군(ARDS)',
            'ICU': '중환자실(ICU)',
            'ER': '응급실(ER)',
            'OR': '수술실(OR)'
        }
        
        for abbrev, full_form in medical_abbreviations.items():
            # 단어 경계에서만 치환 (대소문자 구분)
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            if re.search(pattern, text):
                text = re.sub(pattern, full_form, text)
        
        return text
    
    def _format_medical_lists(self, text: str) -> str:
        """
        의료 관련 리스트 포맷팅
        
        Args:
            text: 입력 텍스트
            
        Returns:
            str: 포맷팅된 텍스트
        """
        # 숫자로 시작하는 리스트 항목들을 마크다운 형식으로 변환
        text = re.sub(r'^(\d+)\.\s*(.+)$', r'1. \2', text, flags=re.MULTILINE)
        
        # 대시나 별표로 시작하는 항목들을 마크다운 형식으로 변환
        text = re.sub(r'^[-*•]\s*(.+)$', r'- \1', text, flags=re.MULTILINE)
        
        # 용법/용량 패턴 포맷팅
        dosage_pattern = r'(\d+(?:\.\d+)?)\s*(mg|g|ml|정|캡슐|알)\s*(?:을|를)?\s*(?:하루|매일|일일)?\s*(\d+)?\s*(?:회|번)'
        text = re.sub(dosage_pattern, r'**\1\2** (하루 \3회)', text)
        
        return text
    
    def _enhance_readability(self, text: str) -> str:
        """
        가독성 향상
        
        Args:
            text: 입력 텍스트
            
        Returns:
            str: 가독성이 향상된 텍스트
        """
        # 중요한 의료 키워드 강조
        important_keywords = [
            '주의사항', '금기사항', '부작용', '경고', '위험', '응급',
            '즉시', '심각한', '중증', '생명위험', '알레르기'
        ]
        
        for keyword in important_keywords:
            text = re.sub(f'({keyword})', r'**\1**', text, flags=re.IGNORECASE)
        
        # 섹션 헤더 감지 및 마크다운 변환
        section_patterns = [
            (r'^(적응증|용법용량|금기사항|주의사항|부작용|상호작용|보관방법):\s*(.+)$', r'## \1\n\2'),
            (r'^(진단|치료|검사|처치|수술)\s*방법\s*[:：]?\s*(.+)$', r'## \1 방법\n\2'),
            (r'^(1차|2차|3차)\s*(치료|요법)\s*[:：]?\s*(.+)$', r'### \1 \2\n\3'),
        ]
        
        for pattern, replacement in section_patterns:
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE | re.IGNORECASE)
        
        # 문단 분리 개선
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        return text
    
    def _extract_title_from_text(self, text: str) -> str:
        """
        텍스트에서 제목 추출
        
        Args:
            text: 텍스트 내용
            
        Returns:
            str: 추출된 제목
        """
        if not text:
            return "의료 가이드라인"
        
        lines = text.split('\n')[:10]  # 첫 10줄에서 제목 찾기
        
        # 마크다운 헤더 찾기
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                title = line.lstrip('#').strip()
                if len(title) > 5 and len(title) < 100:
                    return title
        
        # 의료 관련 키워드가 포함된 첫 번째 줄 찾기
        medical_keywords = [
            '가이드라인', '지침', '프로토콜', '표준', '권고', '치료',
            'guideline', 'protocol', 'standard', 'treatment', 'therapy'
        ]
        
        for line in lines:
            line = line.strip()
            if (len(line) > 10 and len(line) < 150 and
                any(keyword in line.lower() for keyword in medical_keywords)):
                return line
        
        # 적절한 길이의 첫 번째 줄 사용
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 100:
                return line
        
        return "의료 가이드라인 문서"
