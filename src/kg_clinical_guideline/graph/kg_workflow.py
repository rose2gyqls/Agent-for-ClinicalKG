"""
지식그래프 생성 LangGraph 워크플로우
"""

from typing import Dict, Any, List, Optional
from typing_extensions import TypedDict
from enum import Enum
from langgraph.graph import StateGraph, END
from dataclasses import dataclass, field
import time

from .entity_extractor import EntityExtractor, ClinicalEntity
from .triple_generator import TripleGenerator, Triple
from .neo4j_loader import Neo4jLoader, LoadResult
from ..mapping.omop_mapper import OMOPMapper, EntityMapping
from ..mapping.elasticsearch_client import ElasticsearchClient
from ..extraction.dp_extractor import DigitalPhenotype


class KGProcessingStatus(Enum):
    """지식그래프 처리 상태"""
    PENDING = "pending"
    EXTRACTING_ENTITIES = "extracting_entities"
    MAPPING_TO_OMOP = "mapping_to_omop"
    GENERATING_TRIPLES = "generating_triples"
    LOADING_TO_NEO4J = "loading_to_neo4j"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class KGProcessingState:
    """지식그래프 처리 상태"""
    # 입력 데이터
    validated_dps: List[DigitalPhenotype] = field(default_factory=list)
    original_text: str = ""
    
    # 처리 상태
    status: KGProcessingStatus = KGProcessingStatus.PENDING
    current_step: Optional[str] = None
    progress: float = 0.0
    
    # Step 4 처리 결과들
    extracted_entities: List[ClinicalEntity] = field(default_factory=list)
    entity_mappings: List[EntityMapping] = field(default_factory=list)
    generated_triples: List[Triple] = field(default_factory=list)
    neo4j_load_result: Optional[LoadResult] = None
    
    # 결과 데이터
    entity_extraction_result: Dict[str, Any] = field(default_factory=dict)
    omop_mapping_result: Dict[str, Any] = field(default_factory=dict)
    triple_generation_result: Dict[str, Any] = field(default_factory=dict)
    
    # 에러 처리
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # 처리 설정
    processing_options: Dict[str, Any] = field(default_factory=dict)
    
    # 시간 추적
    processing_start_time: Optional[float] = None
    step_start_times: Dict[str, float] = field(default_factory=dict)


class KGWorkflowState(TypedDict):
    """LangGraph State용 타입"""
    # 입력
    validated_dps: List[DigitalPhenotype]
    original_text: str
    
    # 상태 관리
    status: KGProcessingStatus
    current_step: Optional[str]
    progress: float
    
    # 단계별 결과
    extracted_entities: List[ClinicalEntity]
    entity_mappings: List[EntityMapping]
    generated_triples: List[Triple]
    neo4j_load_result: Optional[LoadResult]
    
    # 상세 결과
    entity_extraction_result: Dict[str, Any]
    omop_mapping_result: Dict[str, Any]
    triple_generation_result: Dict[str, Any]
    
    # 에러 처리
    errors: List[str]
    warnings: List[str]
    
    # 설정
    processing_options: Dict[str, Any]
    
    # 시간 추적
    processing_start_time: Optional[float]
    step_start_times: Dict[str, float]


class KnowledgeGraphWorkflow:
    """지식그래프 생성 워크플로우"""
    
    def __init__(
        self,
        entity_extractor: Optional[EntityExtractor] = None,
        omop_mapper: Optional[OMOPMapper] = None,
        triple_generator: Optional[TripleGenerator] = None,
        neo4j_loader: Optional[Neo4jLoader] = None,
        processing_options: Dict[str, Any] = None
    ):
        """
        지식그래프 워크플로우 초기화
        
        Args:
            entity_extractor: 엔티티 추출기
            omop_mapper: OMOP CDM 매핑기
            triple_generator: 트리플 생성기
            neo4j_loader: Neo4j 로더
            processing_options: 처리 옵션
        """
        self.entity_extractor = entity_extractor or EntityExtractor.create_default()
        self.omop_mapper = omop_mapper or OMOPMapper.create_default()
        self.triple_generator = triple_generator or TripleGenerator.create_default()
        self.neo4j_loader = neo4j_loader or Neo4jLoader.create_default()
        self.processing_options = processing_options or {}
        
        # 워크플로우 그래프 구축
        self.workflow = self._build_workflow()
        
        print(f"✅ KnowledgeGraphWorkflow 초기화 완료")
    
    def _build_workflow(self) -> StateGraph:
        """LangGraph 워크플로우 구축"""
        
        # StateGraph 생성
        workflow = StateGraph(KGWorkflowState)
        
        # 노드 추가
        workflow.add_node("extract_entities", self._extract_entities_node)
        workflow.add_node("map_to_omop", self._map_to_omop_node)
        workflow.add_node("generate_triples", self._generate_triples_node)
        workflow.add_node("load_to_neo4j", self._load_to_neo4j_node)
        workflow.add_node("finalize", self._finalize_node)
        workflow.add_node("handle_error", self._handle_error_node)
        
        # 엣지 정의
        workflow.set_entry_point("extract_entities")
        
        workflow.add_conditional_edges(
            "extract_entities",
            self._should_continue_after_extraction,
            {
                "continue": "map_to_omop",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "map_to_omop",
            self._should_continue_after_mapping,
            {
                "continue": "generate_triples",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "generate_triples",
            self._should_continue_after_triple_generation,
            {
                "finalize": "finalize",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "load_to_neo4j",
            self._should_continue_after_neo4j_loading,
            {
                "finalize": "finalize",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("finalize", END)
        workflow.add_edge("handle_error", END)
        
        return workflow.compile()
    
    def _extract_entities_node(self, state: KGWorkflowState) -> KGWorkflowState:
        """엔티티 추출 노드"""
        try:
            state['status'] = KGProcessingStatus.EXTRACTING_ENTITIES
            state['current_step'] = "extracting_entities"
            state['progress'] = 0.1
            state['step_start_times']['extract_entities'] = time.time()
            
            print("🔄 Step 4.1: 엔티티 추출 시작...")
            
            # 엔티티 추출 실행
            extraction_result = self.entity_extractor.extract_entities_from_dps(
                state['validated_dps'],
                state['original_text']
            )
            
            # 결과 저장
            state['entity_extraction_result'] = extraction_result
            state['extracted_entities'] = [
                self._dict_to_clinical_entity(entity_data) 
                for entity_data in extraction_result.get('entities', [])
            ]
            
            state['progress'] = 0.25
            print(f"✅ Step 4.1: 엔티티 추출 완료 - {len(state['extracted_entities'])}개 엔티티")
            
        except Exception as e:
            state['errors'].append(f"엔티티 추출 중 오류: {str(e)}")
            state['status'] = KGProcessingStatus.FAILED
            print(f"❌ Step 4.1: 엔티티 추출 실패 - {str(e)}")
        
        return state
    
    def _map_to_omop_node(self, state: KGWorkflowState) -> KGWorkflowState:
        """OMOP CDM 매핑 노드"""
        try:
            state['status'] = KGProcessingStatus.MAPPING_TO_OMOP
            state['current_step'] = "mapping_to_omop"
            state['progress'] = 0.35
            state['step_start_times']['map_to_omop'] = time.time()
            
            print("🔄 Step 4.2: OMOP CDM 매핑 시작...")
            
            # OMOP 매핑 실행
            mapping_result = self.omop_mapper.map_entities_to_omop(
                state['extracted_entities']
            )
            
            # 결과 저장
            state['omop_mapping_result'] = mapping_result
            state['entity_mappings'] = [
                self._dict_to_entity_mapping(mapping_data)
                for mapping_data in mapping_result.get('successful_mappings', [])
            ]
            
            state['progress'] = 0.5
            print(f"✅ Step 4.2: OMOP CDM 매핑 완료 - {len(state['entity_mappings'])}개 매핑")
            
        except Exception as e:
            state['errors'].append(f"OMOP 매핑 중 오류: {str(e)}")
            state['status'] = KGProcessingStatus.FAILED
            print(f"❌ Step 4.2: OMOP CDM 매핑 실패 - {str(e)}")
        
        return state
    
    def _generate_triples_node(self, state: KGWorkflowState) -> KGWorkflowState:
        """트리플 생성 노드"""
        try:
            state['status'] = KGProcessingStatus.GENERATING_TRIPLES
            state['current_step'] = "generating_triples"
            state['progress'] = 0.6
            state['step_start_times']['generate_triples'] = time.time()
            
            print("🔄 Step 4.3: 트리플 생성 시작...")
            
            # LLM을 사용하여 직접 DP에서 트리플 생성 (dp_to_triple.txt 프롬프트 사용)
            triple_result = self.triple_generator.generate_triples_from_dps(
                state['validated_dps'],
                state['original_text'],
                use_llm=True
            )
            
            # 결과 저장
            state['triple_generation_result'] = triple_result
            state['generated_triples'] = [
                self._dict_to_triple(triple_data)
                for triple_data in triple_result.get('triples', [])
            ]
            
            state['progress'] = 0.75
            print(f"✅ Step 4.3: 트리플 생성 완료 - {len(state['generated_triples'])}개 트리플")
            
        except Exception as e:
            state['errors'].append(f"트리플 생성 중 오류: {str(e)}")
            state['status'] = KGProcessingStatus.FAILED
            print(f"❌ Step 4.3: 트리플 생성 실패 - {str(e)}")
        
        return state
    
    def _load_to_neo4j_node(self, state: KGWorkflowState) -> KGWorkflowState:
        """Neo4j 로딩 노드"""
        try:
            state['status'] = KGProcessingStatus.LOADING_TO_NEO4J
            state['current_step'] = "loading_to_neo4j"
            state['progress'] = 0.85
            state['step_start_times']['load_to_neo4j'] = time.time()
            
            print("🔄 Step 4.4: Neo4j 적재 시작...")
            
            # Neo4j 로딩 설정
            clear_existing = state['processing_options'].get('clear_existing_graph', False)
            batch_size = state['processing_options'].get('neo4j_batch_size', 1000)
            
            # Neo4j 로딩 실행
            load_result = self.neo4j_loader.load_triples_to_neo4j(
                state['generated_triples'],
                clear_existing=clear_existing,
                batch_size=batch_size
            )
            
            # 결과 저장
            state['neo4j_load_result'] = load_result
            
            state['progress'] = 0.95
            if load_result.success:
                print(f"✅ Step 4.4: Neo4j 적재 완료")
                print(f"   - 노드: {load_result.nodes_created}개")
                print(f"   - 관계: {load_result.relationships_created}개")
            else:
                state['errors'].append(f"Neo4j 로딩 실패: {load_result.error_message}")
                print(f"❌ Step 4.4: Neo4j 적재 실패 - {load_result.error_message}")
            
        except Exception as e:
            state['errors'].append(f"Neo4j 로딩 중 오류: {str(e)}")
            state['status'] = KGProcessingStatus.FAILED
            print(f"❌ Step 4.4: Neo4j 적재 실패 - {str(e)}")
        
        return state
    
    def _finalize_node(self, state: KGWorkflowState) -> KGWorkflowState:
        """최종화 노드"""
        try:
            state['status'] = KGProcessingStatus.COMPLETED
            state['current_step'] = "completed"
            state['progress'] = 1.0
            
            # 전체 처리 시간 계산
            if state['processing_start_time']:
                total_time = time.time() - state['processing_start_time']
                print(f"✅ Step 4: 지식그래프 생성 완료! (총 {total_time:.2f}초)")
            
            # 최종 검증
            if not state['generated_triples']:
                state['warnings'].append("생성된 트리플이 없습니다.")
            
            if state['neo4j_load_result'] and not state['neo4j_load_result'].success:
                state['warnings'].append("Neo4j 로딩에 실패했습니다.")
            
        except Exception as e:
            state['errors'].append(f"최종화 중 오류: {str(e)}")
            state['status'] = KGProcessingStatus.FAILED
        
        return state
    
    def _handle_error_node(self, state: KGWorkflowState) -> KGWorkflowState:
        """에러 처리 노드"""
        state['status'] = KGProcessingStatus.FAILED
        state['current_step'] = "error"
        
        # 에러 요약 생성
        if state['errors']:
            error_summary = f"총 {len(state['errors'])}개의 오류가 발생했습니다: " + "; ".join(state['errors'][-3:])
            print(f"❌ Step 4 실패: {error_summary}")
        
        return state
    
    # 조건부 엣지 함수들
    def _should_continue_after_extraction(self, state: KGWorkflowState) -> str:
        """엔티티 추출 후 다음 단계 결정"""
        if state['errors'] or state['status'] == KGProcessingStatus.FAILED:
            return "error"
        if not state['extracted_entities']:
            state['errors'].append("추출된 엔티티가 없습니다.")
            return "error"
        return "continue"
    
    def _should_continue_after_mapping(self, state: KGWorkflowState) -> str:
        """OMOP 매핑 후 다음 단계 결정"""
        if state['errors'] or state['status'] == KGProcessingStatus.FAILED:
            return "error"
        if not state['entity_mappings']:
            state['warnings'].append("매핑된 엔티티가 없지만 계속 진행합니다.")
        return "continue"
    
    def _should_continue_after_triple_generation(self, state: KGWorkflowState) -> str:
        """트리플 생성 후 다음 단계 결정 (Neo4j 적재 생략)"""
        if state['errors'] or state['status'] == KGProcessingStatus.FAILED:
            return "error"
        if not state['generated_triples']:
            state['warnings'].append("생성된 트리플이 없지만 계속 진행합니다.")
        return "finalize"
    
    def _should_continue_after_neo4j_loading(self, state: KGWorkflowState) -> str:
        """Neo4j 로딩 후 다음 단계 결정"""
        if state['errors'] or state['status'] == KGProcessingStatus.FAILED:
            return "error"
        return "finalize"
    
    # 헬퍼 메서드들
    def _dict_to_clinical_entity(self, entity_data: Dict[str, Any]) -> ClinicalEntity:
        """딕셔너리를 ClinicalEntity로 변환"""
        from ..graph.entity_extractor import EntityType
        
        return ClinicalEntity(
            text=entity_data.get('text', ''),
            entity_type=EntityType(entity_data.get('entity_type', 'unknown')),
            normalized_text=entity_data.get('normalized_text', ''),
            confidence=entity_data.get('confidence', 0.0),
            start_pos=entity_data.get('start_pos'),
            end_pos=entity_data.get('end_pos'),
            context=entity_data.get('context'),
            metadata=entity_data.get('metadata', {})
        )
    
    def _dict_to_entity_mapping(self, mapping_data: Dict[str, Any]) -> EntityMapping:
        """딕셔너리를 EntityMapping으로 변환"""
        from ..mapping.omop_mapper import OMOPConcept, MappingConfidence
        
        # 소스 엔티티 재구성
        source_entity = self._dict_to_clinical_entity(mapping_data['source_entity'])
        
        # OMOP 컨셉 재구성
        omop_data = mapping_data['omop_concept']
        omop_concept = OMOPConcept(
            concept_id=omop_data.get('concept_id', ''),
            concept_name=omop_data.get('concept_name', ''),
            domain_id=omop_data.get('domain_id', ''),
            vocabulary_id=omop_data.get('vocabulary_id', ''),
            concept_class_id=omop_data.get('concept_class_id', ''),
            standard_concept=omop_data.get('standard_concept', ''),
            concept_code=omop_data.get('concept_code', '')
        )
        
        return EntityMapping(
            source_entity=source_entity,
            omop_concept=omop_concept,
            mapping_score=mapping_data.get('mapping_score', 0.0),
            mapping_confidence=MappingConfidence(mapping_data.get('mapping_confidence', 'low')),
            mapping_method=mapping_data.get('mapping_method', 'unknown'),
            alternative_concepts=[]  # 간단히 처리
        )
    
    def _dict_to_triple(self, triple_data: Dict[str, Any]) -> Triple:
        """딕셔너리를 Triple로 변환"""
        from ..graph.triple_generator import TripleType
        
        return Triple(
            subject=triple_data.get('subject', ''),
            predicate=triple_data.get('predicate', ''),
            object=triple_data.get('object', ''),
            triple_type=TripleType(triple_data.get('triple_type', 'entity_has_concept')),
            confidence=triple_data.get('confidence', 0.0),
            metadata=triple_data.get('metadata', {})
        )
    
    def process_sync(
        self,
        validated_dps: List[DigitalPhenotype],
        original_text: str,
        processing_options: Dict[str, Any] = None
    ) -> KGWorkflowState:
        """
        동기 지식그래프 생성 처리
        
        Args:
            validated_dps: 검증된 DP 리스트
            original_text: 원본 텍스트
            processing_options: 처리 옵션
            
        Returns:
            KGWorkflowState: 최종 처리 결과
        """
        # 초기 상태 생성
        initial_state: KGWorkflowState = {
            'validated_dps': validated_dps,
            'original_text': original_text,
            'status': KGProcessingStatus.PENDING,
            'current_step': None,
            'progress': 0.0,
            'extracted_entities': [],
            'entity_mappings': [],
            'generated_triples': [],
            'neo4j_load_result': None,
            'entity_extraction_result': {},
            'omop_mapping_result': {},
            'triple_generation_result': {},
            'errors': [],
            'warnings': [],
            'processing_options': {**self.processing_options, **(processing_options or {})},
            'processing_start_time': time.time(),
            'step_start_times': {}
        }
        
        # 워크플로우 실행
        final_state = self.workflow.invoke(initial_state)
        
        return final_state
    
    async def process(
        self,
        validated_dps: List[DigitalPhenotype],
        original_text: str,
        processing_options: Dict[str, Any] = None
    ) -> KGWorkflowState:
        """
        비동기 지식그래프 생성 처리
        
        Args:
            validated_dps: 검증된 DP 리스트
            original_text: 원본 텍스트
            processing_options: 처리 옵션
            
        Returns:
            KGWorkflowState: 최종 처리 결과
        """
        # 초기 상태 생성
        initial_state: KGWorkflowState = {
            'validated_dps': validated_dps,
            'original_text': original_text,
            'status': KGProcessingStatus.PENDING,
            'current_step': None,
            'progress': 0.0,
            'extracted_entities': [],
            'entity_mappings': [],
            'generated_triples': [],
            'neo4j_load_result': None,
            'entity_extraction_result': {},
            'omop_mapping_result': {},
            'triple_generation_result': {},
            'errors': [],
            'warnings': [],
            'processing_options': {**self.processing_options, **(processing_options or {})},
            'processing_start_time': time.time(),
            'step_start_times': {}
        }
        
        # 워크플로우 실행
        final_state = await self.workflow.ainvoke(initial_state)
        
        return final_state
    
    @classmethod
    def create_default(cls) -> 'KnowledgeGraphWorkflow':
        """기본 설정으로 워크플로우 생성"""
        return cls() 