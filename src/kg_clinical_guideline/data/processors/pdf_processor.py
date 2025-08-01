"""
PDF file processor.
"""

import io
from pathlib import Path
from typing import Dict, Any
import requests

from .base_processor import BaseProcessor
from ..state import DataProcessingState, ProcessingStatus


class PDFProcessor(BaseProcessor):
    """PDF 파일 프로세서"""
    
    def process(self, state: DataProcessingState) -> DataProcessingState:
        """
        PDF 파일 처리
        
        Args:
            state: 현재 상태
            
        Returns:
            DataProcessingState: 업데이트된 상태
        """
        try:
            self.update_progress(state, 0.2, "pdf_loading")
            
            # PDF 콘텐츠 추출
            raw_content = self.extract_content(state)
            state['raw_content'] = raw_content
            
            self.update_progress(state, 0.6, "pdf_preprocessing")
            
            # 텍스트 전처리
            processed_text = self.preprocess_text(raw_content)
            
            # 제목 추출
            title = self._extract_title(processed_text, state)
            
            self.update_progress(state, 0.8, "pdf_structuring")
            
            # ProcessedContent 생성
            processed_content = self.create_processed_content(
                title=title,
                content=processed_text,
                state=state
            )
            
            state['processed_content'] = processed_content
            state['cache_key'] = self.generate_cache_key(state['input_data'])
            
            self.update_progress(state, 1.0, "pdf_completed")
            
        except Exception as e:
            self.add_error(state, f"PDF 처리 중 오류 발생: {str(e)}")
        
        return state
    
    def extract_content(self, state: DataProcessingState) -> str:
        """
        PDF에서 텍스트 추출
        
        Args:
            state: 현재 상태
            
        Returns:
            str: 추출된 텍스트
        """
        input_data = state['input_data']
        
        try:
            # PyPDF2를 사용한 PDF 텍스트 추출
            try:
                import PyPDF2
                return self._extract_with_pypdf2(input_data)
            except ImportError:
                pass
            
            # pdfplumber를 사용한 추출 시도
            try:
                import pdfplumber
                return self._extract_with_pdfplumber(input_data)
            except ImportError:
                pass
            
            # PDF 라이브러리가 없는 경우 경고
            self.add_warning(state, "PDF 처리 라이브러리가 설치되지 않았습니다. 기본 텍스트 처리를 시도합니다.")
            
            # 파일이 텍스트 파일인 경우 직접 읽기 시도
            if isinstance(input_data, (str, Path)):
                path = Path(input_data)
                if path.exists():
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            return f.read()
                    except UnicodeDecodeError:
                        with open(path, 'r', encoding='latin-1') as f:
                            return f.read()
            
            return ""
            
        except Exception as e:
            raise Exception(f"PDF 콘텐츠 추출 실패: {str(e)}")
    
    def _extract_with_pypdf2(self, input_data) -> str:
        """PyPDF2를 사용한 텍스트 추출"""
        import PyPDF2
        
        content = ""
        
        if isinstance(input_data, (str, Path)):
            # 로컬 파일
            with open(input_data, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    content += page.extract_text() + "\n"
        
        return content
    
    def _extract_with_pdfplumber(self, input_data) -> str:
        """pdfplumber를 사용한 텍스트 추출"""
        import pdfplumber
        
        content = ""
        
        if isinstance(input_data, (str, Path)):
            # 로컬 파일
            with pdfplumber.open(input_data) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        content += page_text + "\n"
        
        return content
    
    def _extract_title(self, content: str, state: DataProcessingState) -> str:
        """
        PDF에서 제목 추출
        
        Args:
            content: 추출된 텍스트
            state: 현재 상태
            
        Returns:
            str: 추출된 제목
        """
        # 파일명에서 제목 추출
        if isinstance(state['input_data'], (str, Path)):
            file_path = Path(state['input_data'])
            base_title = file_path.stem.replace('_', ' ').replace('-', ' ')
        else:
            base_title = "의료 가이드라인 문서"
        
        # 텍스트 첫 부분에서 제목 후보 찾기
        lines = content.split('\n')[:10]  # 첫 10줄에서 찾기
        
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 100:  # 적절한 길이의 제목
                # 특별한 키워드가 포함된 경우
                if any(keyword in line.lower() for keyword in ['guideline', '가이드라인', 'protocol', '지침', 'standard', '표준']):
                    return line
        
        return base_title
    
    def extract_metadata(self, state: DataProcessingState) -> Dict[str, Any]:
        """PDF 특화 메타데이터 추출"""
        metadata = super().extract_metadata(state)
        
        # PDF 특화 정보 추가
        if isinstance(state['input_data'], (str, Path)):
            file_path = Path(state['input_data'])
            metadata.update({
                'file_name': file_path.name,
                'file_size': file_path.stat().st_size if file_path.exists() else 0,
                'file_extension': file_path.suffix
            })
        
        return metadata
