"""
Variable two-track DP validation system for clinical guidelines.
Uses external prompt files and similarity-based evidence finding.
"""

from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import re
import time
import os
from pathlib import Path
from difflib import SequenceMatcher
import nltk
from sentence_transformers import SentenceTransformer
import numpy as np

from ..extraction.dp_extractor import DigitalPhenotype
from ..llm import LLMFactory, BaseLLM

# NLTK 데이터 다운로드 (처음 실행 시)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)


class ValidationTrack(Enum):
    """검증 트랙"""
    SIMILARITY = "similarity"
    EVIDENCE_BASED = "evidence_based"


@dataclass
class SentenceSimilarityResult:
    """문장 유사도 검증 결과"""
    dp_sentence: str
    best_match_sentence: str
    similarity_score: float
    match_index: int


@dataclass
class EvidenceBasedResult:
    """증거 기반 검증 결과"""
    question: str
    best_evidence: str
    evidence_score: float
    evidence_sentence_index: int


@dataclass
class TrackValidationResult:
    """트랙별 검증 결과"""
    track: ValidationTrack
    overall_score: float
    details: List[Any]  # SentenceSimilarityResult 또는 EvidenceBasedResult
    processing_time: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class DPValidationResult:
    """DP 검증 결과"""
    dp: DigitalPhenotype
    similarity_result: TrackValidationResult
    evidence_result: TrackValidationResult
    final_score: float
    passed: bool
    retry_recommended: bool
    processing_time: float
    validation_issues: List[str] = field(default_factory=list)


@dataclass
class ValidationProgress:
    """검증 진행 상황"""
    current_dp_index: int
    total_dps: int
    current_track: str
    current_step: str
    progress_percentage: float
    estimated_time_remaining: float


class VariableDPValidator:
    """개선된 DP 검증기 - 외부 프롬프트 파일 사용 및 유사도 기반 증거 검색"""
    
    def __init__(
        self, 
        llm: Optional[BaseLLM] = None,
        similarity_threshold: float = 0.7,
        evidence_threshold: float = 0.6,
        final_threshold: float = 0.65,
        max_retries: int = 2,
        progress_callback: Optional[Callable[[ValidationProgress], None]] = None
    ):
        """
        개선된 DP 검증기 초기화
        
        Args:
            llm: LLM 인스턴스
            similarity_threshold: 유사도 검증 임계치
            evidence_threshold: 증거 검증 임계치  
            final_threshold: 최종 임계치
            max_retries: 최대 재시도 횟수
            progress_callback: 진행상황 콜백 함수
        """
        self.llm = llm or LLMFactory.get_default_llm()
        self.similarity_threshold = similarity_threshold
        self.evidence_threshold = evidence_threshold
        self.final_threshold = final_threshold
        self.max_retries = max_retries
        self.progress_callback = progress_callback
        
        # 프롬프트 파일 경로 설정
        self.base_path = Path(__file__).parent.parent
        self.validate_prompt_path = self.base_path / "prompt" / "validate_dp.txt"
        self.re_extract_prompt_path = self.base_path / "prompt" / "re_extract_dp.txt"
        
        # 문장 임베딩 모델 초기화 (가벼운 모델 사용)
        try:
            self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ 문장 임베딩 모델 로드 완료")
        except Exception as e:
            print(f"⚠️ 문장 임베딩 모델 로드 실패: {str(e)}")
            self.sentence_model = None
        
        # 프롬프트 파일 로드
        self._load_prompts()
        
        print(f"✅ 개선된 DP 검증기 초기화 완료")
        print(f"   - 유사도 임계치: {similarity_threshold}")
        print(f"   - 증거 임계치: {evidence_threshold}")
        print(f"   - 최종 임계치: {final_threshold}")
    
    def _load_prompts(self):
        """프롬프트 파일들을 로드"""
        try:
            with open(self.validate_prompt_path, 'r', encoding='utf-8') as f:
                self.validate_prompt_template = f.read()
            print(f"✅ 검증 프롬프트 로드 완료: {self.validate_prompt_path}")
        except Exception as e:
            print(f"⚠️ 검증 프롬프트 로드 실패: {e}")
            self.validate_prompt_template = self._get_default_validate_prompt()
        
        try:
            with open(self.re_extract_prompt_path, 'r', encoding='utf-8') as f:
                self.re_extract_prompt_template = f.read()
            print(f"✅ 재추출 프롬프트 로드 완료: {self.re_extract_prompt_path}")
        except Exception as e:
            print(f"⚠️ 재추출 프롬프트 로드 실패: {e}")
            self.re_extract_prompt_template = self._get_default_re_extract_prompt()
    
    def _get_default_validate_prompt(self) -> str:
        """기본 검증 프롬프트"""
        return """Generate 5 validation questions for this DP:
- Condition: {condition}
- Symptom: {symptom}  
- Relationship: {relationship}

Return JSON with validation_questions array."""
    
    def _get_default_re_extract_prompt(self) -> str:
        """기본 재추출 프롬프트"""
        return """Re-extract DP from this text section.
Failed DP: {condition}, {symptom}, {relationship}
Issues: {validation_issues}

Text: {text_section}

Return JSON with condition, symptom, relationship fields."""
    
    def validate_dps_with_selective_retry(
        self,
        initial_dps: List[DigitalPhenotype],
        original_text: str,
        dp_extractor: Any = None
    ) -> Tuple[List[DigitalPhenotype], List[DPValidationResult], Dict[str, Any]]:
        """
        개별 DP별 선택적 재추출을 포함한 검증
        
        Args:
            initial_dps: 초기 추출된 DP 리스트
            original_text: 원본 텍스트
            dp_extractor: DP 추출기 (재추출용)
            
        Returns:
            Tuple[List[DigitalPhenotype], List[DPValidationResult], Dict[str, Any]]: 
            최종 DP 리스트, 검증 결과, 요약
        """
        start_time = time.time()
        all_validation_results = []
        final_dps = []
        retry_history = []
        original_sentences = self._split_into_sentences(original_text)
        
        print(f"\n🔍 {len(initial_dps)}개 DP 검증 시작")
        
        for i, dp in enumerate(initial_dps):
            print(f"\n📋 DP {i+1}/{len(initial_dps)} 검증 중: {dp.label}")
            
            # 진행상황 업데이트
            if self.progress_callback:
                progress = ValidationProgress(
                    current_dp_index=i,
                    total_dps=len(initial_dps),
                    current_track="validation",
                    current_step=f"DP {i+1} 검증",
                    progress_percentage=(i / len(initial_dps)) * 100,
                    estimated_time_remaining=0.0
                )
                self.progress_callback(progress)
            
            current_dp = dp
            retry_count = 0
            dp_validated = False
            
            # 개별 DP에 대한 재시도 루프
            while retry_count <= self.max_retries and not dp_validated:
                # DP 검증 실행
                validation_result = self.validate_single_dp(current_dp, original_sentences, original_text)
                all_validation_results.append(validation_result)
                
                if validation_result.passed:
                    print(f"✅ DP 검증 통과 (점수: {validation_result.final_score:.3f})")
                    final_dps.append(current_dp)
                    dp_validated = True
                elif retry_count < self.max_retries and dp_extractor:
                    # 재추출 시도
                    retry_count += 1
                    print(f"🔄 DP 재추출 시도 {retry_count}/{self.max_retries}")
                    
                    try:
                        # 재추출 수행
                        new_dp = self._re_extract_single_dp(
                            current_dp, validation_result, original_text, dp_extractor
                        )
                        
                        if new_dp:
                            current_dp = new_dp
                            # 안전하게 validation_issues 접근
                            validation_issues = getattr(validation_result, 'validation_issues', [])
                            retry_history.append({
                                'original_dp_id': dp.dp_id,
                                'retry_count': retry_count,
                                'new_dp_id': new_dp.dp_id,
                                'issues': validation_issues
                            })
                            print(f"🔄 새로운 DP 생성: {new_dp.label}")
                        else:
                            print("❌ 재추출 실패")
                            break
                            
                    except Exception as e:
                        print(f"❌ 재추출 중 오류: {str(e)}")
                        break
                else:
                    print(f"❌ DP 검증 실패 (점수: {validation_result.final_score:.3f})")
                    # 임계치를 넘지 못했지만 재시도가 없거나 불가능한 경우 제외
                    break
        
        # 요약 정보 생성
        summary = {
            'total_initial_dps': len(initial_dps),
            'total_final_dps': len(final_dps),
            'total_validation_results': len(all_validation_results),
            'retry_history': retry_history,
            'processing_time': time.time() - start_time,
            'success_rate': len(final_dps) / len(initial_dps) if initial_dps else 0
        }
        
        print(f"\n📊 검증 완료:")
        print(f"   - 초기 DP: {len(initial_dps)}개")
        print(f"   - 최종 DP: {len(final_dps)}개")
        print(f"   - 성공률: {summary['success_rate']:.1%}")
        
        return final_dps, all_validation_results, summary
    
    def validate_single_dp(
        self, 
        dp: DigitalPhenotype, 
        original_sentences: List[str],
        original_text: str
    ) -> DPValidationResult:
        """단일 DP 검증"""
        start_time = time.time()
        
        # 트랙 1: 유사도 검증
        similarity_result = self._validate_track_similarity(dp, original_sentences)
        
        # 트랙 2: 증거 기반 검증 (유사도 기반)
        evidence_result = self._validate_track_evidence_similarity(dp, original_sentences, original_text)
        
        # 최종 점수 계산 (가중 평균: 유사도 40%, 증거 60%)
        similarity_weight = 0.4
        evidence_weight = 0.6
        
        final_score = (
            similarity_result.overall_score * similarity_weight +
            evidence_result.overall_score * evidence_weight
        )
        
        # 검증 통과 여부 결정
        passed = final_score >= self.final_threshold
        
        # 검증 이슈 수집
        validation_issues = []
        if similarity_result.overall_score < self.similarity_threshold:
            validation_issues.append(f"낮은 유사도 점수: {similarity_result.overall_score:.3f}")
        if evidence_result.overall_score < self.evidence_threshold:
            validation_issues.append(f"낮은 증거 점수: {evidence_result.overall_score:.3f}")
        if not similarity_result.success:
            validation_issues.append(f"유사도 검증 오류: {similarity_result.error_message}")
        if not evidence_result.success:
            validation_issues.append(f"증거 검증 오류: {evidence_result.error_message}")
        
        return DPValidationResult(
            dp=dp,
            similarity_result=similarity_result,
            evidence_result=evidence_result,
            final_score=final_score,
            passed=passed,
            retry_recommended=not passed,
            processing_time=time.time() - start_time,
            validation_issues=validation_issues
        )
    
    def _validate_track_similarity(
        self, 
        dp: DigitalPhenotype, 
        original_sentences: List[str]
    ) -> TrackValidationResult:
        """트랙 1: 유사도 기반 검증"""
        start_time = time.time()
        
        try:
            # DP 정보를 문장으로 변환
            dp_sentence = f"{dp.label}: {dp.definition}"
            
            # 가장 유사한 문장 찾기
            similarity_result = self._find_best_sentence_match(dp_sentence, original_sentences)
            
            return TrackValidationResult(
                track=ValidationTrack.SIMILARITY,
                overall_score=similarity_result.similarity_score,
                details=[similarity_result],
                processing_time=time.time() - start_time,
                success=True
            )
            
        except Exception as e:
            return TrackValidationResult(
                track=ValidationTrack.SIMILARITY,
                overall_score=0.0,
                details=[],
                processing_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
    
    def _validate_track_evidence_similarity(
        self,
        dp: DigitalPhenotype,
        original_sentences: List[str],
        original_text: str
    ) -> TrackValidationResult:
        """트랙 2: 증거 기반 검증 (유사도 사용)"""
        start_time = time.time()
        
        try:
            # 검증 질문 생성
            questions = self._generate_validation_questions(dp)
            
            if not questions:
                raise Exception("검증 질문 생성 실패")
            
            evidence_results = []
            
            # 각 질문에 대해 원본 텍스트에서 유사도 기반 증거 찾기
            for question in questions:
                evidence_result = self._find_evidence_by_similarity(question, original_sentences)
                evidence_results.append(evidence_result)
            
            # 평균 점수 계산
            if evidence_results:
                overall_score = np.mean([r.evidence_score for r in evidence_results])
            else:
                overall_score = 0.0
            
            return TrackValidationResult(
                track=ValidationTrack.EVIDENCE_BASED,
                overall_score=overall_score,
                details=evidence_results,
                processing_time=time.time() - start_time,
                success=True
            )
            
        except Exception as e:
            return TrackValidationResult(
                track=ValidationTrack.EVIDENCE_BASED,
                overall_score=0.0,
                details=[],
                processing_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
    
    def _generate_validation_questions(self, dp: DigitalPhenotype) -> List[str]:
        """DP에 대한 검증 질문 생성 (외부 프롬프트 파일 사용)"""
        try:
            # DP 정보 추출
            condition = dp.label
            symptom = dp.definition
            relationship = "indicates"  # 기본값, 향후 DP 구조에서 가져올 수 있음
            
            # 프롬프트 템플릿에 정보 삽입
            prompt = self.validate_prompt_template.format(
                condition=condition,
                symptom=symptom,
                relationship=relationship
            )
            
            # LLM에 질문 생성 요청
            response = self.llm.generate(prompt)
            
            # JSON 응답 파싱 (여러 방법 시도)
            questions = self._extract_json_questions(response.content)
            if questions:
                return questions
            else:
                print(f"⚠️ JSON 파싱 실패, 기본 질문 사용. 응답: {response.content[:200]}...")
                return self._get_default_validation_questions(dp)
                
        except Exception as e:
            print(f"⚠️ 검증 질문 생성 실패: {str(e)}")
            return self._get_default_validation_questions(dp)
    
    def _extract_json_questions(self, response: str) -> List[str]:
        """LLM 응답에서 JSON 질문들을 추출"""
        if not response or not response.strip():
            return []
        
        # 방법 1: 직접 JSON 파싱 시도
        try:
            result = json.loads(response.strip())
            if isinstance(result, dict) and 'validation_questions' in result:
                questions = result['validation_questions']
                if isinstance(questions, list) and len(questions) >= 3:
                    return questions[:5]  # 최대 5개
        except json.JSONDecodeError:
            pass
        
        # 방법 2: JSON 블록 찾기 (```json ... ``` 형태)
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                result = json.loads(json_str)
                if isinstance(result, dict) and 'validation_questions' in result:
                    questions = result['validation_questions']
                    if isinstance(questions, list) and len(questions) >= 3:
                        return questions[:5]
            except json.JSONDecodeError:
                pass
        
        # 방법 3: { ... } 블록 찾기
        json_match = re.search(r'\{.*?\}', response, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                if isinstance(result, dict) and 'validation_questions' in result:
                    questions = result['validation_questions']
                    if isinstance(questions, list) and len(questions) >= 3:
                        return questions[:5]
            except json.JSONDecodeError:
                pass
        
        # 방법 4: 배열 형태 직접 찾기 ["질문1", "질문2", ...]
        array_match = re.search(r'\[.*?\]', response, re.DOTALL)
        if array_match:
            try:
                array_str = array_match.group(0)
                questions = json.loads(array_str)
                if isinstance(questions, list) and len(questions) >= 3:
                    # 각 항목이 문자열인지 확인
                    valid_questions = [q for q in questions if isinstance(q, str) and len(q.strip()) > 10]
                    if valid_questions:
                        return valid_questions[:5]
            except json.JSONDecodeError:
                pass
        
        # 방법 5: 줄 단위로 질문 추출 (1., 2., 3. 형태)
        lines = response.split('\n')
        questions = []
        for line in lines:
            line = line.strip()
            # 번호가 있는 질문 찾기
            question_match = re.match(r'^\d+\.\s*(.+)', line)
            if question_match:
                question = question_match.group(1).strip()
                if len(question) > 10 and '?' in question:
                    questions.append(question)
            # 간단한 질문 형태 찾기
            elif line.endswith('?') and len(line) > 15:
                questions.append(line)
        
        if len(questions) >= 3:
            return questions[:5]
        
        # 모든 방법 실패
        return []
    
    def _get_default_validation_questions(self, dp: DigitalPhenotype) -> List[str]:
        """기본 검증 질문들"""
        return [
            f"{dp.label}의 정의가 의학적으로 정확한가?",
            f"{dp.label}을 진단하는 기준은 무엇인가?",
            f"{dp.label}의 임상적 의미는 무엇인가?",
            f"{dp.label}을 어떻게 측정하거나 확인하는가?",
            f"{dp.label}과 관련된 다른 증상이나 징후는 무엇인가?"
        ]
    
    def _find_evidence_by_similarity(
        self, 
        question: str, 
        original_sentences: List[str]
    ) -> EvidenceBasedResult:
        """질문에 대한 증거를 유사도로 찾기"""
        best_score = 0.0
        best_evidence = ""
        best_index = -1
        
        for i, sentence in enumerate(original_sentences):
            # 질문과 문장 간 유사도 계산
            similarity_score = self._calculate_similarity(question, sentence)
            
            if similarity_score > best_score:
                best_score = similarity_score
                best_evidence = sentence
                best_index = i
        
        return EvidenceBasedResult(
            question=question,
            best_evidence=best_evidence,
            evidence_score=best_score,
            evidence_sentence_index=best_index
        )
    
    def _re_extract_single_dp(
        self,
        failed_dp: DigitalPhenotype,
        validation_result: DPValidationResult,
        original_text: str,
        dp_extractor: Any
    ) -> Optional[DigitalPhenotype]:
        """단일 DP 재추출"""
        try:
            # 검증 이슈들을 문자열로 변환 (안전한 접근)
            validation_issues_list = getattr(validation_result, 'validation_issues', [])
            validation_issues = "; ".join(validation_issues_list) if validation_issues_list else "검증 실패"
            
            # 재추출 프롬프트 생성
            prompt = self.re_extract_prompt_template.format(
                condition=failed_dp.label,
                symptom=failed_dp.definition,
                relationship="indicates",  # 기본값
                validation_issues=validation_issues,
                text_section=original_text[:3000]  # 텍스트 길이 제한
            )
            
            # LLM에 재추출 요청
            response = self.llm.generate(prompt)
            
            # JSON 응답 파싱 (견고한 방법)
            result = self._extract_json_dp_result(response.content)
            
            if result and result.get('condition') and result.get('symptom'):
                # 새로운 DP 객체 생성
                new_dp = DigitalPhenotype(
                    dp_id=f"RETRY_{failed_dp.dp_id}_{int(time.time())}",
                    label=result['condition'],
                    definition=result['symptom'],
                    section_reference=failed_dp.section_reference,
                    confidence_score=0.8,  # 재추출된 DP의 기본 신뢰도
                    metadata={
                        'retry_from': failed_dp.dp_id,
                        'retry_reason': validation_issues,
                        'text_evidence': result.get('text_evidence', ''),
                        'retry_confidence': result.get('confidence', 'medium')
                    }
                )
                return new_dp
            else:
                print("⚠️ 재추출 결과에서 유효한 DP를 찾을 수 없음")
                if result:
                    print(f"   파싱된 결과: {result}")
                return None
                
        except Exception as e:
            print(f"⚠️ DP 재추출 중 오류: {str(e)}")
            return None
    
    def _extract_json_dp_result(self, response: str) -> Optional[dict]:
        """LLM 응답에서 DP 결과 JSON을 추출"""
        if not response or not response.strip():
            return None
        
        # 방법 1: 직접 JSON 파싱 시도
        try:
            result = json.loads(response.strip())
            if isinstance(result, dict) and ('condition' in result or 'symptom' in result):
                return result
        except json.JSONDecodeError:
            pass
        
        # 방법 2: JSON 블록 찾기 (```json ... ``` 형태)
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                result = json.loads(json_str)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        
        # 방법 3: { ... } 블록 찾기 (가장 큰 블록)
        json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        for json_str in reversed(json_matches):  # 가장 큰 것부터 시도
            try:
                result = json.loads(json_str)
                if isinstance(result, dict) and ('condition' in result or 'symptom' in result):
                    return result
            except json.JSONDecodeError:
                continue
        
        # 방법 4: 키-값 쌍 직접 추출
        try:
            result = {}
            
            # condition 찾기
            condition_match = re.search(r'"condition":\s*"([^"]*)"', response, re.IGNORECASE)
            if condition_match:
                result['condition'] = condition_match.group(1)
            
            # symptom 찾기
            symptom_match = re.search(r'"symptom":\s*"([^"]*)"', response, re.IGNORECASE)
            if symptom_match:
                result['symptom'] = symptom_match.group(1)
            
            # relationship 찾기
            relationship_match = re.search(r'"relationship":\s*"([^"]*)"', response, re.IGNORECASE)
            if relationship_match:
                result['relationship'] = relationship_match.group(1)
            
            # confidence 찾기
            confidence_match = re.search(r'"confidence":\s*"([^"]*)"', response, re.IGNORECASE)
            if confidence_match:
                result['confidence'] = confidence_match.group(1)
            
            # text_evidence 찾기
            evidence_match = re.search(r'"text_evidence":\s*"([^"]*)"', response, re.IGNORECASE)
            if evidence_match:
                result['text_evidence'] = evidence_match.group(1)
            
            # null 값 처리
            for key in ['condition', 'symptom', 'relationship']:
                if key in result and result[key].lower() in ['null', 'none', '']:
                    result[key] = None
            
            if result and ('condition' in result or 'symptom' in result):
                return result
        except Exception:
            pass
        
        # 모든 방법 실패
        print(f"⚠️ 재추출 응답에서 JSON을 찾을 수 없음. 응답: {response[:200]}...")
        return None
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """텍스트를 문장으로 분리"""
        try:
            sentences = nltk.sent_tokenize(text)
            return [s.strip() for s in sentences if len(s.strip()) > 5]
        except:
            # NLTK 실패 시 간단한 분리
            sentences = re.split(r'[.!?]+', text)
            return [s.strip() for s in sentences if len(s.strip()) > 5]
    
    def _find_best_sentence_match(
        self,
        dp_sentence: str,
        original_sentences: List[str]
    ) -> SentenceSimilarityResult:
        """가장 유사한 문장 찾기"""
        best_score = 0.0
        best_match = ""
        best_index = -1
        
        for i, original_sentence in enumerate(original_sentences):
            # 유사도 계산
            similarity_score = self._calculate_similarity(dp_sentence, original_sentence)
            
            if similarity_score > best_score:
                best_score = similarity_score
                best_match = original_sentence
                best_index = i
        
        return SentenceSimilarityResult(
            dp_sentence=dp_sentence,
            best_match_sentence=best_match,
            similarity_score=best_score,
            match_index=best_index
        )
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """두 텍스트 간 유사도 계산 (Sentence Transformers 전용)"""
        
        # Sentence Transformers 모델이 로드되어 있는 경우
        if self.sentence_model:
            try:
                embeddings = self.sentence_model.encode([text1, text2])
                cosine_sim = np.dot(embeddings[0], embeddings[1]) / (
                    np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
                )
                # 코사인 유사도는 -1~1 범위이므로 0~1로 정규화
                return max(0.0, float(cosine_sim))
            except Exception as e:
                print(f"⚠️ Sentence Transformers 계산 실패: {e}")
                # fallback으로 키워드 유사도 사용
                return self._calculate_keyword_similarity_fallback(text1, text2)
        else:
            print("⚠️ Sentence Transformers 모델이 로드되지 않음. Fallback 사용.")
            # fallback으로 키워드 유사도 사용
            return self._calculate_keyword_similarity_fallback(text1, text2)
    
    def _calculate_keyword_similarity_fallback(self, text1: str, text2: str) -> float:
        """Sentence Transformers 실패 시 fallback용 키워드 유사도"""
        words1 = set(re.findall(r'\b\w+\b', text1.lower()))
        words2 = set(re.findall(r'\b\w+\b', text2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0


# 기존 클래스명 호환성을 위한 별칭
TwoTrackDPValidator = VariableDPValidator 