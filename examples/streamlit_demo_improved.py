import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import streamlit as st
import json
import time
from io import StringIO
from typing import Optional

# 필요한 모듈 import
from kg_clinical_guideline.data import DataProcessingWorkflow, InputType
from kg_clinical_guideline.extraction import DPExtractor
from kg_clinical_guideline.validation import TwoTrackDPValidator
from kg_clinical_guideline.graph import KnowledgeGraphWorkflow

def main():
    st.set_page_config(
        page_title="의료 가이드라인 지식 그래프 변환기",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🏥 의료 가이드라인 지식 그래프 변환기")
    st.markdown("**PDF/텍스트 → 마크다운 → DP 추출 → 검증 → 지식그래프 생성**")
    
    # 사이드바에서 페이지 선택
    with st.sidebar:
        st.header("📋 메뉴")
        page = st.radio(
            "페이지 선택:",
            ["🔄 데이터 처리", "📊 결과 확인", "📥 파일 다운로드"],
            index=0
        )
        
        st.markdown("---")
        st.markdown("### 📈 처리 현황")
        
        # 세션 상태 확인
        if 'processing_status' not in st.session_state:
            st.session_state.processing_status = {
                'markdown_completed': False,
                'dp_completed': False, 
                'validation_completed': False,
                'kg_completed': False
            }
        
        status = st.session_state.processing_status
        st.write("✅ 마크다운 변환" if status['markdown_completed'] else "⏳ 마크다운 변환")
        st.write("✅ DP 추출" if status['dp_completed'] else "⏳ DP 추출")
        st.write("✅ DP 검증" if status['validation_completed'] else "⏳ DP 검증")
        st.write("✅ 지식그래프 생성" if status['kg_completed'] else "⏳ 지식그래프 생성")
    
    # 페이지별 내용 표시
    if page == "🔄 데이터 처리":
        show_data_processing_page()
    elif page == "📊 결과 확인":
        show_results_page()
    elif page == "📥 파일 다운로드":
        show_download_page()

def show_data_processing_page():
    """데이터 처리 페이지"""
    st.header("🔄 데이터 처리")
    
    # 입력 방식 선택
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📝 입력 설정")
        input_method = st.selectbox(
            "입력 방식 선택:",
            ["텍스트 직접 입력", "파일 업로드", "JSON 입력"],
            index=0
        )
        
        # 처리 옵션
        st.subheader("⚙️ 처리 옵션")
        extract_dp = st.checkbox("DP 추출", value=True)
        validate_dp = st.checkbox("DP 검증", value=True) 
        create_kg = st.checkbox("지식그래프 생성", value=True)
        
        # KG 옵션
        if create_kg:
            entity_confidence = st.slider("엔티티 신뢰도", 0.0, 1.0, 0.3, 0.05)
            use_llm_triples = st.checkbox("LLM 기반 트리플 생성", value=True)
    
    with col2:
        st.subheader("📄 입력 데이터")
        
        input_text = None
        input_type = "text"  # 기본값
        
        if input_method == "텍스트 직접 입력":
            input_text = st.text_area(
                "의료 가이드라인 텍스트를 입력하세요:",
                height=200,
                placeholder="예: 당뇨병 환자의 혈당 관리 지침..."
            )
            input_type = "text"
        elif input_method == "JSON 입력":
            input_text = st.text_area(
                "JSON 형태의 의료 가이드라인 데이터를 입력하세요:",
                height=200,
                placeholder='''{
  "title": "당뇨병 치료 가이드라인",
  "content": "당뇨병은 혈당 조절에 문제가 있는 만성 질환입니다.",
  "sections": [
    {
      "title": "진단 기준",
      "content": "공복 혈당 126mg/dL 이상"
    },
    {
      "title": "치료",
      "content": "메트포르민 500mg 하루 2회 복용"
    }
  ]
}'''
            )
            input_type = "json"
            
            # JSON 유효성 검사
            if input_text:
                try:
                    json.loads(input_text)
                    st.success("✅ 유효한 JSON 형식입니다.")
                except json.JSONDecodeError as e:
                    st.error(f"❌ JSON 형식 오류: {str(e)}")
                    input_text = None
        else:
            uploaded_file = st.file_uploader(
                "PDF, 텍스트 또는 JSON 파일 업로드:",
                type=['pdf', 'txt', 'json'],
                help="PDF, 텍스트 또는 JSON 파일을 업로드하세요"
            )
            if uploaded_file:
                if uploaded_file.type == "application/pdf":
                    st.info("PDF 파일이 업로드되었습니다.")
                    input_text = "PDF_FILE"  # 실제로는 PDF 처리 로직 필요
                    input_type = "pdf"
                elif uploaded_file.type == "application/json":
                    try:
                        input_text = str(uploaded_file.read(), "utf-8")
                        json.loads(input_text)  # JSON 유효성 검사
                        input_type = "json"
                        st.success("✅ 유효한 JSON 파일이 업로드되었습니다.")
                    except json.JSONDecodeError as e:
                        st.error(f"❌ JSON 파일 형식 오류: {str(e)}")
                        input_text = None
                else:
                    input_text = str(uploaded_file.read(), "utf-8")
                    input_type = "text"
    
    # 처리 시작 버튼
    if st.button("🚀 처리 시작", type="primary", use_container_width=True):
        if input_text:
            process_pipeline(input_text, input_method, input_type, extract_dp, validate_dp, create_kg, 
                           entity_confidence if create_kg else 0.3, 
                           use_llm_triples if create_kg else True)
        else:
            st.error("입력 데이터를 제공해주세요.")

def process_pipeline(input_text, input_method, input_type, extract_dp, validate_dp, create_kg, 
                    entity_confidence, use_llm_triples):
    """전체 처리 파이프라인 실행"""
    
    # 진행률 표시
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # Step 1: 마크다운 변환
        status_text.text("🔄 Step 1: 마크다운 변환 중...")
        progress_bar.progress(0.2)
        
        # 설정 옵션
        workflow_config = {
            'include_metadata': True,
            'include_toc': True
        }
        
        data_workflow = DataProcessingWorkflow(workflow_config)
        
        # 입력 타입에 따른 처리
        if input_type == "json":
            # JSON 데이터 처리 - JSON 문자열을 파싱해서 전달
            try:
                json_data = json.loads(input_text)
                result = data_workflow.process_sync(json_data)
            except json.JSONDecodeError as e:
                st.error(f"JSON 파싱 오류: {str(e)}")
                return
        elif input_type == "pdf":
            # PDF 처리 (실제 구현 필요)
            st.warning("PDF 처리는 현재 구현 중입니다. 텍스트로 처리합니다.")
            result = data_workflow.process_sync(input_text)
        else:
            # 텍스트 처리
            result = data_workflow.process_sync(input_text)
        
        # 결과 상태 확인 (안전한 접근)
        result_status = result.get('status')
        if hasattr(result_status, 'value'):
            status_value = result_status.value
        else:
            status_value = str(result_status)
        
        if status_value == 'completed':
            st.session_state.markdown_result = result
            st.session_state.processing_status['markdown_completed'] = True
            progress_bar.progress(0.3)
            status_text.text("✅ Step 1: 마크다운 변환 완료")
            
            if extract_dp:
                # Step 2: DP 추출
                status_text.text("🔄 Step 2: DP 추출 중...")
                progress_bar.progress(0.5)
                
                dp_extractor = DPExtractor.create_default()
                dp_result = dp_extractor.extract_dps_with_metadata(
                    result['markdown_content'],
                    document_metadata={'source': input_method},
                    max_dps=3  # 테스트용 제한
                )
                
                st.session_state.dp_result = dp_result
                st.session_state.processing_status['dp_completed'] = True
                progress_bar.progress(0.6)
                status_text.text("✅ Step 2: DP 추출 완료")
                
                if validate_dp and dp_result['digital_phenotypes']:
                    # Step 3: DP 검증
                    status_text.text("🔄 Step 3: DP 검증 중...")
                    progress_bar.progress(0.7)
                    
                    # 검증 진행 상황 표시
                    validation_info = st.empty()
                    validation_info.info(f"검증 대상 DP: {len(dp_result['digital_phenotypes'])}개")
                    
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
                        similarity_threshold=0.7,
                        evidence_threshold=0.6,
                        final_threshold=0.65,
                        max_retries=2
                    )
                    
                    # DP 검증 실행 (올바른 메서드명과 반환값 처리)
                    final_dps, validation_results, validation_summary = dp_validator.validate_dps_with_selective_retry(
                        dp_objects, 
                        result['markdown_content']
                    )
                    
                    # 검증 결과를 세션에 저장할 형태로 변환
                    validation_result = {
                        'validated_dps': final_dps,
                        'validation_results': validation_results,
                        'validation_summary': validation_summary,
                        'validation_metadata': {
                            'total_dps': len(dp_objects),
                            'validated_count': len(final_dps),
                            'processing_time': validation_summary.get('total_processing_time', 0),
                            'auto_accepted_count': validation_summary.get('auto_accepted_count', 0),
                            'retry_count': validation_summary.get('retry_count', 0)
                        }
                    }
                    
                    st.session_state.validation_result = validation_result
                    st.session_state.processing_status['validation_completed'] = True
                    progress_bar.progress(0.8)
                    status_text.text("✅ Step 3: DP 검증 완료")
                    
                    if create_kg:
                        # Step 4: 지식그래프 생성
                        status_text.text("🔄 Step 4: 지식그래프 생성 중...")
                        progress_bar.progress(0.9)
                        
                        # final_dps는 이미 검증 과정에서 생성됨
                        if final_dps:
                            kg_workflow = KnowledgeGraphWorkflow()
                            
                            kg_options = {
                                'entity_confidence_threshold': entity_confidence,
                                'use_llm_triples': use_llm_triples
                            }
                            
                            kg_result = kg_workflow.process_sync(
                                final_dps,
                                result['markdown_content'], 
                                kg_options
                            )
                            
                            st.session_state.kg_result = kg_result
                            st.session_state.processing_status['kg_completed'] = True
                            progress_bar.progress(1.0)
                            status_text.text("✅ Step 4: 지식그래프 생성 완료")
                            
                            st.success("🎉 모든 처리가 완료되었습니다! '📊 결과 확인' 페이지에서 결과를 확인하세요.")
                        else:
                            st.warning("검증된 DP가 없어서 지식그래프 생성을 건너뜁니다.")
                else:
                    st.warning("DP 추출 결과가 없어서 검증을 건너뜁니다.")
            else:
                st.info("DP 추출이 비활성화되었습니다.")
        else:
            st.error("마크다운 변환에 실패했습니다.")
            
    except ImportError as e:
        st.error(f"모듈 import 오류: {str(e)}")
        st.info("필요한 패키지가 설치되지 않았을 수 있습니다. 설치 가이드를 확인해주세요.")
    except json.JSONDecodeError as e:
        st.error(f"JSON 형식 오류: {str(e)}")
        st.info("입력한 JSON 형식을 다시 확인해주세요.")
    except TypeError as e:
        if "unexpected keyword argument" in str(e):
            st.error(f"클래스 초기화 파라미터 오류: {str(e)}")
            st.info("클래스의 초기화 파라미터가 변경되었을 수 있습니다. 최신 문서를 확인해주세요.")
        else:
            st.error(f"타입 오류: {str(e)}")
            st.info("함수 호출 시 잘못된 타입의 인수가 전달되었습니다.")
    except AttributeError as e:
        st.error(f"속성 오류: {str(e)}")
        st.info("클래스 메서드 호출에 문제가 있습니다. 메서드명이나 속성명을 다시 확인해주세요.")
    except Exception as e:
        st.error(f"처리 중 오류가 발생했습니다: {str(e)}")
        import traceback
        st.text("상세 오류 정보:")
        st.code(traceback.format_exc())
        st.info("문제가 지속되면 관리자에게 문의하세요.")

def show_results_page():
    """결과 확인 페이지"""
    st.header("📊 처리 결과 확인")
    
    # 탭으로 각 단계별 결과 표시
    tab1, tab2, tab3, tab4 = st.tabs(["📄 마크다운", "🧬 DP 추출", "✅ DP 검증", "🌐 지식그래프"])
    
    with tab1:
        show_markdown_results()
    
    with tab2:
        show_dp_results()
    
    with tab3:
        show_validation_results()
    
    with tab4:
        show_kg_results()

def show_markdown_results():
    """마크다운 결과 표시"""
    if 'markdown_result' in st.session_state:
        result = st.session_state.markdown_result
        
        st.subheader("📄 마크다운 변환 결과")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("상태", result['status'].value.upper())
        with col2:
            st.metric("텍스트 길이", f"{len(result['markdown_content'])} 문자")
        
        with st.expander("📝 변환된 마크다운 내용", expanded=False):
            st.markdown(result['markdown_content'])
        
        with st.expander("🔍 원본 마크다운 텍스트 보기"):
            st.text(result['markdown_content'])
    else:
        st.info("아직 마크다운 변환이 완료되지 않았습니다.")

def show_dp_results():
    """DP 추출 결과 표시"""
    if 'dp_result' in st.session_state:
        dp_result = st.session_state.dp_result
        dps = dp_result['digital_phenotypes']
        
        st.subheader(f"🧬 DP 추출 결과 ({len(dps)}개)")
        
        if dps:
            # 통계 정보
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("총 DP 수", len(dps))
            with col2:
                processing_time = dp_result.get('extraction_metadata', {}).get('processing_time', 0)
                st.metric("처리 시간", f"{processing_time:.2f}초")
            with col3:
                llm_model = dp_result.get('extraction_metadata', {}).get('llm_model', 'Unknown')
                st.metric("LLM 모델", llm_model)
            
            # DP 상세 정보
            for i, dp in enumerate(dps):
                with st.expander(f"📋 DP {i+1}: {dp['label']}", expanded=i==0):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**기본 정보:**")
                        st.write(f"- **ID**: {dp['dp_id']}")
                        st.write(f"- **라벨**: {dp['label']}")
                        st.write(f"- **섹션**: {dp.get('section_reference', 'N/A')}")
                        if dp.get('confidence_score'):
                            st.write(f"- **신뢰도**: {dp['confidence_score']:.3f}")
                    
                    with col2:
                        st.write("**정의:**")
                        st.write(dp['definition'])
                        
                        if dp.get('metadata'):
                            st.write("**메타데이터:**")
                            st.json(dp['metadata'])
        else:
            st.info("추출된 DP가 없습니다.")
    else:
        st.info("아직 DP 추출이 완료되지 않았습니다.")

def show_validation_results():
    """DP 검증 결과 표시"""
    if 'validation_result' in st.session_state:
        validation_result = st.session_state.validation_result
        validated_dps = validation_result.get('validated_dps', [])
        validation_metadata = validation_result.get('validation_metadata', {})
        validation_summary = validation_result.get('validation_summary', {})
        
        st.subheader(f"✅ DP 검증 결과 ({len(validated_dps)}개)")
        
        if validated_dps:
            # 검증 통계
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("검증된 DP 수", len(validated_dps))
            with col2:
                processing_time = validation_metadata.get('processing_time', 0)
                st.metric("검증 시간", f"{processing_time:.2f}초")
            with col3:
                auto_accepted = validation_metadata.get('auto_accepted_count', 0)
                st.metric("자동 승인", f"{auto_accepted}개")
            with col4:
                retry_count = validation_metadata.get('retry_count', 0)
                st.metric("재시도 횟수", f"{retry_count}개")
            
            # 검증 요약 정보
            if validation_summary:
                with st.expander("📊 검증 요약 정보"):
                    st.json(validation_summary)
            
            # 검증된 DP 상세 정보
            for i, dp in enumerate(validated_dps):
                with st.expander(f"✅ 검증된 DP {i+1}: {dp.label}", expanded=i==0):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**기본 정보:**")
                        st.write(f"- **ID**: {dp.dp_id}")
                        st.write(f"- **라벨**: {dp.label}")
                        st.write(f"- **섹션**: {dp.section_reference or 'N/A'}")
                        if hasattr(dp, 'confidence_score') and dp.confidence_score:
                            st.write(f"- **신뢰도**: {dp.confidence_score:.3f}")
                    
                    with col2:
                        st.write("**정의:**")
                        st.write(dp.definition)
                        
                        if hasattr(dp, 'metadata') and dp.metadata:
                            st.write("**메타데이터:**")
                            st.json(dp.metadata)
            
            # 검증 결과 상세 정보 (validation_results가 있는 경우)
            validation_results = validation_result.get('validation_results', [])
            if validation_results:
                with st.expander("🔍 검증 상세 결과"):
                    for i, val_result in enumerate(validation_results):
                        if hasattr(val_result, 'dp') and hasattr(val_result, 'final_score'):
                            st.write(f"**{val_result.dp.label}**")
                            st.write(f"- 최종 점수: {val_result.final_score:.3f}")
                            st.write(f"- 통과 여부: {'✅' if val_result.passed else '❌'}")
                            if hasattr(val_result, 'validation_issues') and val_result.validation_issues:
                                st.write(f"- 검증 이슈: {', '.join(val_result.validation_issues)}")
                            st.markdown("---")
        else:
            st.info("검증된 DP가 없습니다.")
    else:
        st.info("아직 DP 검증이 완료되지 않았습니다.")

def show_kg_results():
    """지식그래프 결과 표시"""
    if 'kg_result' in st.session_state:
        kg_result = st.session_state.kg_result
        
        st.subheader("🌐 지식그래프 생성 결과")
        
        # 상태 표시
        status = kg_result.get('status', 'unknown')
        if hasattr(status, 'value'):
            status_value = status.value
        else:
            status_value = str(status)
        
        if status_value == 'completed':
            st.success("✅ 지식그래프 생성이 성공적으로 완료되었습니다!")
        else:
            st.warning(f"⚠️ 처리 상태: {status_value}")
        
        # Neo4j 그래프 구조 미리보기
        if kg_result.get('generated_triples'):
            from examples.streamlit_demo_modified import create_neo4j_friendly_graph
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
            
            # 상세 그래프 정보
            tab1, tab2, tab3, tab4 = st.tabs(["📍 노드", "🔗 관계", "📈 통계", "🔍 원본 트리플"])
            
            with tab1:
                st.markdown("**노드 정보 (상위 10개)**")
                nodes_preview = neo4j_preview["nodes"][:10]
                for node in nodes_preview:
                    with st.expander(f"🏷️ {node['id']} ({', '.join(node['labels'])})"):
                        st.json(node['properties'])
            
            with tab2:
                st.markdown("**관계 정보 (상위 10개)**")
                rels_preview = neo4j_preview["relationships"][:10]
                for i, rel in enumerate(rels_preview):
                    start = rel['start_node']
                    end = rel['end_node']
                    rel_type = rel['type']
                    props = rel['properties']
                    
                    st.markdown(f"**{i+1}. ({start}) -[{rel_type}]-> ({end})**")
                    st.json(props)
                    st.markdown("---")
            
            with tab3:
                st.markdown("**그래프 통계**")
                stats = neo4j_preview["statistics"]
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**노드 타입별 분포:**")
                    for node_type, count in stats["node_types"].items():
                        st.markdown(f"- {node_type}: {count}개")
                    
                    st.markdown("**어휘 분포:**")
                    for voca, count in stats.get("vocabulary_distribution", {}).items():
                        st.markdown(f"- {voca}: {count}개")
                
                with col2:
                    st.markdown("**관계 타입별 분포:**")
                    for rel_type, count in stats["relationship_types"].items():
                        st.markdown(f"- {rel_type}: {count}개")
                    
                    st.markdown("**전이성 분포:**")
                    trans_dist = stats.get("transitivity_distribution", {})
                    for trans, count in trans_dist.items():
                        st.markdown(f"- {trans}: {count}개")
            
            with tab4:
                st.markdown("**원본 트리플 (상위 20개)**")
                triples_data = []
                for triple in kg_result['generated_triples'][:20]:
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
        else:
            st.info("생성된 트리플이 없습니다.")
    else:
        st.info("아직 지식그래프 생성이 완료되지 않았습니다.")

def show_download_page():
    """파일 다운로드 페이지"""
    st.header("📥 파일 다운로드")
    
    st.markdown("""
    이 페이지에서는 처리된 결과를 다양한 형식으로 다운로드할 수 있습니다.
    **모든 다운로드 버튼을 사용할 수 있으며, 다운로드 후에도 페이지가 초기화되지 않습니다.**
    
    💡 **지원되는 입력 형식**: 텍스트, JSON, PDF, 파일 업로드
    """)
    
    # JSON 입력 예시 표시
    with st.expander("📝 JSON 입력 형식 예시"):
        st.code('''{
  "title": "의료 가이드라인 제목",
  "content": "가이드라인의 주요 내용",
  "sections": [
    {
      "title": "섹션 제목",
      "content": "섹션 내용"
    }
  ],
  "metadata": {
    "version": "1.0",
    "date": "2024-01-01"
  }
}''', language="json")
    
    # 다운로드 가능한 파일들을 섹션별로 구분
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📄 기본 결과 파일")
        
        # 마크다운 다운로드
        if 'markdown_result' in st.session_state:
            result = st.session_state.markdown_result
            st.download_button(
                label="📥 마크다운 파일 다운로드",
                data=result['markdown_content'],
                file_name=f"medical_guideline_{int(time.time())}.md",
                mime="text/markdown",
                key="download_markdown"
            )
        else:
            st.info("마크다운 변환이 완료되지 않았습니다.")
        
        # DP 결과 다운로드
        if 'dp_result' in st.session_state:
            dp_data = json.dumps(st.session_state.dp_result, ensure_ascii=False, indent=2, default=str)
            st.download_button(
                label="📥 DP 추출 결과 다운로드 (JSON)",
                data=dp_data,
                file_name=f"dp_extraction_{int(time.time())}.json",
                mime="application/json",
                key="download_dp"
            )
        else:
            st.info("DP 추출이 완료되지 않았습니다.")
        
        # 검증 결과 다운로드
        if 'validation_result' in st.session_state:
            validation_data = json.dumps(st.session_state.validation_result, ensure_ascii=False, indent=2, default=str)
            st.download_button(
                label="📥 DP 검증 결과 다운로드 (JSON)",
                data=validation_data,
                file_name=f"dp_validation_{int(time.time())}.json",
                mime="application/json",
                key="download_validation"
            )
        else:
            st.info("DP 검증이 완료되지 않았습니다.")
    
    with col2:
        st.subheader("🌐 지식그래프 파일")
        
        if 'kg_result' in st.session_state:
            kg_result = st.session_state.kg_result
            
            # RDF 트리플 다운로드
            triple_generation_result = kg_result.get('triple_generation_result', {})
            rdf_graph = triple_generation_result.get('rdf_graph', {})
            
            if rdf_graph and rdf_graph.get('turtle'):
                st.download_button(
                    label="📥 RDF 트리플 다운로드 (Turtle)",
                    data=rdf_graph['turtle'],
                    file_name=f"knowledge_graph_{int(time.time())}.ttl",
                    mime="text/turtle",
                    key="download_rdf"
                )
            
            # Neo4j 그래프 구조 다운로드
            try:
                from examples.streamlit_demo_modified import create_neo4j_friendly_graph, generate_cypher_queries
                
                neo4j_graph_data = create_neo4j_friendly_graph(kg_result)
                neo4j_json = json.dumps(neo4j_graph_data, ensure_ascii=False, indent=2, default=str)
                st.download_button(
                    label="📥 Neo4j 그래프 구조 다운로드 (JSON)",
                    data=neo4j_json,
                    file_name=f"neo4j_graph_{int(time.time())}.json",
                    mime="application/json",
                    key="download_neo4j_json"
                )
                
                # Cypher 쿼리 다운로드
                cypher_queries = generate_cypher_queries(kg_result)
                st.download_button(
                    label="📥 Neo4j Cypher 쿼리 다운로드",
                    data=cypher_queries,
                    file_name=f"neo4j_queries_{int(time.time())}.cypher",
                    mime="text/plain",
                    key="download_cypher"
                )
                
                # 전체 결과 다운로드
                complete_result = {
                    "timestamp": int(time.time()),
                    "markdown_result": st.session_state.get('markdown_result', {}),
                    "dp_result": st.session_state.get('dp_result', {}),
                    "validation_result": st.session_state.get('validation_result', {}),
                    "kg_result": kg_result,
                    "neo4j_graph": neo4j_graph_data
                }
                
                complete_json = json.dumps(complete_result, ensure_ascii=False, indent=2, default=str)
                st.download_button(
                    label="📥 전체 처리 결과 다운로드 (JSON)",
                    data=complete_json,
                    file_name=f"complete_result_{int(time.time())}.json",
                    mime="application/json",
                    key="download_complete"
                )
                
            except ImportError:
                st.error("Neo4j 변환 함수를 가져올 수 없습니다.")
        else:
            st.info("지식그래프 생성이 완료되지 않았습니다.")
    
    # 다운로드 가이드
    st.markdown("---")
    st.subheader("📖 다운로드 파일 설명")
    
    with st.expander("📋 각 파일의 용도"):
        st.markdown("""
        **📄 기본 결과 파일:**
        - **마크다운 파일**: 원본 텍스트를 마크다운으로 변환한 결과
        - **DP 추출 결과**: 추출된 디지털 표현형(Digital Phenotype) 정보
        - **DP 검증 결과**: 검증 과정을 거친 최종 DP 정보
        
        **🌐 지식그래프 파일:**
        - **RDF 트리플**: 표준 RDF 형식의 지식그래프 (Turtle 형식)
        - **Neo4j 그래프 구조**: Neo4j 데이터베이스에 적합한 JSON 형식
        - **Neo4j Cypher 쿼리**: Neo4j에서 바로 실행 가능한 Cypher 명령어
        - **전체 처리 결과**: 모든 단계의 결과를 포함한 완전한 데이터
        """)

if __name__ == "__main__":
    main() 