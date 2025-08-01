"""
Google Gemini LLM implementation.
"""

import google.generativeai as genai
from typing import Dict, Any, Optional
import json
import time
import os
from dotenv import load_dotenv

from .base_llm import BaseLLM, LLMResponse, LLMConfig

# 안전한 환경 변수 로딩
load_dotenv()

try:
    from ..config import config
except:
    # config 로딩 실패 시 직접 환경 변수 사용
    class Config:
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    config = Config()


class GeminiLLM(BaseLLM):
    """Google Gemini LLM 구현체"""
    
    def __init__(self, config_obj: Optional[LLMConfig] = None):
        # 기본 설정 생성
        if config_obj is None:
            # 직접 환경 변수에서 API 키 가져오기
            api_key = os.getenv("GEMINI_API_KEY")
            
            if not api_key:
                # 한번 더 시도
                load_dotenv()
                api_key = os.getenv("GEMINI_API_KEY")
            
            config_obj = LLMConfig(
                model_name="gemini-1.5-flash",
                api_key=api_key,
                temperature=0.1,
                max_tokens=8192
            )
        
        super().__init__(config_obj)
        
    def _initialize_client(self):
        """Gemini 클라이언트 초기화"""
        try:
            if not self.config.api_key:
                print("❌ Gemini API 키가 설정되지 않았습니다.")
                print("💡 해결 방법:")
                print("   1. 프로젝트 루트에 .env 파일을 생성하세요")
                print("   2. .env 파일에 다음 내용을 추가하세요:")
                print("      GEMINI_API_KEY=your_actual_api_key_here")
                print("   3. Gemini API 키는 https://makersuite.google.com/app/apikey 에서 발급받을 수 있습니다")
                self.client = None
                return
            
            print(f"🔑 Gemini API 키 확인됨 (마지막 4자리: ...{self.config.api_key[-4:]})")
            
            # Gemini API 설정
            genai.configure(api_key=self.config.api_key)
            
            # 안전 설정
            safety_settings = self.config.safety_settings or {
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE", 
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE"
            }
            
            # 생성 설정
            generation_config = {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p or 0.95,
                "top_k": self.config.top_k or 40,
                "max_output_tokens": self.config.max_tokens or 8192,
            }
            
            # 모델 초기화
            self.client = genai.GenerativeModel(
                model_name=self.config.model_name,
                safety_settings=safety_settings,
                generation_config=generation_config
            )
            
            # 연결 테스트 (간단한 테스트)
            try:
                test_response = self.client.generate_content("Test")
                print(f"✅ Gemini LLM 초기화 성공: {self.config.model_name}")
            except Exception as test_error:
                print(f"⚠️ Gemini 연결 테스트 실패: {str(test_error)}")
                print("💡 API 키가 유효한지 확인하거나 인터넷 연결을 확인하세요")
                self.client = None
                return
            
        except Exception as e:
            print(f"❌ Gemini LLM 초기화 실패: {str(e)}")
            print("💡 상세 오류 정보를 확인하여 문제를 해결하세요")
            self.client = None
    
    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """
        Gemini를 사용한 텍스트 생성
        
        Args:
            prompt: 입력 프롬프트
            **kwargs: 추가 매개변수
            
        Returns:
            LLMResponse: 생성된 응답
        """
        if not self.client:
            raise Exception("Gemini 클라이언트가 초기화되지 않았습니다.")
        
        try:
            # 요청 시작 시간
            start_time = time.time()
            
            # 응답 생성
            response = self.client.generate_content(prompt)
            
            # 응답 시간 계산
            generation_time = time.time() - start_time
            
            # 응답 텍스트 추출
            if response.candidates and len(response.candidates) > 0:
                content = response.candidates[0].content.parts[0].text
                finish_reason = response.candidates[0].finish_reason.name if response.candidates[0].finish_reason else "STOP"
            else:
                content = ""
                finish_reason = "NO_CANDIDATES"
            
            # 사용량 정보 (Gemini 2.0 호환)
            usage_info = {
                "generation_time": generation_time,
            }
            
            # 사용량 메타데이터 안전하게 추출
            try:
                if hasattr(response, 'usage_metadata'):
                    usage_metadata = response.usage_metadata
                    if hasattr(usage_metadata, 'prompt_token_count'):
                        usage_info["prompt_token_count"] = usage_metadata.prompt_token_count
                    if hasattr(usage_metadata, 'candidates_token_count'):
                        usage_info["candidates_token_count"] = usage_metadata.candidates_token_count
                    if hasattr(usage_metadata, 'total_token_count'):
                        usage_info["total_token_count"] = usage_metadata.total_token_count
            except Exception as e:
                # 사용량 정보 추출 실패 시 기본값 사용
                usage_info.update({
                    "prompt_token_count": 0,
                    "candidates_token_count": 0,
                    "total_token_count": 0,
                    "usage_error": str(e)
                })
            
            return LLMResponse(
                content=content,
                usage=usage_info,
                model=self.config.model_name,
                finish_reason=finish_reason,
                metadata={
                    "safety_ratings": [
                        {
                            "category": rating.category.name,
                            "probability": rating.probability.name
                        } 
                        for rating in (response.candidates[0].safety_ratings if response.candidates else [])
                    ]
                }
            )
            
        except Exception as e:
            raise Exception(f"Gemini 텍스트 생성 실패: {str(e)}")
    
    def is_available(self) -> bool:
        """Gemini LLM 사용 가능 여부 확인"""
        return self.client is not None
    
    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        JSON 형식 응답 생성
        
        Args:
            prompt: 입력 프롬프트
            **kwargs: 추가 매개변수
            
        Returns:
            Dict: 파싱된 JSON 응답
        """
        # JSON 형식 요청을 위한 프롬프트 수정
        json_prompt = f"{prompt}\n\n응답은 반드시 유효한 JSON 형식으로만 제공해주세요. 다른 텍스트는 포함하지 마세요."
        
        response = self.generate(json_prompt, **kwargs)
        
        try:
            # JSON 파싱 시도
            json_content = response.content.strip()
            
            # 코드 블록 제거 (```json ... ``` 형태)
            if json_content.startswith("```json"):
                json_content = json_content[7:]
            if json_content.startswith("```"):
                json_content = json_content[3:]
            if json_content.endswith("```"):
                json_content = json_content[:-3]
            
            json_content = json_content.strip()
            
            return json.loads(json_content)
            
        except json.JSONDecodeError as e:
            # JSON 파싱 실패 시 재시도
            retry_prompt = f"""
            다음 텍스트를 유효한 JSON 형식으로 변환해주세요. 반드시 올바른 JSON만 응답하세요:
            
            {response.content}
            """
            
            retry_response = self.generate(retry_prompt, **kwargs)
            
            try:
                retry_content = retry_response.content.strip()
                if retry_content.startswith("```json"):
                    retry_content = retry_content[7:]
                if retry_content.startswith("```"):
                    retry_content = retry_content[3:]
                if retry_content.endswith("```"):
                    retry_content = retry_content[:-3]
                retry_content = retry_content.strip()
                
                return json.loads(retry_content)
            except:
                raise Exception(f"JSON 파싱 실패: {response.content}")
    
    @classmethod
    def create_default(cls) -> 'GeminiLLM':
        """기본 설정으로 GeminiLLM 인스턴스 생성"""
        return cls() 