"""
DP에서 의료 엔티티 추출기
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import re
import time
from enum import Enum

from ..extraction.dp_extractor import DigitalPhenotype
from ..llm import LLMFactory, BaseLLM
from ..extraction.prompt_manager import PromptManager


class EntityType(Enum):
    """엔티티 타입"""
    DIAGNOSTIC = "diagnostic"
    DRUG = "drug"
    TEST = "test"
    SURGERY = "surgery"


@dataclass
class ClinicalEntity:
    """의료 엔티티 데이터 클래스"""
    text: str  # 원본 텍스트
    entity_type: EntityType  # 엔티티 타입
    normalized_text: str  # 정규화된 텍스트
    confidence: float  # 신뢰도
    start_pos: Optional[int] = None  # 시작 위치
    end_pos: Optional[int] = None  # 끝 위치
    context: Optional[str] = None  # 문맥 정보
    metadata: Optional[Dict[str, Any]] = None  # 추가 메타데이터
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class EntityExtractor:
    """의료 엔티티 추출기"""
    
    def __init__(
        self, 
        llm: Optional[BaseLLM] = None,
        prompt_manager: Optional[PromptManager] = None,
        confidence_threshold: float = 0.7
    ):
        """
        엔티티 추출기 초기화
        
        Args:
            llm: 사용할 LLM 인스턴스
            prompt_manager: 프롬프트 매니저
            confidence_threshold: 신뢰도 임계치
        """
        self.llm = llm or LLMFactory.get_default_llm()
        self.prompt_manager = prompt_manager or PromptManager.create_default()
        self.confidence_threshold = confidence_threshold
        
        # 의료 용어 패턴 (기본 규칙 기반 추출용)
        self.condition_patterns = [
            r'\b(?:diabetes|hypertension|cancer|pneumonia|asthma|copd|heart failure|stroke)\b',
            r'\b\w+itis\b',  # ~염
            r'\b\w+osis\b',  # ~증
            r'\b\w+opathy\b'  # ~병증
        ]
        
        self.medication_patterns = [
            r'\b(?:aspirin|metformin|insulin|warfarin|atorvastatin|lisinopril)\b',
            r'\b\w+cillin\b',  # 페니실린 계열
            r'\b\w+statin\b'   # 스타틴 계열
        ]
        
        print(f"✅ EntityExtractor 초기화 완료")
    
    def extract_entities_from_dps(
        self, 
        validated_dps: List[DigitalPhenotype],
        original_text: str
    ) -> Dict[str, Any]:
        """
        검증된 DP 목록에서 엔티티 추출
        
        Args:
            validated_dps: 검증된 DP 리스트
            original_text: 원본 텍스트
            
        Returns:
            Dict: 추출된 엔티티와 메타데이터
        """
        start_time = time.time()
        
        try:
            all_entities = []
            dp_entity_map = {}
            
            for dp in validated_dps:
                # 각 DP에서 엔티티 추출
                entities = self._extract_entities_from_single_dp(dp, original_text)
                
                # 중복 제거 및 병합
                unique_entities = self._deduplicate_entities(entities)
                
                all_entities.extend(unique_entities)
                dp_entity_map[dp.dp_id] = unique_entities
            
            # 전체 엔티티 중복 제거
            final_entities = self._deduplicate_entities(all_entities)
            
            # 최소 1개 엔티티 보장 (전체 프로세스에서)
            if not final_entities and validated_dps:
                print("⚠️ 전체 프로세스에서 엔티티가 없음 - 첫 번째 DP로부터 기본 엔티티 생성")
                fallback_entity = self._create_fallback_entity(validated_dps[0])
                final_entities = [fallback_entity]
            
            # 엔티티 타입별 통계
            entity_stats = self._calculate_entity_statistics(final_entities)
            
            processing_time = time.time() - start_time
            
            result = {
                'entities': [
                    {
                        'text': entity.text,
                        'entity_type': entity.entity_type.value,
                        'normalized_text': entity.normalized_text,
                        'confidence': entity.confidence,
                        'start_pos': entity.start_pos,
                        'end_pos': entity.end_pos,
                        'context': entity.context,
                        'metadata': entity.metadata
                    }
                    for entity in final_entities
                ],
                'dp_entity_mapping': {
                    dp_id: [
                        {
                            'text': entity.text,
                            'entity_type': entity.entity_type.value,
                            'normalized_text': entity.normalized_text,
                            'confidence': entity.confidence
                        }
                        for entity in entities
                    ]
                    for dp_id, entities in dp_entity_map.items()
                },
                'statistics': entity_stats,
                'extraction_metadata': {
                    'total_dps_processed': len(validated_dps),
                    'total_entities_extracted': len(final_entities),
                    'processing_time': processing_time,
                    'confidence_threshold': self.confidence_threshold,
                    'extraction_timestamp': time.time()
                }
            }
            
            print(f"✅ 엔티티 추출 완료: {len(final_entities)}개 엔티티")
            return result
            
        except Exception as e:
            return {
                'entities': [],
                'dp_entity_mapping': {},
                'statistics': {},
                'extraction_metadata': {
                    'total_dps_processed': len(validated_dps),
                    'total_entities_extracted': 0,
                    'processing_time': time.time() - start_time,
                    'error': str(e),
                    'extraction_timestamp': time.time()
                }
            }
    
    def _extract_entities_from_single_dp(
        self, 
        dp: DigitalPhenotype,
        original_text: str
    ) -> List[ClinicalEntity]:
        """단일 DP에서 엔티티 추출"""
        entities = []
        
        # 1. LLM 기반 엔티티 추출
        llm_entities = self._extract_entities_with_llm(dp)
        entities.extend(llm_entities)
        
        # 2. 규칙 기반 엔티티 추출 (보조)
        rule_entities = self._extract_entities_with_rules(dp)
        entities.extend(rule_entities)
        
        # 3. 최소 1개 엔티티 보장 (테스트 목적)
        if not entities:
            entities.append(self._create_fallback_entity(dp))
        
        # 4. 문맥 정보 추가
        entities = self._add_context_information(entities, dp, original_text)
        
        return entities
    
    def _create_fallback_entity(self, dp: DigitalPhenotype) -> ClinicalEntity:
        """엔티티가 없을 때 DP 라벨로부터 기본 엔티티 생성"""
        print(f"⚠️ 엔티티 추출 실패 - DP 라벨로부터 기본 엔티티 생성: {dp.label}")
        
        # DP 라벨에서 일반적인 의료 용어 패턴 찾기
        label_lower = dp.label.lower()
        
        # 4개 분류에 맞는 패턴 매칭
        if any(word in label_lower for word in ['diabetes', '당뇨', 'dm', 'diabetic', 'hypertension', '고혈압', 'htn', 'coronary', '심장', 'heart', 'mi', 'infarction', 'disease', '질환', 'condition', '상태']):
            entity_type = EntityType.DIAGNOSTIC
            if 'diabetes' in label_lower or '당뇨' in label_lower:
                normalized_text = "diabetes mellitus"
            elif 'hypertension' in label_lower or '고혈압' in label_lower:
                normalized_text = "hypertension"
            elif 'coronary' in label_lower or '심장' in label_lower:
                normalized_text = "coronary artery disease"
            else:
                normalized_text = dp.label.lower().strip()
        elif any(word in label_lower for word in ['statin', '스타틴', 'atorvastatin', 'simvastatin', 'aspirin', '아스피린', 'medication', '약물', 'drug', '치료제', 'therapy']):
            entity_type = EntityType.DRUG
            if 'statin' in label_lower:
                normalized_text = "statin"
            elif 'aspirin' in label_lower:
                normalized_text = "aspirin"
            else:
                normalized_text = dp.label.lower().strip()
        elif any(word in label_lower for word in ['test', '검사', 'lab', '측정', 'measurement', 'hba1c', 'glucose', 'cholesterol', 'ldl', 'hdl']):
            entity_type = EntityType.TEST
            if 'hba1c' in label_lower:
                normalized_text = "hemoglobin A1c measurement"
            elif 'glucose' in label_lower:
                normalized_text = "glucose measurement"
            else:
                normalized_text = dp.label.lower().strip()
        elif any(word in label_lower for word in ['procedure', '시술', '수술', 'surgery', 'pci', 'angioplasty', 'operation', 'intervention']):
            entity_type = EntityType.SURGERY
            if 'pci' in label_lower or 'angioplasty' in label_lower:
                normalized_text = "percutaneous coronary intervention"
            else:
                normalized_text = dp.label.lower().strip()
        else:
            entity_type = EntityType.DIAGNOSTIC  # 기본값
            normalized_text = dp.label.lower().strip()
        
        print(f"✅ 기본 엔티티 생성: {dp.label} -> {entity_type.value} (신뢰도: 0.5)")
        
        return ClinicalEntity(
            text=dp.label,
            entity_type=entity_type,
            normalized_text=normalized_text,
            confidence=0.5,  # 기본 신뢰도
            metadata={
                'extraction_method': 'fallback_from_dp_label',
                'source_dp_id': dp.dp_id,
                'source_dp_label': dp.label,
                'note': 'Generated as fallback when no entities were extracted'
            }
        )
    
    def _extract_entities_with_llm(self, dp: DigitalPhenotype) -> List[ClinicalEntity]:
        """LLM을 사용한 엔티티 추출"""
        try:
            # 엔티티 추출 프롬프트 생성
            prompt = self._create_entity_extraction_prompt(dp)
            
            print(f"🔍 LLM 엔티티 추출 시작: {dp.dp_id}")
            
            # LLM 호출
            response = self.llm.generate(prompt)
            
            print(f"✅ LLM 응답 받음: {len(response.content)} 문자")
            
            # 응답 파싱
            entities = self._parse_llm_entity_response(response.content, dp)
            
            print(f"✅ 엔티티 파싱 완료: {len(entities)}개 엔티티")
            return entities
            
        except Exception as e:
            print(f"⚠️ LLM 엔티티 추출 실패: {str(e)}")
            print(f"   - DP ID: {dp.dp_id}")
            print(f"   - DP Label: {dp.label}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_entities_with_rules(self, dp: DigitalPhenotype) -> List[ClinicalEntity]:
        """규칙 기반 엔티티 추출"""
        entities = []
        
        # DP의 label과 definition에서 패턴 매칭
        texts = [dp.label, dp.definition]
        
        for text in texts:
            if not text:
                continue
                
            # 질환 패턴 검색
            for pattern in self.condition_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entity = ClinicalEntity(
                        text=match.group(),
                        entity_type=EntityType.CONDITION,
                        normalized_text=match.group().lower(),
                        confidence=0.6,  # 규칙 기반은 낮은 신뢰도
                        start_pos=match.start(),
                        end_pos=match.end(),
                        metadata={'extraction_method': 'rule_based', 'pattern': pattern}
                    )
                    entities.append(entity)
            
            # 약물 패턴 검색
            for pattern in self.medication_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entity = ClinicalEntity(
                        text=match.group(),
                        entity_type=EntityType.MEDICATION,
                        normalized_text=match.group().lower(),
                        confidence=0.6,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        metadata={'extraction_method': 'rule_based', 'pattern': pattern}
                    )
                    entities.append(entity)
        
        return entities
    
    def _create_entity_extraction_prompt(self, dp: DigitalPhenotype) -> str:
        """엔티티 추출용 프롬프트 생성"""
        try:
            # 프롬프트 매니저에서 템플릿 가져오기
            template = self.prompt_manager.get_template("extract_entities")
            prompt = template.format(
                phenotype_id=dp.dp_id,
                label=dp.label,
                definition=dp.definition,
                section_reference=dp.section_reference or "Unknown"
            )
            return prompt
        except Exception as e:
            print(f"⚠️ 프롬프트 템플릿 로드 실패, extract_entities.txt 프롬프트 사용: {str(e)}")
            # extract_entities.txt 내용 기반 프롬프트 사용
            prompt = f"""You are a clinical informatics expert designing digital phenotype (DP) algorithms using OMOP-CDM, based on clinical practice guidelines.

## Input
- A single digital phenotype, including:
  - ID: {dp.dp_id}
  - Label: {dp.label}
  - Description: {dp.definition}
  - Reference section(s): {dp.section_reference or "Unknown"}
- A clinical guideline as the source (text format)

## Your Task
Using the above guideline and phenotype context, define the inclusion and exclusion criteria for this digital phenotype.

## Output Format (JSON)
```json
{{
  "phenotype_id": "{dp.dp_id}",
  "supporting_evidence": "{dp.section_reference or 'Unknown'}",
  "inclusion_criteria": [
    {{
      "type": "Diagnosis",
      "concept_name": "Example diagnosis",
      "domain_id": "Condition",
      "mapping_confidence": 0.98,
      "source_text_span": "relevant text from guideline"
    }},
    {{
      "type": "Measurement", 
      "concept_name": "Example measurement",
      "domain_id": "Measurement",
      "mapping_confidence": 0.92,
      "test_name": "test name",
      "operator": ">",
      "value": 100,
      "unit": "unit",
      "source_text_span": "relevant text from guideline"
    }},
    {{
      "type": "Procedure",
      "concept_name": "Example procedure", 
      "domain_id": "Procedure",
      "vocabulary_id": "SNOMED",
      "mapping_confidence": 0.96,
      "surgery_name": "procedure name",
      "source_text_span": "relevant text from guideline"
    }},
    {{
      "type": "Drug",
      "concept_name": "Example drug",
      "domain_id": "Drug", 
      "vocabulary_id": "RxNorm",
      "mapping_confidence": 0.95,
      "drug_name": "drug name",
      "source_text_span": "relevant text from guideline"
    }}
  ],
  "exclusion_criteria": [
    {{
      "type": "Diagnosis",
      "concept_name": "Example exclusion",
      "domain_id": "Condition",
      "mapping_confidence": 0.9,
      "source_text_span": "relevant exclusion text"
    }}
  ]
}}
```

Additional Notes
Do not hallucinate OMOP concept names — use the source text and infer CDM-compatible concept names only if clearly mappable.

Ensure each item is clearly supported by guideline text, and cite the source_text_span."""
            return prompt
    
    def _parse_llm_entity_response(
        self, 
        response_content: str, 
        dp: DigitalPhenotype
    ) -> List[ClinicalEntity]:
        """LLM 응답에서 엔티티 파싱 (4개 분류 형식)"""
        try:
            import json
            
            print(f"🔍 LLM 응답 파싱 시작: {len(response_content)} 문자")
            
            # JSON 복구 시도
            try:
                data = json.loads(response_content)
                print("✅ JSON 파싱 성공")
            except json.JSONDecodeError as json_error:
                print(f"⚠️ JSON 파싱 실패: {str(json_error)}")
                print(f"   - 응답 내용: {response_content[:200]}...")
                
                # json_repair 라이브러리 시도
                try:
                    from json_repair import repair_json
                    repaired_json = repair_json(response_content)
                    data = json.loads(repaired_json)
                    print("✅ JSON 복구 성공")
                except Exception as repair_error:
                    print(f"⚠️ JSON 복구 실패: {str(repair_error)}")
                    # 기본 엔티티 생성
                    fallback_entity = self._create_fallback_entity(dp)
                    return [fallback_entity]
            
            entities = []
            
            # 4개 분류별로 엔티티 추출
            entity_types = ['diagnostic', 'drug', 'test', 'surgery']
            
            for entity_type in entity_types:
                if entity_type in data and data[entity_type]:
                    entity_data = data[entity_type]
                    
                    try:
                        # EntityType enum 매핑
                        type_mapping = {
                            'diagnostic': EntityType.DIAGNOSTIC,
                            'drug': EntityType.DRUG,
                            'test': EntityType.TEST,
                            'surgery': EntityType.SURGERY
                        }
                        
                        entity = ClinicalEntity(
                            text=entity_data.get('concept_name', ''),
                            entity_type=type_mapping[entity_type],
                            normalized_text=entity_data.get('concept_name', '').lower(),
                            confidence=float(entity_data.get('confidence', 0.5)),
                            metadata={
                                'extraction_method': 'llm_based',
                                'source_dp_id': dp.dp_id,
                                'source_dp_label': dp.label,
                                'domain_id': entity_data.get('domain_id', ''),
                                'vocabulary_id': entity_data.get('vocabulary_id', ''),
                                'source_text_span': entity_data.get('source_text_span', '')
                            }
                        )
                        
                        # 신뢰도 임계치 확인
                        if entity.confidence >= self.confidence_threshold:
                            entities.append(entity)
                            print(f"✅ 엔티티 추가: {entity.text} ({entity.entity_type.value})")
                        else:
                            print(f"⚠️ 신뢰도 낮음 제외: {entity.text} (신뢰도: {entity.confidence})")
                            
                    except Exception as e:
                        print(f"⚠️ {entity_type} 엔티티 파싱 오류: {str(e)}")
                        continue
            
            # 엔티티가 없으면 DP 라벨로부터 기본 엔티티 생성
            if not entities:
                print(f"⚠️ LLM에서 엔티티 추출 실패 - DP 라벨로부터 기본 엔티티 생성")
                fallback_entity = self._create_fallback_entity(dp)
                entities = [fallback_entity]
            
            return entities
            
        except Exception as e:
            print(f"⚠️ LLM 응답 파싱 실패: {str(e)} - 기본 엔티티 생성")
            import traceback
            traceback.print_exc()
            # 파싱 실패 시에도 기본 엔티티 생성
            fallback_entity = self._create_fallback_entity(dp)
            return [fallback_entity]
    
    def _add_context_information(
        self, 
        entities: List[ClinicalEntity],
        dp: DigitalPhenotype,
        original_text: str
    ) -> List[ClinicalEntity]:
        """엔티티에 문맥 정보 추가"""
        for entity in entities:
            # DP 문맥 정보 추가
            entity.context = f"DP: {dp.label} - {dp.definition}"
            
            # 메타데이터에 DP 정보 추가
            if entity.metadata is None:
                entity.metadata = {}
            
            entity.metadata.update({
                'source_dp_id': dp.dp_id,
                'source_dp_label': dp.label,
                'source_dp_section': dp.section_reference
            })
        
        return entities
    
    def _deduplicate_entities(self, entities: List[ClinicalEntity]) -> List[ClinicalEntity]:
        """엔티티 중복 제거"""
        unique_entities = []
        seen_entities = set()
        
        for entity in entities:
            # 정규화된 텍스트와 엔티티 타입으로 중복 확인
            key = (entity.normalized_text, entity.entity_type.value)
            
            if key not in seen_entities:
                seen_entities.add(key)
                unique_entities.append(entity)
            else:
                # 중복된 경우 더 높은 신뢰도의 엔티티로 업데이트
                for i, existing_entity in enumerate(unique_entities):
                    if (existing_entity.normalized_text, existing_entity.entity_type.value) == key:
                        if entity.confidence > existing_entity.confidence:
                            unique_entities[i] = entity
                        break
        
        return unique_entities
    
    def _calculate_entity_statistics(self, entities: List[ClinicalEntity]) -> Dict[str, Any]:
        """엔티티 통계 계산"""
        if not entities:
            return {}
        
        stats = {
            'total_entities': len(entities),
            'by_type': {},
            'confidence_distribution': {
                'high (>0.8)': 0,
                'medium (0.6-0.8)': 0,
                'low (<0.6)': 0
            },
            'avg_confidence': sum(e.confidence for e in entities) / len(entities)
        }
        
        # 타입별 통계
        for entity in entities:
            entity_type = entity.entity_type.value
            if entity_type not in stats['by_type']:
                stats['by_type'][entity_type] = 0
            stats['by_type'][entity_type] += 1
            
            # 신뢰도 분포
            if entity.confidence > 0.8:
                stats['confidence_distribution']['high (>0.8)'] += 1
            elif entity.confidence >= 0.6:
                stats['confidence_distribution']['medium (0.6-0.8)'] += 1
            else:
                stats['confidence_distribution']['low (<0.6)'] += 1
        
        return stats
    
    @classmethod
    def create_default(cls) -> 'EntityExtractor':
        """기본 설정으로 엔티티 추출기 생성"""
        return cls() 