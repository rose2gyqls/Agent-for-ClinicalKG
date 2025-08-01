"""
Local JSON data processor.
"""

import json
from pathlib import Path
from typing import Dict, Any, Union

from .base_processor import BaseProcessor
from ..state import DataProcessingState


class JsonProcessor(BaseProcessor):
    """로컬 JSON 데이터 프로세서"""
    
    def process(self, state: DataProcessingState) -> DataProcessingState:
        """
        JSON 데이터 처리
        
        Args:
            state: 현재 상태
            
        Returns:
            DataProcessingState: 업데이트된 상태
        """
        try:
            self.update_progress(state, 0.2, "json_loading")
            
            # JSON 데이터 로드
            json_data = self._load_json_data(state)
            state['raw_data'] = json_data
            
            self.update_progress(state, 0.5, "json_extracting")
            
            # JSON에서 텍스트 추출
            raw_content = self.extract_content(state)
            state['raw_content'] = raw_content
            
            self.update_progress(state, 0.7, "json_preprocessing")
            
            # 텍스트 전처리
            processed_text = self.preprocess_text(raw_content)
            
            # 제목 추출
            title = self._extract_title_from_json(json_data, state)
            
            self.update_progress(state, 0.9, "json_structuring")
            
            # ProcessedContent 생성
            processed_content = self.create_processed_content(
                title=title,
                content=processed_text,
                state=state
            )
            
            state['processed_content'] = processed_content
            state['cache_key'] = self.generate_cache_key(state['input_data'])
            
            self.update_progress(state, 1.0, "json_completed")
            
        except Exception as e:
            self.add_error(state, f"JSON 처리 중 오류 발생: {str(e)}")
        
        return state
    
    def _load_json_data(self, state: DataProcessingState) -> Dict[str, Any]:
        """
        JSON 데이터 로드
        
        Args:
            state: 현재 상태
            
        Returns:
            Dict: JSON 데이터
        """
        input_data = state['input_data']
        
        if isinstance(input_data, dict):
            # 이미 딕셔너리 형태인 경우
            return input_data
        
        elif isinstance(input_data, (str, Path)):
            input_str = str(input_data)
            
            # 파일 경로인 경우
            if self._is_file_path(input_str):
                path = Path(input_str)
                if not path.exists():
                    raise FileNotFoundError(f"JSON 파일을 찾을 수 없습니다: {path}")
                
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            # JSON 문자열인 경우
            else:
                try:
                    return json.loads(input_str)
                except json.JSONDecodeError as e:
                    raise ValueError(f"유효하지 않은 JSON 문자열입니다: {str(e)}")
        
        else:
            raise ValueError(f"지원하지 않는 입력 타입입니다: {type(input_data)}")
    
    def _is_file_path(self, input_str: str) -> bool:
        """파일 경로인지 확인"""
        try:
            path = Path(input_str)
            return (path.exists() or 
                   '/' in input_str or 
                   '\\' in input_str or 
                   path.suffix == '.json')
        except:
            return False
    
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
        
        # 의료 가이드라인 관련 필드들에서 우선 추출
        priority_fields = [
            'content', 'text', 'body', 'description', 'guideline_text',
            'recommendations', 'procedures', 'treatment_guidelines',
            'clinical_content', 'medical_content', 'guideline_content'
        ]
        
        # 우선순위 필드에서 텍스트 추출
        extracted_text = self._extract_text_from_fields(json_data, priority_fields)
        
        if extracted_text.strip():
            return extracted_text
        
        # 우선순위 필드에서 찾지 못한 경우 전체 구조를 텍스트로 변환
        return self._convert_json_to_readable_text(json_data)
    
    def _extract_text_from_fields(self, data: Any, target_fields: list) -> str:
        """
        지정된 필드들에서 텍스트 추출
        
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
                            elif isinstance(item, dict):
                                text_parts.append(self._extract_text_from_fields(item, target_fields))
                    elif isinstance(value, dict):
                        text_parts.append(self._extract_text_from_fields(value, target_fields))
                else:
                    # 중첩된 구조에서도 찾기
                    if isinstance(value, (dict, list)):
                        nested_text = self._extract_text_from_fields(value, target_fields)
                        if nested_text.strip():
                            text_parts.append(nested_text)
        
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    text_parts.append(self._extract_text_from_fields(item, target_fields))
                elif isinstance(item, str):
                    text_parts.append(item)
        
        return '\n'.join(filter(lambda x: x.strip(), text_parts))
    
    def _convert_json_to_readable_text(self, data: Dict[str, Any]) -> str:
        """
        JSON 데이터를 읽기 가능한 텍스트로 변환
        
        Args:
            data: JSON 데이터
            
        Returns:
            str: 변환된 텍스트
        """
        text_parts = []
        
        # 제목 정보
        title_fields = ['title', 'name', 'guideline_title', 'document_title', 'subject']
        for field in title_fields:
            if field in data and isinstance(data[field], str):
                text_parts.append(f"# {data[field]}\n")
                break
        
        # 메타 정보
        meta_fields = ['version', 'date', 'author', 'organization', 'category']
        meta_info = []
        for field in meta_fields:
            if field in data and isinstance(data[field], str):
                meta_info.append(f"**{field.title()}**: {data[field]}")
        
        if meta_info:
            text_parts.append('\n'.join(meta_info) + '\n')
        
        # 주요 콘텐츠 섹션들
        self._add_section_content(data, text_parts, 'summary', '## 요약')
        self._add_section_content(data, text_parts, 'overview', '## 개요')
        self._add_section_content(data, text_parts, 'description', '## 설명')
        self._add_section_content(data, text_parts, 'background', '## 배경')
        
        # 가이드라인 관련 섹션들
        self._add_section_content(data, text_parts, 'guidelines', '## 가이드라인')
        self._add_section_content(data, text_parts, 'recommendations', '## 권고사항')
        self._add_section_content(data, text_parts, 'procedures', '## 절차')
        self._add_section_content(data, text_parts, 'contraindications', '## 금기사항')
        self._add_section_content(data, text_parts, 'side_effects', '## 부작용')
        self._add_section_content(data, text_parts, 'dosage', '## 용법/용량')
        
        # 기타 긴 텍스트 필드들
        processed_keys = {
            'title', 'name', 'guideline_title', 'document_title', 'subject',
            'version', 'date', 'author', 'organization', 'category',
            'summary', 'overview', 'description', 'background',
            'guidelines', 'recommendations', 'procedures', 
            'contraindications', 'side_effects', 'dosage'
        }
        
        for key, value in data.items():
            if key not in processed_keys:
                if isinstance(value, str) and len(value) > 50:
                    text_parts.append(f"## {key.replace('_', ' ').title()}\n{value}\n")
                elif isinstance(value, list):
                    list_content = self._format_list_content(value, key)
                    if list_content:
                        text_parts.append(f"## {key.replace('_', ' ').title()}\n{list_content}\n")
        
        return '\n'.join(text_parts)
    
    def _add_section_content(self, data: Dict[str, Any], text_parts: list, key: str, header: str):
        """섹션 콘텐츠 추가"""
        if key not in data:
            return
        
        value = data[key]
        
        if isinstance(value, str):
            text_parts.append(f"{header}\n{value}\n")
        elif isinstance(value, list):
            content = self._format_list_content(value, key)
            if content:
                text_parts.append(f"{header}\n{content}\n")
        elif isinstance(value, dict):
            content = self._format_dict_content(value)
            if content:
                text_parts.append(f"{header}\n{content}\n")
    
    def _format_list_content(self, items: list, context: str = "") -> str:
        """리스트 콘텐츠 포맷팅"""
        if not items:
            return ""
        
        formatted_items = []
        
        for i, item in enumerate(items, 1):
            if isinstance(item, str):
                formatted_items.append(f"{i}. {item}")
            elif isinstance(item, dict):
                if 'title' in item and 'content' in item:
                    formatted_items.append(f"{i}. **{item['title']}**: {item['content']}")
                elif 'name' in item and 'description' in item:
                    formatted_items.append(f"{i}. **{item['name']}**: {item['description']}")
                else:
                    # 딕셔너리의 첫 번째 값을 사용
                    if item:
                        first_key = list(item.keys())[0]
                        formatted_items.append(f"{i}. {item[first_key]}")
        
        return '\n'.join(formatted_items)
    
    def _format_dict_content(self, data: dict) -> str:
        """딕셔너리 콘텐츠 포맷팅"""
        if not data:
            return ""
        
        formatted_items = []
        
        for key, value in data.items():
            if isinstance(value, str):
                formatted_items.append(f"**{key.replace('_', ' ').title()}**: {value}")
            elif isinstance(value, list) and value:
                list_content = self._format_list_content(value)
                if list_content:
                    formatted_items.append(f"**{key.replace('_', ' ').title()}**:\n{list_content}")
        
        return '\n'.join(formatted_items)
    
    def _extract_title_from_json(self, json_data: Dict[str, Any], state: DataProcessingState) -> str:
        """
        JSON 데이터에서 제목 추출
        
        Args:
            json_data: JSON 데이터
            state: 현재 상태
            
        Returns:
            str: 추출된 제목
        """
        # 제목 필드들
        title_fields = [
            'title', 'name', 'guideline_title', 'document_title', 
            'subject', 'heading', 'guideline_name'
        ]
        
        for field in title_fields:
            if field in json_data and isinstance(json_data[field], str):
                return json_data[field].strip()
        
        # 파일 경로에서 제목 추출
        if isinstance(state['input_data'], (str, Path)):
            input_str = str(state['input_data'])
            if self._is_file_path(input_str):
                path = Path(input_str)
                return path.stem.replace('_', ' ').replace('-', ' ').title()
        
        return "의료 가이드라인 문서"
