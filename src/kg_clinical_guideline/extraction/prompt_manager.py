"""
Prompt management for LLM interactions.
"""

from typing import Dict, Any, Optional
from pathlib import Path
import os


class PromptManager:
    """프롬프트 템플릿 관리 클래스"""
    
    def __init__(self, prompt_dir: Optional[str] = None):
        """
        프롬프트 매니저 초기화
        
        Args:
            prompt_dir: 프롬프트 템플릿 디렉토리 경로
        """
        if prompt_dir is None:
            # 기본 프롬프트 디렉토리 설정
            current_dir = Path(__file__).parent.parent
            self.prompt_dir = current_dir / "prompt"
        else:
            self.prompt_dir = Path(prompt_dir)
        
        self._templates = {}
        self._load_templates()
    
    def _load_templates(self):
        """프롬프트 템플릿 파일들을 로드"""
        if not self.prompt_dir.exists():
            print(f"프롬프트 디렉토리를 찾을 수 없습니다: {self.prompt_dir}")
            return
        
        for template_file in self.prompt_dir.glob("*.txt"):
            template_name = template_file.stem
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    self._templates[template_name] = f.read().strip()
                print(f"프롬프트 템플릿 로드됨: {template_name}")
            except Exception as e:
                print(f"프롬프트 템플릿 로드 실패 {template_name}: {str(e)}")
    
    def get_template(self, template_name: str) -> str:
        """
        프롬프트 템플릿 가져오기
        
        Args:
            template_name: 템플릿 이름
            
        Returns:
            str: 프롬프트 템플릿
        """
        if template_name not in self._templates:
            raise ValueError(f"프롬프트 템플릿을 찾을 수 없습니다: {template_name}")
        
        return self._templates[template_name]
    
    def format_template(self, template_name: str, **kwargs) -> str:
        """
        프롬프트 템플릿 포매팅
        
        Args:
            template_name: 템플릿 이름
            **kwargs: 템플릿 변수들
            
        Returns:
            str: 포매팅된 프롬프트
        """
        template = self.get_template(template_name)
        return template.format(**kwargs)
    
    def list_templates(self) -> list:
        """사용 가능한 템플릿 목록 반환"""
        return list(self._templates.keys())
    
    def add_template(self, template_name: str, template_content: str):
        """
        프롬프트 템플릿 추가
        
        Args:
            template_name: 템플릿 이름
            template_content: 템플릿 내용
        """
        self._templates[template_name] = template_content
    
    def save_template(self, template_name: str, template_content: str):
        """
        프롬프트 템플릿을 파일로 저장
        
        Args:
            template_name: 템플릿 이름
            template_content: 템플릿 내용
        """
        template_file = self.prompt_dir / f"{template_name}.txt"
        
        # 디렉토리가 없으면 생성
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        
        with open(template_file, 'w', encoding='utf-8') as f:
            f.write(template_content)
        
        # 메모리에도 추가
        self._templates[template_name] = template_content
        print(f"프롬프트 템플릿 저장됨: {template_name}")
    
    @classmethod
    def create_default(cls) -> 'PromptManager':
        """기본 설정으로 프롬프트 매니저 생성"""
        return cls() 