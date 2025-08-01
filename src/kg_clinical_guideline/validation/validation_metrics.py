"""
2트랙 검증 메트릭 유틸리티 모듈
"""

from typing import List, Dict, Any, Optional
import json
import time
import numpy as np

from .dp_validator import (
    DPValidationResult,
    TrackValidationResult, 
    ValidationTrack,
    SentenceSimilarityResult,
    EvidenceBasedResult
)


class ValidationMetrics:
    """검증 메트릭 유틸리티"""
    
    @staticmethod
    def convert_to_serializable(obj):
        """객체를 JSON 직렬화 가능한 형태로 변환"""
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
                return ValidationMetrics.convert_to_serializable(asdict(obj))
            else:
                # 일반 클래스인 경우
                return {key: ValidationMetrics.convert_to_serializable(value) for key, value in obj.__dict__.items()}
        elif isinstance(obj, dict):
            return {key: ValidationMetrics.convert_to_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [ValidationMetrics.convert_to_serializable(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # 기타 객체는 문자열로 변환
            return str(obj)
    
    @staticmethod
    def export_validation_results_to_json(
        results: List[DPValidationResult],
        summary: Dict[str, Any],
        filename: str
    ) -> Dict[str, Any]:
        """
        검증 결과를 JSON으로 내보내기
        
        Args:
            results: 검증 결과 리스트
            summary: 검증 요약
            filename: 저장할 파일명
            
        Returns:
            Dict[str, Any]: JSON 데이터
        """
        export_data = {
            "validation_metadata": {
                "timestamp": time.time(),
                "export_filename": filename,
                "total_dps": len(results),
                "validation_summary": summary
            },
            "validation_results": []
        }
        
        for result in results:
            # result가 딕셔너리인지 객체인지 안전하게 처리
            def safe_get(obj, attr_path, default=None):
                """중첩된 속성에 안전하게 접근하는 helper 함수"""
                try:
                    if isinstance(obj, dict):
                        keys = attr_path.split('.')
                        current = obj
                        for key in keys:
                            current = current.get(key, {})
                        return current if current != {} else default
                    else:
                        keys = attr_path.split('.')
                        current = obj
                        for key in keys:
                            current = getattr(current, key, None)
                            if current is None:
                                return default
                        return current
                except:
                    return default
            
            # 트랙 1: 유사도 검증 결과
            similarity_details = []
            similarity_success = safe_get(result, 'similarity_result.success', False)
            if similarity_success:
                similarity_details_raw = safe_get(result, 'similarity_result.details', [])
                for detail in similarity_details_raw:
                    if isinstance(detail, SentenceSimilarityResult):
                        similarity_details.append({
                            "dp_sentence": detail.dp_sentence,
                            "best_match_sentence": detail.best_match_sentence,
                            "similarity_score": detail.similarity_score,
                            "match_index": detail.match_index
                        })
                    elif isinstance(detail, dict):
                        similarity_details.append({
                            "dp_sentence": detail.get("dp_sentence", ""),
                            "best_match_sentence": detail.get("best_match_sentence", ""),
                            "similarity_score": detail.get("similarity_score", 0.0),
                            "match_index": detail.get("match_index", -1)
                        })
            
            # 트랙 2: 증거 기반 검증 결과
            evidence_details = []
            evidence_success = safe_get(result, 'evidence_result.success', False)
            if evidence_success:
                evidence_details_raw = safe_get(result, 'evidence_result.details', [])
                for detail in evidence_details_raw:
                    if isinstance(detail, EvidenceBasedResult):
                        evidence_details.append({
                            "question": detail.question,
                            "best_evidence": detail.best_evidence,
                            "evidence_score": detail.evidence_score,
                            "evidence_sentence_index": detail.evidence_sentence_index
                        })
                    elif isinstance(detail, dict):
                        evidence_details.append({
                            "question": detail.get("question", ""),
                            "best_evidence": detail.get("best_evidence", ""),
                            "evidence_score": detail.get("evidence_score", 0.0),
                            "evidence_sentence_index": detail.get("evidence_sentence_index", -1)
                        })
            
            # 안전하게 결과 데이터 구성
            result_data = {
                "dp_info": {
                    "dp_id": safe_get(result, 'dp.dp_id', ''),
                    "label": safe_get(result, 'dp.label', ''),
                    "definition": safe_get(result, 'dp.definition', ''),
                    "section_reference": safe_get(result, 'dp.section_reference', ''),
                    "confidence_score": ValidationMetrics.convert_to_serializable(safe_get(result, 'dp.confidence_score', 0.0)),
                    "metadata": safe_get(result, 'dp.metadata', {})
                },
                "similarity_result": {
                    "track": safe_get(result, 'similarity_result.track.value', 'similarity') or safe_get(result, 'similarity_result.track', 'similarity'),
                    "overall_score": safe_get(result, 'similarity_result.overall_score', 0.0),
                    "processing_time": safe_get(result, 'similarity_result.processing_time', 0.0),
                    "success": similarity_success,
                    "error_message": safe_get(result, 'similarity_result.error_message', None),
                    "details": similarity_details
                },
                "evidence_result": {
                    "track": safe_get(result, 'evidence_result.track.value', 'evidence_based') or safe_get(result, 'evidence_result.track', 'evidence_based'),
                    "overall_score": safe_get(result, 'evidence_result.overall_score', 0.0),
                    "processing_time": safe_get(result, 'evidence_result.processing_time', 0.0),
                    "success": evidence_success,
                    "error_message": safe_get(result, 'evidence_result.error_message', None),
                    "details": evidence_details
                },
                "final_score": safe_get(result, 'final_score', 0.0),
                "passed": safe_get(result, 'passed', False),
                "retry_recommended": safe_get(result, 'retry_recommended', False),
                "processing_time": safe_get(result, 'processing_time', 0.0),
                "validation_issues": safe_get(result, 'validation_issues', [])
            }
            
            export_data["validation_results"].append(result_data)
        
        # # JSON 파일로 저장 (안전한 직렬화)
        # with open(filename, 'w', encoding='utf-8') as f:
        #     json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
        
        # print(f"✅ 검증 결과를 {filename}에 저장했습니다")
        
        # JSON 직렬화 안전성을 위한 변환
        return ValidationMetrics.convert_to_serializable(export_data)
    
    @staticmethod
    def generate_validation_report(results: List, summary: Dict) -> str:
        """검증 결과 텍스트 보고서 생성"""
        report_lines = []
        
        # 헤더
        report_lines.append("=" * 60)
        report_lines.append("DP 검증 결과 보고서")
        report_lines.append("=" * 60)
        report_lines.append()
        
        # 요약 정보
        report_lines.append("📊 검증 요약")
        report_lines.append("-" * 20)
        report_lines.append(f"초기 DP 수: {summary.get('total_initial_dps', len(results))}")
        report_lines.append(f"최종 DP 수: {summary.get('total_final_dps', sum(1 for r in results if r.passed))}")
        report_lines.append(f"성공률: {summary.get('success_rate', sum(1 for r in results if r.passed) / len(results) if results else 0):.1%}")
        report_lines.append(f"재시도 횟수: {len(summary.get('retry_history', []))}")
        report_lines.append(f"총 처리 시간: {summary.get('processing_time', 0):.2f}초")
        report_lines.append()
        
        # 개별 DP 결과
        report_lines.append("📋 개별 DP 검증 결과")
        report_lines.append("-" * 30)
        
        for i, result in enumerate(results, 1):
            status = "✅ 통과" if result.passed else "❌ 실패"
            retry_mark = " 🔄" if "RETRY" in result.dp.dp_id else ""
            
            report_lines.append(f"{i}. {result.dp.label} [{status}]{retry_mark}")
            report_lines.append(f"   최종 점수: {result.final_score:.3f}")
            report_lines.append(f"   유사도 점수: {result.similarity_result.overall_score:.3f}")
            report_lines.append(f"   증거 점수: {result.evidence_result.overall_score:.3f}")
            report_lines.append(f"   처리 시간: {result.processing_time:.2f}초")
            
            # 검증 이슈 표시
            if hasattr(result, 'validation_issues') and result.validation_issues:
                report_lines.append(f"   이슈: {'; '.join(result.validation_issues)}")
            
            # 오류 메시지
            if not result.similarity_result.success:
                report_lines.append(f"   ⚠️ 유사도 검증 오류: {result.similarity_result.error_message}")
            if not result.evidence_result.success:
                report_lines.append(f"   ⚠️ 증거 검증 오류: {result.evidence_result.error_message}")
            
            report_lines.append()
        
        # 재시도 이력
        if summary.get('retry_history'):
            report_lines.append("🔄 재시도 이력")
            report_lines.append("-" * 15)
            for retry in summary['retry_history']:
                report_lines.append(f"재시도: {retry['original_dp_id']} → {retry['new_dp_id']}")
                if retry.get('issues'):
                    report_lines.append(f"  사유: {retry['issues']}")
            report_lines.append()
        
        # 통계 분석
        if results:
            report_lines.append("📈 상세 통계")
            report_lines.append("-" * 15)
            
            final_scores = [r.final_score for r in results]
            similarity_scores = [r.similarity_result.overall_score for r in results if r.similarity_result.success]
            evidence_scores = [r.evidence_result.overall_score for r in results if r.evidence_result.success]
            
            if final_scores:
                report_lines.append(f"평균 최종 점수: {sum(final_scores)/len(final_scores):.3f}")
                report_lines.append(f"최고 점수: {max(final_scores):.3f}")
                report_lines.append(f"최저 점수: {min(final_scores):.3f}")
            
            if similarity_scores:
                report_lines.append(f"평균 유사도 점수: {sum(similarity_scores)/len(similarity_scores):.3f}")
            
            if evidence_scores:
                report_lines.append(f"평균 증거 점수: {sum(evidence_scores)/len(evidence_scores):.3f}")
        
        # 처리 시간 통계
        report_lines.append()
        report_lines.append("⏱️ 처리 시간 분석")
        report_lines.append("-" * 20)
        
        if results:
            processing_times = [r.processing_time for r in results]
            similarity_times = [r.similarity_result.processing_time for r in results]
            evidence_times = [r.evidence_result.processing_time for r in results]
            
            report_lines.append(f"평균 DP 처리 시간: {sum(processing_times)/len(processing_times):.2f}초")
            report_lines.append(f"평균 유사도 검증 시간: {sum(similarity_times)/len(similarity_times):.2f}초")
            report_lines.append(f"평균 증거 검증 시간: {sum(evidence_times)/len(evidence_times):.2f}초")
            report_lines.append(f"총 처리 시간: {sum(r.evidence_result.processing_time for r in results):.2f}초")
        
        return "\n".join(report_lines)
    
    @staticmethod
    def export_step_results(
        step_name: str,
        data: Any,
        filename: str
    ) -> None:
        """
        단계별 결과 내보내기
        
        Args:
            step_name: 단계명
            data: 내보낼 데이터
            filename: 파일명
        """
        step_data = {
            "step": step_name,
            "timestamp": time.time(),
            "data": data
        }
        
        # with open(filename, 'w', encoding='utf-8') as f:
        #     json.dump(step_data, f, ensure_ascii=False, indent=2)
        
        # print(f"✅ {step_name} 결과를 {filename}에 저장했습니다")
    
    @staticmethod
    def calculate_track_statistics(results: List[DPValidationResult]) -> Dict[str, Any]:
        """
        트랙별 통계 계산
        
        Args:
            results: 검증 결과 리스트
            
        Returns:
            Dict[str, Any]: 트랙별 통계
        """
        if not results:
            return {}
        
        # 트랙 1: 유사도 통계
        similarity_scores = [r.similarity_result.overall_score for r in results if r.similarity_result.success]
        similarity_success_rate = len(similarity_scores) / len(results) if results else 0.0
        
        # 트랙 2: 증거 통계
        evidence_scores = [r.evidence_result.overall_score for r in results if r.evidence_result.success]
        evidence_success_rate = len(evidence_scores) / len(results) if results else 0.0
        
        # 최종 점수 통계
        final_scores = [r.final_score for r in results]
        
        track_stats = {
            "track_1_similarity": {
                "success_rate": similarity_success_rate,
                "avg_score": sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0,
                "min_score": min(similarity_scores) if similarity_scores else 0.0,
                "max_score": max(similarity_scores) if similarity_scores else 0.0,
                "total_processing_time": sum(r.similarity_result.processing_time for r in results)
            },
            "track_2_evidence": {
                "success_rate": evidence_success_rate,
                "avg_score": sum(evidence_scores) / len(evidence_scores) if evidence_scores else 0.0,
                "min_score": min(evidence_scores) if evidence_scores else 0.0,
                "max_score": max(evidence_scores) if evidence_scores else 0.0,
                "total_processing_time": sum(r.evidence_result.processing_time for r in results)
            },
            "final_scores": {
                "avg_score": sum(final_scores) / len(final_scores) if final_scores else 0.0,
                "min_score": min(final_scores) if final_scores else 0.0,
                "max_score": max(final_scores) if final_scores else 0.0,
                "pass_rate": len([r for r in results if r.passed]) / len(results) if results else 0.0
            }
        }
        
        return ValidationMetrics.convert_to_serializable(track_stats)
    
    @staticmethod
    def export_detailed_similarity_results(results: List, output_path: str):
        """상세 유사도 결과 내보내기"""
        detailed_results = []
        
        for result in results:
            if result.similarity_result.success and result.similarity_result.details:
                for detail in result.similarity_result.details:
                    detailed_results.append({
                        "dp_id": result.dp.dp_id,
                        "dp_label": result.dp.label,
                        "dp_sentence": detail.dp_sentence,
                        "best_match_sentence": detail.best_match_sentence,
                        "similarity_score": detail.similarity_score,
                        "match_index": detail.match_index
                    })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)
        
        return detailed_results
    
    @staticmethod
    def export_detailed_evidence_results(results: List, output_path: str):
        """상세 증거 결과 내보내기"""
        detailed_results = []
        
        for result in results:
            if result.evidence_result.success:
                dp_detail = {
                    "dp_id": result.dp.dp_id,
                    "dp_label": result.dp.label,
                    "dp_definition": result.dp.definition,
                    "overall_score": result.evidence_result.overall_score,
                    "question_answers": []
                }
                
                for detail in result.evidence_result.details:
                    if isinstance(detail, EvidenceBasedResult):
                        dp_detail["question_answers"].append({
                            "question": detail.question,
                            "best_evidence": detail.best_evidence,
                            "evidence_score": detail.evidence_score,
                            "evidence_sentence_index": detail.evidence_sentence_index
                        })
                
                detailed_results.append(dp_detail)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)
        
        return detailed_results 