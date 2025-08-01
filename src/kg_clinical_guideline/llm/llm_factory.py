"""
LLM Factory for creating LLM instances.
"""

from typing import Optional, Dict, Any
from enum import Enum

from .base_llm import BaseLLM, LLMConfig
from .gemini_llm import GeminiLLM


class LLMType(Enum):
    """지원되는 LLM 타입"""
    GEMINI = "gemini"


class LLMFactory:
    """LLM 인스턴스 생성 팩토리"""
    
    _llm_classes = {
        LLMType.GEMINI: GeminiLLM,
    }
    
    @classmethod
    def create_llm(
        cls, 
        llm_type: LLMType, 
        config: Optional[LLMConfig] = None,
        **kwargs
    ) -> BaseLLM:
        """
        LLM 인스턴스 생성
        
        Args:
            llm_type: LLM 타입
            config: LLM 설정
            **kwargs: 추가 매개변수
            
        Returns:
            BaseLLM: 생성된 LLM 인스턴스
        """
        if llm_type not in cls._llm_classes:
            raise ValueError(f"지원되지 않는 LLM 타입: {llm_type}")
        
        llm_class = cls._llm_classes[llm_type]
        
        if config:
            return llm_class(config)
        else:
            return llm_class(**kwargs)
    
    @classmethod
    def create_gemini(
        cls,
        model_name: str = "gemini-2.0-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> GeminiLLM:
        """
        Gemini LLM 인스턴스 생성
        
        Args:
            model_name: 모델명
            api_key: API 키
            temperature: 온도 설정
            max_tokens: 최대 토큰 수
            **kwargs: 추가 매개변수
            
        Returns:
            GeminiLLM: Gemini LLM 인스턴스
        """
        # API 키가 None이면 환경 변수에서 가져오기
        if api_key is None:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("GEMINI_API_KEY")
        
        config = LLMConfig(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return GeminiLLM(config)
    
    @classmethod
    def get_default_llm(cls) -> BaseLLM:
        """기본 LLM 인스턴스 반환 (Gemini)"""
        return cls.create_gemini()
    
    @classmethod
    def list_available_llms(cls) -> Dict[str, str]:
        """사용 가능한 LLM 목록 반환"""
        return {llm_type.value: llm_class.__name__ for llm_type, llm_class in cls._llm_classes.items()} 