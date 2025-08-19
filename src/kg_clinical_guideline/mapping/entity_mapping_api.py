"""
엔티티 매핑 API 모듈
Input: 엔티티 정보
Output: OMOP CDM에 매핑된 엔티티 정보
"""

from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import time
import logging
from enum import Enum

from .elasticsearch_client import ElasticsearchClient
from .omop_mapper import OMOPMapper, EntityMapping, MappingConfidence

logger = logging.getLogger(__name__)


class EntityTypeAPI(Enum):
    """API용 엔티티 타입"""
    DIAGNOSTIC = "diagnostic"
    DRUG = "drug"
    TEST = "test"
    SURGERY = "surgery"


@dataclass
class EntityInput:
    """API 입력용 엔티티 데이터"""
    entity_name: str
    entity_type: EntityTypeAPI
    domain_id: Optional[str] = None
    vocabulary_id: Optional[str] = None
    confidence: float = 1.0


@dataclass
class MappingResult:
    """매핑 결과 데이터"""
    source_entity: EntityInput
    mapped_concept_id: str
    mapped_concept_name: str
    domain_id: str
    vocabulary_id: str
    concept_class_id: str
    standard_concept: str
    concept_code: str
    mapping_score: float
    mapping_confidence: str
    mapping_method: str
    alternative_concepts: List[Dict[str, Any]]


def get_es_index(domain_id: str) -> str:
    """도메인 ID에 따른 Elasticsearch 인덱스 반환"""
    domain_to_index = {
        "Condition": "concept-condition",
        "Drug": "concept-drug", 
        "Measurement": "concept-measurement",
        "Procedure": "concept-procedure"
    }
    return domain_to_index.get(domain_id, "concept-condition")


class EntityMappingAPI:
    """엔티티 매핑 API 클래스"""
    
    def __init__(
        self,
        es_client: Optional[ElasticsearchClient] = None,
        confidence_threshold: float = 0.5
    ):
        """
        엔티티 매핑 API 초기화
        
        Args:
            es_client: Elasticsearch 클라이언트
            confidence_threshold: 매핑 신뢰도 임계치
        """
        self.es_client = es_client or ElasticsearchClient.create_default()
        self.confidence_threshold = confidence_threshold
        
        logger.info("✅ EntityMappingAPI 초기화 완료")
    
    def map_entity(self, entity_input: EntityInput) -> Optional[MappingResult]:
        """
        단일 엔티티를 OMOP CDM에 매핑
        
        Args:
            entity_input: 매핑할 엔티티 정보
            
        Returns:
            MappingResult: 매핑 결과 또는 None (매핑 실패시)
        """
        try:
            # 엔티티 타입별 사전 매핑 정보 세팅
            entities_to_map = self._prepare_entity_for_mapping(entity_input)
            
            if not entities_to_map:
                logger.warning(f"엔티티 매핑 준비 실패: {entity_input.entity_name}")
                return None
            
            entity_info = entities_to_map[0]
            entity_name = entity_info["entity_name"]
            domain_id = entity_info["domain_id"]
            vocabulary_id = entity_info["vocabulary_id"]
            
            # 도메인에 맞는 인덱스 선택
            es_index = get_es_index(domain_id)
            logger.info(f"검색할 인덱스: {es_index}, 엔티티: {entity_name}")
            
            # Elasticsearch 쿼리 구성
            should_queries = [
                {
                    "term": {
                        "concept_name.keyword": {
                            "value": entity_name,
                            "boost": 500
                        }
                    }
                }
            ]

            must_queries = [
                {
                    "match": {
                        "concept_name": {
                            "query": entity_name
                        }
                    }
                },
                {
                    "term": {
                        "standard_concept.keyword": "S"
                    }
                }
            ]
            
            query = {
                "query": {
                    "function_score": {
                        "query": {
                            "bool": {
                                "must": must_queries,
                                "should": should_queries
                            }
                        },
                        "functions": [
                            {
                                "gauss": {
                                    "concept_name_length": {
                                        "origin": len(entity_name),
                                        "scale": "1",
                                        "decay": 0.9
                                    }
                                },
                                "weight": 30
                            }
                        ],
                        "boost_mode": "sum",
                        "score_mode": "sum"
                    }
                }
            }
            
            # Elasticsearch 검색 수행
            response = self.es_client.es_client.search(
                index=es_index,
                body=query
            )
            
            # 검색 결과 처리
            if response['hits']['total']['value'] > 0:
                best_hit = response['hits']['hits'][0]
                source = best_hit['_source']
                score = best_hit['_score']
                
                # 대안 컨셉들 추출
                alternative_concepts = []
                for hit in response['hits']['hits'][1:4]:  # 상위 3개 대안
                    alt_source = hit['_source']
                    alternative_concepts.append({
                        'concept_id': str(alt_source.get('concept_id', '')),
                        'concept_name': alt_source.get('concept_name', ''),
                        'vocabulary_id': alt_source.get('vocabulary_id', ''),
                        'score': hit['_score']
                    })
                
                # 매핑 신뢰도 계산
                normalized_score = self._normalize_score(score)
                mapping_confidence = self._determine_confidence(normalized_score)
                
                # 매핑 결과 생성
                mapping_result = MappingResult(
                    source_entity=entity_input,
                    mapped_concept_id=str(source.get('concept_id', '')),
                    mapped_concept_name=source.get('concept_name', ''),
                    domain_id=source.get('domain_id', domain_id),
                    vocabulary_id=source.get('vocabulary_id', vocabulary_id),
                    concept_class_id=source.get('concept_class_id', ''),
                    standard_concept=source.get('standard_concept', ''),
                    concept_code=source.get('concept_code', ''),
                    mapping_score=normalized_score,
                    mapping_confidence=mapping_confidence,
                    mapping_method="elasticsearch_search",
                    alternative_concepts=alternative_concepts
                )
                
                logger.info(f"✅ 매핑 성공: {entity_name} -> {mapping_result.mapped_concept_name}")
                return mapping_result
            else:
                logger.warning(f"⚠️ 매핑 실패 - 검색 결과 없음: {entity_name}")
                return None
                
        except Exception as e:
            logger.error(f"⚠️ 엔티티 매핑 오류: {str(e)}")
            return None
    
    def map_entities_batch(self, entity_inputs: List[EntityInput]) -> Dict[str, Any]:
        """
        여러 엔티티를 일괄 매핑
        
        Args:
            entity_inputs: 매핑할 엔티티 리스트
            
        Returns:
            Dict: 매핑 결과와 통계 정보
        """
        start_time = time.time()
        successful_mappings = []
        failed_mappings = []
        
        for entity_input in entity_inputs:
            mapping_result = self.map_entity(entity_input)
            
            if mapping_result and mapping_result.mapping_score >= self.confidence_threshold:
                successful_mappings.append(mapping_result)
            else:
                failed_mappings.append({
                    'entity_name': entity_input.entity_name,
                    'entity_type': entity_input.entity_type.value,
                    'reason': 'Low confidence score' if mapping_result else 'No mapping found',
                    'mapping_score': mapping_result.mapping_score if mapping_result else 0.0
                })
        
        processing_time = time.time() - start_time
        
        result = {
            'successful_mappings': [
                {
                    'source_entity': {
                        'entity_name': mapping.source_entity.entity_name,
                        'entity_type': mapping.source_entity.entity_type.value,
                        'confidence': mapping.source_entity.confidence
                    },
                    'mapped_concept': {
                        'concept_id': mapping.mapped_concept_id,
                        'concept_name': mapping.mapped_concept_name,
                        'domain_id': mapping.domain_id,
                        'vocabulary_id': mapping.vocabulary_id,
                        'concept_class_id': mapping.concept_class_id,
                        'standard_concept': mapping.standard_concept,
                        'concept_code': mapping.concept_code
                    },
                    'mapping_score': mapping.mapping_score,
                    'mapping_confidence': mapping.mapping_confidence,
                    'mapping_method': mapping.mapping_method,
                    'alternative_concepts': mapping.alternative_concepts
                }
                for mapping in successful_mappings
            ],
            'failed_mappings': failed_mappings,
            'statistics': {
                'total_entities': len(entity_inputs),
                'successful_mappings': len(successful_mappings),
                'failed_mappings': len(failed_mappings),
                'success_rate': len(successful_mappings) / len(entity_inputs) if entity_inputs else 0.0,
                'processing_time': processing_time
            }
        }
        
        logger.info(f"✅ 일괄 매핑 완료: {len(successful_mappings)}/{len(entity_inputs)} 성공")
        return result
    
    def _prepare_entity_for_mapping(self, entity_input: EntityInput) -> List[Dict[str, Any]]:
        """엔티티 타입별 사전 매핑 정보 세팅"""
        entities_to_map = []
        
        # 4개 분류별 사전 매핑 정보 세팅
        if entity_input.entity_type == EntityTypeAPI.DIAGNOSTIC:
            entities_to_map.append({
                "entity_type": "diagnostic",
                "entity_name": entity_input.entity_name,
                "domain_id": entity_input.domain_id or "Condition",
                "vocabulary_id": entity_input.vocabulary_id or "SNOMED"
            })
        
        elif entity_input.entity_type == EntityTypeAPI.DRUG:
            entities_to_map.append({
                "entity_type": "drug",
                "entity_name": entity_input.entity_name,
                "domain_id": entity_input.domain_id or "Drug",
                "vocabulary_id": entity_input.vocabulary_id or "RxNorm"
            })
        
        elif entity_input.entity_type == EntityTypeAPI.TEST:
            entities_to_map.append({
                "entity_type": "test",
                "entity_name": entity_input.entity_name,
                "domain_id": entity_input.domain_id or "Measurement",
                "vocabulary_id": entity_input.vocabulary_id or "LOINC"
            })
        
        elif entity_input.entity_type == EntityTypeAPI.SURGERY:
            entities_to_map.append({
                "entity_type": "surgery",
                "entity_name": entity_input.entity_name,
                "domain_id": entity_input.domain_id or "Procedure",
                "vocabulary_id": entity_input.vocabulary_id or "SNOMED"
            })
        
        return entities_to_map
    
    def _normalize_score(self, raw_score: float) -> float:
        """Elasticsearch 점수 정규화"""
        if raw_score >= 50.0:
            return 0.95 + (raw_score - 50.0) / 100.0
        elif raw_score >= 20.0:
            return 0.85 + (raw_score - 20.0) / 100.0
        elif raw_score >= 10.0:
            return 0.70 + (raw_score - 10.0) / 30.0
        elif raw_score >= 5.0:
            return 0.50 + (raw_score - 5.0) / 10.0
        else:
            return raw_score / 10.0
    
    def _determine_confidence(self, score: float) -> str:
        """매핑 신뢰도 결정"""
        if score > 0.9:
            return "high"
        elif score > 0.7:
            return "medium"
        elif score > 0.5:
            return "low"
        else:
            return "very_low"
    
    def health_check(self) -> Dict[str, Any]:
        """API 상태 확인"""
        es_health = self.es_client.health_check()
        
        return {
            "api_status": "healthy",
            "elasticsearch_status": es_health,
            "supported_entity_types": [et.value for et in EntityTypeAPI],
            "confidence_threshold": self.confidence_threshold
        }


# API 편의 함수들
def map_single_entity(
    entity_name: str,
    entity_type: str,
    domain_id: Optional[str] = None,
    vocabulary_id: Optional[str] = None,
    confidence: float = 1.0
) -> Optional[MappingResult]:
    """
    단일 엔티티 매핑 편의 함수
    
    Args:
        entity_name: 엔티티 이름
        entity_type: 엔티티 타입 ('diagnostic', 'drug', 'test', 'surgery')
        domain_id: OMOP 도메인 ID (선택사항)
        vocabulary_id: OMOP 어휘체계 ID (선택사항)
        confidence: 엔티티 신뢰도
        
    Returns:
        MappingResult: 매핑 결과 또는 None
    """
    try:
        entity_type_enum = EntityTypeAPI(entity_type)
        entity_input = EntityInput(
            entity_name=entity_name,
            entity_type=entity_type_enum,
            domain_id=domain_id,
            vocabulary_id=vocabulary_id,
            confidence=confidence
        )
        
        api = EntityMappingAPI()
        return api.map_entity(entity_input)
        
    except ValueError:
        logger.error(f"지원하지 않는 엔티티 타입: {entity_type}")
        return None


def map_entities_from_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM 분석 결과에서 엔티티 매핑
    
    Args:
        analysis: LLM 분석 결과 딕셔너리
        
    Returns:
        Dict: 매핑 결과
    """
    api = EntityMappingAPI()
    entity_inputs = []
    
    # 진단 관련 엔티티 추출
    if "diagnostic" in analysis and analysis["diagnostic"]:
        diagnostic = analysis["diagnostic"]
        entity_inputs.append(EntityInput(
            entity_name=diagnostic["concept_name"],
            entity_type=EntityTypeAPI.DIAGNOSTIC,
            domain_id=diagnostic.get("domain_id", "Condition"),
            vocabulary_id=diagnostic.get("vocabulary_id", "SNOMED"),
            confidence=diagnostic.get("confidence", 1.0)
        ))
    
    # 약물 관련 엔티티 추출
    if "drug" in analysis and analysis["drug"]:
        drug = analysis["drug"]
        entity_inputs.append(EntityInput(
            entity_name=drug["concept_name"],
            entity_type=EntityTypeAPI.DRUG,
            domain_id=drug.get("domain_id", "Drug"),
            vocabulary_id=drug.get("vocabulary_id", "RxNorm"),
            confidence=drug.get("confidence", 1.0)
        ))
    
    # 검사 관련 엔티티 추출
    if "test" in analysis and analysis["test"]:
        test = analysis["test"]
        entity_inputs.append(EntityInput(
            entity_name=test["concept_name"],
            entity_type=EntityTypeAPI.TEST,
            domain_id=test.get("domain_id", "Measurement"),
            vocabulary_id=test.get("vocabulary_id", "LOINC"),
            confidence=test.get("confidence", 1.0)
        ))
    
    # 수술 관련 엔티티 추출
    if "surgery" in analysis and analysis["surgery"]:
        surgery = analysis["surgery"]
        entity_inputs.append(EntityInput(
            entity_name=surgery["concept_name"],
            entity_type=EntityTypeAPI.SURGERY,
            domain_id=surgery.get("domain_id", "Procedure"),
            vocabulary_id=surgery.get("vocabulary_id", "SNOMED"),
            confidence=surgery.get("confidence", 1.0)
        ))
    
    if not entity_inputs:
        return {
            'successful_mappings': [],
            'failed_mappings': [],
            'statistics': {
                'total_entities': 0,
                'successful_mappings': 0,
                'failed_mappings': 0,
                'success_rate': 0.0,
                'processing_time': 0.0
            }
        }
    
    return api.map_entities_batch(entity_inputs)
