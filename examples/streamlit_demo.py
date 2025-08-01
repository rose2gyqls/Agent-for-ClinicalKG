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


def display_progress_callback(placeholder, progress_bar):
    """진행상황 콜백 함수 생성"""
    def callback(progress: ValidationProgress):
        # 진행바 업데이트
        progress_bar.progress(progress.progress_percentage / 100)
        
        # 상태 메시지 업데이트
        track_emoji = {
            "starting": "🔄",
            "similarity": "📊",
            "llm_evidence": "🧠"
        }
        
        step_msg = {
            "initializing": "초기화 중",
            "calculating_similarity": "유사도 계산 중",
            "generating_questions": "검증 질문 생성 중"
        }
        
        emoji = track_emoji.get(progress.current_track, "🔍")
        step = step_msg.get(progress.current_step, progress.current_step)
        
        placeholder.write(f"{emoji} DP {progress.current_dp_index + 1}/{progress.total_dps} - {step}")
    
    return callback


def export_step_results(step_name: str, data: any, step_number: int):
    """단계별 결과 내보내기"""
    timestamp = int(time.time())
    filename = f"step_{step_number:02d}_{step_name}_{timestamp}.json"
    
    # JSON 직렬화 가능하도록 데이터 변환
    serializable_data = convert_to_serializable(data)
    
    step_data = {
        "step": step_name,
        "step_number": step_number,
        "timestamp": timestamp,
        "data": serializable_data
    }
    
    result_json = json.dumps(step_data, ensure_ascii=False, indent=2, default=str)
    
    return st.download_button(
        label=f"📥 Step {step_number}: {step_name} 다운로드",
        data=result_json,
        file_name=filename,
        mime="application/json",
        key=f"download_{step_number}_{timestamp}"
    )


def convert_to_serializable(obj):
    """객체를 JSON 직렬화 가능한 형태로 변환"""
    import numpy as np
    
    # numpy 타입들 처리
    if isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif hasattr(obj, '__dict__'):
        # dataclass나 일반 클래스 객체를 딕셔너리로 변환
        if hasattr(obj, '__dataclass_fields__'):
            # dataclass인 경우
            from dataclasses import asdict
            return convert_to_serializable(asdict(obj))
        else:
            # 일반 클래스인 경우
            return {key: convert_to_serializable(value) for key, value in obj.__dict__.items()}
    elif isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        # 기타 객체는 문자열로 변환
        return str(obj)


def safe_get_attribute(obj, attr_name, default=None):
    """객체에서 안전하게 속성 값을 가져오는 helper 함수"""
    if isinstance(obj, dict):
        return obj.get(attr_name, default)
    else:
        return getattr(obj, attr_name, default)


def display_saved_results():
    """세션에 저장된 결과들을 화면에 표시"""
    
    # Step 1: 마크다운 결과 표시
    if hasattr(st.session_state, 'result_markdown'):
        result_markdown = st.session_state.result_markdown
        
        st.markdown("### 📄 Step 1: 마크다운 변환 결과")
        
        # Step 1 다운로드
        col1, col2 = st.columns([1, 1])
        with col1:
            st.download_button(
                label="📥 마크다운 다운로드",
                data=result_markdown['markdown_content'],
                file_name="medical_guideline.md",
                mime="text/markdown",
                key="saved_download_markdown"
            )
        with col2:
            timestamp = int(time.time()) 
            st.download_button(
                label="📥 Step 1: markdown_conversion 다운로드",
                data=json.dumps({
                    "step": "markdown_conversion",
                    "step_number": 1,
                    "timestamp": timestamp,
                    "data": convert_to_serializable({
                        'markdown_content': result_markdown['markdown_content'],
                        'metadata': result_markdown.get('processed_content')
                    })
                }, ensure_ascii=False, indent=2, default=str),
                file_name=f"step_01_markdown_conversion_{timestamp}.json",
                mime="application/json",
                key=f"saved_download_step1_{timestamp}"
            )
    
    # Step 2: DP 추출 결과 표시
    if hasattr(st.session_state, 'result_dp_extraction'):
        dp_result = st.session_state.result_dp_extraction
        
        st.markdown("---")
        st.markdown(f"### 🧬 Step 2: DP 추출 완료 ({len(dp_result['digital_phenotypes'])}개)")
        
        # Step 2 다운로드
        col1, col2 = st.columns([1, 1])
        with col1:
            result_json = json.dumps(dp_result, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 DP 추출 결과 다운로드",
                data=result_json,
                file_name="extracted_dps.json",
                mime="application/json",
                key="saved_download_dp_extraction"
            )
        with col2:
            timestamp = int(time.time())
            st.download_button(
                label="📥 Step 2: dp_extraction 다운로드",
                data=json.dumps({
                    "step": "dp_extraction",
                    "step_number": 2,
                    "timestamp": timestamp,
                    "data": convert_to_serializable(dp_result)
                }, ensure_ascii=False, indent=2, default=str),
                file_name=f"step_02_dp_extraction_{timestamp}.json",
                mime="application/json",
                key=f"saved_download_step2_{timestamp}"
            )
    
    # Step 3: 검증 결과 표시
    if hasattr(st.session_state, 'result_validation'):
        validation_data = st.session_state.result_validation
        final_dps = validation_data.get('final_dps', [])
        validation_results = validation_data['validation_results']
        validation_summary = validation_data['validation_summary']
        
        st.markdown("---")
        st.markdown(f"### 🔍 Step 3: 2트랙 검증 완료 (최종 {len(final_dps)}개 DP)")
        
        # 요약 통계 (새로운 구조)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("초기 DP", validation_summary['total_initial_dps'])
        with col2:
            st.metric("최종 DP", validation_summary['total_final_dps'])
        with col3:
            st.metric("성공률", f"{validation_summary['success_rate']:.1%}")
        with col4:
            st.metric("재시도 수", len(validation_summary.get('retry_history', [])))
        
        # 평균 점수 계산 (안전한 접근)
        if validation_results:
            # 안전한 속성 접근을 위한 helper 함수
            def safe_get_nested(obj, attr_path, default=0.0):
                try:
                    if isinstance(obj, dict):
                        keys = attr_path.split('.')
                        current = obj
                        for key in keys:
                            current = current.get(key, {})
                        return current if isinstance(current, (int, float)) else default
                    else:
                        keys = attr_path.split('.')
                        current = obj
                        for key in keys:
                            current = getattr(current, key, None)
                            if current is None:
                                return default
                        return current if isinstance(current, (int, float)) else default
                except:
                    return default

            final_scores = [safe_get_nested(r, 'final_score', 0.0) for r in validation_results]
            avg_final_score = sum(final_scores) / len(final_scores) if final_scores else 0.0
            
            # 유사도 점수 계산
            similarity_scores = []
            for r in validation_results:
                if safe_get_nested(r, 'similarity_result.success', False):
                    score = safe_get_nested(r, 'similarity_result.overall_score', 0.0)
                    if score > 0:
                        similarity_scores.append(score)
            avg_similarity_score = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
            
            # 증거 점수 계산
            evidence_scores = []
            for r in validation_results:
                if safe_get_nested(r, 'evidence_result.success', False):
                    score = safe_get_nested(r, 'evidence_result.overall_score', 0.0)
                    if score > 0:
                        evidence_scores.append(score)
            avg_evidence_score = sum(evidence_scores) / len(evidence_scores) if evidence_scores else 0.0
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("평균 최종 점수", f"{avg_final_score:.3f}")
            with col2:
                st.metric("평균 유사도", f"{avg_similarity_score:.3f}")
            with col3:
                st.metric("평균 증거 점수", f"{avg_evidence_score:.3f}")
        
        # 최종 통과 DP만 표시
        st.markdown("##### 📋 최종 통과 DP 목록")
        st.info(f"✅ 검증을 통과한 {len(final_dps)}개의 DP만 표시됩니다.")
        
        for i, dp in enumerate(final_dps, 1):
            retry_icon = "🔄" if "RETRY" in dp.dp_id else ""
            title = f"최종 DP {i}: {dp.label} ✅ {retry_icon}"
            
            with st.expander(title, expanded=i <= 3):
                # 기본 정보
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.write("**ID:**", dp.dp_id)
                    st.write("**Label:**", dp.label)
                    st.write("**Section:**", dp.section_reference)
                
                with col2:
                    # 해당 DP의 검증 결과 찾기 (안전한 접근)
                    dp_validation_result = None
                    for result in validation_results:
                        # 안전하게 result.dp.dp_id 접근
                        result_dp_id = safe_get_attribute(result, 'dp', {})
                        if isinstance(result_dp_id, dict):
                            result_dp_id = result_dp_id.get('dp_id', '')
                        else:
                            result_dp_id = getattr(result_dp_id, 'dp_id', '') if result_dp_id else ''
                        
                        # DP ID 비교
                        if (result_dp_id == dp.dp_id or 
                            (hasattr(dp, 'metadata') and dp.metadata and 
                             dp.metadata.get('retry_from') and result_dp_id == dp.metadata['retry_from'])):
                            dp_validation_result = result
                            break
                    
                    if dp_validation_result:
                        # 안전하게 검증 결과 속성 접근
                        final_score = safe_get_attribute(dp_validation_result, 'final_score', 0.0)
                        processing_time = safe_get_attribute(dp_validation_result, 'processing_time', 0.0)
                        st.metric("최종 점수", f"{final_score:.3f}")
                        st.metric("처리 시간", f"{processing_time:.2f}초")
                
                # 정의
                st.write("**정의:**")
                st.write(dp.definition)
                
                # 재추출 정보 (있는 경우)
                if hasattr(dp, 'metadata') and dp.metadata and dp.metadata.get('retry_from'):
                    st.markdown("**🔄 재추출 정보:**")
                    st.write(f"- 원본 DP: {dp.metadata['retry_from']}")
                    st.write(f"- 재추출 사유: {dp.metadata.get('retry_reason', 'N/A')}")
        
        # Step 3 다운로드
        st.markdown("##### 📥 Step 3: 검증 결과 다운로드")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 최종 통과 DP 결과
            final_dps_export = [
                {
                    'dp_id': dp.dp_id,
                    'label': dp.label,
                    'definition': dp.definition,
                    'section_reference': dp.section_reference,
                    'confidence_score': dp.confidence_score,
                    'metadata': dp.metadata
                }
                for dp in final_dps
            ]
            
            st.download_button(
                label="📥 최종 통과 DP",
                data=json.dumps({
                    "final_dps": final_dps_export,
                    "count": len(final_dps),
                    "success_rate": validation_summary['success_rate']
                }, ensure_ascii=False, indent=2, default=str),
                file_name="final_validated_dps.json",
                mime="application/json",
                key="saved_download_final_dps"
            )
        
        with col2:
            # 전체 검증 결과
            validation_export = ValidationMetrics.export_validation_results_to_json(
                validation_results,
                validation_summary,
                f"temp_validation_results_{int(time.time())}.json"
            )
            
            result_json = json.dumps(validation_export, ensure_ascii=False, indent=2, default=str)
            st.download_button(
                label="📥 전체 검증 결과",
                data=result_json,
                file_name="validation_results_complete.json",
                mime="application/json",
                key="saved_download_validation_complete"
            )
        
        with col3:
            # Step 3 구조화된 결과
            timestamp = int(time.time())
            st.download_button(
                label="📥 Step 3: 검증 완료",
                data=json.dumps({
                    "step": "two_track_validation",
                    "step_number": 3,
                    "timestamp": timestamp,
                    "data": convert_to_serializable({
                        'final_dps': final_dps_export,
                        'validation_results': validation_export,
                        'summary': validation_summary
                    })
                }, ensure_ascii=False, indent=2, default=str),
                file_name=f"step_03_two_track_validation_{timestamp}.json",
                mime="application/json",
                key=f"saved_download_step3_{timestamp}"
            )
    
            # Step 4: 지식그래프 결과 표시
    if hasattr(st.session_state, 'result_knowledge_graph'):
        kg_data = st.session_state.result_knowledge_graph
        kg_result = kg_data.get('kg_workflow_result', {})
        
        st.markdown("---")
        st.markdown("### 🌐 Step 4: 지식그래프 생성 완료")
        
        # 처리 상태 표시
        status = kg_result.get('status', 'unknown')
        if hasattr(status, 'value'):
            status_value = status.value
        else:
            status_value = str(status)
        
        if status_value == 'completed':
            st.success("✅ 지식그래프 생성이 성공적으로 완료되었습니다!")
        elif status_value == 'failed':
            st.error("❌ 지식그래프 생성에 실패했습니다.")
        else:
            st.info(f"ℹ️ 처리 상태: {status_value}")
        
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
        
        # 트리플 시각화 섹션 추가
        if kg_result.get('generated_triples'):
            st.markdown("#### 📊 생성된 트리플 시각화")
            
            # 트리플 목록 표시
            with st.expander("🔍 트리플 상세 보기", expanded=False):
                triples_df = []
                for triple in kg_result['generated_triples']:
                    triple_type = triple.triple_type.value if hasattr(triple.triple_type, 'value') else str(triple.triple_type)
                    triples_df.append({
                        'Subject': triple.subject,
                        'Predicate': triple.predicate, 
                        'Object': triple.object,
                        'Type': triple_type,
                        'Confidence': triple.confidence
                    })
                
                if triples_df:
                    import pandas as pd
                    df = pd.DataFrame(triples_df)
                    st.dataframe(df, use_container_width=True)
            
            # 트리플 네트워크 그래프 (간단한 방식)
            with st.expander("🕸️ 트리플 네트워크 그래프", expanded=True):
                try:
                    import networkx as nx
                    import matplotlib.pyplot as plt
                    import matplotlib
                    matplotlib.use('Agg')  # GUI 없는 백엔드 사용
                    
                    # 네트워크 그래프 생성
                    G = nx.DiGraph()
                    
                    for triple in kg_result['generated_triples'][:20]:  # 처음 20개만 표시
                        subj = triple.subject
                        obj = triple.object
                        pred = triple.predicate
                        
                        G.add_edge(subj, obj, label=pred, weight=triple.confidence)
                    
                    if G.number_of_nodes() > 0:
                        fig, ax = plt.subplots(figsize=(12, 8))
                        
                        # 레이아웃 설정
                        pos = nx.spring_layout(G, k=3, iterations=50)
                        
                        # 노드 그리기
                        nx.draw_networkx_nodes(G, pos, 
                                             node_color='lightblue',
                                             node_size=1000,
                                             alpha=0.7,
                                             ax=ax)
                        
                        # 엣지 그리기
                        nx.draw_networkx_edges(G, pos, 
                                             edge_color='gray',
                                             arrows=True,
                                             arrowsize=20,
                                             alpha=0.6,
                                             ax=ax)
                        
                        # 레이블 그리기
                        labels = {node: node[:15] + "..." if len(node) > 15 else node for node in G.nodes()}
                        nx.draw_networkx_labels(G, pos, labels, 
                                              font_size=8,
                                              font_weight='bold',
                                              ax=ax)
                        
                        ax.set_title("지식그래프 트리플 네트워크\n(처음 20개 트리플만 표시)", 
                                    fontsize=14, fontweight='bold')
                        ax.axis('off')
                        
                        st.pyplot(fig)
                        plt.close(fig)
                    else:
                        st.info("표시할 트리플이 없습니다.")
                        
                except ImportError:
                    st.warning("그래프 시각화를 위해 networkx와 matplotlib이 필요합니다.")
                except Exception as e:
                    st.error(f"그래프 시각화 중 오류 발생: {str(e)}")
            
            # RDF 형식 표시
            triple_generation_result = kg_result.get('triple_generation_result', {})
            rdf_graph = triple_generation_result.get('rdf_graph', {})
            
            if rdf_graph:
                with st.expander("📄 RDF 형식 보기", expanded=False):
                    rdf_format = st.selectbox(
                        "RDF 형식 선택:",
                        ['turtle', 'json_ld', 'n3', 'xml'],
                        key="rdf_format_select"
                    )
                    
                    if rdf_format in rdf_graph and rdf_graph[rdf_format]:
                        st.code(rdf_graph[rdf_format], language=rdf_format)
                    else:
                        st.info(f"{rdf_format} 형식의 데이터가 없습니다.")
        
        # 세부 결과 표시
        if kg_result.get('entity_extraction_result'):
            with st.expander("🔍 Step 4.1: 엔티티 추출 세부 결과", expanded=False):
                entity_stats = kg_result['entity_extraction_result'].get('statistics', {})
                if entity_stats:
                    st.write("**타입별 엔티티 수:**")
                    for entity_type, count in entity_stats.get('by_type', {}).items():
                        st.write(f"- {entity_type}: {count}개")
        
        if kg_result.get('omop_mapping_result'):
            with st.expander("🔍 Step 4.2: OMOP CDM 매핑 세부 결과", expanded=False):
                mapping_stats = kg_result['omop_mapping_result'].get('mapping_statistics', {})
                if mapping_stats:
                    st.write("**도메인별 매핑 수:**")
                    for domain, count in mapping_stats.get('by_domain', {}).items():
                        st.write(f"- {domain}: {count}개")
                    
                    st.write("**어휘체계별 매핑 수:**")
                    for vocab, count in mapping_stats.get('by_vocabulary', {}).items():
                        st.write(f"- {vocab}: {count}개")
        
        if kg_result.get('triple_generation_result'):
            with st.expander("🔍 Step 4.3: 트리플 생성 세부 결과", expanded=False):
                triple_stats = kg_result['triple_generation_result'].get('statistics', {})
                if triple_stats:
                    st.write("**트리플 타입별 수:**")
                    for triple_type, count in triple_stats.get('by_type', {}).items():
                        st.write(f"- {triple_type}: {count}개")
                    
                    st.write(f"**평균 신뢰도:** {triple_stats.get('avg_confidence', 0.0):.3f}")
        
        if kg_result.get('neo4j_load_result'):
            with st.expander("🔍 Step 4.4: Neo4j 적재 세부 결과", expanded=False):
                neo4j_result = kg_result['neo4j_load_result']
                if hasattr(neo4j_result, 'success') and neo4j_result.success:
                    st.write(f"**생성된 노드:** {getattr(neo4j_result, 'nodes_created', 0)}개")
                    st.write(f"**생성된 관계:** {getattr(neo4j_result, 'relationships_created', 0)}개")
                    st.write(f"**설정된 속성:** {getattr(neo4j_result, 'properties_set', 0)}개")
                    st.write(f"**처리 시간:** {getattr(neo4j_result, 'processing_time', 0.0):.2f}초")
                else:
                    st.write(f"**오류 메시지:** {getattr(neo4j_result, 'error_message', 'Unknown error')}")
        
        # Step 4 다운로드
        st.markdown("##### 📥 Step 4: 지식그래프 결과 다운로드")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 전체 Step 4 결과
            timestamp = int(time.time())
            st.download_button(
                label="📥 Step 4: 전체 결과",
                data=json.dumps({
                    "step": "knowledge_graph_generation",
                    "step_number": 4,
                    "timestamp": timestamp,
                    "data": convert_to_serializable(kg_result)
                }, ensure_ascii=False, indent=2, default=str),
                file_name=f"step_04_knowledge_graph_{timestamp}.json",
                mime="application/json",
                key=f"saved_download_step4_{timestamp}"
            )
        
        with col2:
            # RDF 트리플 (Turtle 형식)
            rdf_graph = kg_result.get('triple_generation_result', {}).get('rdf_graph', {})
            if rdf_graph.get('turtle'):
                st.download_button(
                    label="📥 RDF 트리플 (Turtle)",
                    data=rdf_graph['turtle'],
                    file_name="knowledge_graph.ttl",
                    mime="text/turtle",
                    key="saved_download_rdf_turtle"
                )
        
        with col3:
            # Neo4j 쿼리 결과 (사용 가능한 경우)
            if kg_result.get('neo4j_load_result') and hasattr(kg_result['neo4j_load_result'], 'success') and kg_result['neo4j_load_result'].success:
                sample_queries = {
                    "nodes_count": "MATCH (n) RETURN count(n) as total_nodes",
                    "relationships_count": "MATCH ()-[r]->() RETURN count(r) as total_relationships",
                    "concepts_by_domain": "MATCH (c:Concept) RETURN c.domain_id, count(*) as count ORDER BY count DESC"
                }
                
                st.download_button(
                    label="📥 Neo4j 쿼리 예제",
                    data=json.dumps(sample_queries, ensure_ascii=False, indent=2),
                    file_name="neo4j_sample_queries.json",
                    mime="application/json",
                    key="saved_download_neo4j_queries"
                )
    
    # 경고 표시
    if hasattr(st.session_state, 'result_markdown') and st.session_state.result_markdown.get('warnings'):
        st.warning("⚠️ 경고: " + "; ".join(st.session_state.result_markdown['warnings']))


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
        similarity_threshold = st.slider("유사도 임계치", 0.0, 1.0, 0.5, 0.05, help="문장 유사도 검증 임계치")
        evidence_threshold = st.slider("증거 임계치", 0.0, 1.0, 0.5, 0.05, help="LLM 증거 검증 임계치")
        final_threshold = st.slider("최종 임계치", 0.0, 1.0, 0.6, 0.05, help="최종 통과 임계치")
        max_retries = st.selectbox("최대 재시도 횟수", [0, 1, 2, 3], index=1, help="검증 실패 시 재추출 시도 횟수")
        
                                st.markdown("### 🌐 Step 4: 지식그래프 생성")
        create_kg = st.checkbox("지식그래프 생성 실행", value=True, help="검증된 DP로부터 트리플 생성 (Neo4j 적재 제외)")
        entity_confidence = st.slider("엔티티 신뢰도", 0.0, 1.0, 0.7, 0.05, help="엔티티 추출 신뢰도 임계치")
        use_llm_triples = st.checkbox("LLM 기반 트리플 생성", value=True, help="dp_to_triple.txt 프롬프트를 사용한 LLM 기반 트리플 생성")
        
        st.markdown("---")
        st.markdown("### 지원 형식")
        st.markdown("- 📄 텍스트")
        st.markdown("- 📋 JSON 데이터")
        st.markdown("- 📁 PDF 파일")
        st.markdown("- 🌐 웹 URL")
        st.markdown("- ☁️ AWS S3")
        
        st.markdown("---")
        st.markdown("### 🔄 세션 관리")
        
        # 세션 상태 표시
        if hasattr(st.session_state, 'result_markdown'):
            st.success("✅ 저장된 결과가 있습니다")
            if st.button("🗑️ 결과 초기화", help="저장된 모든 결과를 삭제합니다"):
                for key in list(st.session_state.keys()):
                    if key.startswith('result_'):
                        del st.session_state[key]
                st.rerun()
        else:
            st.info("ℹ️ 저장된 결과가 없습니다")
    
    # 메인 영역
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📥 입력")
        
        # 입력 방식 선택
        input_method = st.selectbox(
            "입력 방식 선택",
            ["직접 텍스트 입력", "JSON 데이터", "파일 업로드", "URL 입력", "S3 경로"]
        )
        
        input_data = None
        
        if input_method == "직접 텍스트 입력":
            # 테스트 텍스트가 설정되어 있으면 사용
            default_value = st.session_state.get('test_text', '')
            
            input_data = st.text_area(
                "의료 가이드라인 텍스트를 입력하세요",
                value=default_value,
                height=300,
                key="input_text_area"
            )
            
            # 텍스트 길이 표시 및 경고
            if input_data:
                char_count = len(input_data)
                st.caption(f"📝 입력 텍스트 길이: {char_count:,} 문자")
                
                if char_count > 30000:
                    st.warning(f"⚠️ 텍스트가 너무 깁니다. 할당량 초과 위험이 있습니다. (권장: 30,000 문자 이하)")
                elif char_count > 20000:
                    st.info(f"💡 텍스트가 다소 깁니다. 할당량 소모가 클 수 있습니다.")
        
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
                except Exception as e:
                    st.error(f"JSON 파일을 읽을 수 없습니다: {str(e)}")
        
        elif input_method == "파일 업로드":
            uploaded_file = st.file_uploader(
                "파일을 업로드하세요",
                type=['pdf', 'txt', 'json'],
                help="PDF, 텍스트, JSON 파일을 지원합니다"
            )
            
            if uploaded_file is not None:
                if uploaded_file.type == "application/pdf":
                    st.warning("PDF 처리를 위해서는 PyPDF2 또는 pdfplumber 라이브러리가 필요합니다.")
                    input_data = uploaded_file
                elif uploaded_file.type == "application/json":
                    try:
                        input_data = json.load(uploaded_file)
                    except json.JSONDecodeError as e:
                        st.error(f"JSON 파일 형식 오류: {str(e)}")
                    except Exception as e:
                        st.error(f"JSON 파일을 읽을 수 없습니다: {str(e)}")
                else:
                    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
                    input_data = stringio.read()
        
        elif input_method == "URL 입력":
            url = st.text_input(
                "URL을 입력하세요",
                placeholder="https://example.com/guideline.html"
            )
            if url:
                input_data = url
        
        elif input_method == "S3 경로":
            s3_path = st.text_input(
                "S3 경로를 입력하세요",
                placeholder="s3://bucket-name/path/to/guideline.json"
            )
            if s3_path:
                input_data = s3_path
                st.info("AWS 자격 증명이 설정되어 있는지 확인하세요.")
        
        # 처리 버튼
        process_button = st.button("🔄 처리 시작", type="primary", disabled=not input_data)
        
        # 새로 처리할 때 기존 결과 초기화
        if process_button:
            for key in list(st.session_state.keys()):
                if key.startswith('result_'):
                    del st.session_state[key]
    
    with col2:
        st.header("📤 출력")
        
        # 세션에서 처리 결과 복원 또는 새로 처리
        if process_button and input_data:
            try:
                # 전체 진행상황
                overall_progress = st.progress(0)
                overall_status = st.empty()
                
                # Step 1: 마크다운 변환
                overall_status.write("🔄 Step 1: 마크다운 변환 중...")
                overall_progress.progress(0.1)
                
                # 워크플로우 설정
                # workflow_options = {
                #     'include_metadata': include_metadata,
                #     'include_toc': include_toc
                # }
                
                # 처리 시작
                workflow = DataProcessingWorkflow()
                result = workflow.process_sync(input_data)
                
                if result['status'].value == 'completed':
                    overall_progress.progress(0.3)
                    overall_status.write("✅ Step 1: 마크다운 변환 완료")
                    
                    # Step 1 결과를 세션에 저장
                    st.session_state.result_markdown = {
                        'markdown_content': result.get('markdown_content'),
                        'processed_content': result.get('processed_content'),
                        'warnings': result.get('warnings', [])
                    }
                    
                    # Step 1 결과 표시 및 다운로드
                    if result.get('markdown_content'):
                        st.markdown("### 📄 Step 1: 마크다운 변환 결과")
                        
                        # Step 1 다운로드
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            st.download_button(
                                label="📥 마크다운 다운로드",
                                data=result['markdown_content'],
                                file_name="medical_guideline.md",
                                mime="text/markdown",
                                key="download_markdown"
                            )
                        with col2:
                            export_step_results("markdown_conversion", {
                                'markdown_content': result['markdown_content'],
                                'metadata': result.get('processed_content')
                            }, 1)
                        
                        # DP 추출 수행
                        if extract_dp:
                            overall_status.write("🔄 Step 2: DP 추출 초기화 중...")
                            overall_progress.progress(0.4)
                            
                            try:
                                dp_extractor = DPExtractor.create_default()
                                
                                overall_status.write("🧬 Step 2: DP 추출 중...")
                                overall_progress.progress(0.5)
                                
                                # DP 추출 실행
                                dp_result = dp_extractor.extract_dps_with_metadata(
                                    result['markdown_content'],
                                    document_metadata={
                                        'source': input_method,
                                        'processing_timestamp': result.get('processing_timestamp')
                                    }
                                )
                                
                                overall_progress.progress(0.6)
                                overall_status.write("✅ Step 2: DP 추출 완료")
                                
                                if dp_result['digital_phenotypes']:
                                    # Step 2 결과를 세션에 저장
                                    st.session_state.result_dp_extraction = dp_result
                                    
                                    st.markdown("---")
                                    st.markdown(f"### 🧬 Step 2: DP 추출 완료 ({len(dp_result['digital_phenotypes'])}개)")
                                    
                                    # Step 2 다운로드
                                    col1, col2 = st.columns([1, 1])
                                    with col1:
                                        result_json = json.dumps(dp_result, ensure_ascii=False, indent=2)
                                        st.download_button(
                                            label="📥 DP 추출 결과 다운로드",
                                            data=result_json,
                                            file_name="extracted_dps.json",
                                            mime="application/json",
                                            key="download_dp_extraction"
                                        )
                                    with col2:
                                        export_step_results("dp_extraction", dp_result, 2)
                                    
                                    # DP 검증 수행
                                    if validate_dp:
                                        overall_status.write("🔄 Step 3: 2트랙 검증 초기화 중...")
                                        overall_progress.progress(0.7)
                                        
                                        try:
                                            # 진행상황 표시용 컨테이너
                                            validation_progress_container = st.container()
                                            with validation_progress_container:
                                                st.markdown("---")
                                                st.markdown("### 🔍 Step 3: 2트랙 DP 검증")
                                                validation_progress_bar = st.progress(0)
                                                validation_status = st.empty()
                                                validation_detail = st.empty()
                                            
                                            # 검증기 초기화 (진행상황 콜백 포함)
                                            progress_callback = display_progress_callback(validation_detail, validation_progress_bar)
                                            
                                            dp_validator = TwoTrackDPValidator(
                                                similarity_threshold=similarity_threshold,
                                                evidence_threshold=evidence_threshold,
                                                final_threshold=final_threshold,
                                                max_retries=max_retries,
                                                progress_callback=progress_callback
                                            )
                                            
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
                                            
                                            validation_status.write("🔍 2트랙 검증 및 재추출 시작...")
                                            
                                            # 검증 및 재추출 실행 (개별 DP별 선택적 재추출)
                                            final_dps, validation_results, validation_summary = dp_validator.validate_dps_with_selective_retry(
                                                dp_objects,
                                                result['markdown_content'],
                                                dp_extractor
                                            )
                                            
                                            overall_progress.progress(0.9)
                                            overall_status.write("✅ Step 3: 2트랙 검증 완료")
                                            validation_status.write("✅ 2트랙 검증 및 재추출 완료")
                                            validation_detail.write("")
                                            validation_progress_bar.progress(1.0)
                                            
                                            # 검증 결과를 세션에 저장 (최종 DP 리스트 포함)
                                            st.session_state.result_validation = {
                                                'final_dps': final_dps,
                                                'validation_results': validation_results,
                                                'validation_summary': validation_summary,
                                                'dp_objects': dp_objects
                                            }
                                            
                                            # Step 4: 지식그래프 생성
                                            if create_kg and final_dps:
                                                try:
                                                    overall_status.write("🔄 Step 4: 지식그래프 생성 시작...")
                                                    overall_progress.progress(0.91)
                                                    
                                                    # 지식그래프 워크플로우 초기화
                                                    kg_workflow = KnowledgeGraphWorkflow()
                                                    
                                                                                        # Step 4 처리 옵션 설정
                                    kg_options = {
                                        'entity_confidence_threshold': entity_confidence,
                                        'use_llm_triples': use_llm_triples
                                    }
                                                    
                                                    # Step 4 실행
                                                    kg_result = kg_workflow.process_sync(
                                                        final_dps,
                                                        result['markdown_content'], 
                                                        kg_options
                                                    )
                                                    
                                                    # Step 4 결과를 세션에 저장
                                                    st.session_state.result_knowledge_graph = {
                                                        'kg_workflow_result': kg_result,
                                                        'processing_options': kg_options
                                                    }
                                                    
                                                    overall_progress.progress(1.0)
                                                    overall_status.write("✅ Step 4: 지식그래프 생성 완료!")
                                                    
                                                    print(f"✅ Step 4 완료 - 상태: {kg_result['status']}")
                                                    
                                                except Exception as e:
                                                    error_msg = str(e)
                                                    print(f"❌ Step 4 실패: {error_msg}")
                                                    
                                                    if "할당량 초과" in error_msg or "quota" in error_msg.lower():
                                                        st.error("❌ Step 4: Gemini API 할당량 초과")
                                                    elif "Neo4j" in error_msg:
                                                        st.warning("⚠️ Step 4: Neo4j 연결 오류 - 그래프 적재는 실패했지만 다른 단계는 완료됨")
                                                    elif "Elasticsearch" in error_msg:
                                                        st.warning("⚠️ Step 4: Elasticsearch 연결 오류 - OMOP 매핑은 실패했지만 엔티티 추출은 완료됨")
                                                    else:
                                                        st.error(f"❌ Step 4: 지식그래프 생성 실패 - {error_msg}")
                                            
                                            # 검증 결과 표시
                                            if validation_results:
                                                # 최종 통과 DP만 표시
                                                st.markdown("##### 📋 최종 통과 DP 목록")
                                                
                                                for i, dp in enumerate(final_dps, 1):
                                                    # 해당 DP의 검증 결과 찾기
                                                    dp_validation_result = None
                                                    for result in validation_results:
                                                        if result.dp.dp_id == dp.dp_id or (hasattr(dp, 'metadata') and dp.metadata and dp.metadata.get('retry_from') and result.dp.dp_id == dp.metadata['retry_from']):
                                                            dp_validation_result = result
                                                            break
                                                    
                                                    retry_icon = "🔄" if "RETRY" in dp.dp_id else ""
                                                    title = f"최종 DP {i}: {dp.label} ✅ {retry_icon}"
                                                    
                                                    with st.expander(title, expanded=i <= 3):
                                                        # 기본 정보
                                                        col1, col2 = st.columns([1, 1])
                                                        
                                                        with col1:
                                                            st.write("**ID:**", dp.dp_id)
                                                            st.write("**Label:**", dp.label)
                                                            st.write("**Section:**", dp.section_reference)
                                                        
                                                        with col2:
                                                            if dp_validation_result:
                                                                # 안전하게 검증 결과 속성 접근
                                                                final_score = safe_get_attribute(dp_validation_result, 'final_score', 0.0)
                                                                processing_time = safe_get_attribute(dp_validation_result, 'processing_time', 0.0)
                                                                st.metric("최종 점수", f"{final_score:.3f}")
                                                                st.metric("처리 시간", f"{processing_time:.2f}초")
                                                            else:
                                                                st.write("검증 결과를 찾을 수 없음")
                                                        
                                                        # 정의
                                                        st.write("**정의:**")
                                                        st.write(dp.definition)
                                                        
                                                        # 검증 세부 결과 (있는 경우) - 안전한 접근
                                                        if dp_validation_result:
                                                            with st.expander("🔍 검증 세부 결과", expanded=False):
                                                                st.write("**트랙 1 - 유사도 검증:**")
                                                                # 안전하게 유사도 결과 접근
                                                                try:
                                                                    similarity_result = getattr(dp_validation_result, 'similarity_result', None)
                                                                    if similarity_result:
                                                                        sim_overall_score = getattr(similarity_result, 'overall_score', 0.0)
                                                                        sim_details = getattr(similarity_result, 'details', [])
                                                                    else:
                                                                        sim_overall_score = 0.0
                                                                        sim_details = []
                                                                    
                                                                    st.write(f"점수: {sim_overall_score:.3f}")
                                                                    if sim_details:
                                                                        for detail in sim_details:
                                                                            try:
                                                                                match_sentence = getattr(detail, 'best_match_sentence', '') if detail else ''
                                                                                similarity_score_val = getattr(detail, 'similarity_score', 0.0) if detail else 0.0
                                                                                
                                                                                st.write(f"- 매칭 문장: {str(match_sentence)[:100]}...")
                                                                                st.write(f"- 유사도: {similarity_score_val:.3f}")
                                                                            except Exception as e:
                                                                                st.write(f"- 세부 정보 처리 오류: {str(e)}")
                                                                except Exception as e:
                                                                    st.write(f"유사도 정보 처리 오류: {str(e)}")
                                                                
                                                                st.write("**트랙 2 - 증거 기반 검증:**")
                                                                # 안전하게 증거 결과 접근
                                                                try:
                                                                    evidence_result = getattr(dp_validation_result, 'evidence_result', None)
                                                                    if evidence_result:
                                                                        ev_overall_score = getattr(evidence_result, 'overall_score', 0.0)
                                                                        ev_details = getattr(evidence_result, 'details', [])
                                                                    else:
                                                                        ev_overall_score = 0.0
                                                                        ev_details = []
                                                                    
                                                                    st.write(f"점수: {ev_overall_score:.3f}")
                                                                    if ev_details:
                                                                        for j, evidence in enumerate(ev_details[:3], 1):
                                                                            try:
                                                                                question = getattr(evidence, 'question', '') if evidence else ''
                                                                                best_evidence = getattr(evidence, 'best_evidence', '') if evidence else ''
                                                                                evidence_score_val = getattr(evidence, 'evidence_score', 0.0) if evidence else 0.0
                                                                                
                                                                                st.write(f"질문 {j}: {str(question)}")
                                                                                st.write(f"증거: {str(best_evidence)[:100]}...")
                                                                                st.write(f"점수: {evidence_score_val:.3f}")
                                                                            except Exception as e:
                                                                                st.write(f"- 증거 세부 정보 처리 오류: {str(e)}")
                                                                except Exception as e:
                                                                    st.write(f"증거 정보 처리 오류: {str(e)}")
                                                
                                                # Step 3 결과 다운로드
                                                st.markdown("##### 📥 검증 결과 다운로드")
                                                
                                                col1, col2, col3 = st.columns(3)
                                                
                                                with col1:
                                                    # 최종 통과 DP 결과
                                                    final_dps_export = [
                                                        {
                                                            'dp_id': dp.dp_id,
                                                            'label': dp.label,
                                                            'definition': dp.definition,
                                                            'section_reference': dp.section_reference,
                                                            'confidence_score': dp.confidence_score,
                                                            'metadata': dp.metadata
                                                        }
                                                        for dp in final_dps
                                                    ]
                                                    
                                                    st.download_button(
                                                        label="📥 최종 통과 DP",
                                                        data=json.dumps({
                                                            "final_dps": final_dps_export,
                                                            "count": len(final_dps),
                                                            "success_rate": validation_summary['success_rate']
                                                        }, ensure_ascii=False, indent=2, default=str),
                                                        file_name="final_validated_dps.json",
                                                        mime="application/json",
                                                        key="download_final_dps"
                                                    )
                                                
                                                with col2:
                                                    # 전체 검증 결과
                                                    validation_export = ValidationMetrics.export_validation_results_to_json(
                                                        validation_results,
                                                        validation_summary,
                                                        f"temp_validation_results_{int(time.time())}.json"
                                                    )
                                                    
                                                    st.download_button(
                                                        label="📥 전체 검증 결과",
                                                        data=json.dumps(validation_export, ensure_ascii=False, indent=2, default=str),
                                                        file_name="validation_results_complete.json",
                                                        mime="application/json",
                                                        key="download_validation_complete"
                                                    )
                                                
                                                with col3:
                                                    # Step 3 구조화된 결과
                                                    timestamp = int(time.time())
                                                    st.download_button(
                                                        label="📥 Step 3: 검증 완료",
                                                        data=json.dumps({
                                                            "step": "two_track_validation",
                                                            "step_number": 3,
                                                            "timestamp": timestamp,
                                                            "data": convert_to_serializable({
                                                                'final_dps': final_dps_export,
                                                                'validation_results': validation_export,
                                                                'summary': validation_summary
                                                            })
                                                        }, ensure_ascii=False, indent=2, default=str),
                                                        file_name=f"step_03_two_track_validation_{timestamp}.json",
                                                        mime="application/json",
                                                        key=f"download_step3_{timestamp}"
                                                    )
                                            else:
                                                st.warning("⚠️ 검증 결과가 없습니다.")
                                        
                                        except Exception as e:
                                            error_msg = str(e)
                                            
                                            if "할당량 초과" in error_msg or "quota" in error_msg.lower():
                                                st.error("❌ Gemini API 할당량 초과")
                                                st.warning("⚠️ 무료 티어 제한에 걸렸습니다")
                                                
                                                with st.expander("💡 해결 방법"):
                                                    st.markdown("""
                                                    **할당량 초과 해결 방법:**
                                                    
                                                    1. **잠시 대기**: 1-2분 후 다시 시도
                                                    2. **입력 텍스트 줄이기**: 더 짧은 텍스트로 테스트
                                                    3. **유료 플랜**: [Google AI Studio](https://makersuite.google.com/app/apikey)에서 업그레이드
                                                    
                                                    **무료 티어 제한:**
                                                    - 분당 250,000 토큰 (약 200,000 문자)
                                                    - 일일 요청 수 제한
                                                    
                                                    **팁:**
                                                    - 긴 문서는 여러 번에 나누어 처리
                                                    - 오프타임(한국 시간 새벽)에 사용 시 더 안정적
                                                    """)
                                            else:
                                                st.error(f"❌ 2트랙 검증 중 오류 발생: {error_msg}")
                                                st.info("💡 팁: Gemini API 키가 올바르게 설정되어 있는지 확인하세요.")
                                
                                else:
                                    st.warning("⚠️ 추출된 디지털 표현형이 없습니다.")
                                    
                                    # 오류 정보 표시
                                    if dp_result['extraction_metadata'].get('error'):
                                        st.error(f"오류: {dp_result['extraction_metadata']['error']}")
                            
                            except Exception as e:
                                error_msg = str(e)
                                
                                if "할당량 초과" in error_msg or "quota" in error_msg.lower():
                                    st.error("❌ Gemini API 할당량 초과")
                                    st.warning("⚠️ 무료 티어 제한에 걸렸습니다")
                                    
                                    with st.expander("💡 해결 방법"):
                                        st.markdown("""
                                        **할당량 초과 해결 방법:**
                                        
                                        1. **잠시 대기**: 1-2분 후 다시 시도
                                        2. **입력 텍스트 줄이기**: 더 짧은 텍스트로 테스트
                                        3. **유료 플랜**: [Google AI Studio](https://makersuite.google.com/app/apikey)에서 업그레이드
                                        
                                        **무료 티어 제한:**
                                        - 분당 250,000 토큰 (약 200,000 문자)
                                        - 일일 요청 수 제한
                                        
                                        **팁:**
                                        - 긴 문서는 여러 번에 나누어 처리
                                        - 오프타임(한국 시간 새벽)에 사용 시 더 안정적
                                        """)
                                else:
                                    st.error(f"❌ DP 추출 중 오류 발생: {error_msg}")
                                    st.info("💡 팁: Gemini API 키가 올바르게 설정되어 있는지 확인하세요.")
                    
                    # 전체 처리 완료
                    overall_progress.progress(1.0)
                    overall_status.write("✅ 모든 처리 완료!")
                
                else:
                    if result.get('errors'):
                        st.error("오류: " + "; ".join(result['errors']))
                
            except Exception as e:
                st.error(f"처리 중 오류가 발생했습니다: {str(e)}")
        
        # 세션에 저장된 결과가 있으면 표시 (페이지 리로드 후에도 유지)
        elif hasattr(st.session_state, 'result_markdown'):
            display_saved_results()
        
        else:
            st.info("왼쪽에서 데이터를 입력하고 '처리 시작' 버튼을 클릭하세요.")
    
    # 하단 정보
    st.markdown("---")
    
    with st.expander("ℹ️ 사용법 및 정보"):
        st.markdown("""
        ### 📖 사용법
        1. **입력 방식 선택**: 텍스트, JSON, 파일, URL, S3 중 선택
        2. **처리 설정**: 2트랙 검증 및 지식그래프 생성 옵션 조정
        3. **데이터 입력**: 의료 가이드라인 데이터 입력
        4. **처리 시작**: '처리 시작' 버튼 클릭
        5. **4단계 처리**: 마크다운 변환 → DP 추출 → 검증 → 지식그래프 생성
        6. **결과 확인**: 각 Step별 결과 및 진행상황 확인
        7. **다운로드**: 각 단계별 결과 파일 다운로드
        
        ### 🔧 2트랙 검증 시스템
        - **트랙 1: 문장별 유사도 검증**
          - 문장 임베딩 및 유사도 계산
          - 키워드 매칭 및 시퀀스 매칭
          - 원본 텍스트와의 정확한 대응 관계 확인
          
        - **트랙 2: LLM 증거 기반 검증**
          - 5가지 검증 질문 자동 생성
          - 원본 텍스트에서 증거 탐색
          - 의학적 타당성 및 논리적 일관성 검증
          
        - **재추출 로직**
          - 임계치 미달 시 자동 재추출
          - 개선된 프롬프트로 재시도
          - 최대 재시도 횟수 제한으로 무한루프 방지
        
        ### 🔧 지원 기능
        - **다양한 입력 형식**: 텍스트, JSON, PDF, URL, S3
        - **지능형 구조화**: AI 기반 콘텐츠 분석 및 구조화
        - **마크다운 변환**: 표준화된 마크다운 형식으로 출력
        - **DP 추출**: Gemini LLM을 활용한 디지털 표현형 추출
        - **2트랙 DP 검증**: 유사도 + LLM 증거 기반 이중 검증
        - **재추출 로직**: 검증 실패 시 자동 재추출
        - **엔티티 추출**: LLM + 규칙 기반 의료 엔티티 추출
        - **OMOP CDM 매핑**: Elasticsearch 기반 표준 용어 매핑
        - **RDF 트리플 생성**: 지식그래프 표준 형식 생성
        - **Neo4j 적재**: 그래프 데이터베이스 자동 구축
        - **실시간 진행상황**: 단계별 진행률 및 상태 표시
        - **단계별 다운로드**: 각 처리 단계별 결과 다운로드
        - **상세 보고서**: 검증 결과 및 통계 보고서
        
        ### ⚠️ 주의사항
        - PDF 처리를 위해서는 추가 라이브러리 설치 필요
        - S3 접근을 위해서는 AWS 자격 증명 설정 필요
        - DP 추출을 위해서는 Gemini API 키 설정 필요
        - 2트랙 검증 및 재추출은 추가 LLM 비용 발생
        - **Step 4 실행 시 추가 요구사항:**
          - OMOP CDM 매핑: Elasticsearch 서버 필요
          - 지식그래프 적재: Neo4j 데이터베이스 필요
          - 엔티티 추출: 추가 LLM API 비용 발생
        - 대용량 파일의 경우 처리 시간이 오래 걸릴 수 있음
        - 재시도 횟수가 많을수록 더 많은 API 비용 발생
        - 문장 임베딩 모델 첫 로드 시 시간이 걸릴 수 있음
        - Neo4j와 Elasticsearch 연결 실패 시에도 다른 단계는 정상 작동
        """)


if __name__ == "__main__":
    main() 