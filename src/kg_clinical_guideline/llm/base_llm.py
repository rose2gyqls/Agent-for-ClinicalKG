"""
Base LLM interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """LLM 응답 데이터 클래스"""
    content: str
    usage: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class LLMConfig:
    """LLM 설정 데이터 클래스"""
    model_name: str
    api_key: Optional[str] = None
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    safety_settings: Optional[Dict[str, Any]] = None


class BaseLLM(ABC):
    """LLM 기본 인터페이스"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        self._initialize_client()
    
    @abstractmethod
    def _initialize_client(self):
        """LLM 클라이언트 초기화"""
        pass
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """
        텍스트 생성
        
        Args:
            prompt: 입력 프롬프트
            **kwargs: 추가 매개변수
            
        Returns:
            LLMResponse: 생성된 응답
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """LLM 사용 가능 여부 확인"""
        pass
    
    def generate_with_template(self, template: str, **template_vars) -> LLMResponse:
        """
        템플릿을 사용한 텍스트 생성
        
        Args:
            template: 프롬프트 템플릿
            **template_vars: 템플릿 변수들
            
        Returns:
            LLMResponse: 생성된 응답
        """
        formatted_prompt = template.format(**template_vars)
        return self.generate(formatted_prompt)
    
    def batch_generate(self, prompts: List[str], **kwargs) -> List[LLMResponse]:
        """
        배치 텍스트 생성
        
        Args:
            prompts: 프롬프트 리스트
            **kwargs: 추가 매개변수
            
        Returns:
            List[LLMResponse]: 생성된 응답 리스트
        """
        responses = []
        for prompt in prompts:
            response = self.generate(prompt, **kwargs)
            responses.append(response)
        return responses 