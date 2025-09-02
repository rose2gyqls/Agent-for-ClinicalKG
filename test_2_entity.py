#!/usr/bin/env python3
"""
엔티티 매핑 API 테스트 코드
두 개의 엔티티에 대해 5단계별로 후보군과 점수를 확인
"""

import sys
import os
import logging
from typing import Dict, Any, List

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from kg_clinical_guideline.mapping.entity_mapping_api import (
    EntityMappingAPI, 
    EntityInput, 
    EntityTypeAPI
)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EntityMappingTester:
    """엔티티 매핑 API 테스트 클래스"""
    
    def __init__(self):
        """테스트 초기화"""
        self.api = EntityMappingAPI()
        logger.info("✅ EntityMappingTester 초기화 완료")
    
    def test_entity_mapping_5_steps(self, entity_name: str, entity_type: str, 
                                   golden_concept_id: str, golden_concept_name: str) -> None:
        """
        엔티티 매핑을 5단계별로 상세 테스트
        
        Args:
            entity_name: 테스트할 엔티티 이름
            entity_type: 엔티티 타입
            golden_concept_id: 골든셋 컨셉 ID
            golden_concept_name: 골든셋 컨셉 이름
        """
        print(f"\n{'='*80}")
        print(f"🔍 엔티티: {entity_name}")
        print(f"🎯 골든셋: {golden_concept_id} - {golden_concept_name}")
        print(f"{'='*80}")
        
        # 엔티티 이름 전처리
        preprocessed_name = self.api._preprocess_entity_name(entity_name)
        print(f"📝 전처리: '{entity_name}' → '{preprocessed_name}'")
        
        # 엔티티 입력 생성
        entity_input = EntityInput(
            entity_name=preprocessed_name,
            entity_type=EntityTypeAPI(entity_type),
            confidence=1.0
        )
        
        # 사전 매핑 정보 준비
        entities_to_map = self.api._prepare_entity_for_mapping(entity_input)
        if not entities_to_map:
            print("❌ 엔티티 매핑 준비 실패")
            return
        
        entity_info = entities_to_map[0]
        
        # ===== 1단계: Elasticsearch 검색 → 상위 5개 후보 (쿼리의 Function Score 기반) =====
        print(f"\n🔍 1단계: Elasticsearch 검색 → 상위 5개 후보 (Function Score 기반)")
        print(f"{'='*60}")
        
        candidates = self.api._search_similar_concepts(entity_input, entity_info, top_k=5)
        
        if not candidates:
            print("❌ 검색 결과 없음")
            return
        
        print(f"총 {len(candidates)}개 후보 발견:")
        for i, candidate in enumerate(candidates, 1):
            source = candidate['_source']
            score = candidate['_score']
            print(f"  {i}. Function Score: {score:.2f}")
            print(f"     컨셉 ID: {source.get('concept_id', 'N/A')}")
            print(f"     컨셉명: {source.get('concept_name', 'N/A')}")
            print(f"     도메인: {source.get('domain_id', 'N/A')}")
            print(f"     어휘체계: {source.get('vocabulary_id', 'N/A')}")
            print(f"     표준여부: {source.get('standard_concept', 'N/A')}")
            print()
        
        # ===== 2단계: Standard/Non-standard 분류 =====
        print(f"🔄 2단계: Standard/Non-standard 분류")
        print(f"{'='*60}")
        
        standard_candidates = []
        non_standard_candidates = []
        
        for i, candidate in enumerate(candidates, 1):
            source = candidate['_source']
            if source.get('standard_concept') == 'S':
                standard_candidates.append(candidate)
                print(f"  {i}. ✅ Standard: {source.get('concept_name', 'N/A')}")
            else:
                non_standard_candidates.append(candidate)
                print(f"  {i}. ⚠️ Non-standard: {source.get('concept_name', 'N/A')}")
        
        print(f"\n  📊 분류 결과: Standard {len(standard_candidates)}개, Non-standard {len(non_standard_candidates)}개")
        
        # ===== 3단계: Non-standard인 경우 → Maps to 관계로 Standard 후보 조회 =====
        print(f"\n🔗 3단계: Non-standard → Maps to 관계로 Standard 후보 조회")
        print(f"{'='*60}")
        
        all_standard_candidates = []
        
        # Standard 후보들은 그대로 사용
        for candidate in standard_candidates:
            source = candidate['_source']
            all_standard_candidates.append({
                'concept': source,
                'final_score': candidate['_score'],
                'is_original_standard': True,
                'original_candidate': candidate
            })
        
        # Non-standard 후보들은 Standard 후보 조회
        for i, candidate in enumerate(non_standard_candidates, 1):
            source = candidate['_source']
            concept_id = str(source.get('concept_id', ''))
            print(f"  Non-standard {i}: {source.get('concept_name', 'N/A')} (ID: {concept_id})")
            
            standard_candidates_from_non = self.api._get_standard_candidates(concept_id, entity_info["domain_id"])
            
            if standard_candidates_from_non:
                print(f"    → Maps to 관계로 {len(standard_candidates_from_non)}개 Standard 후보 발견")
                for j, std_candidate in enumerate(standard_candidates_from_non[:3], 1):  # 상위 3개만 출력
                    print(f"      {j}. {std_candidate.get('concept_name', 'N/A')} (ID: {std_candidate.get('concept_id', 'N/A')})")
            else:
                print(f"    → Maps to 관계 없음")
            
            print()
        
        # ===== 4단계: Python 유사도 재계산 → 최적 후보 선택 =====
        print(f"🐍 4단계: Python 유사도 재계산 → 최적 후보 선택")
        print(f"{'='*60}")
        
        # Non-standard 후보들의 Standard 후보들과 유사도 재계산
        for i, candidate in enumerate(non_standard_candidates, 1):
            source = candidate['_source']
            concept_id = str(source.get('concept_id', ''))
            standard_candidates_from_non = self.api._get_standard_candidates(concept_id, entity_info["domain_id"])
            
            if standard_candidates_from_non:
                best_standard = self.api._find_best_standard_candidate(entity_input, standard_candidates_from_non)
                if best_standard:
                    similarity_score = best_standard.get('similarity_score', 0)
                    print(f"  Non-standard {i}: {source.get('concept_name', 'N/A')}")
                    print(f"    → 최적 Standard: {best_standard.get('concept_name', 'N/A')}")
                    print(f"    → 유사도 점수: {similarity_score:.3f}")
                    
                    all_standard_candidates.append({
                        'concept': best_standard,
                        'final_score': similarity_score,
                        'is_original_standard': False,
                        'original_non_standard': source,
                        'original_candidate': candidate
                    })
                    print()
        
        # ===== 5단계: 점수 정규화 (0.0~1.0) → 최종 매핑 결과 =====
        print(f"📊 5단계: 점수 정규화 (0.0~1.0) → 최종 매핑 결과")
        print(f"{'='*60}")
        
        if not all_standard_candidates:
            print("❌ 처리된 후보 없음")
            return
        
        # 점수별 정렬
        sorted_candidates = sorted(all_standard_candidates, key=lambda x: x['final_score'], reverse=True)
        
        print("최종 후보 순위:")
        for i, candidate in enumerate(sorted_candidates, 1):
            concept = candidate['concept']
            final_score = candidate['final_score']
            is_standard = candidate['is_original_standard']
            mapping_type = "직접 Standard" if is_standard else "Non-standard → Standard"
            
            # 점수 정규화
            normalized_score = self.api._normalize_score(final_score)
            confidence = self.api._determine_confidence(normalized_score)
            
            print(f"  {i}. 원본 점수: {final_score:.3f} → 정규화: {normalized_score:.3f} ({confidence})")
            print(f"     컨셉 ID: {concept.get('concept_id', 'N/A')}")
            print(f"     컨셉명: {concept.get('concept_name', 'N/A')}")
            print(f"     도메인: {concept.get('domain_id', 'N/A')}")
            print(f"     어휘체계: {concept.get('vocabulary_id', 'N/A')}")
            print(f"     매핑 방법: {mapping_type}")
            print()
        
        # 골든셋과 비교
        best_candidate = sorted_candidates[0]
        best_concept = best_candidate['concept']
        best_concept_id = str(best_concept.get('concept_id', ''))
        
        print(f"🎯 골든셋 비교:")
        if best_concept_id == golden_concept_id:
            print(f"  ✅ 성공! 골든셋과 정확히 일치")
        else:
            print(f"  ❌ 불일치")
        
        print(f"  예상: {golden_concept_id} - {golden_concept_name}")
        print(f"  실제: {best_concept_id} - {best_concept.get('concept_name', 'N/A')}")
        
        print(f"\n{'='*80}")


def main():
    """메인 테스트 함수"""
    print("🚀 엔티티 매핑 API 테스트 시작")
    
    # API 상태 확인
    tester = EntityMappingTester()
    health_check = tester.api.health_check()
    print(f"📊 API 상태: {health_check}")
    
    # 테스트 케이스 1: ST-segment elevation myocardial infarction (STEMI)
    print("\n" + "="*80)
    print("📋 테스트 케이스 1: ST-segment elevation myocardial infarction (STEMI)")
    print("="*80)
    tester.test_entity_mapping_5_steps(
        entity_name="ST-segment elevation myocardial infarction (STEMI)",
        entity_type="diagnostic",
        golden_concept_id="4296653",
        golden_concept_name="Acute ST segment elevation myocardial infarction"
    )
    
    # 테스트 케이스 2: Acute Coronary Syndromes (ACS)
    print("\n" + "="*80)
    print("📋 테스트 케이스 2: Acute Coronary Syndromes (ACS)")
    print("="*80)
    tester.test_entity_mapping_5_steps(
        entity_name="Acute Coronary Syndromes (ACS)",
        entity_type="diagnostic",
        golden_concept_id="4215140",
        golden_concept_name="Acute coronary syndrome"
    )
    
    print("\n🎉 모든 테스트 완료!")


if __name__ == "__main__":
    main()
