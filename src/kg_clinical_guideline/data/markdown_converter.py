"""
Markdown converter for processed content.
"""

import re
from typing import Dict, Any
from .state import ProcessedContent


class MarkdownConverter:
    """ProcessedContent를 마크다운으로 변환하는 클래스"""
    
    def __init__(self, processing_options: Dict[str, Any] = None):
        """
        컨버터 초기화
        
        Args:
            processing_options: 처리 옵션
        """
        self.processing_options = processing_options or {}
        self.include_metadata = self.processing_options.get('include_metadata', False)
        self.include_toc = self.processing_options.get('include_toc', False)
    
    def convert(self, processed_content: ProcessedContent) -> str:
        """
        ProcessedContent를 마크다운으로 변환
        
        Args:
            processed_content: 처리된 콘텐츠
            
        Returns:
            str: 마크다운 문자열
        """
        markdown_parts = []
        
        # 제목 추가
        markdown_parts.append(f"# {processed_content.title}\n")
        
        # 메타데이터 추가 (옵션)
        if self.include_metadata and processed_content.metadata:
            metadata_md = self._format_metadata(processed_content.metadata)
            if metadata_md:
                markdown_parts.append(metadata_md)
        
        # 목차 추가 (옵션)
        if self.include_toc and processed_content.sections:
            toc_md = self._generate_toc(processed_content.sections)
            if toc_md:
                markdown_parts.append(toc_md)
        
        # 섹션별 콘텐츠 추가
        if processed_content.sections:
            sections_md = self._format_sections(processed_content.sections)
            markdown_parts.append(sections_md)
        else:
            # 섹션이 없는 경우 전체 콘텐츠 추가
            content_md = self._format_content(processed_content.content)
            markdown_parts.append(content_md)
        
        # 소스 정보 추가 (옵션)
        if processed_content.source_info:
            source_md = self._format_source_info(processed_content.source_info)
            if source_md:
                markdown_parts.append(source_md)
        
        return "\n".join(markdown_parts)
    
    def _format_metadata(self, metadata: Dict[str, Any]) -> str:
        """메타데이터를 마크다운으로 포맷"""
        if not metadata:
            return ""
        
        lines = ["## 📋 문서 정보\n"]
        
        # 중요한 메타데이터만 표시
        important_fields = {
            'processor_type': '처리기',
            'input_type': '입력 타입',
            'character_count': '문자 수',
            'word_count': '단어 수',
            'file_name': '파일명',
            'source_url': '출처 URL',
            's3_bucket': 'S3 버킷',
            'domain': '도메인'
        }
        
        for key, label in important_fields.items():
            if key in metadata and metadata[key]:
                value = metadata[key]
                if isinstance(value, (int, float)):
                    if key in ['character_count', 'word_count']:
                        value = f"{value:,}"
                lines.append(f"- **{label}**: {value}")
        
        return "\n".join(lines) + "\n" if len(lines) > 1 else ""
    
    def _generate_toc(self, sections: list) -> str:
        """목차 생성"""
        if not sections:
            return ""
        
        lines = ["## 📑 목차\n"]
        
        for i, section in enumerate(sections, 1):
            title = section.get('title', f'섹션 {i}')
            level = section.get('level', 1)
            
            # 마크다운 링크 생성 (제목을 링크로 변환)
            link = title.lower().replace(' ', '-').replace('/', '').replace('(', '').replace(')', '')
            link = re.sub(r'[^\w\-가-힣]', '', link)
            
            indent = "  " * (level - 1)
            lines.append(f"{indent}- [{title}](#{link})")
        
        return "\n".join(lines) + "\n"
    
    def _format_sections(self, sections: list) -> str:
        """섹션들을 마크다운으로 포맷"""
        if not sections:
            return ""
        
        formatted_sections = []
        
        for section in sections:
            section_md = self._format_single_section(section)
            if section_md:
                formatted_sections.append(section_md)
        
        return "\n".join(formatted_sections)
    
    def _format_single_section(self, section: Dict[str, Any]) -> str:
        """단일 섹션을 마크다운으로 포맷"""
        title = section.get('title', '').strip()
        content = section.get('content', '').strip()
        level = section.get('level', 2)
        
        if not content:
            return ""
        
        # 헤딩 레벨 조정 (최소 2, 최대 6)
        heading_level = max(2, min(level + 1, 6))
        heading = "#" * heading_level
        
        # 제목이 이미 마크다운 헤딩인지 확인
        if title and not title.startswith('#'):
            section_parts = [f"{heading} {title}\n"]
        else:
            section_parts = []
        
        # 콘텐츠 포맷팅
        formatted_content = self._format_content(content)
        section_parts.append(formatted_content)
        
        return "\n".join(section_parts) + "\n"
    
    def _format_content(self, content: str) -> str:
        """콘텐츠를 마크다운으로 포맷"""
        if not content:
            return ""
        
        # 이미 마크다운 형식인지 확인
        if self._is_already_markdown(content):
            return content
        
        # 텍스트를 마크다운으로 변환
        formatted_content = self._convert_to_markdown(content)
        
        return formatted_content
    
    def _is_already_markdown(self, text: str) -> bool:
        """텍스트가 이미 마크다운 형식인지 확인"""
        markdown_indicators = [
            r'^#{1,6}\s',  # 헤딩
            r'^\*\s',      # 리스트
            r'^-\s',       # 리스트
            r'^\d+\.\s',   # 번호 리스트
            r'\*\*.*\*\*', # 볼드
            r'\[.*\]\(.*\)', # 링크
        ]
        
        lines = text.split('\n')[:10]  # 첫 10줄만 검사
        
        for line in lines:
            for pattern in markdown_indicators:
                if re.search(pattern, line.strip(), re.MULTILINE):
                    return True
        
        return False
    
    def _convert_to_markdown(self, text: str) -> str:
        """일반 텍스트를 마크다운으로 변환"""
        lines = text.split('\n')
        formatted_lines = []
        
        in_list = False
        
        for line in lines:
            line = line.strip()
            
            if not line:
                formatted_lines.append('')
                in_list = False
                continue
            
            # 의료 용어 강조 (이미 처리되지 않은 경우)
            if '**' not in line:
                line = self._emphasize_medical_terms(line)
            
            # 리스트 항목 감지
            if self._is_list_item(line):
                if not line.startswith(('-', '*', '+')):
                    line = f"- {line}"
                in_list = True
            elif in_list and line and not line.startswith(('-', '*', '+')):
                # 리스트가 끝난 경우
                in_list = False
            
            # 번호 리스트 정규화
            line = re.sub(r'^(\d+)[\.\)]\s*(.+)', r'\1. \2', line)
            
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def _emphasize_medical_terms(self, line: str) -> str:
        """의료 용어 강조"""
        # 중요한 의료 키워드 강조
        important_terms = [
            r'(주의사항|금기사항|부작용|경고|위험|응급|즉시|심각한|중증|생명위험|알레르기)',
            r'(용법|용량|복용법|투여|처방)',
            r'(진단|치료|수술|시술|검사|처치)',
            r'(\d+\s*(?:mg|g|ml|정|캡슐|알)(?:\s*\/\s*\d+\s*(?:kg|회|일|시간))?)'
        ]
        
        for pattern in important_terms:
            line = re.sub(pattern, r'**\1**', line, flags=re.IGNORECASE)
        
        return line
    
    def _is_list_item(self, line: str) -> bool:
        """라인이 리스트 항목인지 확인"""
        list_patterns = [
            r'^[-*+•]\s',     # 기본 리스트
            r'^\d+[\.\)]\s',  # 번호 리스트
            r'^[가-힣]\.\s',   # 한글 번호 리스트
            r'^[(]\d+[)]\s',  # 괄호 번호
            r'^[①-⑳]\s',     # 원 숫자
        ]
        
        for pattern in list_patterns:
            if re.match(pattern, line):
                return True
        
        # 의료 가이드라인 특화 패턴
        medical_list_patterns = [
            r'^[가-힣]+\s*[:：]\s',  # "적응증: ", "용법:" 등
            r'^\d+차\s*(치료|요법|처방)',  # "1차 치료", "2차 요법" 등
        ]
        
        for pattern in medical_list_patterns:
            if re.match(pattern, line):
                return True
        
        return False
    
    def _format_source_info(self, source_info: Dict[str, Any]) -> str:
        """소스 정보를 마크다운으로 포맷"""
        if not source_info:
            return ""
        
        lines = ["---", "## 📎 출처 정보\n"]
        
        input_type = source_info.get('input_type', 'unknown')
        input_data = source_info.get('input_data', '')
        
        lines.append(f"- **입력 타입**: {input_type}")
        lines.append(f"- **소스**: {input_data}")
        
        return "\n".join(lines)
