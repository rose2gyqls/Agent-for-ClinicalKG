"""
RDF 트리플 생성기
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import time
from enum import Enum

# Optional imports for RDF support
try:
    from rdflib import Graph, Namespace, URIRef, Literal, BNode
    from rdflib.namespace import RDF, RDFS, OWL, XSD
    HAS_RDFLIB = True
except ImportError:
    HAS_RDFLIB = False
    # Dummy classes for when rdflib is not available
    class Graph:
        def __init__(self): pass
        def bind(self, *args): pass
        def add(self, *args): pass
        def serialize(self, format='turtle'): return f"# RDFLib not available, format: {format}"
    
    class Namespace:
        def __init__(self, uri): self.uri = uri
        def __getitem__(self, name): return f"{self.uri}{name}"
        def __getattr__(self, name): return f"{self.uri}{name}"
    
    URIRef = Literal = BNode = str
    RDF = RDFS = OWL = XSD = Namespace("http://dummy/")

from ..mapping.omop_mapper import EntityMapping
from ..extraction.dp_extractor import DigitalPhenotype


class TripleType(Enum):
    """트리플 타입"""
    ENTITY_HAS_CONCEPT = "entity_has_concept"
    CONCEPT_IS_A = "concept_is_a"
    DP_CONTAINS_ENTITY = "dp_contains_entity"
    ENTITY_IN_SECTION = "entity_in_section"
    CONCEPT_SYNONYM = "concept_synonym"


@dataclass
class Triple:
    """RDF 트리플 데이터 클래스"""
    subject: str
    predicate: str
    object: str
    triple_type: TripleType
    confidence: float
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TripleGenerator:
    """RDF 트리플 생성기"""
    
    def __init__(self, base_uri: str = "http://kg-clinical-guideline.org/"):
        """
        트리플 생성기 초기화
        
        Args:
            base_uri: 기본 네임스페이스 URI
        """
        self.base_uri = base_uri
        
        # 네임스페이스 정의
        self.KG = Namespace(base_uri + "kg/")
        self.OMOP = Namespace(base_uri + "omop/")
        self.ENTITY = Namespace(base_uri + "entity/")
        self.DP = Namespace(base_uri + "dp/")
        self.SECTION = Namespace(base_uri + "section/")
        
        # 커스텀 속성들
        self.HAS_CONCEPT = self.KG.hasConcept if HAS_RDFLIB else f"{base_uri}kg/hasConcept"
        self.CONTAINS_ENTITY = self.KG.containsEntity if HAS_RDFLIB else f"{base_uri}kg/containsEntity"
        self.IN_SECTION = self.KG.inSection if HAS_RDFLIB else f"{base_uri}kg/inSection"
        self.HAS_CONFIDENCE = self.KG.hasConfidence if HAS_RDFLIB else f"{base_uri}kg/hasConfidence"
        self.HAS_MAPPING_METHOD = self.KG.hasMappingMethod if HAS_RDFLIB else f"{base_uri}kg/hasMappingMethod"
        self.MAPPING_SCORE = self.KG.mappingScore if HAS_RDFLIB else f"{base_uri}kg/mappingScore"
        self.ENTITY_TYPE = self.KG.entityType if HAS_RDFLIB else f"{base_uri}kg/entityType"
        self.CONCEPT_ID = self.KG.conceptId if HAS_RDFLIB else f"{base_uri}kg/conceptId"
        self.DOMAIN_ID = self.KG.domainId if HAS_RDFLIB else f"{base_uri}kg/domainId"
        self.VOCABULARY_ID = self.KG.vocabularyId if HAS_RDFLIB else f"{base_uri}kg/vocabularyId"
        
        rdf_status = "RDFLib 사용 가능" if HAS_RDFLIB else "RDFLib 없음 (기본 기능만)"
        print(f"✅ TripleGenerator 초기화 완료 - {rdf_status}")
    
    def generate_triples_from_dps(
        self,
        validated_dps: List[DigitalPhenotype],
        original_text: str,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        DP로부터 직접 트리플 생성
        
        Args:
            validated_dps: 검증된 DP 리스트
            original_text: 원본 텍스트
            use_llm: LLM을 사용하여 트리플 생성할지 여부
            
        Returns:
            Dict: 생성된 트리플과 메타데이터
        """
        start_time = time.time()
        
        try:
            all_triples = []
            
            if use_llm:
                # LLM을 사용하여 dp_to_triple.txt 프롬프트로 트리플 생성
                all_triples = self._generate_triples_with_llm(validated_dps, original_text)
            else:
                # 기존 방식으로 트리플 생성 (엔티티 매핑 필요)
                return self.generate_triples_from_mappings([], validated_dps, original_text)
            
            # 트리플 통계 계산
            triple_stats = self._calculate_triple_statistics(all_triples)
            
            # RDF 그래프 생성
            graph = Graph()
            self._bind_namespaces(graph)
            self._add_triples_to_graph(all_triples, graph)
            
            # RDF 그래프를 다양한 형식으로 직렬화
            serialized_formats = self._serialize_graph(graph)
            
            processing_time = time.time() - start_time
            
            result = {
                'triples': [
                    {
                        'subject': triple.subject,
                        'predicate': triple.predicate,
                        'object': triple.object,
                        'triple_type': triple.triple_type.value,
                        'confidence': triple.confidence,
                        'metadata': triple.metadata
                    }
                    for triple in all_triples
                ],
                'rdf_graph': {
                    'turtle': serialized_formats['turtle'],
                    'json_ld': serialized_formats['json_ld'],
                    'n3': serialized_formats['n3'],
                    'xml': serialized_formats['xml']
                },
                'statistics': triple_stats,
                'generation_metadata': {
                    'total_triples': len(all_triples),
                    'total_dps': len(validated_dps),
                    'processing_time': processing_time,
                    'base_uri': self.base_uri,
                    'generation_timestamp': time.time(),
                    'method': 'llm' if use_llm else 'mapping'
                }
            }
            
            print(f"✅ 트리플 생성 완료: {len(all_triples)}개 트리플")
            return result
            
        except Exception as e:
            return {
                'triples': [],
                'rdf_graph': {},
                'statistics': {},
                'generation_metadata': {
                    'total_triples': 0,
                    'total_dps': len(validated_dps),
                    'processing_time': time.time() - start_time,
                    'error': str(e),
                    'generation_timestamp': time.time()
                }
            }
    
    def generate_triples_from_mappings(
        self,
        entity_mappings: List[EntityMapping],
        validated_dps: List[DigitalPhenotype],
        original_text: str
    ) -> Dict[str, Any]:
        """
        엔티티 매핑으로부터 트리플 생성
        
        Args:
            entity_mappings: 엔티티 매핑 리스트
            validated_dps: 검증된 DP 리스트
            original_text: 원본 텍스트
            
        Returns:
            Dict: 생성된 트리플과 메타데이터
        """
        start_time = time.time()
        
        try:
            # RDF 그래프 초기화
            graph = Graph()
            self._bind_namespaces(graph)
            
            all_triples = []
            
            # 1. DP 관련 트리플 생성
            dp_triples = self._generate_dp_triples(validated_dps, graph)
            all_triples.extend(dp_triples)
            
            # 2. 엔티티-OMOP 매핑 트리플 생성
            mapping_triples = self._generate_mapping_triples(entity_mappings, graph)
            all_triples.extend(mapping_triples)
            
            # 3. 엔티티-DP 관계 트리플 생성
            entity_dp_triples = self._generate_entity_dp_triples(entity_mappings, validated_dps, graph)
            all_triples.extend(entity_dp_triples)
            
            # 4. 계층구조 트리플 생성
            hierarchy_triples = self._generate_hierarchy_triples(entity_mappings, graph)
            all_triples.extend(hierarchy_triples)
            
            # 트리플 통계 계산
            triple_stats = self._calculate_triple_statistics(all_triples)
            
            # RDF 그래프를 다양한 형식으로 직렬화
            serialized_formats = self._serialize_graph(graph)
            
            processing_time = time.time() - start_time
            
            result = {
                'triples': [
                    {
                        'subject': triple.subject,
                        'predicate': triple.predicate,
                        'object': triple.object,
                        'triple_type': triple.triple_type.value,
                        'confidence': triple.confidence,
                        'metadata': triple.metadata
                    }
                    for triple in all_triples
                ],
                'rdf_graph': {
                    'turtle': serialized_formats['turtle'],
                    'json_ld': serialized_formats['json_ld'],
                    'n3': serialized_formats['n3'],
                    'xml': serialized_formats['xml']
                },
                'statistics': triple_stats,
                'generation_metadata': {
                    'total_triples': len(all_triples),
                    'total_entities': len(entity_mappings),
                    'total_dps': len(validated_dps),
                    'processing_time': processing_time,
                    'base_uri': self.base_uri,
                    'generation_timestamp': time.time()
                }
            }
            
            print(f"✅ 트리플 생성 완료: {len(all_triples)}개 트리플")
            return result
            
        except Exception as e:
            return {
                'triples': [],
                'rdf_graph': {},
                'statistics': {},
                'generation_metadata': {
                    'total_triples': 0,
                    'total_entities': len(entity_mappings),
                    'total_dps': len(validated_dps),
                    'processing_time': time.time() - start_time,
                    'error': str(e),
                    'generation_timestamp': time.time()
                }
            }
    
    def _bind_namespaces(self, graph: Graph):
        """네임스페이스 바인딩"""
        graph.bind("kg", self.KG)
        graph.bind("omop", self.OMOP)
        graph.bind("entity", self.ENTITY)
        graph.bind("dp", self.DP)
        graph.bind("section", self.SECTION)
        graph.bind("owl", OWL)
        graph.bind("rdfs", RDFS)
    
    def _generate_dp_triples(
        self,
        validated_dps: List[DigitalPhenotype],
        graph: Graph
    ) -> List[Triple]:
        """DP 관련 트리플 생성"""
        triples = []
        
        for dp in validated_dps:
            dp_uri = self.DP[self._safe_uri_name(dp.dp_id)]
            
            # DP 타입 선언
            graph.add((dp_uri, RDF.type, self.KG.DigitalPhenotype))
            triples.append(Triple(
                subject=str(dp_uri),
                predicate=str(RDF.type),
                object=str(self.KG.DigitalPhenotype),
                triple_type=TripleType.DP_CONTAINS_ENTITY,
                confidence=1.0,
                metadata={'dp_id': dp.dp_id}
            ))
            
            # DP 속성들
            graph.add((dp_uri, RDFS.label, Literal(dp.label)))
            graph.add((dp_uri, RDFS.comment, Literal(dp.definition)))
            graph.add((dp_uri, self.KG.hasConfidence, Literal(dp.confidence_score or 0.0, datatype=XSD.float)))
            
            # 섹션 정보
            if dp.section_reference:
                section_uri = self.SECTION[self._safe_uri_name(dp.section_reference)]
                graph.add((dp_uri, self.IN_SECTION, section_uri))
                graph.add((section_uri, RDF.type, self.KG.Section))
                graph.add((section_uri, RDFS.label, Literal(dp.section_reference)))
        
        return triples
    
    def _generate_mapping_triples(
        self,
        entity_mappings: List[EntityMapping],
        graph: Graph
    ) -> List[Triple]:
        """엔티티-OMOP 매핑 트리플 생성"""
        triples = []
        
        for mapping in entity_mappings:
            entity = mapping.source_entity
            concept = mapping.omop_concept
            
            # 엔티티 URI 생성
            entity_uri = self.ENTITY[self._safe_uri_name(f"{entity.text}_{entity.entity_type.value}")]
            concept_uri = self.OMOP[f"concept_{concept.concept_id}"]
            
            # 엔티티 타입 선언
            graph.add((entity_uri, RDF.type, self.KG.ClinicalEntity))
            graph.add((entity_uri, self.ENTITY_TYPE, Literal(entity.entity_type.value)))
            graph.add((entity_uri, RDFS.label, Literal(entity.text)))
            graph.add((entity_uri, self.KG.normalizedText, Literal(entity.normalized_text)))
            graph.add((entity_uri, self.HAS_CONFIDENCE, Literal(entity.confidence, datatype=XSD.float)))
            
            # OMOP 컨셉 선언
            graph.add((concept_uri, RDF.type, self.KG.OMOPConcept))
            graph.add((concept_uri, RDFS.label, Literal(concept.concept_name)))
            graph.add((concept_uri, self.CONCEPT_ID, Literal(concept.concept_id)))
            graph.add((concept_uri, self.DOMAIN_ID, Literal(concept.domain_id)))
            graph.add((concept_uri, self.VOCABULARY_ID, Literal(concept.vocabulary_id)))
            
            # 매핑 관계
            graph.add((entity_uri, self.HAS_CONCEPT, concept_uri))
            graph.add((entity_uri, self.MAPPING_SCORE, Literal(mapping.mapping_score, datatype=XSD.float)))
            graph.add((entity_uri, self.HAS_MAPPING_METHOD, Literal(mapping.mapping_method)))
            
            triples.append(Triple(
                subject=str(entity_uri),
                predicate=str(self.HAS_CONCEPT),
                object=str(concept_uri),
                triple_type=TripleType.ENTITY_HAS_CONCEPT,
                confidence=mapping.mapping_score,
                metadata={
                    'entity_text': entity.text,
                    'entity_type': entity.entity_type.value,
                    'concept_id': concept.concept_id,
                    'concept_name': concept.concept_name,
                    'mapping_method': mapping.mapping_method
                }
            ))
            
            # 대안 컨셉들
            for alt_concept in mapping.alternative_concepts:
                alt_concept_uri = self.OMOP[f"concept_{alt_concept.concept_id}"]
                graph.add((alt_concept_uri, RDF.type, self.KG.OMOPConcept))
                graph.add((alt_concept_uri, RDFS.label, Literal(alt_concept.concept_name)))
                graph.add((entity_uri, self.KG.hasAlternativeConcept, alt_concept_uri))
        
        return triples
    
    def _generate_entity_dp_triples(
        self,
        entity_mappings: List[EntityMapping],
        validated_dps: List[DigitalPhenotype],
        graph: Graph
    ) -> List[Triple]:
        """엔티티-DP 관계 트리플 생성"""
        triples = []
        
        # DP별 엔티티 매핑 생성
        for mapping in entity_mappings:
            entity = mapping.source_entity
            
            # 엔티티가 속한 DP 찾기
            source_dp_id = entity.metadata.get('source_dp_id')
            if source_dp_id:
                # DP URI와 엔티티 URI
                dp_uri = self.DP[self._safe_uri_name(source_dp_id)]
                entity_uri = self.ENTITY[self._safe_uri_name(f"{entity.text}_{entity.entity_type.value}")]
                
                # DP가 엔티티를 포함하는 관계
                graph.add((dp_uri, self.CONTAINS_ENTITY, entity_uri))
                
                triples.append(Triple(
                    subject=str(dp_uri),
                    predicate=str(self.CONTAINS_ENTITY),
                    object=str(entity_uri),
                    triple_type=TripleType.DP_CONTAINS_ENTITY,
                    confidence=entity.confidence,
                    metadata={
                        'dp_id': source_dp_id,
                        'entity_text': entity.text,
                        'entity_type': entity.entity_type.value
                    }
                ))
        
        return triples
    
    def _generate_hierarchy_triples(
        self,
        entity_mappings: List[EntityMapping],
        graph: Graph
    ) -> List[Triple]:
        """계층구조 트리플 생성"""
        triples = []
        
        # 같은 도메인의 컨셉들 간 관계 추가
        concepts_by_domain = {}
        
        for mapping in entity_mappings:
            concept = mapping.omop_concept
            domain = concept.domain_id
            
            if domain not in concepts_by_domain:
                concepts_by_domain[domain] = []
            concepts_by_domain[domain].append(concept)
        
        # 도메인별 상위 클래스 생성
        for domain, concepts in concepts_by_domain.items():
            domain_uri = self.KG[f"Domain_{domain}"]
            graph.add((domain_uri, RDF.type, self.KG.ConceptDomain))
            graph.add((domain_uri, RDFS.label, Literal(f"{domain} Domain")))
            
            for concept in concepts:
                concept_uri = self.OMOP[f"concept_{concept.concept_id}"]
                graph.add((concept_uri, self.KG.belongsToDomain, domain_uri))
                
                triples.append(Triple(
                    subject=str(concept_uri),
                    predicate=str(self.KG.belongsToDomain),
                    object=str(domain_uri),
                    triple_type=TripleType.CONCEPT_IS_A,
                    confidence=1.0,
                    metadata={
                        'concept_id': concept.concept_id,
                        'domain': domain
                    }
                ))
        
        return triples
    
    def _serialize_graph(self, graph: Graph) -> Dict[str, str]:
        """RDF 그래프를 다양한 형식으로 직렬화"""
        formats = {}
        
        try:
            formats['turtle'] = graph.serialize(format='turtle')
        except Exception as e:
            formats['turtle'] = f"# Turtle serialization error: {str(e)}"
        
        try:
            formats['json_ld'] = graph.serialize(format='json-ld')
        except Exception as e:
            formats['json_ld'] = '{"error": "JSON-LD serialization error: ' + str(e) + '"}'
        
        try:
            formats['n3'] = graph.serialize(format='n3')
        except Exception as e:
            formats['n3'] = f"# N3 serialization error: {str(e)}"
        
        try:
            formats['xml'] = graph.serialize(format='xml')
        except Exception as e:
            formats['xml'] = f"<!-- XML serialization error: {str(e)} -->"
        
        return formats
    
    def _safe_uri_name(self, name: str) -> str:
        """URI 안전 이름 생성"""
        import re
        # 특수문자를 언더스코어로 변환
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(name))
        # 연속된 언더스코어 제거
        safe_name = re.sub(r'_{2,}', '_', safe_name)
        # 시작과 끝의 언더스코어 제거
        safe_name = safe_name.strip('_')
        return safe_name or 'unnamed'
    
    def _calculate_triple_statistics(self, triples: List[Triple]) -> Dict[str, Any]:
        """트리플 통계 계산"""
        if not triples:
            return {}
        
        stats = {
            'total_triples': len(triples),
            'by_type': {},
            'confidence_distribution': {
                'high (>0.8)': 0,
                'medium (0.6-0.8)': 0,
                'low (<0.6)': 0
            },
            'avg_confidence': sum(t.confidence for t in triples) / len(triples),
            'unique_subjects': len(set(t.subject for t in triples)),
            'unique_predicates': len(set(t.predicate for t in triples)),
            'unique_objects': len(set(t.object for t in triples))
        }
        
        # 타입별 통계
        for triple in triples:
            triple_type = triple.triple_type.value
            if triple_type not in stats['by_type']:
                stats['by_type'][triple_type] = 0
            stats['by_type'][triple_type] += 1
            
            # 신뢰도 분포
            if triple.confidence > 0.8:
                stats['confidence_distribution']['high (>0.8)'] += 1
            elif triple.confidence >= 0.6:
                stats['confidence_distribution']['medium (0.6-0.8)'] += 1
            else:
                stats['confidence_distribution']['low (<0.6)'] += 1
        
        return stats
    
    def _generate_triples_with_llm(
        self,
        validated_dps: List[DigitalPhenotype],
        original_text: str
    ) -> List[Triple]:
        """LLM을 사용하여 DP에서 트리플 생성"""
        all_triples = []
        
        try:
            # LLM Factory 동적 import 시도
            try:
                from ..llm.llm_factory import LLMFactory
                llm = LLMFactory.get_default_llm()
                print("✅ LLMFactory에서 LLM 생성 완료")
            except (ImportError, AttributeError) as e:
                print(f"⚠️ LLMFactory import/초기화 실패: {str(e)}")
                # 기본 LLM 생성 시도
                from ..llm.gemini_llm import GeminiLLM
                llm = GeminiLLM.create_default()
                print("✅ GeminiLLM에서 LLM 생성 완료")
            
            print(f"🔄 {len(validated_dps)}개 DP에 대해 LLM 트리플 생성 시작")
            
            for i, dp in enumerate(validated_dps):
                print(f"\n📋 DP {i+1}/{len(validated_dps)}: {dp.dp_id}")
                print(f"   라벨: {dp.label}")
                print(f"   정의: {dp.definition[:100]}...")
                
                # dp_to_triple.txt 프롬프트 사용
                prompt = self._create_triple_extraction_prompt(dp)
                print(f"   프롬프트 길이: {len(prompt)} 문자")
                
                try:
                    print(f"   🔄 LLM 호출 중...")
                    response = llm.generate(prompt)
                    print(f"   ✅ LLM 응답 수신: {len(response.content)} 문자")
                    
                    triples = self._parse_llm_triple_response(response.content, dp)
                    all_triples.extend(triples)
                    print(f"   ✅ DP {dp.dp_id}에서 {len(triples)}개 트리플 생성 완료")
                    
                except Exception as e:
                    print(f"   ⚠️ DP {dp.dp_id}에서 트리플 추출 실패: {str(e)}")
                    # 이 DP에 대해서도 기본 트리플 생성
                    basic_triples = self._generate_basic_triples_from_single_dp(dp)
                    all_triples.extend(basic_triples)
                    print(f"   🔧 기본 트리플 {len(basic_triples)}개 생성")
        
        except Exception as e:
            print(f"⚠️ LLM 기반 트리플 생성 실패: {str(e)}")
            # 폴백으로 기본 트리플 생성
            return self._generate_basic_triples_from_dps(validated_dps)
        
        # 최소 1개 트리플 보장
        if not all_triples and validated_dps:
            print("⚠️ 트리플이 하나도 생성되지 않음 - 기본 트리플 생성")
            all_triples = self._generate_basic_triples_from_dps(validated_dps)
        
        print(f"\n🎉 LLM 트리플 생성 완료: 총 {len(all_triples)}개 트리플")
        return all_triples
    
    def _create_triple_extraction_prompt(self, dp: DigitalPhenotype) -> str:
        """dp_to_triple.txt 프롬프트 기반 트리플 추출 프롬프트 생성"""
        # dp_to_triple.txt 내용을 기반으로 한 프롬프트
        prompt = f"""You are a biomedical knowledge graph engineer. Your task is to transform a digital phenotype algorithm into a list of subject-predicate-object triples.

## Input
- A digital phenotype with fields:
  - DP_ID: {dp.dp_id}
  - Label: {dp.label}  
  - Definition: {dp.definition}
  - Section: {dp.section_reference or "Unknown"}

## Output
- A list of triplets (subject, predicate, object) that represent the semantic content of the phenotype.

## Output Format (JSON array only):
```json
[
  ["{dp.dp_id}", "has_diagnosis", "diagnosis_name"],
  ["{dp.dp_id}", "has_measurement", "test_name"],
  ["test_name", "value_condition", "condition_description"],
  ["{dp.dp_id}", "has_procedure", "procedure_name"],
  ["procedure_name", "timing_constraint", "timing_description"],
  ["{dp.dp_id}", "has_drug", "drug_name"],
  ["{dp.dp_id}", "excludes_diagnosis", "exclusion_diagnosis"]
]
```

## Instructions:
- Diagnosis: map to ({dp.dp_id}, has_diagnosis, concept_name)
- Measurement: map to ({dp.dp_id}, has_measurement, test_name), then (test_name, value_condition, operator + value + unit)
- Procedure: map to ({dp.dp_id}, has_procedure, surgery_name)
- Drug: map to ({dp.dp_id}, has_drug, drug_name)
- Exclusion: use predicate excludes_diagnosis, excludes_procedure, etc.
- Use label names (not concept_id) in triplets
- Do not include duplicate or null-value triplets
- Ensure all triple elements are non-empty strings
- Use the exact DP_ID: {dp.dp_id}

## Important:
- Output must be valid JSON only
- Do not include any explanatory text outside the JSON array
- Each triple must have exactly 3 elements: [subject, predicate, object]
- All elements must be strings

Based on the DP definition above, extract relevant triples in JSON format only."""
        return prompt
    
    def _parse_llm_triple_response(
        self, 
        response_content: str, 
        dp: DigitalPhenotype
    ) -> List[Triple]:
        """LLM 응답에서 트리플 파싱"""
        try:
            import json
            import re
            
            print(f"🔍 LLM 응답 파싱 시작: {len(response_content)} 문자")
            print(f"응답 내용: {response_content[:200]}...")
            
            # 1. JSON 배열 찾기 (더 정확한 패턴)
            json_pattern = r'\[\s*\[.*?\]\s*\]'
            match = re.search(json_pattern, response_content, re.DOTALL)
            
            if not match:
                # 2. 대안: 단순 배열 패턴
                json_pattern = r'\[.*?\]'
                match = re.search(json_pattern, response_content, re.DOTALL)
                
            if not match:
                print("⚠️ JSON 배열을 찾을 수 없음")
                return []
            
            json_str = match.group(0)
            print(f"🔍 추출된 JSON: {json_str[:100]}...")
            
            # 3. JSON 정리 (불필요한 문자 제거)
            json_str = json_str.strip()
            
            # 4. JSON 파싱 시도
            try:
                triple_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {str(e)}")
                # 5. 대안: 수동 파싱 시도
                triple_data = self._manual_parse_triples(json_str)
            
            if not triple_data:
                print("⚠️ 트리플 데이터가 비어있음")
                return []
            
            triples = []
            for i, triple_list in enumerate(triple_data):
                try:
                    if isinstance(triple_list, list) and len(triple_list) >= 3:
                        subject, predicate, obj = triple_list[:3]
                        
                        # 6. 값 검증 및 정리
                        subject = str(subject).strip() if subject else ""
                        predicate = str(predicate).strip() if predicate else ""
                        obj = str(obj).strip() if obj else ""
                        
                        # 빈 값 필터링
                        if not subject or not predicate or not obj:
                            print(f"⚠️ 빈 값 발견 - 인덱스 {i}: {triple_list}")
                            continue
                        
                        # 트리플 타입 결정
                        triple_type = self._determine_triple_type(predicate)
                        
                        triple = Triple(
                            subject=subject,
                            predicate=predicate,
                            object=obj,
                            triple_type=triple_type,
                            confidence=0.8,  # LLM 생성 기본 신뢰도
                            metadata={
                                'source_dp_id': dp.dp_id,
                                'extraction_method': 'llm_based',
                                'dp_label': dp.label,
                                'triple_index': i
                            }
                        )
                        triples.append(triple)
                        print(f"✅ 트리플 생성: {subject} -> {predicate} -> {obj}")
                    else:
                        print(f"⚠️ 잘못된 트리플 형식 - 인덱스 {i}: {triple_list}")
                except Exception as e:
                    print(f"⚠️ 개별 트리플 파싱 실패 - 인덱스 {i}: {str(e)}")
                    continue
            
            print(f"✅ 총 {len(triples)}개 트리플 파싱 완료")
            return triples
            
        except Exception as e:
            print(f"⚠️ LLM 트리플 응답 파싱 실패: {str(e)}")
            return []
    
    def _manual_parse_triples(self, json_str: str) -> List[List[str]]:
        """수동 트리플 파싱 (JSON 파싱 실패 시 대안)"""
        try:
            import re
            
            # 트리플 패턴 찾기: ["subject", "predicate", "object"]
            triple_pattern = r'\[\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\]'
            matches = re.findall(triple_pattern, json_str)
            
            triples = []
            for match in matches:
                subject, predicate, obj = match
                if subject and predicate and obj:
                    triples.append([subject, predicate, obj])
            
            print(f"🔧 수동 파싱으로 {len(triples)}개 트리플 추출")
            return triples
            
        except Exception as e:
            print(f"⚠️ 수동 파싱도 실패: {str(e)}")
            return []
    
    def _determine_triple_type(self, predicate: str) -> TripleType:
        """predicate를 기반으로 트리플 타입 결정"""
        predicate_lower = predicate.lower()
        
        if 'has_' in predicate_lower or 'contains' in predicate_lower:
            return TripleType.DP_CONTAINS_ENTITY
        elif 'excludes' in predicate_lower:
            return TripleType.DP_CONTAINS_ENTITY
        elif 'is_a' in predicate_lower or 'type' in predicate_lower:
            return TripleType.CONCEPT_IS_A
        else:
            return TripleType.ENTITY_HAS_CONCEPT
    
    def _generate_basic_triples_from_dps(
        self,
        validated_dps: List[DigitalPhenotype]
    ) -> List[Triple]:
        """기본 트리플 생성 (폴백용)"""
        triples = []
        
        print(f"🔧 {len(validated_dps)}개 DP에 대해 기본 트리플 생성 시작")
        
        for dp in validated_dps:
            # 단일 DP 기본 트리플 생성 함수 사용
            dp_triples = self._generate_basic_triples_from_single_dp(dp)
            triples.extend(dp_triples)
        
        print(f"🔧 기본 트리플 생성 완료: 총 {len(triples)}개 트리플")
        return triples
    
    def _generate_basic_triples_from_single_dp(self, dp: DigitalPhenotype) -> List[Triple]:
        """단일 DP에 대한 기본 트리플 생성"""
        triples = []
        
        # DP ID를 주제로 사용
        dp_id = dp.dp_id
        
        # 1. 기본 DP 정보 트리플
        triples.append(Triple(
            subject=dp_id,
            predicate="rdf:type",
            object="DigitalPhenotype",
            triple_type=TripleType.DP_CONTAINS_ENTITY,
            confidence=1.0,
            metadata={'dp_id': dp.dp_id, 'method': 'basic_single', 'info_type': 'type'}
        ))
        
        triples.append(Triple(
            subject=dp_id,
            predicate="rdfs:label",
            object=dp.label,
            triple_type=TripleType.DP_CONTAINS_ENTITY,
            confidence=1.0,
            metadata={'dp_id': dp.dp_id, 'method': 'basic_single', 'info_type': 'label'}
        ))
        
        triples.append(Triple(
            subject=dp_id,
            predicate="rdfs:comment",
            object=dp.definition,
            triple_type=TripleType.DP_CONTAINS_ENTITY,
            confidence=1.0,
            metadata={'dp_id': dp.dp_id, 'method': 'basic_single', 'info_type': 'definition'}
        ))
        
        # 2. 섹션 참조 트리플
        if dp.section_reference:
            triples.append(Triple(
                subject=dp_id,
                predicate="has_section_reference",
                object=dp.section_reference,
                triple_type=TripleType.DP_CONTAINS_ENTITY,
                confidence=1.0,
                metadata={'dp_id': dp.dp_id, 'method': 'basic_single', 'info_type': 'section'}
            ))
        
        # 3. 정의에서 키워드 추출하여 트리플 생성
        definition_keywords = self._extract_keywords_from_definition(dp.definition)
        for keyword in definition_keywords:
            if keyword.lower() not in ['the', 'and', 'or', 'in', 'of', 'to', 'for', 'with', 'by', 'from']:
                triples.append(Triple(
                    subject=dp_id,
                    predicate="contains_keyword",
                    object=keyword,
                    triple_type=TripleType.DP_CONTAINS_ENTITY,
                    confidence=0.7,
                    metadata={'dp_id': dp.dp_id, 'method': 'basic_single', 'info_type': 'keyword'}
                ))
        
        # 4. 라벨에서 주요 개념 추출
        label_concepts = self._extract_concepts_from_label(dp.label)
        for concept in label_concepts:
            triples.append(Triple(
                subject=dp_id,
                predicate="has_main_concept",
                object=concept,
                triple_type=TripleType.DP_CONTAINS_ENTITY,
                confidence=0.9,
                metadata={'dp_id': dp.dp_id, 'method': 'basic_single', 'info_type': 'concept'}
            ))
        
        print(f"🔧 기본 트리플 {len(triples)}개 생성 완료 (DP: {dp.dp_id})")
        return triples
    
    def _extract_keywords_from_definition(self, definition: str) -> List[str]:
        """정의에서 키워드 추출"""
        import re
        
        # 특수문자 제거 및 소문자 변환
        clean_text = re.sub(r'[^\w\s]', ' ', definition.lower())
        
        # 단어 분리 및 필터링
        words = clean_text.split()
        keywords = []
        
        for word in words:
            if len(word) > 2 and word.isalpha():  # 2글자 이상, 알파벳만
                keywords.append(word)
        
        # 중복 제거 및 상위 10개만 반환
        unique_keywords = list(set(keywords))[:10]
        return unique_keywords
    
    def _extract_concepts_from_label(self, label: str) -> List[str]:
        """라벨에서 주요 개념 추출"""
        import re
        
        # 라벨을 단어로 분리
        words = re.findall(r'\b[A-Za-z]+\b', label)
        
        # 의미있는 단어 필터링 (2글자 이상, 일반적인 단어 제외)
        stop_words = {'the', 'and', 'or', 'in', 'of', 'to', 'for', 'with', 'by', 'from', 'a', 'an'}
        concepts = []
        
        for word in words:
            if len(word) > 2 and word.lower() not in stop_words:
                concepts.append(word)
        
        return concepts[:5]  # 최대 5개만 반환
    
    def _add_triples_to_graph(self, triples: List[Triple], graph: Graph):
        """트리플을 RDF 그래프에 추가"""
        for triple in triples:
            try:
                # URI 처리
                if triple.subject.startswith('http'):
                    subj = URIRef(triple.subject)
                else:
                    subj = self.KG[self._safe_uri_name(triple.subject)]
                
                if triple.predicate.startswith('http'):
                    pred = URIRef(triple.predicate)
                elif ':' in triple.predicate:
                    # 네임스페이스가 있는 경우
                    ns, local = triple.predicate.split(':', 1)
                    if ns == 'rdf':
                        pred = RDF[local]
                    elif ns == 'rdfs':
                        pred = RDFS[local]
                    elif ns == 'kg':
                        pred = self.KG[local]
                    else:
                        pred = self.KG[self._safe_uri_name(triple.predicate)]
                else:
                    pred = self.KG[self._safe_uri_name(triple.predicate)]
                
                if triple.object.startswith('http'):
                    obj = URIRef(triple.object)
                elif triple.object.startswith('kg:') or triple.object.startswith('omop:'):
                    ns, local = triple.object.split(':', 1)
                    if ns == 'kg':
                        obj = self.KG[local]
                    elif ns == 'omop':
                        obj = self.OMOP[local]
                    else:
                        obj = Literal(triple.object)
                else:
                    obj = Literal(triple.object)
                
                graph.add((subj, pred, obj))
                
            except Exception as e:
                print(f"⚠️ 트리플 추가 실패: {triple.subject} {triple.predicate} {triple.object} - {str(e)}")
                continue
    
    @classmethod
    def create_default(cls) -> 'TripleGenerator':
        """기본 설정으로 트리플 생성기 생성"""
        return cls()