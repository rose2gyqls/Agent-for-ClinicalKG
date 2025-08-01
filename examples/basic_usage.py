"""
KG Clinical Guideline 기본 사용법 예제
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from kg_clinical_guideline.data import DataProcessingWorkflow


def example_text_processing():
    """텍스트 처리 예제"""
    print("=== 텍스트 처리 예제 ===")
    
    # 의료 가이드라인 텍스트 예제
    sample_text = """
    고혈압 치료 가이드라인
    
    개요
    고혈압은 수축기 혈압이 140mmHg 이상 또는 이완기 혈압이 90mmHg 이상인 상태를 말합니다.
    
    1차 치료
    - 생활습관 개선
    - 저염식이
    - 규칙적인 운동
    - 금연 및 금주
    
    약물 치료
    ACE 억제제를 1차 약물로 사용합니다.
    - 리시노프릴 10mg 하루 1회
    - 에날라프릴 5mg 하루 2회
    
    주의사항
    임신 중에는 ACE 억제제 사용을 금지합니다.
    부작용으로 마른기침이 나타날 수 있습니다.
    """
    
    # 워크플로우 초기화
    workflow = DataProcessingWorkflow({
        'include_metadata': True,
        'include_toc': True
    })
    
    # 동기 처리
    result = workflow.process_sync(sample_text)
    
    print(f"처리 상태: {result['status'].value}")
    print(f"진행률: {result['progress']*100:.1f}%")
    
    if result['errors']:
        print(f"오류: {result['errors']}")
    
    if result['markdown_content']:
        print("\n=== 마크다운 결과 ===")
        print(result['markdown_content'])


def example_json_processing():
    """JSON 처리 예제"""
    print("\n=== JSON 처리 예제 ===")
    
    # 의료 가이드라인 JSON 예제
    sample_json = {
        "title": "당뇨병 관리 가이드라인",
        "version": "2024.1",
        "author": "대한당뇨병학회",
        "description": "제2형 당뇨병 환자의 종합적 관리 지침",
        "guidelines": [
            {
                "title": "혈당 목표",
                "content": "당화혈색소(HbA1c) 7% 미만 유지를 목표로 합니다."
            },
            {
                "title": "약물 치료",
                "content": "메트포르민을 1차 치료제로 사용하며, 500mg부터 시작하여 점진적으로 증량합니다."
            }
        ],
        "recommendations": [
            "정기적인 혈당 모니터링",
            "균형잡힌 식단 관리",
            "규칙적인 운동",
            "연 1회 안저검사"
        ],
        "contraindications": [
            "중증 신부전 환자에서 메트포르민 사용 금지",
            "케톤산증 발생 시 즉시 인슐린 치료"
        ]
    }
    
    # 워크플로우 초기화
    workflow = DataProcessingWorkflow()
    
    # 동기 처리
    result = workflow.process_sync(sample_json)
    
    print(f"처리 상태: {result['status'].value}")
    print(f"진행률: {result['progress']*100:.1f}%")
    
    if result['markdown_content']:
        print("\n=== 마크다운 결과 ===")
        print(result['markdown_content'])


def example_streamlit_integration():
    """스트림릿 통합 예제 (시뮬레이션)"""
    print("\n=== 스트림릿 통합 예제 ===")
    
    # 스트림릿에서 사용할 수 있는 간단한 함수
    def process_medical_guideline(input_data, input_type=None):
        """
        의료 가이드라인 처리 함수 (스트림릿용)
        
        Args:
            input_data: 입력 데이터 (텍스트, JSON, 파일 경로 등)
            input_type: 입력 타입 (선택사항)
            
        Returns:
            dict: 처리 결과
        """
        try:
            workflow = DataProcessingWorkflow()
            result = workflow.process_sync(input_data)
            
            return {
                'success': result['status'].value == 'completed',
                'markdown': result.get('markdown_content', ''),
                'progress': result['progress'],
                'errors': result.get('errors', []),
                'warnings': result.get('warnings', []),
                'metadata': result.get('processed_content', {}).metadata if result.get('processed_content') else {}
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'markdown': '',
                'progress': 0.0
            }
    
    # 테스트
    test_input = "심부전 치료: 이뇨제와 ACE 억제제를 병용하여 치료합니다."
    result = process_medical_guideline(test_input)
    
    print(f"성공 여부: {result['success']}")
    print(f"진행률: {result['progress']*100:.1f}%")
    if result['success']:
        print("\n처리된 마크다운:")
        print(result['markdown'])


if __name__ == "__main__":
    # 예제 실행
    example_text_processing()
    example_json_processing() 
    example_streamlit_integration()
    
    print("\n=== 지원되는 입력 타입 ===")
    workflow = DataProcessingWorkflow()
    supported_types = workflow.get_supported_input_types()
    for input_type in supported_types:
        print(f"- {input_type}")
    
    print("\n=== 워크플로우 정보 ===")
    info = workflow.get_workflow_info()
    print(f"처리 단계: {info['processing_steps']}")
    print(f"옵션: {info['options']}")
