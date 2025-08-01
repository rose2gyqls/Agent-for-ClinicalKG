"""
Digital Phenotype (DP) extractor from clinical guidelines.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import time

from ..llm import LLMFactory, BaseLLM
from .prompt_manager import PromptManager


@dataclass
class DigitalPhenotype:
    """디지털 표현형 데이터 클래스"""
    dp_id: str
    label: str
    definition: str
    section_reference: str
    confidence_score: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class DPExtractor:
    """디지털 표현형 추출기"""
    
    def __init__(self, llm: Optional[BaseLLM] = None, prompt_manager: Optional[PromptManager] = None):
        """
        DP 추출기 초기화
        
        Args:
            llm: 사용할 LLM 인스턴스
            prompt_manager: 프롬프트 매니저
        """
        self.llm = llm or LLMFactory.get_default_llm()
        self.prompt_manager = prompt_manager or PromptManager.create_default()
        
        # LLM 사용 가능 여부 확인
        if not self.llm.is_available():
            error_msg = """
❌ LLM을 사용할 수 없습니다.

🔍 확인 사항:
1. .env 파일이 프로젝트 루트에 있는지 확인
2. .env 파일에 GEMINI_API_KEY가 설정되어 있는지 확인
3. Gemini API 키가 유효한지 확인
4. 인터넷 연결 상태 확인

💡 Gemini API 키 발급: https://makersuite.google.com/app/apikey
            """
            raise Exception(error_msg.strip())
        
        print(f"✅ DP 추출기 초기화 완료: {self.llm.__class__.__name__}")
    
    def extract_dps(self, clinical_text: str, max_retries: int = 3, max_dps: int = None) -> List[DigitalPhenotype]:
        """
        의료 가이드라인 텍스트에서 디지털 표현형 추출
        
        Args:
            clinical_text: 의료 가이드라인 텍스트
            max_retries: 최대 재시도 횟수
            
        Returns:
            List[DigitalPhenotype]: 추출된 디지털 표현형 리스트
        """
        try:
            # 입력 텍스트 길이 제한 (토큰 수 대략 계산)
            max_chars = 30000  # 대략 5000-7000 토큰 정도
            if len(clinical_text) > max_chars:
                print(f"⚠️ 입력 텍스트가 너무 깁니다 ({len(clinical_text)} 문자). {max_chars} 문자로 자릅니다.")
                clinical_text = clinical_text[:max_chars] + "..."
            
            # DP 추출 프롬프트 가져오기
            template = self.prompt_manager.get_template("extract_dp")
            prompt = template + f"\n\n입력 문서:\n{clinical_text}"
            
            # LLM을 통한 DP 추출
            for attempt in range(max_retries):
                try:
                    print(f"DP 추출 시도 {attempt + 1}/{max_retries}")
                    
                    if hasattr(self.llm, 'generate_json'):
                        # JSON 생성 특화 메서드가 있는 경우
                        json_response = self.llm.generate_json(prompt)
                    else:
                        # 일반 생성 메서드 사용
                        response = self.llm.generate(prompt)
                        json_response = json.loads(response.content)
                    
                    # JSON 응답을 DigitalPhenotype 객체로 변환
                    dps = []
                    
                    # 응답이 리스트인지 확인
                    if isinstance(json_response, list):
                        dp_list = json_response
                    elif isinstance(json_response, dict) and 'digital_phenotypes' in json_response:
                        dp_list = json_response['digital_phenotypes']
                    elif isinstance(json_response, dict) and 'dps' in json_response:
                        dp_list = json_response['dps']
                    else:
                        # 단일 객체인 경우 리스트로 변환
                        dp_list = [json_response] if isinstance(json_response, dict) else []
                    
                    for dp_data in dp_list:
                        if isinstance(dp_data, dict):
                            dp = DigitalPhenotype(
                                dp_id=dp_data.get('dp_id', f'DP_{len(dps)+1:03d}'),
                                label=dp_data.get('label', ''),
                                definition=dp_data.get('definition', ''),
                                section_reference=dp_data.get('section_reference', ''),
                                confidence_score=dp_data.get('confidence_score'),
                                metadata=dp_data.get('metadata')
                            )
                            dps.append(dp)
                    
                    # max_dps 제한 적용
                    if max_dps is not None and len(dps) > max_dps:
                        print(f"⚠️ DP 개수 제한: {len(dps)}개 → {max_dps}개")
                        dps = dps[:max_dps]
                    
                    print(f"✅ DP 추출 성공: {len(dps)}개의 디지털 표현형 발견")
                    return dps
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON 파싱 오류 (시도 {attempt + 1}): {str(e)}")
                    if attempt == max_retries - 1:
                        raise Exception(f"JSON 파싱 실패 (최대 재시도 횟수 초과): {str(e)}")
                    time.sleep(2)  # 재시도 전 대기
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ DP 추출 오류 (시도 {attempt + 1}): {error_msg}")
                    
                    # 할당량 초과 오류 처리
                    if "429" in error_msg or "quota" in error_msg.lower():
                        wait_time = 10 + (attempt * 5)  # 점진적으로 대기 시간 증가
                        print(f"⏰ API 할당량 초과 - {wait_time}초 대기 중...")
                        time.sleep(wait_time)
                    elif "rate limit" in error_msg.lower():
                        wait_time = 15 + (attempt * 10)
                        print(f"⏰ Rate limit 초과 - {wait_time}초 대기 중...")
                        time.sleep(wait_time)
                    else:
                        time.sleep(2)  # 기본 대기
                    
                    if attempt == max_retries - 1:
                        if "429" in error_msg or "quota" in error_msg.lower():
                            raise Exception(f"API 할당량 초과: Gemini 무료 티어 제한에 걸렸습니다. 잠시 후 다시 시도하거나 유료 플랜 고려하세요.")
                        else:
                            raise Exception(f"DP 추출 실패 (최대 재시도 횟수 초과): {str(e)}")
            
            return []
            
        except Exception as e:
            raise Exception(f"DP 추출 중 오류 발생: {str(e)}")
    
    def extract_dps_with_metadata(self, clinical_text: str, document_metadata: Optional[Dict[str, Any]] = None, max_dps: int = None) -> Dict[str, Any]:
        """
        메타데이터와 함께 DP 추출
        
        Args:
            clinical_text: 의료 가이드라인 텍스트
            document_metadata: 문서 메타데이터
            
        Returns:
            Dict: 추출 결과와 메타데이터
        """
        start_time = time.time()
        
        try:
            # DP 추출
            dps = self.extract_dps(clinical_text, max_dps=max_dps)
            
            # 처리 시간 계산
            processing_time = time.time() - start_time
            
            # 결과 정리
            result = {
                'digital_phenotypes': [
                    {
                        'dp_id': dp.dp_id,
                        'label': dp.label,
                        'definition': dp.definition,
                        'section_reference': dp.section_reference,
                        'confidence_score': dp.confidence_score,
                        'metadata': dp.metadata
                    }
                    for dp in dps
                ],
                'extraction_metadata': {
                    'total_count': len(dps),
                    'processing_time': processing_time,
                    'llm_model': self.llm.config.model_name if hasattr(self.llm, 'config') else 'unknown',
                    'extraction_timestamp': time.time(),
                    'document_metadata': document_metadata
                }
            }
            
            return result
            
        except Exception as e:
            return {
                'digital_phenotypes': [],
                'extraction_metadata': {
                    'total_count': 0,
                    'processing_time': time.time() - start_time,
                    'error': str(e),
                    'extraction_timestamp': time.time(),
                    'document_metadata': document_metadata
                }
            }
    
    def validate_dp(self, dp: DigitalPhenotype) -> bool:
        """
        디지털 표현형 유효성 검증
        
        Args:
            dp: 검증할 디지털 표현형
            
        Returns:
            bool: 유효성 여부
        """
        # 필수 필드 확인
        required_fields = ['dp_id', 'label', 'definition']
        
        for field in required_fields:
            value = getattr(dp, field, None)
            if not value or (isinstance(value, str) and len(value.strip()) == 0):
                return False
        
        # 추가 유효성 검사 (예: 최소 길이, 형식 등)
        if len(dp.label.strip()) < 3:
            return False
        
        if len(dp.definition.strip()) < 10:
            return False
        
        return True
    
    def filter_valid_dps(self, dps: List[DigitalPhenotype]) -> List[DigitalPhenotype]:
        """
        유효한 디지털 표현형만 필터링
        
        Args:
            dps: 디지털 표현형 리스트
            
        Returns:
            List[DigitalPhenotype]: 유효한 디지털 표현형 리스트
        """
        valid_dps = []
        
        for dp in dps:
            if self.validate_dp(dp):
                valid_dps.append(dp)
            else:
                print(f"⚠️ 유효하지 않은 DP 제외됨: {dp.dp_id} - {dp.label}")
        
        return valid_dps
    
    @classmethod
    def create_default(cls) -> 'DPExtractor':
        """기본 설정으로 DP 추출기 생성"""
        return cls() 