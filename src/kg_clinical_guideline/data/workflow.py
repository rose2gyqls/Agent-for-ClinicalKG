"""
LangGraph workflow for data processing.
"""

from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END

from .state import DataProcessingState, InputType, ProcessingStatus
from .input_detector import detect_and_prepare_state
from .processors import (
    PDFProcessor, S3JsonProcessor, JsonProcessor, 
    TextProcessor, URLProcessor
)
from .markdown_converter import MarkdownConverter


class DataProcessingWorkflow:
    """데이터 처리 LangGraph 워크플로우"""
    
    def __init__(self, processing_options: Dict[str, Any] = None):
        """
        워크플로우 초기화
        
        Args:
            processing_options: 처리 옵션
        """
        self.processing_options = processing_options or {}
        
        # 프로세서 초기화
        self.processors = {
            InputType.PDF: PDFProcessor(processing_options),
            InputType.S3_JSON: S3JsonProcessor(processing_options),
            InputType.LOCAL_JSON: JsonProcessor(processing_options),
            InputType.TEXT: TextProcessor(processing_options),
            InputType.URL: URLProcessor(processing_options)
        }
        
        self.markdown_converter = MarkdownConverter(processing_options)
        
        # 워크플로우 그래프 구축
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """LangGraph 워크플로우 구축"""
        
        # StateGraph 생성
        workflow = StateGraph(DataProcessingState)
        
        # 노드 추가
        workflow.add_node("detect_input", self._detect_input_node)
        workflow.add_node("process_data", self._process_data_node)
        workflow.add_node("convert_to_markdown", self._convert_to_markdown_node)
        workflow.add_node("finalize", self._finalize_node)
        workflow.add_node("handle_error", self._handle_error_node)
        
        # 엣지 정의
        workflow.set_entry_point("detect_input")
        
        workflow.add_conditional_edges(
            "detect_input",
            self._should_continue_after_detection,
            {
                "process": "process_data",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "process_data", 
            self._should_continue_after_processing,
            {
                "convert": "convert_to_markdown",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "convert_to_markdown",
            self._should_continue_after_conversion,
            {
                "finalize": "finalize",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("finalize", END)
        workflow.add_edge("handle_error", END)
        
        return workflow.compile()
    
    def _detect_input_node(self, state: DataProcessingState) -> DataProcessingState:
        """입력 감지 노드"""
        try:
            # 입력 타입이 이미 감지되지 않은 경우에만 감지
            if not state.get('input_type'):
                from .input_detector import InputDetector
                input_type = InputDetector.detect_input_type(state['input_data'])
                state['input_type'] = input_type
            
            state['current_step'] = "input_detected"
            state['progress'] = 0.1
            
            # 입력 타입에 따른 추가 정보 설정
            if state['input_type'] == InputType.S3_JSON:
                from .input_detector import InputDetector
                s3_info = InputDetector.extract_s3_info(str(state['input_data']))
                state.update({
                    's3_bucket': s3_info['bucket'],
                    's3_key': s3_info['key'],
                    'aws_region': s3_info['region']
                })
            
        except Exception as e:
            state['errors'].append(f"입력 감지 중 오류: {str(e)}")
            state['status'] = ProcessingStatus.FAILED
        
        return state
    
    def _process_data_node(self, state: DataProcessingState) -> DataProcessingState:
        """데이터 처리 노드"""
        try:
            input_type = state['input_type']
            
            if input_type == InputType.UNKNOWN:
                state['errors'].append("지원하지 않는 입력 타입입니다.")
                state['status'] = ProcessingStatus.FAILED
                return state
            
            # 해당 타입의 프로세서로 처리
            if input_type in self.processors:
                processor = self.processors[input_type]
                state = processor.process(state)
            else:
                state['errors'].append(f"'{input_type.value}' 타입의 프로세서를 찾을 수 없습니다.")
                state['status'] = ProcessingStatus.FAILED
            
        except Exception as e:
            state['errors'].append(f"데이터 처리 중 오류: {str(e)}")
            state['status'] = ProcessingStatus.FAILED
        
        return state
    
    def _convert_to_markdown_node(self, state: DataProcessingState) -> DataProcessingState:
        """마크다운 변환 노드"""
        try:
            if not state.get('processed_content'):
                state['errors'].append("변환할 처리된 콘텐츠가 없습니다.")
                state['status'] = ProcessingStatus.FAILED
                return state
            
            # 마크다운으로 변환
            markdown_content = self.markdown_converter.convert(state['processed_content'])
            state['markdown_content'] = markdown_content
            
            state['current_step'] = "markdown_converted"
            state['progress'] = 0.9
            
        except Exception as e:
            state['errors'].append(f"마크다운 변환 중 오류: {str(e)}")
            state['status'] = ProcessingStatus.FAILED
        
        return state
    
    def _finalize_node(self, state: DataProcessingState) -> DataProcessingState:
        """최종화 노드"""
        try:
            state['status'] = ProcessingStatus.COMPLETED
            state['current_step'] = "completed"
            state['progress'] = 1.0
            
            # 최종 검증
            if not state.get('markdown_content'):
                state['warnings'].append("마크다운 콘텐츠가 생성되지 않았습니다.")
            
        except Exception as e:
            state['errors'].append(f"최종화 중 오류: {str(e)}")
            state['status'] = ProcessingStatus.FAILED
        
        return state
    
    def _handle_error_node(self, state: DataProcessingState) -> DataProcessingState:
        """에러 처리 노드"""
        state['status'] = ProcessingStatus.FAILED
        state['current_step'] = "error"
        
        # 에러 요약 생성
        if state['errors']:
            error_summary = f"총 {len(state['errors'])}개의 오류가 발생했습니다: " + "; ".join(state['errors'][-3:])
            state['errors'].append(error_summary)
        
        return state
    
    def _should_continue_after_detection(self, state: DataProcessingState) -> str:
        """입력 감지 후 다음 단계 결정"""
        if state['errors'] or state['status'] == ProcessingStatus.FAILED:
            return "error"
        return "process"
    
    def _should_continue_after_processing(self, state: DataProcessingState) -> str:
        """데이터 처리 후 다음 단계 결정"""
        if state['errors'] or state['status'] == ProcessingStatus.FAILED:
            return "error"
        return "convert"
    
    def _should_continue_after_conversion(self, state: DataProcessingState) -> str:
        """마크다운 변환 후 다음 단계 결정"""
        if state['errors'] or state['status'] == ProcessingStatus.FAILED:
            return "error"
        return "finalize"
    
    async def process(self, input_data, processing_options: Dict[str, Any] = None) -> DataProcessingState:
        """
        비동기 데이터 처리 실행
        
        Args:
            input_data: 입력 데이터
            processing_options: 처리 옵션
            
        Returns:
            DataProcessingState: 최종 처리 결과
        """
        # 초기 상태 생성
        initial_state = detect_and_prepare_state(
            input_data, 
            processing_options or self.processing_options
        )
        
        # 워크플로우 실행
        final_state = await self.workflow.ainvoke(initial_state)
        
        return final_state
    
    def process_sync(self, input_data, processing_options: Dict[str, Any] = None) -> DataProcessingState:
        """
        동기 데이터 처리 실행
        
        Args:
            input_data: 입력 데이터
            processing_options: 처리 옵션
            
        Returns:
            DataProcessingState: 최종 처리 결과
        """
        # 초기 상태 생성
        initial_state = detect_and_prepare_state(
            input_data, 
            processing_options or self.processing_options
        )
        
        # 워크플로우 실행
        final_state = self.workflow.invoke(initial_state)
        
        return final_state
    
    def get_supported_input_types(self) -> list:
        """지원되는 입력 타입 목록 반환"""
        return [input_type.value for input_type in self.processors.keys()]
    
    def get_workflow_info(self) -> Dict[str, Any]:
        """워크플로우 정보 반환"""
        return {
            "supported_input_types": self.get_supported_input_types(),
            "processing_steps": [
                "detect_input",
                "process_data", 
                "convert_to_markdown",
                "finalize"
            ],
            "options": self.processing_options
        }
