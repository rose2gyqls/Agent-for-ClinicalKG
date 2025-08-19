"""
OMOP CDM 매핑기
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import time
from enum import Enum

from .elasticsearch_client import ElasticsearchClient, SearchResult
from ..graph.entity_extractor import ClinicalEntity, EntityType


class MappingConfidence(Enum):
    """매핑 신뢰도"""
    HIGH = "high"        # > 0.9
    MEDIUM = "medium"    # 0.7 - 0.9
    LOW = "low"          # 0.5 - 0.7
    VERY_LOW = "very_low"  # < 0.5


@dataclass
class OMOPConcept:
    """OMOP CDM Concept 데이터 클래스"""
    concept_id: str
    concept_name: str
    domain_id: str
    vocabulary_id: str
    concept_class_id: str
    standard_concept: str
    concept_code: str
    valid_start_date: Optional[str] = None
    valid_end_date: Optional[str] = None
    invalid_reason: Optional[str] = None


@dataclass 
class EntityMapping:
    """엔티티 매핑 결과 데이터 클래스"""
    source_entity: ClinicalEntity
    omop_concept: OMOPConcept
    mapping_score: float
    mapping_confidence: MappingConfidence
    mapping_method: str
    alternative_concepts: List[OMOPConcept] = None
    
    def __post_init__(self):
        if self.alternative_concepts is None:
            self.alternative_concepts = []


class OMOPMapper:
    """OMOP CDM 매핑기"""
    
    def __init__(
        self,
        es_client: Optional[ElasticsearchClient] = None,
        confidence_threshold: float = 0.5,
        max_alternatives: int = 3
    ):
        """
        OMOP 매핑기 초기화
        
        Args:
            es_client: Elasticsearch 클라이언트
            confidence_threshold: 매핑 신뢰도 임계치
            max_alternatives: 대안 컨셉 최대 개수
        """
        self.es_client = es_client or ElasticsearchClient.create_default()
        self.confidence_threshold = confidence_threshold
        self.max_alternatives = max_alternatives
        
        # 4개 분류별 OMOP 도메인 매핑
        self.entity_to_domain_mapping = {
            EntityType.DIAGNOSTIC: ["Condition"],
            EntityType.DRUG: ["Drug"],
            EntityType.TEST: ["Measurement"],
            EntityType.SURGERY: ["Procedure"]
        }
        
        # 4개 분류별 선호 어휘체계
        self.entity_to_vocabulary_mapping = {
            EntityType.DIAGNOSTIC: ["SNOMED"],
            EntityType.DRUG: ["RxNorm"],
            EntityType.TEST: ["LOINC"],
            EntityType.SURGERY: ["SNOMED"]
        }
        
        print(f"✅ OMOPMapper 초기화 완료")
    
    def map_entities_to_omop(
        self,
        entities: List[ClinicalEntity]
    ) -> Dict[str, Any]:
        """
        엔티티들을 OMOP CDM에 매핑
        
        Args:
            entities: 매핑할 엔티티 리스트
            
        Returns:
            Dict: 매핑 결과와 메타데이터
        """
        start_time = time.time()
        
        try:
            successful_mappings = []
            failed_mappings = []
            
            for entity in entities:
                try:
                    # 단일 엔티티 매핑
                    mapping = self._map_single_entity(entity)
                    
                    if mapping and mapping.mapping_score >= self.confidence_threshold:
                        successful_mappings.append(mapping)
                    else:
                        failed_mappings.append({
                            'entity': entity,
                            'reason': 'Low confidence score' if mapping else 'No mapping found',
                            'best_mapping': mapping
                        })
                        
                except Exception as e:
                    failed_mappings.append({
                        'entity': entity,
                        'reason': f'Mapping error: {str(e)}',
                        'best_mapping': None
                    })
            
            # 매핑 통계 계산
            mapping_stats = self._calculate_mapping_statistics(successful_mappings)
            
            processing_time = time.time() - start_time
            
            result = {
                'successful_mappings': [
                    {
                        'source_entity': {
                            'text': mapping.source_entity.text,
                            'entity_type': mapping.source_entity.entity_type.value,
                            'normalized_text': mapping.source_entity.normalized_text,
                            'confidence': mapping.source_entity.confidence
                        },
                        'omop_concept': {
                            'concept_id': mapping.omop_concept.concept_id,
                            'concept_name': mapping.omop_concept.concept_name,
                            'domain_id': mapping.omop_concept.domain_id,
                            'vocabulary_id': mapping.omop_concept.vocabulary_id,
                            'concept_class_id': mapping.omop_concept.concept_class_id,
                            'standard_concept': mapping.omop_concept.standard_concept,
                            'concept_code': mapping.omop_concept.concept_code
                        },
                        'mapping_score': mapping.mapping_score,
                        'mapping_confidence': mapping.mapping_confidence.value,
                        'mapping_method': mapping.mapping_method,
                        'alternative_concepts': [
                            {
                                'concept_id': alt.concept_id,
                                'concept_name': alt.concept_name,
                                'vocabulary_id': alt.vocabulary_id
                            }
                            for alt in mapping.alternative_concepts
                        ]
                    }
                    for mapping in successful_mappings
                ],
                'failed_mappings': [
                    {
                        'entity_text': failure['entity'].text,
                        'entity_type': failure['entity'].entity_type.value,
                        'failure_reason': failure['reason'],
                        'best_attempt': {
                            'concept_name': failure['best_mapping'].omop_concept.concept_name if failure['best_mapping'] else None,
                            'mapping_score': failure['best_mapping'].mapping_score if failure['best_mapping'] else 0.0
                        } if failure['best_mapping'] else None
                    }
                    for failure in failed_mappings
                ],
                'mapping_statistics': mapping_stats,
                'mapping_metadata': {
                    'total_entities': len(entities),
                    'successful_mappings': len(successful_mappings),
                    'failed_mappings': len(failed_mappings),
                    'success_rate': len(successful_mappings) / len(entities) if entities else 0.0,
                    'processing_time': processing_time,
                    'confidence_threshold': self.confidence_threshold,
                    'mapping_timestamp': time.time()
                }
            }
            
            print(f"✅ OMOP 매핑 완료: {len(successful_mappings)}/{len(entities)} 성공")
            return result
            
        except Exception as e:
            return {
                'successful_mappings': [],
                'failed_mappings': [],
                'mapping_statistics': {},
                'mapping_metadata': {
                    'total_entities': len(entities),
                    'successful_mappings': 0,
                    'failed_mappings': len(entities),
                    'success_rate': 0.0,
                    'processing_time': time.time() - start_time,
                    'error': str(e),
                    'mapping_timestamp': time.time()
                }
            }
    
    def _map_single_entity(self, entity: ClinicalEntity) -> Optional[EntityMapping]:
        """단일 엔티티를 OMOP CDM에 매핑"""
        
        # Elasticsearch 클라이언트 확인 (수정: es_client.es_client 사용)
        if not self.es_client or not self.es_client.es_client:
            print(f"⚠️ Elasticsearch 클라이언트 없음 - 더미 매핑 생성: {entity.text}")
            return self._create_dummy_mapping(entity)
        
        # 1. 엔티티 타입에 따른 도메인 및 어휘체계 결정
        domain_ids = self.entity_to_domain_mapping.get(entity.entity_type, [])
        vocabulary_ids = self.entity_to_vocabulary_mapping.get(entity.entity_type, [])
        
        print(f"🔍 매핑 시도: '{entity.text}' (타입: {entity.entity_type.value})")
        print(f"  - 도메인: {domain_ids}")
        print(f"  - 어휘체계: {vocabulary_ids}")
        
        # 2. 정확 매칭 시도
        print(f"  📋 정확 매칭 검색 중...")
        exact_matches = self._search_exact_matches(entity, domain_ids, vocabulary_ids)
        print(f"    결과: {len(exact_matches)}개")
        
        if exact_matches:
            print(f"    ✅ 정확 매칭 성공: {exact_matches[0].concept_name}")
            return self._create_mapping_from_search_results(
                entity, exact_matches, "exact_match"
            )
        
        # 3. 퍼지 매칭 시도
        print(f"  🔍 퍼지 매칭 검색 중...")
        fuzzy_matches = self._search_fuzzy_matches(entity, domain_ids, vocabulary_ids)
        print(f"    결과: {len(fuzzy_matches)}개")
        
        if fuzzy_matches:
            print(f"    ✅ 퍼지 매칭 성공: {fuzzy_matches[0].concept_name}")
            return self._create_mapping_from_search_results(
                entity, fuzzy_matches, "fuzzy_match"
            )
        
        # 4. 동의어 매칭 시도
        print(f"  🔗 동의어 매칭 검색 중...")
        synonym_matches = self._search_synonym_matches(entity, domain_ids, vocabulary_ids)
        print(f"    결과: {len(synonym_matches)}개")
        
        if synonym_matches:
            print(f"    ✅ 동의어 매칭 성공: {synonym_matches[0].concept_name}")
            return self._create_mapping_from_search_results(
                entity, synonym_matches, "synonym_match"
            )
        
        # 5. 매핑 실패 시 더미 매핑 생성
        print(f"⚠️ 모든 매핑 방법 실패 - 더미 매핑 생성: {entity.text}")
        return self._create_dummy_mapping(entity)
    
    def _create_dummy_mapping(self, entity: ClinicalEntity) -> EntityMapping:
        """더미 OMOP 매핑 생성 (Elasticsearch 없을 때 사용)"""
        
        # 4개 분류에 따른 기본 도메인 설정
        domain_mapping = {
            EntityType.DIAGNOSTIC: "Condition",
            EntityType.DRUG: "Drug",
            EntityType.TEST: "Measurement",
            EntityType.SURGERY: "Procedure"
        }
        
        vocabulary_mapping = {
            EntityType.DIAGNOSTIC: "SNOMED",
            EntityType.DRUG: "RxNorm",
            EntityType.TEST: "LOINC",
            EntityType.SURGERY: "SNOMED"
        }
        
        domain_id = domain_mapping.get(entity.entity_type, "Condition")
        vocabulary_id = vocabulary_mapping.get(entity.entity_type, "SNOMED")
        
        # 더미 OMOP 컨셉 생성
        dummy_concept = OMOPConcept(
            concept_id=f"DUMMY_{entity.entity_type.value.upper()}_{hash(entity.text) % 10000}",
            concept_name=entity.normalized_text,
            domain_id=domain_id,
            vocabulary_id=vocabulary_id,
            concept_class_id="Clinical Finding",
            standard_concept="S",
            concept_code=f"DUMMY_{entity.text.replace(' ', '_').upper()}"
        )
        
        # 더미 매핑 생성
        mapping = EntityMapping(
            source_entity=entity,
            omop_concept=dummy_concept,
            mapping_score=0.3,  # 낮은 신뢰도
            mapping_confidence=MappingConfidence.LOW,
            mapping_method="dummy_mapping",
            alternative_concepts=[]
        )
        
        print(f"✅ 더미 매핑 생성: {entity.text} -> {dummy_concept.concept_name}")
        return mapping
    
    def _search_exact_matches(
        self,
        entity: ClinicalEntity,
        domain_ids: List[str],
        vocabulary_ids: List[str]
    ) -> List[SearchResult]:
        """정확 매칭 검색 (직접 Elasticsearch 쿼리 사용)"""
        try:
            print(f"    🔍 정확 매칭 검색 시작: '{entity.normalized_text}'")
            
            # 간단한 검색 쿼리 (필터 제거, test_elasticsearch_connection.py 방식)
            search_body = {
                "query": {
                    "bool": {
                        "should": [
                            {"match": {"concept_name": {"query": entity.normalized_text, "boost": 3.0}}},
                            {"match": {"concept_code": {"query": entity.normalized_text, "boost": 2.0}}},
                            {"wildcard": {"concept_name": {"value": f"*{entity.normalized_text}*", "boost": 1.5}}},
                            {"fuzzy": {"concept_name": {"value": entity.normalized_text, "fuzziness": "AUTO", "boost": 1.0}}}
                        ],
                        "minimum_should_match": 1
                    }
                },
                "size": 10,
                "sort": [{"_score": {"order": "desc"}}]
            }
            
            print(f"      - 간단한 검색 쿼리 사용 (필터 제거)")
            
            # 모든 concept 인덱스에서 검색
            concept_indices = self._get_concept_indices()
            print(f"      - 검색 인덱스: {concept_indices}")
            
            print(f"      - 검색 쿼리 실행 중...")
            response = self.es_client.es_client.search(
                index=",".join(concept_indices),
                body=search_body
            )
            
            print(f"      - 검색 응답 받음: {response['hits']['total']['value']}개 결과")
            
            # SearchResult로 변환
            results = self._convert_elasticsearch_response_to_search_results(response)
            print(f"      - 변환된 결과: {len(results)}개")
            
            # 정확 매칭 필터링 (높은 점수)
            exact_matches = [r for r in results if r.score > 8.0]
            print(f"      - 정확 매칭 (점수 > 8.0): {len(exact_matches)}개")
            
            if exact_matches:
                print(f"      - 최고 점수: {exact_matches[0].score:.2f}")
                print(f"      - 최고 결과: {exact_matches[0].concept_name}")
            
            return exact_matches
            
        except Exception as e:
            print(f"⚠️ 정확 매칭 검색 실패: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _search_fuzzy_matches(
        self,
        entity: ClinicalEntity,
        domain_ids: List[str],
        vocabulary_ids: List[str]
    ) -> List[SearchResult]:
        """퍼지 매칭 검색 (직접 Elasticsearch 쿼리 사용)"""
        try:
            # 직접 Elasticsearch 쿼리 구성
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "bool": {
                                    "should": [
                                        {"match": {"concept_name": {"query": entity.text, "boost": 3.0}}},
                                        {"match": {"concept_code": {"query": entity.text, "boost": 2.0}}},
                                        {"wildcard": {"concept_name": {"value": f"*{entity.text}*", "boost": 1.5}}},
                                        {"fuzzy": {"concept_name": {"value": entity.text, "fuzziness": "AUTO", "boost": 1.0}}}
                                    ],
                                    "minimum_should_match": 1
                                }
                            }
                        ],
                        "filter": []
                    }
                },
                "size": 10,
                "sort": [{"_score": {"order": "desc"}}]
            }
            
            # 도메인 필터 추가
            if domain_ids:
                search_body["query"]["bool"]["filter"].append({"terms": {"domain_id": domain_ids}})
            
            # 어휘체계 필터 추가
            if vocabulary_ids:
                search_body["query"]["bool"]["filter"].append({"terms": {"vocabulary_id": vocabulary_ids}})
            
            # 표준 컨셉 필터 (선택적)
            search_body["query"]["bool"]["filter"].append({
                "bool": {
                    "should": [
                        {"term": {"standard_concept": "S"}},
                        {"bool": {"must_not": {"exists": {"field": "standard_concept"}}}}
                    ]
                }
            })
            
            # 모든 concept 인덱스에서 검색
            concept_indices = self._get_concept_indices()
            
            response = self.es_client.es_client.search(
                index=",".join(concept_indices),
                body=search_body
            )
            
            # SearchResult로 변환
            results = self._convert_elasticsearch_response_to_search_results(response)
            
            # 중간 점수 결과 필터링
            fuzzy_matches = [r for r in results if 5.0 <= r.score <= 8.0]
            return fuzzy_matches
            
        except Exception as e:
            print(f"⚠️ 퍼지 매칭 검색 실패: {str(e)}")
            return []
    
    def _search_synonym_matches(
        self,
        entity: ClinicalEntity,
        domain_ids: List[str],
        vocabulary_ids: List[str]
    ) -> List[SearchResult]:
        """동의어 매칭 검색 (직접 Elasticsearch 쿼리 사용)"""
        try:
            # 동의어 검색을 위한 확장된 쿼리
            search_body = {
                "query": {
                    "bool": {
                        "should": [
                            {
                                "bool": {
                                    "should": [
                                        {"match": {"concept_name": {"query": entity.text, "boost": 3.0}}},
                                        {"wildcard": {"concept_name": {"value": f"*{entity.text}*", "boost": 1.5}}}
                                    ],
                                    "minimum_should_match": 1
                                }
                            },
                            # 부분 매칭을 위한 쿼리
                            {
                                "bool": {
                                    "should": [
                                        {"match": {"concept_name": {"query": entity.text.split()[0], "boost": 2.0}}},
                                        {"wildcard": {"concept_name": {"value": f"*{entity.text.split()[0]}*", "boost": 1.0}}}
                                    ],
                                    "minimum_should_match": 1
                                }
                            }
                        ],
                        "minimum_should_match": 1,
                        "filter": []
                    }
                },
                "size": 15,
                "sort": [{"_score": {"order": "desc"}}]
            }
            
            # 도메인 필터 추가
            if domain_ids:
                search_body["query"]["bool"]["filter"].append({"terms": {"domain_id": domain_ids}})
            
            # 어휘체계 필터 추가
            if vocabulary_ids:
                search_body["query"]["bool"]["filter"].append({"terms": {"vocabulary_id": vocabulary_ids}})
            
            # 표준 컨셉 필터 (비표준도 포함)
            search_body["query"]["bool"]["filter"].append({
                "bool": {
                    "should": [
                        {"term": {"standard_concept": "S"}},
                        {"bool": {"must_not": {"exists": {"field": "standard_concept"}}}},
                        {"term": {"standard_concept": "C"}}  # Classification
                    ]
                }
            })
            
            # 모든 concept 인덱스에서 검색
            concept_indices = self._get_concept_indices()
            
            response = self.es_client.es_client.search(
                index=",".join(concept_indices),
                body=search_body
            )
            
            # SearchResult로 변환
            results = self._convert_elasticsearch_response_to_search_results(response)
            
            # 낮은 점수 결과도 포함 (동의어 매칭용)
            synonym_matches = [r for r in results if r.score >= 2.0]
            return synonym_matches
            
        except Exception as e:
            print(f"⚠️ 동의어 매칭 검색 실패: {str(e)}")
            return []
    
    def _get_concept_indices(self) -> List[str]:
        """사용 가능한 concept 인덱스 목록 반환"""
        try:
            indices = self.es_client.es_client.cat.indices(format='json')
            concept_indices = []
            
            for idx in indices:
                index_name = idx['index']
                if any(keyword in index_name.lower() for keyword in ['concept', 'omop', 'snomed', 'rxnorm', 'loinc']):
                    concept_indices.append(index_name)
            
            return concept_indices
        except Exception as e:
            print(f"⚠️ concept 인덱스 조회 실패: {str(e)}")
            # 기본값으로 concept-drug 반환
            return ["concept-drug"]
    
    def _convert_elasticsearch_response_to_search_results(self, response: Dict[str, Any]) -> List[SearchResult]:
        """Elasticsearch 응답을 SearchResult 리스트로 변환"""
        results = []
        
        try:
            for hit in response['hits']['hits']:
                source = hit['_source']
                score = hit['_score']
                
                # SearchResult 객체 생성
                search_result = SearchResult(
                    concept_id=str(source.get('concept_id', '')),
                    concept_name=source.get('concept_name', ''),
                    domain_id=source.get('domain_id', ''),
                    vocabulary_id=source.get('vocabulary_id', ''),
                    concept_class_id=source.get('concept_class_id', ''),
                    standard_concept=source.get('standard_concept', ''),
                    concept_code=source.get('concept_code', ''),
                    score=score
                )
                
                results.append(search_result)
                
        except Exception as e:
            print(f"⚠️ 응답 변환 실패: {str(e)}")
        
        return results
    
    def _create_mapping_from_search_results(
        self,
        entity: ClinicalEntity,
        search_results: List[SearchResult],
        mapping_method: str
    ) -> Optional[EntityMapping]:
        """검색 결과에서 매핑 생성"""
        if not search_results:
            return None
        
        # 최고 점수 결과를 메인 매핑으로 사용
        best_result = search_results[0]
        
        # OMOP Concept 생성
        omop_concept = OMOPConcept(
            concept_id=best_result.concept_id,
            concept_name=best_result.concept_name,
            domain_id=best_result.domain_id,
            vocabulary_id=best_result.vocabulary_id,
            concept_class_id=best_result.concept_class_id,
            standard_concept=best_result.standard_concept,
            concept_code=best_result.concept_code
        )
        
        # 매핑 점수 정규화 (개선된 버전)
        # Elasticsearch 점수 범위를 고려한 정규화
        raw_score = best_result.score
        
        # 점수 범위별 정규화 (더 세밀한 구분)
        if raw_score >= 50.0:
            # 매우 높은 점수 (50+): 0.95-1.0
            normalized_score = 0.95 + (raw_score - 50.0) / 100.0
        elif raw_score >= 20.0:
            # 높은 점수 (20-49): 0.85-0.95
            normalized_score = 0.85 + (raw_score - 20.0) / 100.0
        elif raw_score >= 10.0:
            # 중간 점수 (10-19): 0.70-0.85
            normalized_score = 0.70 + (raw_score - 10.0) / 30.0
        elif raw_score >= 5.0:
            # 낮은 점수 (5-9): 0.50-0.70
            normalized_score = 0.50 + (raw_score - 5.0) / 10.0
        else:
            # 매우 낮은 점수 (<5): 0.0-0.50
            normalized_score = raw_score / 10.0
        
        # 0-1 범위로 제한
        normalized_score = max(0.0, min(1.0, normalized_score))
        
        # 매핑 신뢰도 결정
        mapping_confidence = self._determine_mapping_confidence(normalized_score, mapping_method)
        
        # 대안 컨셉들
        alternative_concepts = []
        for result in search_results[1:self.max_alternatives+1]:
            alt_concept = OMOPConcept(
                concept_id=result.concept_id,
                concept_name=result.concept_name,
                domain_id=result.domain_id,
                vocabulary_id=result.vocabulary_id,
                concept_class_id=result.concept_class_id,
                standard_concept=result.standard_concept,
                concept_code=result.concept_code
            )
            alternative_concepts.append(alt_concept)
        
        mapping = EntityMapping(
            source_entity=entity,
            omop_concept=omop_concept,
            mapping_score=normalized_score,
            mapping_confidence=mapping_confidence,
            mapping_method=mapping_method,
            alternative_concepts=alternative_concepts
        )
        
        return mapping
    
    def _determine_mapping_confidence(
        self,
        score: float,
        mapping_method: str
    ) -> MappingConfidence:
        """매핑 신뢰도 결정"""
        
        # 매핑 방법에 따른 가중치
        method_weights = {
            "exact_match": 1.0,
            "fuzzy_match": 0.8,
            "synonym_match": 0.6
        }
        
        weighted_score = score * method_weights.get(mapping_method, 0.5)
        
        if weighted_score > 0.9:
            return MappingConfidence.HIGH
        elif weighted_score > 0.7:
            return MappingConfidence.MEDIUM
        elif weighted_score > 0.5:
            return MappingConfidence.LOW
        else:
            return MappingConfidence.VERY_LOW
    
    def _calculate_mapping_statistics(
        self,
        mappings: List[EntityMapping]
    ) -> Dict[str, Any]:
        """매핑 통계 계산"""
        if not mappings:
            return {}
        
        stats = {
            'total_mappings': len(mappings),
            'by_confidence': {},
            'by_method': {},
            'by_domain': {},
            'by_vocabulary': {},
            'avg_mapping_score': sum(m.mapping_score for m in mappings) / len(mappings)
        }
        
        # 신뢰도별 통계
        for mapping in mappings:
            confidence = mapping.mapping_confidence.value
            if confidence not in stats['by_confidence']:
                stats['by_confidence'][confidence] = 0
            stats['by_confidence'][confidence] += 1
            
            # 방법별 통계
            method = mapping.mapping_method
            if method not in stats['by_method']:
                stats['by_method'][method] = 0
            stats['by_method'][method] += 1
            
            # 도메인별 통계
            domain = mapping.omop_concept.domain_id
            if domain not in stats['by_domain']:
                stats['by_domain'][domain] = 0
            stats['by_domain'][domain] += 1
            
            # 어휘체계별 통계
            vocabulary = mapping.omop_concept.vocabulary_id
            if vocabulary not in stats['by_vocabulary']:
                stats['by_vocabulary'][vocabulary] = 0
            stats['by_vocabulary'][vocabulary] += 1
        
        return stats
    
    def health_check(self) -> Dict[str, Any]:
        """매핑기 상태 확인"""
        es_health = self.es_client.health_check()
        
        return {
            "omop_mapper_status": "initialized",
            "elasticsearch_status": es_health,
            "configuration": {
                "confidence_threshold": self.confidence_threshold,
                "max_alternatives": self.max_alternatives,
                "supported_entity_types": [et.value for et in EntityType],
                "domain_mappings": {et.value: domains for et, domains in self.entity_to_domain_mapping.items()},
                "vocabulary_mappings": {et.value: vocabs for et, vocabs in self.entity_to_vocabulary_mapping.items()}
            }
        }
    
    @classmethod
    def create_default(cls) -> 'OMOPMapper':
        """기본 설정으로 매핑기 생성"""
        return cls() 