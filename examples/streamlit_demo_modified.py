import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import streamlit as st
import json
from io import StringIO
import time
from typing import Optional

from kg_clinical_guideline.data import DataProcessingWorkflow, InputType
from kg_clinical_guideline.extraction import DPExtractor
from kg_clinical_guideline.validation import (
    TwoTrackDPValidator,
    ValidationProgress,
    ValidationMetrics
)
from kg_clinical_guideline.graph import (
    KnowledgeGraphWorkflow,
    EntityExtractor,
    TripleGenerator,
    Neo4jLoader
)
from kg_clinical_guideline.mapping import (
    OMOPMapper,
    ElasticsearchClient
)


def main():
    st.set_page_config(
        page_title="의료 가이드라인 지식 그래프 변환기",
        page_icon="🏥",
        layout="wide"
    )
    
    st.title("🏥 의료 가이드라인 지식 그래프 변환기")
    st.markdown("4단계 파이프라인을 통한 의료 지침 가이드라인에서 지식 그래프 생성까지")
    
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 설정")
        extract_dp = st.checkbox("DP 추출 실행", value=True)
        validate_dp = st.checkbox("DP 검증 실행", value=True)
        similarity_threshold = st.slider("유사도 임계치", 0.0, 1.0, 0.5, 0.05)
        evidence_threshold = st.slider("증거 임계치", 0.0, 1.0, 0.5, 0.05)
        final_threshold = st.slider("최종 임계치", 0.0, 1.0, 0.6, 0.05)
        max_retries = st.selectbox("최대 재시도 횟수", [0, 1, 2, 3], index=1)
        
        st.markdown("### 🌐 Step 4: 지식그래프 생성")
        create_kg = st.checkbox("지식그래프 생성 실행", value=True, help="검증된 DP로부터 트리플 생성")
        entity_confidence = st.slider("엔티티 신뢰도", 0.0, 1.0, 0.3, 0.05)
        use_llm_triples = st.checkbox("LLM 기반 트리플 생성", value=True, help="dp_to_triple.txt 프롬프트 사용")
    
    # 메인 영역
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📥 입력")
        
        input_method = st.selectbox(
            "입력 방식 선택",
            ["직접 텍스트 입력", "JSON 데이터", "파일 업로드"]
        )
        
        input_data = None
        
        if input_method == "직접 텍스트 입력":
            input_data = st.text_area(
                "의료 가이드라인 텍스트를 입력하세요",
                height=300
            )
            
        elif input_method == "JSON 데이터":
            json_input = st.text_area(
                "JSON 형식의 가이드라인 데이터를 입력하세요",
                height=300
            )
            
            if json_input:
                try:
                    input_data = json.loads(json_input)
                except json.JSONDecodeError as e:
                    st.error(f"JSON 파일 형식 오류: {str(e)}")
                    
        elif input_method == "파일 업로드":
            uploaded_file = st.file_uploader(
                "파일을 업로드하세요",
                type=['txt', 'json']
            )
            
            if uploaded_file is not None:
                if uploaded_file.type == "application/json":
                    try:
                        input_data = json.load(uploaded_file)
                    except json.JSONDecodeError as e:
                        st.error(f"JSON 파일 형식 오류: {str(e)}")
                else:
                    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
                    input_data = stringio.read()
        
        process_button = st.button("🔄 처리 시작", type="primary", disabled=not input_data)
    
    with col2:
        st.header("📤 출력")
        
        if process_button and input_data:
            try:
                # 전체 진행상황
                overall_progress = st.progress(0)
                overall_status = st.empty()
                
                # Step 1: 마크다운 변환
                overall_status.write("🔄 Step 1: 마크다운 변환 중...")
                overall_progress.progress(0.1)
                
                workflow = DataProcessingWorkflow()
                result = workflow.process_sync(input_data)
                
                if result['status'].value == 'completed':
                    overall_progress.progress(0.3)
                    overall_status.write("✅ Step 1: 마크다운 변환 완료")
                    
                    st.markdown("### 📄 Step 1: 마크다운 변환 결과")
                    st.download_button(
                        label="📥 마크다운 다운로드",
                        data=result['markdown_content'],
                        file_name="medical_guideline.md",
                        mime="text/markdown"
                    )
                    
                    # Step 2: DP 추출
                    if extract_dp:
                        overall_status.write("🔄 Step 2: DP 추출 중...")
                        overall_progress.progress(0.4)
                        
                        dp_extractor = DPExtractor.create_default()
                        dp_result = dp_extractor.extract_dps_with_metadata(
                            result['markdown_content'],
                            document_metadata={'source': input_method},
                            max_dps=3  # 테스트 시간 단축을 위해 최대 3개로 제한
                        )
                        
                        overall_progress.progress(0.6)
                        overall_status.write("✅ Step 2: DP 추출 완료")
                        
                        if dp_result['digital_phenotypes']:
                            st.markdown(f"### 🧬 Step 2: DP 추출 완료 ({len(dp_result['digital_phenotypes'])}개)")
                            
                            # Step 3: 검증
                            if validate_dp:
                                overall_status.write("🔄 Step 3: 2트랙 검증 중...")
                                overall_progress.progress(0.7)
                                
                                # DP 객체 변환
                                from kg_clinical_guideline.extraction.dp_extractor import DigitalPhenotype
                                
                                dp_objects = []
                                for dp_data in dp_result['digital_phenotypes']:
                                    dp_obj = DigitalPhenotype(
                                        dp_id=dp_data['dp_id'],
                                        label=dp_data['label'],
                                        definition=dp_data['definition'],
                                        section_reference=dp_data['section_reference'],
                                        confidence_score=dp_data.get('confidence_score'),
                                        metadata=dp_data.get('metadata')
                                    )
                                    dp_objects.append(dp_obj)
                                
                                # 검증 실행
                                dp_validator = TwoTrackDPValidator(
                                    similarity_threshold=similarity_threshold,
                                    evidence_threshold=evidence_threshold,
                                    final_threshold=final_threshold,
                                    max_retries=max_retries
                                )
                                
                                final_dps, validation_results, validation_summary = dp_validator.validate_dps_with_selective_retry(
                                    dp_objects,
                                    result['markdown_content'],
                                    dp_extractor
                                )
                                
                                overall_progress.progress(0.9)
                                overall_status.write("✅ Step 3: 2트랙 검증 완료")
                                
                                st.markdown(f"### 🔍 Step 3: 검증 완료 (최종 {len(final_dps)}개 DP)")
                                
                                # Step 4: 지식그래프 생성 (트리플까지만)
                                if create_kg and final_dps:
                                    overall_status.write("🔄 Step 4: 트리플 생성 중...")
                                    overall_progress.progress(0.95)
                                    
                                    kg_workflow = KnowledgeGraphWorkflow()
                                    
                                    # 수정된 워크플로우로 트리플 생성만 수행
                                    kg_options = {
                                        'entity_confidence_threshold': entity_confidence,
                                        'use_llm_triples': use_llm_triples
                                    }
                                    
                                    try:
                                        kg_result = kg_workflow.process_sync(
                                            final_dps,
                                            result['markdown_content'], 
                                            kg_options
                                        )
                                    except Exception as kg_error:
                                        st.error(f"🔴 지식그래프 생성 중 오류: {str(kg_error)}")
                                        import traceback
                                        st.text("상세 오류 정보:")
                                        st.code(traceback.format_exc())
                                        kg_result = None
                                    
                                    overall_progress.progress(1.0)
                                    overall_status.write("✅ Step 4: 트리플 생성 완료!")
                                    
                                    # 트리플 결과 표시
                                    if kg_result:
                                        display_triple_results(kg_result)
                                    
                else:
                    st.error("마크다운 변환에 실패했습니다.")
                    
            except Exception as e:
                st.error(f"처리 중 오류가 발생했습니다: {str(e)}")
                
        else:
            st.info("왼쪽에서 데이터를 입력하고 '처리 시작' 버튼을 클릭하세요.")


def display_triple_results(kg_result):
    """트리플 결과 표시 함수"""
    st.markdown("### 🌐 Step 4: 트리플 생성 완료")
    
    # 상태 표시
    status = kg_result.get('status', 'unknown')
    if hasattr(status, 'value'):
        status_value = status.value
    else:
        status_value = str(status)
    
    if status_value == 'completed':
        st.success("✅ 트리플 생성이 성공적으로 완료되었습니다!")
    else:
        st.warning(f"⚠️ 처리 상태: {status_value}")
    
    # 통계 표시
    col1, col2, col3 = st.columns(3)
    
    with col1:
        entity_count = len(kg_result.get('extracted_entities', []))
        st.metric("추출된 엔티티", f"{entity_count}개")
    
    with col2:
        mapping_count = len(kg_result.get('entity_mappings', []))
        st.metric("OMOP 매핑", f"{mapping_count}개")
    
    with col3:
        triple_count = len(kg_result.get('generated_triples', []))
        st.metric("생성된 트리플", f"{triple_count}개")
    
            # 트리플 시각화
        if kg_result.get('generated_triples'):
            st.markdown("#### 📊 생성된 트리플")
            
            # Neo4j 그래프 구조 미리보기
            neo4j_preview = create_neo4j_friendly_graph(kg_result)
            
            # 그래프 통계
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("노드 수", neo4j_preview["statistics"]["total_nodes"])
            with col2:
                st.metric("관계 수", neo4j_preview["statistics"]["total_relationships"])
            with col3:
                direct_rels = sum(1 for rel in neo4j_preview["relationships"] if rel['properties'].get('trans') == 'DIRECT')
                st.metric("직접 관계", f"{direct_rels}개")
            with col4:
                node_types = len(neo4j_preview["statistics"]["node_types"])
                st.metric("노드 타입 수", f"{node_types}개")
            
            # Neo4j 노드 및 관계 미리보기
            with st.expander("🌐 Neo4j 그래프 구조 미리보기", expanded=True):
                tab1, tab2, tab3 = st.tabs(["📍 노드", "🔗 관계", "📈 통계"])
                
                with tab1:
                    st.markdown("**노드 정보 (Node 예시 5개)**")
                    nodes_preview = neo4j_preview["nodes"][:5]
                    for node in nodes_preview:
                        st.markdown(f"**{node['id']}**")
                        st.markdown(f"- 라벨: `{', '.join(node['labels'])}`")
                        st.markdown(f"- 속성: `{node['properties']}`")
                        st.markdown("---")
                
                with tab2:
                    st.markdown("**관계 정보 (Relationship 예시 5개)**")
                    rels_preview = neo4j_preview["relationships"][:5]
                    for rel in rels_preview:
                        start = rel['start_node']
                        end = rel['end_node']
                        rel_type = rel['type']
                        rela_source = rel['properties'].get('rela_source', 'N/A')
                        rela = rel['properties'].get('rela', 'N/A')
                        trans = rel['properties'].get('trans', 'N/A')
                        
                        st.markdown(f"**({start}) -[{rel_type}]-> ({end})**")
                        st.markdown(f"- 관계: {rela}")
                        st.markdown(f"- 소스: {rela_source}")
                        st.markdown(f"- 전이성: {trans}")
                        st.markdown("---")
                
                with tab3:
                    st.markdown("**그래프 통계**")
                    stats = neo4j_preview["statistics"]
                    
                    st.markdown("**노드 타입별 분포:**")
                    for node_type, count in stats["node_types"].items():
                        st.markdown(f"- {node_type}: {count}개")
                    
                    st.markdown("**관계 타입별 분포:**")
                    for rel_type, count in stats["relationship_types"].items():
                        st.markdown(f"- {rel_type}: {count}개")
                    
                    st.markdown("**전이성 분포:**")
                    trans_dist = {"DIRECT": 0, "INDIRECT": 0}
                    for rel in neo4j_preview["relationships"]:
                        trans = rel['properties'].get('trans', 'UNKNOWN')
                        if trans in trans_dist:
                            trans_dist[trans] += 1
                    
                    st.markdown(f"- 직접 관계 (DIRECT): {trans_dist['DIRECT']}개")
                    st.markdown(f"- 간접 관계 (INDIRECT): {trans_dist['INDIRECT']}개")
                    
                    st.markdown("**관계 소스 분포:**")
                    source_dist = {}
                    for rel in neo4j_preview["relationships"]:
                        source = rel['properties'].get('rela_source', 'UNKNOWN')
                        source_dist[source] = source_dist.get(source, 0) + 1
                    
                    for source, count in source_dist.items():
                        st.markdown(f"- {source}: {count}개")
            
            # 트리플 테이블 표시
            with st.expander("🔍 원본 트리플 상세 보기"):
                triples_data = []
                for triple in kg_result['generated_triples']:
                    # Triple은 dataclass이므로 점 표기법으로 접근
                    triple_type = triple.triple_type.value if hasattr(triple.triple_type, 'value') else str(triple.triple_type)
                    triples_data.append({
                        'Subject': triple.subject,
                        'Predicate': triple.predicate, 
                        'Object': triple.object,
                        'Type': triple_type,
                        'Confidence': f"{triple.confidence:.3f}"
                    })
                
                if triples_data:
                    import pandas as pd
                    df = pd.DataFrame(triples_data)
                    st.dataframe(df, use_container_width=True)
        
        # RDF 형식 다운로드
        triple_generation_result = kg_result.get('triple_generation_result', {})
        rdf_graph = triple_generation_result.get('rdf_graph', {})
        
        if rdf_graph and rdf_graph.get('turtle'):
            st.download_button(
                label="📥 RDF 트리플 다운로드 (Turtle 형식)",
                data=rdf_graph['turtle'],
                file_name="knowledge_graph.ttl",
                mime="text/turtle"
            )
        
        # Neo4j 친화적인 그래프 구조 다운로드
        neo4j_graph_data = create_neo4j_friendly_graph(kg_result)
        st.download_button(
            label="📥 Neo4j 그래프 구조 다운로드 (JSON)",
            data=json.dumps(neo4j_graph_data, ensure_ascii=False, indent=2, default=str),
            file_name=f"neo4j_graph_{int(time.time())}.json",
            mime="application/json"
        )
        
        # Cypher 쿼리 다운로드
        cypher_queries = generate_cypher_queries(kg_result)
        st.download_button(
            label="📥 Neo4j Cypher 쿼리 다운로드",
            data=cypher_queries,
            file_name=f"neo4j_queries_{int(time.time())}.cypher",
            mime="text/plain"
        )


def create_neo4j_friendly_graph(kg_result):
    """Neo4j에 최적화된 그래프 구조 생성"""
    import hashlib
    
    nodes = {}
    relationships = []
    node_counter = 0
    rel_counter = 0
    
    # 트리플에서 노드와 관계 추출
    triples = kg_result.get('generated_triples', [])
    
    for triple in triples:
        subject = triple.subject if hasattr(triple, 'subject') else triple.get('subject', '')
        predicate = triple.predicate if hasattr(triple, 'predicate') else triple.get('predicate', '')
        object_val = triple.object if hasattr(triple, 'object') else triple.get('object', '')
        confidence = triple.confidence if hasattr(triple, 'confidence') else triple.get('confidence', 0.0)
        triple_type = triple.triple_type if hasattr(triple, 'triple_type') else triple.get('triple_type', '')
        metadata = triple.metadata if hasattr(triple, 'metadata') else triple.get('metadata', {})
        
        if isinstance(triple_type, object) and hasattr(triple_type, 'value'):
            triple_type = triple_type.value
        
        # Subject 노드 추가
        subject_id = create_node_id(subject)
        if subject_id not in nodes:
            node_labels = determine_node_labels(subject, metadata)
            source_code, concept_id = extract_code_and_concept_id(subject, metadata)
            
            nodes[subject_id] = {
                "id": subject_id,
                "labels": node_labels,
                "properties": {
                    "source_code": source_code,
                    "source_name": extract_display_name(subject),
                    "voca_id": determine_vocabulary_id(subject, metadata, node_labels),
                    "concept_id": concept_id
                }
            }
        
        # Object 노드 추가 (리터럴이 아닌 경우)
        object_id = create_node_id(object_val)
        if not is_literal_value(object_val) and object_id not in nodes:
            object_labels = determine_node_labels(object_val, metadata)
            obj_source_code, obj_concept_id = extract_code_and_concept_id(object_val, metadata)
            
            nodes[object_id] = {
                "id": object_id,
                "labels": object_labels,
                "properties": {
                    "source_code": obj_source_code,
                    "source_name": extract_display_name(object_val),
                    "voca_id": determine_vocabulary_id(object_val, metadata, object_labels),
                    "concept_id": obj_concept_id
                }
            }
        
        # 관계 추가 (리터럴이 아닌 경우만)
        if not is_literal_value(object_val):
            relationship = {
                "id": f"rel_{rel_counter}",
                "start_node": subject_id,
                "end_node": object_id,
                "type": clean_relationship_type(predicate),
                "properties": {
                    "rela_source": determine_rela_source(predicate, metadata),
                    "rela": extract_relation_name(predicate),
                    "trans": determine_transitivity(confidence, metadata),
                    "create_date": int(time.time())  # 현재 타임스탬프
                }
            }
            relationships.append(relationship)
            rel_counter += 1
    
    # 엔티티 정보 추가
    entities = kg_result.get('extracted_entities', [])
    for entity in entities:
        entity_name = entity.get('text', '') if isinstance(entity, dict) else getattr(entity, 'text', '')
        entity_type = entity.get('entity_type', '') if isinstance(entity, dict) else getattr(entity, 'entity_type', '')
        
        if isinstance(entity_type, object) and hasattr(entity_type, 'value'):
            entity_type = entity_type.value
        
        entity_id = create_node_id(entity_name)
        if entity_id not in nodes:
            entity_labels = [entity_type.upper() if entity_type else "ENTITY"]
            ent_source_code, ent_concept_id = extract_code_and_concept_id(entity_name, 
                entity.get('metadata', {}) if isinstance(entity, dict) else getattr(entity, 'metadata', {}))
            
            nodes[entity_id] = {
                "id": entity_id,
                "labels": entity_labels,
                "properties": {
                    "source_code": ent_source_code,
                    "source_name": entity_name,
                    "voca_id": map_entity_type_to_vocabulary(entity_type),
                    "concept_id": ent_concept_id
                }
            }
    
    # 통계 계산
    statistics = {
        "total_nodes": len(nodes),
        "total_relationships": len(relationships),
        "node_types": {},
        "relationship_types": {},
        "vocabulary_distribution": {},
        "transitivity_distribution": {
            "DIRECT": 0,
            "INDIRECT": 0
        },
        "relation_source_distribution": {}
    }
    
    # 노드 타입별 통계
    for node in nodes.values():
        for label in node["labels"]:
            statistics["node_types"][label] = statistics["node_types"].get(label, 0) + 1
        
        # 어휘 분포 통계
        voca_id = node["properties"].get("voca_id", "UNKNOWN")
        statistics["vocabulary_distribution"][voca_id] = statistics["vocabulary_distribution"].get(voca_id, 0) + 1
    
    # 관계 타입별 통계
    for rel in relationships:
        rel_type = rel["type"]
        statistics["relationship_types"][rel_type] = statistics["relationship_types"].get(rel_type, 0) + 1
        
        # 전이성 분포
        trans = rel["properties"].get("trans", "UNKNOWN")
        if trans in statistics["transitivity_distribution"]:
            statistics["transitivity_distribution"][trans] += 1
        
        # 관계 소스 분포
        rela_source = rel["properties"].get("rela_source", "UNKNOWN")
        statistics["relation_source_distribution"][rela_source] = statistics["relation_source_distribution"].get(rela_source, 0) + 1
    
    return {
        "graph_info": {
            "description": "의료 가이드라인에서 추출된 지식그래프",
            "extraction_timestamp": int(time.time()),
            "format": "Neo4j Compatible JSON"
        },
        "nodes": list(nodes.values()),
        "relationships": relationships,
        "statistics": statistics,
        "neo4j_import_guide": {
            "step_1": "각 노드를 CREATE 또는 MERGE 명령으로 생성 (source_code, source_name, voca_id, concept_id 속성 포함)",
            "step_2": "관계를 MATCH...CREATE 명령으로 연결 (rela_source, rela, trans, create_date 속성 포함)",
            "step_3": "인덱스 생성으로 성능 최적화 (source_code, concept_id 기준)",
            "cypher_example": "MERGE (n:DISEASE {source_code: 'D001017', source_name: 'Aortic Coarctation', voca_id: 'SNOMED', concept_id: 45618848}) RETURN n",
            "relationship_example": "MATCH (a {source_code: 'D001017'}) MATCH (b {source_code: '598'}) MERGE (a)-[r:MAY_TREAT {rela_source: 'MEDRT', rela: 'may treat', trans: 'DIRECT', create_date: 1640995200}]->(b)"
        }
    }


def create_node_id(name):
    """노드 ID 생성 (안전한 식별자)"""
    import re
    import hashlib
    
    # 특수 문자 제거 및 정리
    clean_name = re.sub(r'[^\w\s-]', '', str(name)).strip()
    clean_name = re.sub(r'\s+', '_', clean_name)
    
    # 너무 길면 해시 사용
    if len(clean_name) > 50:
        hash_suffix = hashlib.md5(name.encode()).hexdigest()[:8]
        clean_name = clean_name[:42] + "_" + hash_suffix
    
    return clean_name or f"node_{hashlib.md5(str(name).encode()).hexdigest()[:8]}"


def determine_node_labels(node_name, metadata=None):
    """노드 타입에 따른 라벨 결정"""
    labels = ["Node"]
    
    name_lower = str(node_name).lower()
    
    # URI 기반 라벨 결정
    if node_name.startswith('http'):
        if 'dp/' in node_name:
            labels.append("DigitalPhenotype")
        elif 'entity/' in node_name:
            labels.append("Entity")
        elif 'omop/' in node_name:
            labels.append("OMOPConcept")
        elif 'section/' in node_name:
            labels.append("Section")
    
    # 키워드 기반 라벨 결정
    if any(word in name_lower for word in ['dp_', 'phenotype']):
        labels.append("DigitalPhenotype")
    elif any(word in name_lower for word in ['medication', 'drug', '약물']):
        labels.append("Medication")
    elif any(word in name_lower for word in ['condition', 'disease', '질환', '병명']):
        labels.append("Condition")
    elif any(word in name_lower for word in ['procedure', 'surgery', '시술', '수술']):
        labels.append("Procedure")
    elif any(word in name_lower for word in ['measurement', 'test', '검사', '측정']):
        labels.append("Measurement")
    
    # 메타데이터 기반 라벨
    if metadata:
        if metadata.get('entity_type'):
            labels.append(f"{metadata['entity_type'].title()}Entity")
    
    return list(set(labels))  # 중복 제거


def clean_relationship_type(predicate):
    """관계 타입 정리 (Neo4j 규칙에 맞게)"""
    import re
    
    # URI에서 로컬 이름 추출
    if predicate.startswith('http'):
        predicate = predicate.split('/')[-1].split('#')[-1]
    
    # 네임스페이스 제거
    if ':' in predicate:
        predicate = predicate.split(':', 1)[1]
    
    # 카멜케이스를 스네이크케이스로 변환
    predicate = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', predicate).upper()
    
    # 특수 문자를 언더스코어로 변환
    predicate = re.sub(r'[^\w]', '_', predicate)
    
    # 연속된 언더스코어 정리
    predicate = re.sub(r'_+', '_', predicate).strip('_')
    
    return predicate or "RELATED_TO"


def is_literal_value(value):
    """리터럴 값인지 판단"""
    value_str = str(value).lower()
    
    # URI가 아닌 경우 리터럴로 판단
    if not value.startswith('http') and not value.startswith('kg:'):
        return True
    
    return False


def determine_literal_type(value):
    """리터럴 값의 타입 결정"""
    try:
        float(value)
        return "numeric"
    except ValueError:
        pass
    
    if str(value).lower() in ['true', 'false']:
        return "boolean"
    
    if len(str(value)) > 100:
        return "text"
    
    return "string"


def generate_cypher_queries(kg_result):
    """Neo4j Cypher 쿼리 생성"""
    queries = []
    
    # 헤더 추가
    queries.append("// ========================================")
    queries.append("// 의료 가이드라인 지식그래프 Neo4j 임포트")
    queries.append(f"// 생성일시: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    queries.append("// ========================================")
    queries.append("")
    
    # 인덱스 생성
    queries.append("// 1. 인덱스 생성 (성능 최적화)")
    queries.append("CREATE INDEX IF NOT EXISTS FOR (n) ON (n.source_code);")
    queries.append("CREATE INDEX IF NOT EXISTS FOR (n) ON (n.concept_id);")
    queries.append("CREATE INDEX IF NOT EXISTS FOR (n) ON (n.source_name);")
    queries.append("CREATE INDEX IF NOT EXISTS FOR (n) ON (n.voca_id);")
    queries.append("")
    
    # 기존 데이터 삭제 (선택사항)
    queries.append("// 2. 기존 데이터 삭제 (필요시 주석 해제)")
    queries.append("// MATCH (n) DETACH DELETE n;")
    queries.append("")
    
    # 노드 생성
    queries.append("// 3. 노드 생성")
    neo4j_data = create_neo4j_friendly_graph(kg_result)
    
    for node in neo4j_data["nodes"]:
        labels = ":".join(node["labels"])
        props = node["properties"]
        
        # 속성을 Cypher 형식으로 변환
        prop_parts = []
        for key, value in props.items():
            if isinstance(value, str):
                prop_parts.append(f"{key}: '{value.replace(chr(39), chr(92)+chr(39))}'")  # 작은따옴표 이스케이프
            elif isinstance(value, (int, float)):
                prop_parts.append(f"{key}: {value}")
            elif isinstance(value, bool):
                prop_parts.append(f"{key}: {str(value).lower()}")
            else:
                prop_parts.append(f"{key}: '{str(value).replace(chr(39), chr(92)+chr(39))}'")
        
        prop_str = "{" + ", ".join(prop_parts) + "}"
        
        queries.append(f"MERGE (n:{labels} {prop_str});")
    
    queries.append("")
    
    # 관계 생성
    queries.append("// 4. 관계 생성")
    
    for rel in neo4j_data["relationships"]:
        start_node = rel["start_node"]
        end_node = rel["end_node"]
        rel_type = rel["type"]
        props = rel["properties"]
        
        # 관계 속성을 Cypher 형식으로 변환
        prop_parts = []
        for key, value in props.items():
            if isinstance(value, str):
                prop_parts.append(f"{key}: '{value.replace(chr(39), chr(92)+chr(39))}'")
            elif isinstance(value, (int, float)):
                prop_parts.append(f"{key}: {value}")
            else:
                prop_parts.append(f"{key}: '{str(value).replace(chr(39), chr(92)+chr(39))}'")
        
        prop_str = "{" + ", ".join(prop_parts) + "}" if prop_parts else ""
        
        # source_code로 노드 매칭
        queries.append(f"MATCH (a {{source_code: '{start_node}'}})") 
        queries.append(f"MATCH (b {{source_code: '{end_node}'}})") 
        queries.append(f"MERGE (a)-[r:{rel_type} {prop_str}]->(b);")
        queries.append("")
    
    # 유용한 쿼리 예시
    queries.append("// 5. 유용한 조회 쿼리 예시")
    queries.append("// 모든 노드 조회 (속성 포함)")
    queries.append("// MATCH (n) RETURN n.source_code, n.source_name, n.voca_id, n.concept_id LIMIT 10;")
    queries.append("")
    queries.append("// 특정 어휘(SNOMED) 노드들 조회")
    queries.append("// MATCH (n {voca_id: 'SNOMED'}) RETURN n LIMIT 20;")
    queries.append("")
    queries.append("// DIRECT 관계만 조회")
    queries.append("// MATCH (a)-[r {trans: 'DIRECT'}]->(b) RETURN a.source_name, r.rela, b.source_name;")
    queries.append("")
    queries.append("// 특정 관계 소스(MEDRT)의 관계들 조회")
    queries.append("// MATCH (a)-[r {rela_source: 'MEDRT'}]->(b) RETURN a, r, b;")
    queries.append("")
    
    # 통계 정보
    stats = neo4j_data["statistics"]
    queries.append("// 6. 그래프 통계")
    queries.append(f"// 총 노드 수: {stats['total_nodes']}")
    queries.append(f"// 총 관계 수: {stats['total_relationships']}")
    queries.append("// 노드 타입별 분포:")
    for node_type, count in stats["node_types"].items():
        queries.append(f"//   {node_type}: {count}개")
    queries.append("")
    
    return "\n".join(queries)


def extract_code_and_concept_id(name, metadata=None):
    """이름과 메타데이터에서 source_code와 concept_id 추출"""
    import re
    
    # 기본값
    source_code = ""
    concept_id = 0
    
    # DP ID 패턴 (DP_001, DP_002 등)
    if name.startswith('DP_'):
        source_code = name
        # DP ID에서 숫자 부분을 concept_id로 사용
        dp_num = re.search(r'DP_(\d+)', name)
        if dp_num:
            concept_id = int(dp_num.group(1))
    
    # 메타데이터에서 정보 추출
    if metadata:
        if 'source_dp_id' in metadata:
            source_code = metadata['source_dp_id']
        if 'concept_id' in metadata:
            concept_id = metadata['concept_id']
    
    # 이름에서 코드 패턴 찾기
    if not source_code:
        # 다양한 코드 패턴 (예: D001234, C123456 등)
        code_pattern = re.search(r'([A-Z]\d{6,})', name)
        if code_pattern:
            source_code = code_pattern.group(1)
        else:
            # 일반적인 이름인 경우 그대로 사용
            source_code = name.replace(' ', '_')[:20]  # 최대 20자로 제한
    
    # concept_id가 0이면 해시를 사용하여 생성
    if concept_id == 0:
        import hashlib
        concept_id = int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % 100000000
    
    return source_code, concept_id


def extract_display_name(name):
    """표시용 이름 추출"""
    # URI에서 로컬 이름 추출
    if name.startswith('http'):
        return name.split('/')[-1].split('#')[-1]
    
    # 네임스페이스 제거
    if ':' in name:
        return name.split(':', 1)[1]
    
    return name


def determine_vocabulary_id(name, metadata=None, labels=None):
    """어휘 ID 결정 (MeSH, SNOMED, RxNorm 등)"""
    # 메타데이터에서 우선 확인
    if metadata and 'vocabulary_id' in metadata:
        return metadata['vocabulary_id']
    
    # 라벨 기반 결정
    if labels:
        if 'DISEASE' in labels or 'CONDITION' in labels:
            return "SNOMED"
        elif 'DRUG' in labels or 'MEDICATION' in labels:
            return "RxNorm"
        elif 'PROCEDURE' in labels:
            return "CPT"
        elif 'MEASUREMENT' in labels:
            return "LOINC"
    
    # 이름 패턴 기반 결정
    name_lower = name.lower()
    if any(word in name_lower for word in ['drug', 'medication', '약물']):
        return "RxNorm"
    elif any(word in name_lower for word in ['disease', 'condition', '질환', '병명']):
        return "SNOMED"
    elif any(word in name_lower for word in ['procedure', 'surgery', '시술']):
        return "CPT"
    elif any(word in name_lower for word in ['test', 'lab', '검사']):
        return "LOINC"
    
    # 기본값
    return "LOCAL"


def determine_rela_source(predicate, metadata=None):
    """관계 소스 결정"""
    # 메타데이터에서 우선 확인
    if metadata and 'rela_source' in metadata:
        return metadata['rela_source']
    
    # predicate 기반 결정
    if 'has_diagnosis' in predicate.lower():
        return "SNOMED"
    elif 'has_drug' in predicate.lower() or 'medication' in predicate.lower():
        return "RxNorm"
    elif 'has_procedure' in predicate.lower():
        return "CPT"
    elif 'may_treat' in predicate.lower():
        return "MEDRT"
    
    # 기본값
    return "KG"


def extract_relation_name(predicate):
    """관계명 추출"""
    # URI에서 로컬 이름 추출
    if predicate.startswith('http'):
        rel_name = predicate.split('/')[-1].split('#')[-1]
    elif ':' in predicate:
        rel_name = predicate.split(':', 1)[1]
    else:
        rel_name = predicate
    
    # 카멜케이스를 공백으로 변환
    import re
    rel_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', rel_name)
    rel_name = rel_name.replace('_', ' ').strip()
    
    return rel_name


def determine_transitivity(confidence, metadata=None):
    """전이성 결정 (DIRECT/INDIRECT)"""
    # 메타데이터에서 우선 확인
    if metadata and 'transitivity' in metadata:
        return metadata['transitivity']
    
    # 신뢰도 기반 결정
    if confidence >= 0.8:
        return "DIRECT"
    elif confidence >= 0.5:
        return "DIRECT"  # 중간 신뢰도도 DIRECT로 처리
    else:
        return "INDIRECT"


def map_entity_type_to_vocabulary(entity_type):
    """엔티티 타입을 어휘로 매핑"""
    entity_type_lower = str(entity_type).lower()
    
    if entity_type_lower in ['condition', 'disease']:
        return "SNOMED"
    elif entity_type_lower in ['medication', 'drug']:
        return "RxNorm"
    elif entity_type_lower == 'procedure':
        return "CPT"
    elif entity_type_lower in ['measurement', 'observation']:
        return "LOINC"
    elif entity_type_lower == 'symptom':
        return "SNOMED"
    else:
        return "LOCAL"


if __name__ == "__main__":
    main() 