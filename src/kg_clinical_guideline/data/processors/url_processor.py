"""
URL content processor.
"""

import requests
from typing import Dict, Any
from urllib.parse import urlparse
import time

from .base_processor import BaseProcessor
from ..state import DataProcessingState


class URLProcessor(BaseProcessor):
    """URL 콘텐츠 프로세서"""
    
    def __init__(self, processing_options: Dict[str, Any] = None):
        super().__init__(processing_options)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.timeout = processing_options.get('timeout', 30) if processing_options else 30
    
    def process(self, state: DataProcessingState) -> DataProcessingState:
        """
        URL 콘텐츠 처리
        
        Args:
            state: 현재 상태
            
        Returns:
            DataProcessingState: 업데이트된 상태
        """
        try:
            self.update_progress(state, 0.1, "url_connecting")
            
            # URL 유효성 검사
            url = str(state['input_data'])
            if not self._is_valid_url(url):
                self.add_error(state, f"유효하지 않은 URL입니다: {url}")
                return state
            
            self.update_progress(state, 0.3, "url_downloading")
            
            # 콘텐츠 다운로드
            content_type, raw_content = self._download_content(url)
            state['raw_content'] = raw_content
            
            # URL 메타데이터 저장
            parsed_url = urlparse(url)
            state['input_metadata'].update({
                'url': url,
                'domain': parsed_url.netloc,
                'content_type': content_type,
                'url_path': parsed_url.path
            })
            
            self.update_progress(state, 0.6, "url_extracting")
            
            # 콘텐츠 타입에 따른 추출
            extracted_content = self._extract_by_content_type(raw_content, content_type)
            
            self.update_progress(state, 0.8, "url_preprocessing")
            
            # 텍스트 전처리
            processed_text = self.preprocess_text(extracted_content)
            
            # 제목 추출
            title = self._extract_title_from_content(processed_text, url)
            
            # ProcessedContent 생성
            processed_content = self.create_processed_content(
                title=title,
                content=processed_text,
                state=state
            )
            
            state['processed_content'] = processed_content
            state['cache_key'] = self.generate_cache_key(url)
            
            self.update_progress(state, 1.0, "url_completed")
            
        except Exception as e:
            self.add_error(state, f"URL 처리 중 오류 발생: {str(e)}")
        
        return state
    
    def extract_content(self, state: DataProcessingState) -> str:
        """
        URL에서 콘텐츠 추출 (process 메소드에서 이미 처리됨)
        
        Args:
            state: 현재 상태
            
        Returns:
            str: 추출된 콘텐츠
        """
        return state.get('raw_content', '')
    
    def _is_valid_url(self, url: str) -> bool:
        """URL 유효성 검사"""
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc)
        except:
            return False
    
    def _download_content(self, url: str) -> tuple[str, str]:
        """
        URL에서 콘텐츠 다운로드
        
        Args:
            url: 대상 URL
            
        Returns:
            tuple: (content_type, content)
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            
            # 텍스트 콘텐츠 디코딩
            if 'charset=' in content_type:
                encoding = content_type.split('charset=')[1].split(';')[0]
            else:
                encoding = response.encoding or 'utf-8'
            
            try:
                content = response.content.decode(encoding)
            except UnicodeDecodeError:
                content = response.content.decode('utf-8', errors='ignore')
            
            return content_type, content
            
        except requests.exceptions.Timeout:
            raise Exception(f"URL 다운로드 시간 초과: {url}")
        except requests.exceptions.ConnectionError:
            raise Exception(f"URL 연결 실패: {url}")
        except requests.exceptions.HTTPError as e:
            raise Exception(f"HTTP 오류 {e.response.status_code}: {url}")
        except Exception as e:
            raise Exception(f"URL 다운로드 실패: {str(e)}")
    
    def _extract_by_content_type(self, content: str, content_type: str) -> str:
        """
        콘텐츠 타입에 따른 텍스트 추출
        
        Args:
            content: 원본 콘텐츠
            content_type: MIME 타입
            
        Returns:
            str: 추출된 텍스트
        """
        if 'html' in content_type:
            return self._extract_from_html(content)
        elif 'json' in content_type:
            return self._extract_from_json_text(content)
        elif 'xml' in content_type:
            return self._extract_from_xml(content)
        else:
            # 일반 텍스트로 처리
            return content
    
    def _extract_from_html(self, html_content: str) -> str:
        """
        HTML에서 텍스트 추출
        
        Args:
            html_content: HTML 콘텐츠
            
        Returns:
            str: 추출된 텍스트
        """
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 불필요한 태그 제거
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            # 메인 콘텐츠 영역 찾기
            content_selectors = [
                'main', 'article', '[role="main"]', '.content', '.main-content',
                '#content', '#main-content', '.post-content', '.entry-content'
            ]
            
            main_content = None
            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            if main_content:
                text = main_content.get_text(separator='\n', strip=True)
            else:
                # 전체 body에서 추출
                body = soup.find('body')
                if body:
                    text = body.get_text(separator='\n', strip=True)
                else:
                    text = soup.get_text(separator='\n', strip=True)
            
            return text
            
        except ImportError:
            # BeautifulSoup가 없는 경우 간단한 HTML 태그 제거
            import re
            text = re.sub(r'<[^>]+>', '', html_content)
            text = re.sub(r'&[a-zA-Z0-9#]+;', ' ', text)  # HTML 엔티티 제거
            return text
        except Exception:
            # HTML 파싱 실패 시 원본 반환
            return html_content
    
    def _extract_from_json_text(self, json_content: str) -> str:
        """
        JSON 문자열에서 텍스트 추출
        
        Args:
            json_content: JSON 문자열
            
        Returns:
            str: 추출된 텍스트
        """
        try:
            import json
            data = json.loads(json_content)
            
            # JSON 프로세서와 동일한 로직 사용
            from .json_processor import JsonProcessor
            temp_processor = JsonProcessor()
            
            # 임시 상태 생성
            temp_state = {'raw_data': data}
            return temp_processor.extract_content(temp_state)
            
        except:
            return json_content
    
    def _extract_from_xml(self, xml_content: str) -> str:
        """
        XML에서 텍스트 추출
        
        Args:
            xml_content: XML 콘텐츠
            
        Returns:
            str: 추출된 텍스트
        """
        try:
            from xml.etree import ElementTree as ET
            
            root = ET.fromstring(xml_content)
            
            # 모든 텍스트 노드 추출
            texts = []
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    texts.append(elem.text.strip())
            
            return '\n'.join(texts)
            
        except:
            # XML 파싱 실패 시 태그만 제거
            import re
            text = re.sub(r'<[^>]+>', '', xml_content)
            return text
    
    def _extract_title_from_content(self, content: str, url: str) -> str:
        """
        콘텐츠에서 제목 추출
        
        Args:
            content: 텍스트 콘텐츠
            url: 원본 URL
            
        Returns:
            str: 추출된 제목
        """
        # 콘텐츠에서 제목 추출 시도
        lines = content.split('\n')[:10]
        
        for line in lines:
            line = line.strip()
            if (len(line) > 10 and len(line) < 150 and
                any(keyword in line.lower() for keyword in [
                    'guideline', '가이드라인', 'protocol', '지침', 
                    'standard', '표준', 'recommendation', '권고'
                ])):
                return line
        
        # URL에서 제목 추출
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip('/').split('/')
        
        if path_parts and path_parts[-1]:
            filename = path_parts[-1]
            # 확장자 제거
            if '.' in filename:
                filename = filename.rsplit('.', 1)[0]
            # 언더스코어와 하이픈을 공백으로 변환
            title = filename.replace('_', ' ').replace('-', ' ').title()
            if len(title) > 5:
                return title
        
        # 도메인에서 제목 생성
        domain = parsed_url.netloc.replace('www.', '')
        return f"{domain}의 의료 가이드라인"
    
    def extract_metadata(self, state: DataProcessingState) -> Dict[str, Any]:
        """URL 특화 메타데이터 추출"""
        metadata = super().extract_metadata(state)
        
        # URL 특화 정보 추가
        url_metadata = state.get('input_metadata', {})
        metadata.update({
            'source_url': url_metadata.get('url'),
            'domain': url_metadata.get('domain'),
            'content_type': url_metadata.get('content_type'),
            'url_path': url_metadata.get('url_path')
        })
        
        return metadata
