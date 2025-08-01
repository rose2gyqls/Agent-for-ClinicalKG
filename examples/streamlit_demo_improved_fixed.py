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
    st.markdown("**PDF/텍스트/JSON → 마크다운 → DP 추출 → 검증 → 지식그래프 생성**")
    
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
                    # Step 3: DP 검증 (재추출 기능 포함)
                    status_text.text("🔄 Step 3: DP 검증 및 재추출 중...")
                    progress_bar.progress(0.7)
                    
                    # 검증 진행 상황 표시
                    validation_info = st.empty()
                    validation_info.info(f"검증 대상 DP: {len(dp_result['digital_phenotypes'])}개 (재추출 최대 1회)")
                    
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
                    
                    # ✅ 재추출용 DP Extractor 생성 (핵심 추가)
                    # 기존에 이미 import된 DPExtractor 사용
                    try:
                        dp_extractor_for_retry = DPExtractor.create_default()
                        print("✅ 재추출용 DP Extractor 생성 완료")
                    except Exception as e:
                        print(f"⚠️ 재추출용 DP Extractor 생성 실패: {str(e)}")
                        dp_extractor_for_retry = None
                    
                    # 검증 실행 (재추출 기능 활성화)
                    dp_validator = TwoTrackDPValidator(
                        similarity_threshold=0.7,
                        evidence_threshold=0.6,
                        final_threshold=0.65,
                        max_retries=1  # 최대 1회 재추출 시도
                    )
                    
                    # 상세 진행 상황 표시를 위한 콜백 함수
                    validation_progress_container = st.empty()
                    retry_info_container = st.empty()
                    
                    def validation_progress_callback(progress):
                        """검증 진행 상황 콜백"""
                        percentage = progress.progress_percentage
                        current_step = progress.current_step
                        
                        validation_progress_container.info(
                            f"진행 상황: {percentage:.1f}% - {current_step}"
                        )
                    
                    # ✅ DP 검증 및 재추출 실행 (dp_extractor 파라미터 추가)
                    if dp_extractor_for_retry:
                        final_dps, validation_results, validation_summary = dp_validator.validate_dps_with_selective_retry(
                            dp_objects, 
                            result['markdown_content'],
                            dp_extractor=dp_extractor_for_retry  # 🔑 재추출 기능 활성화
                        )
                    else:
                        # 재추출 기능 없이 기본 검증만 실행
                        st.warning("⚠️ 재추출 기능이 비활성화되었습니다. 기본 검증만 실행합니다.")
                        final_dps, validation_results, validation_summary = dp_validator.validate_dps_with_selective_retry(
                            dp_objects, 
                            result['markdown_content']
                        )
                    
                    # 재추출 결과 분석 및 표시
                    retry_history = validation_summary.get('retry_history', [])
                    total_retries = len(retry_history)
                    
                    if total_retries > 0:
                        retry_info_container.success(
                            f"🔄 재추출 완료: {total_retries}개 DP 재생성됨"
                        )
                        
                        # 재추출 상세 정보
                        with st.expander("🔍 재추출 상세 정보"):
                            for retry in retry_history:
                                st.write(f"**원본 DP**: {retry['original_dp_id']}")
                                st.write(f"**재생성 DP**: {retry['new_dp_id']}")
                                st.write(f"**재시도 횟수**: {retry['retry_count']}")
                                if retry.get('issues'):
                                    st.write(f"**검증 이슈**: {', '.join(retry['issues'])}")
                                st.markdown("---")
                    else:
                        retry_info_container.info("ℹ️ 모든 DP가 첫 번째 검증에서 통과했습니다.")
                    
                    # 검증 결과를 세션에 저장할 형태로 변환
                    validation_result = {
                        'validated_dps': final_dps,
                        'validation_results': validation_results,
                        'validation_summary': validation_summary,
                        'validation_metadata': {
                            'total_dps': len(dp_objects),
                            'validated_count': len(final_dps),
                            'processing_time': validation_summary.get('processing_time', 0),
                            'retry_count': total_retries,
                            'success_rate': validation_summary.get('success_rate', 0),
                            'retry_history': retry_history
                        }
                    }
                    
                    st.session_state.validation_result = validation_result
                    st.session_state.processing_status['validation_completed'] = True
                    progress_bar.progress(0.8)
                    
                    # 최종 결과 표시
                    initial_count = len(dp_objects)
                    final_count = len(final_dps)
                    success_rate = validation_summary.get('success_rate', 0)
                    
                    status_text.text("✅ Step 3: DP 검증 및 재추출 완료")
                    validation_info.success(
                        f"검증 완료: {initial_count}개 → {final_count}개 (성공률: {success_rate:.1%}, 재추출: {total_retries}회)"
                    )
                    
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
        if "DPExtractor" in str(e):
            st.error(f"DP 추출기 생성 오류: {str(e)}")
            st.info("DP 추출기 초기화에 문제가 있습니다. 재추출 기능이 비활성화될 수 있습니다.")
        elif "validate_dps_with_selective_retry" in str(e):
            st.error(f"DP 검증 및 재추출 오류: {str(e)}")
            st.info("DP 검증 과정에서 재추출 중 문제가 발생했습니다. 기본 검증만 실행됩니다.")
        else:
            st.error(f"속성 오류: {str(e)}")
            st.info("클래스 메서드 호출에 문제가 있습니다. 메서드명이나 속성명을 다시 확인해주세요.")
    except UnboundLocalError as e:
        if "DPExtractor" in str(e):
            st.error(f"DPExtractor 변수 스코프 오류: {str(e)}")
            st.info("DPExtractor 변수 접근에 문제가 있습니다. 재추출 기능이 비활성화될 수 있습니다.")
        else:
            st.error(f"변수 스코프 오류: {str(e)}")
            st.info("변수 접근에 문제가 있습니다. 코드를 다시 확인해주세요.")
    except Exception as e:
        st.error(f"처리 중 오류가 발생했습니다: {str(e)}")
        
        # 재추출 관련 오류인지 확인
        if "re_extract" in str(e).lower() or "retry" in str(e).lower():
            st.warning("🔄 재추출 과정에서 오류가 발생했습니다. 기본 검증 결과를 사용합니다.")
            st.info("• re_extract_dp.txt 프롬프트 파일을 확인해주세요.")
            st.info("• LLM 응답 형식에 문제가 있을 수 있습니다.")
        
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
            result_status = result.get('status')
            if hasattr(result_status, 'value'):
                status_value = result_status.value
            else:
                status_value = str(result_status)
            st.metric("상태", status_value.upper())
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
            # 검증 통계 (재추출 정보 포함)
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("검증된 DP 수", len(validated_dps))
            with col2:
                processing_time = validation_metadata.get('processing_time', 0)
                st.metric("검증 시간", f"{processing_time:.2f}초")
            with col3:
                success_rate = validation_metadata.get('success_rate', 0)
                st.metric("성공률", f"{success_rate:.1%}")
            with col4:
                retry_count = validation_metadata.get('retry_count', 0)
                st.metric("재추출 횟수", f"{retry_count}개")
            with col5:
                total_dps = validation_metadata.get('total_dps', 0)
                st.metric("초기 DP 수", f"{total_dps}개")
            
            # 🆕 재추출 상세 정보 (새로 추가)
            retry_history = validation_metadata.get('retry_history', [])
            if retry_history:
                with st.expander("🔄 재추출 상세 정보", expanded=False):
                    st.markdown("**`re_extract_dp.txt` 프롬프트를 사용하여 재추출된 DP들:**")
                    
                    for i, retry in enumerate(retry_history):
                        st.markdown(f"### 재추출 {i+1}")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**원본 DP 정보:**")
                            st.write(f"- ID: `{retry['original_dp_id']}`")
                            st.write(f"- 재시도 횟수: {retry['retry_count']}회")
                            
                            if retry.get('issues'):
                                st.write("**검증 실패 이슈:**")
                                for issue in retry['issues']:
                                    st.write(f"- {issue}")
                        
                        with col2:
                            st.write("**재생성된 DP:**")
                            st.write(f"- 새 ID: `{retry['new_dp_id']}`")
                            st.success("✅ 재추출 성공")
                        
                        st.markdown("---")
            else:
                st.info("ℹ️ 모든 DP가 첫 번째 검증에서 통과하여 재추출이 필요하지 않았습니다.")
            
            # 검증 요약 정보
            if validation_summary:
                with st.expander("📊 검증 요약 정보"):
                    # 재추출 관련 통계 하이라이트
                    summary_with_highlight = validation_summary.copy()
                    if 'retry_history' in summary_with_highlight:
                        del summary_with_highlight['retry_history']  # 중복 제거
                    
                    st.json(summary_with_highlight)
            
            # 검증된 DP 상세 정보
            for i, dp in enumerate(validated_dps):
                # 재추출된 DP인지 확인
                is_retry_dp = dp.dp_id.startswith('RETRY_')
                dp_title = f"✅ 검증된 DP {i+1}: {dp.label}"
                
                if is_retry_dp:
                    dp_title += " 🔄 (재추출됨)"
                
                with st.expander(dp_title, expanded=i==0):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**기본 정보:**")
                        st.write(f"- **ID**: {dp.dp_id}")
                        st.write(f"- **라벨**: {dp.label}")
                        st.write(f"- **섹션**: {dp.section_reference or 'N/A'}")
                        if hasattr(dp, 'confidence_score') and dp.confidence_score:
                            st.write(f"- **신뢰도**: {dp.confidence_score:.3f}")
                        
                        # 재추출 정보 표시
                        if is_retry_dp and hasattr(dp, 'metadata') and dp.metadata:
                            st.write("**재추출 정보:**")
                            if 'retry_from' in dp.metadata:
                                st.write(f"- 원본 DP: `{dp.metadata['retry_from']}`")
                            if 'retry_reason' in dp.metadata:
                                st.write(f"- 재추출 이유: {dp.metadata['retry_reason']}")
                            if 'retry_confidence' in dp.metadata:
                                st.write(f"- 재추출 신뢰도: {dp.metadata['retry_confidence']}")
                    
                    with col2:
                        st.write("**정의:**")
                        st.write(dp.definition)
                        
                        # 재추출된 DP의 텍스트 증거 표시
                        if is_retry_dp and hasattr(dp, 'metadata') and dp.metadata:
                            if 'text_evidence' in dp.metadata and dp.metadata['text_evidence']:
                                st.write("**텍스트 증거 (재추출):**")
                                st.info(dp.metadata['text_evidence'])
                        
                        if hasattr(dp, 'metadata') and dp.metadata and not is_retry_dp:
                            st.write("**메타데이터:**")
                            st.json(dp.metadata)
            
            # 검증 결과 상세 정보 (validation_results가 있는 경우)
            validation_results = validation_result.get('validation_results', [])
            if validation_results:
                with st.expander("🔍 검증 상세 결과"):
                    for i, val_result in enumerate(validation_results):
                        if hasattr(val_result, 'dp') and hasattr(val_result, 'final_score'):
                            # 재추출된 DP 여부 확인
                            is_retry_result = val_result.dp.dp_id.startswith('RETRY_')
                            status_emoji = "🔄" if is_retry_result else "📋"
                            
                            st.write(f"**{status_emoji} {val_result.dp.label}**")
                            st.write(f"- 최종 점수: {val_result.final_score:.3f}")
                            st.write(f"- 통과 여부: {'✅' if val_result.passed else '❌'}")
                            if hasattr(val_result, 'validation_issues') and val_result.validation_issues:
                                st.write(f"- 검증 이슈: {', '.join(val_result.validation_issues)}")
                            if is_retry_result:
                                st.info("🔄 이 DP는 재추출을 통해 생성되었습니다.")
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
            try:
                # Neo4j 변환 함수 직접 호출 (import 오류 해결)
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
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["📍 노드", "🔗 관계", "📈 통계", "🔍 원본 트리플", "🧬 엔티티"])
                
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
                
                with tab5:
                    st.markdown("**추출된 엔티티 (상위 20개)**")
                    entities = kg_result.get('extracted_entities', [])
                    if entities:
                        entities_data = []
                        for entity in entities[:20]:
                            entity_name = entity.get('entity_name', '') if isinstance(entity, dict) else getattr(entity, 'entity_name', '')
                            entity_type = entity.get('entity_type', '') if isinstance(entity, dict) else getattr(entity, 'entity_type', '')
                            confidence = entity.get('confidence', 0.0) if isinstance(entity, dict) else getattr(entity, 'confidence', 0.0)
                            
                            if isinstance(entity_type, object) and hasattr(entity_type, 'value'):
                                entity_type = entity_type.value
                            
                            entities_data.append({
                                'Entity Name': entity_name,
                                'Entity Type': str(entity_type),
                                'Confidence': f"{float(confidence):.3f}"
                            })
                        
                        if entities_data:
                            import pandas as pd
                            df = pd.DataFrame(entities_data)
                            st.dataframe(df, use_container_width=True)
                    else:
                        st.info("추출된 엔티티가 없습니다.")
                        
            except Exception as e:
                st.error(f"Neo4j 변환 중 오류가 발생했습니다: {str(e)}")
                import traceback
                st.text("상세 오류 정보:")
                st.code(traceback.format_exc())
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
            
            # 🆕 엔티티 추출 결과 다운로드 (새로 추가)
            if kg_result.get('extracted_entities'):
                try:
                    entities_json_data = create_entities_json(kg_result)
                    entities_json = json.dumps(entities_json_data, ensure_ascii=False, indent=2, default=str)
                    st.download_button(
                        label="📥 엔티티 추출 결과 다운로드 (JSON)",
                        data=entities_json,
                        file_name=f"entities_{int(time.time())}.json",
                        mime="application/json",
                        key="download_entities"
                    )
                except Exception as e:
                    st.error(f"엔티티 JSON 생성 오류: {str(e)}")
            
            # 🆕 트리플 JSON 다운로드 (Turtle 대신 JSON으로)
            if kg_result.get('generated_triples'):
                try:
                    triples_json_data = create_triples_json(kg_result)
                    triples_json = json.dumps(triples_json_data, ensure_ascii=False, indent=2, default=str)
                    st.download_button(
                        label="📥 트리플 결과 다운로드 (JSON)",
                        data=triples_json,
                        file_name=f"triples_{int(time.time())}.json",
                        mime="application/json",
                        key="download_triples_json"
                    )
                except Exception as e:
                    st.error(f"트리플 JSON 생성 오류: {str(e)}")
            
            # RDF 트리플 다운로드 (기존 유지 - 만약 turtle이 있다면)
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
            
            # Neo4j 그래프 구조 다운로드 (import 오류 해결)
            try:
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
                    "neo4j_graph": neo4j_graph_data,
                    "entities_json": create_entities_json(kg_result) if kg_result.get('extracted_entities') else {},
                    "triples_json": create_triples_json(kg_result) if kg_result.get('generated_triples') else {}
                }
                
                complete_json = json.dumps(complete_result, ensure_ascii=False, indent=2, default=str)
                st.download_button(
                    label="📥 전체 처리 결과 다운로드 (JSON)",
                    data=complete_json,
                    file_name=f"complete_result_{int(time.time())}.json",
                    mime="application/json",
                    key="download_complete"
                )
                
            except Exception as e:
                st.error(f"Neo4j 변환 중 오류가 발생했습니다: {str(e)}")
                import traceback
                st.text("상세 오류 정보:")
                st.code(traceback.format_exc())
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
        - **DP 검증 결과**: 검증 과정을 거친 최종 DP 정보 (재추출 내역 포함)
        
        **🌐 지식그래프 파일:**
        - **🆕 엔티티 추출 결과 (JSON)**: 텍스트에서 추출된 의료 엔티티들의 상세 정보
        - **🆕 트리플 결과 (JSON)**: Subject-Predicate-Object 형태의 지식 관계들
        - **RDF 트리플**: 표준 RDF 형식의 지식그래프 (Turtle 형식)
        - **Neo4j 그래프 구조**: Neo4j 데이터베이스에 적합한 JSON 형식
        - **Neo4j Cypher 쿼리**: Neo4j에서 바로 실행 가능한 Cypher 명령어
        - **전체 처리 결과**: 모든 단계의 결과를 포함한 완전한 데이터
        
        **🔧 새로 추가된 기능:**
        - ✅ **엔티티 JSON**: 추출된 엔티티들을 JSON 형식으로 다운로드
        - ✅ **트리플 JSON**: Turtle 대신 JSON 형식으로 트리플 다운로드
        - ✅ **Neo4j Import 오류 해결**: 외부 함수 의존성 제거
        - ✅ **🆕 DP 재추출 기능**: `re_extract_dp.txt` 프롬프트 사용 자동 재추출
        """)
    
    # 다운로드 팁
    with st.expander("💡 다운로드 팁"):
        st.markdown("""
        **다운로드 순서 권장:**
        1. 마크다운 파일 → 변환된 원본 내용 확인
        2. DP 추출/검증 결과 → 추출된 지식 구조 확인 (재추출 내역 포함)
        3. 엔티티 JSON → 개별 의료 엔티티 정보 분석
        4. 트리플 JSON → 지식 관계 구조 분석
        5. Neo4j 파일들 → 그래프 데이터베이스 구축용
        6. 전체 결과 → 완전한 백업 및 재현용
        
        **파일 형식별 활용:**
        - **JSON 파일**: Python/JavaScript 등에서 프로그래밍 처리
        - **Cypher 파일**: Neo4j 데이터베이스에 직접 실행
        - **Turtle 파일**: RDF 표준 도구들에서 활용
        
        **🔄 DP 재추출 기능:**
        - 검증에 실패한 DP들은 `re_extract_dp.txt` 프롬프트로 자동 재추출
        - 최대 2회까지 재시도하여 더 정확한 DP 생성
        - 재추출 내역은 DP 검증 결과 파일에 상세히 기록됨
        """)
    
    # 성능 정보 (재추출 통계 포함)
    if 'kg_result' in st.session_state:
        kg_result = st.session_state.kg_result
        entities_count = len(kg_result.get('extracted_entities', []))
        triples_count = len(kg_result.get('generated_triples', []))
        
        # 재추출 통계 추가
        validation_result = st.session_state.get('validation_result', {})
        retry_count = validation_result.get('validation_metadata', {}).get('retry_count', 0)
        success_rate = validation_result.get('validation_metadata', {}).get('success_rate', 0)
        
        with st.expander("📊 생성된 데이터 요약"):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("추출된 엔티티", f"{entities_count}개")
            with col2:
                st.metric("생성된 트리플", f"{triples_count}개")
            with col3:
                st.metric("DP 재추출", f"{retry_count}회")
            with col4:
                # Neo4j 변환 통계
                try:
                    neo4j_stats = create_neo4j_friendly_graph(kg_result)["statistics"]
                    st.metric("Neo4j 노드", f"{neo4j_stats['total_nodes']}개")
                except:
                    st.metric("검증 성공률", f"{success_rate:.1%}")

# ========================================
# Neo4j 변환 함수들 (Import 오류 해결)
# ========================================

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
        entity_name = entity.get('entity_name', '') if isinstance(entity, dict) else getattr(entity, 'entity_name', '')
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
        voca_id = node["properties"]["voca_id"]
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


def create_triples_json(kg_result):
    """트리플을 JSON 형식으로 변환"""
    triples_data = []
    
    triples = kg_result.get('generated_triples', [])
    for i, triple in enumerate(triples):
        subject = triple.subject if hasattr(triple, 'subject') else triple.get('subject', '')
        predicate = triple.predicate if hasattr(triple, 'predicate') else triple.get('predicate', '')
        object_val = triple.object if hasattr(triple, 'object') else triple.get('object', '')
        confidence = triple.confidence if hasattr(triple, 'confidence') else triple.get('confidence', 0.0)
        triple_type = triple.triple_type if hasattr(triple, 'triple_type') else triple.get('triple_type', '')
        metadata = triple.metadata if hasattr(triple, 'metadata') else triple.get('metadata', {})
        
        if isinstance(triple_type, object) and hasattr(triple_type, 'value'):
            triple_type = triple_type.value
        
        triple_data = {
            "id": f"triple_{i+1}",
            "subject": subject,
            "predicate": predicate,
            "object": object_val,
            "confidence": float(confidence),
            "triple_type": str(triple_type),
            "metadata": metadata,
            "properties": {
                "subject_display": extract_display_name(subject),
                "predicate_display": extract_relation_name(predicate),
                "object_display": extract_display_name(object_val),
                "is_literal": is_literal_value(object_val),
                "relation_source": determine_rela_source(predicate, metadata),
                "transitivity": determine_transitivity(confidence, metadata)
            }
        }
        
        triples_data.append(triple_data)
    
    return {
        "graph_info": {
            "description": "의료 가이드라인에서 추출된 트리플 JSON",
            "extraction_timestamp": int(time.time()),
            "format": "JSON Triple Format",
            "total_triples": len(triples_data)
        },
        "triples": triples_data,
        "statistics": {
            "total_count": len(triples_data),
            "confidence_distribution": {
                "high_confidence": len([t for t in triples_data if t["confidence"] >= 0.8]),
                "medium_confidence": len([t for t in triples_data if 0.5 <= t["confidence"] < 0.8]),
                "low_confidence": len([t for t in triples_data if t["confidence"] < 0.5])
            },
            "transitivity_distribution": {
                "direct": len([t for t in triples_data if t["properties"]["transitivity"] == "DIRECT"]),
                "indirect": len([t for t in triples_data if t["properties"]["transitivity"] == "INDIRECT"])
            }
        }
    }


def create_entities_json(kg_result):
    """엔티티 추출 결과를 JSON 형식으로 변환"""
    entities_data = []
    
    entities = kg_result.get('extracted_entities', [])
    for i, entity in enumerate(entities):
        entity_name = entity.get('entity_name', '') if isinstance(entity, dict) else getattr(entity, 'entity_name', '')
        entity_type = entity.get('entity_type', '') if isinstance(entity, dict) else getattr(entity, 'entity_type', '')
        confidence = entity.get('confidence', 0.0) if isinstance(entity, dict) else getattr(entity, 'confidence', 0.0)
        metadata = entity.get('metadata', {}) if isinstance(entity, dict) else getattr(entity, 'metadata', {})
        
        if isinstance(entity_type, object) and hasattr(entity_type, 'value'):
            entity_type = entity_type.value
        
        source_code, concept_id = extract_code_and_concept_id(entity_name, metadata)
        vocabulary_id = map_entity_type_to_vocabulary(entity_type)
        
        entity_data = {
            "id": f"entity_{i+1}",
            "entity_name": entity_name,
            "entity_type": str(entity_type),
            "confidence": float(confidence),
            "metadata": metadata,
            "properties": {
                "source_code": source_code,
                "concept_id": concept_id,
                "vocabulary_id": vocabulary_id,
                "display_name": extract_display_name(entity_name)
            }
        }
        
        entities_data.append(entity_data)
    
    # 통계 계산
    entity_type_distribution = {}
    vocabulary_distribution = {}
    
    for entity in entities_data:
        # 엔티티 타입별 분포
        entity_type = entity["entity_type"]
        entity_type_distribution[entity_type] = entity_type_distribution.get(entity_type, 0) + 1
        
        # 어휘별 분포
        vocabulary_id = entity["properties"]["vocabulary_id"]
        vocabulary_distribution[vocabulary_id] = vocabulary_distribution.get(vocabulary_id, 0) + 1
    
    return {
        "extraction_info": {
            "description": "의료 가이드라인에서 추출된 엔티티 JSON",
            "extraction_timestamp": int(time.time()),
            "format": "JSON Entity Format",
            "total_entities": len(entities_data)
        },
        "entities": entities_data,
        "statistics": {
            "total_count": len(entities_data),
            "entity_type_distribution": entity_type_distribution,
            "vocabulary_distribution": vocabulary_distribution,
            "confidence_distribution": {
                "high_confidence": len([e for e in entities_data if e["confidence"] >= 0.8]),
                "medium_confidence": len([e for e in entities_data if 0.5 <= e["confidence"] < 0.8]),
                "low_confidence": len([e for e in entities_data if e["confidence"] < 0.5])
            }
        }
    }

if __name__ == "__main__":
    main() 