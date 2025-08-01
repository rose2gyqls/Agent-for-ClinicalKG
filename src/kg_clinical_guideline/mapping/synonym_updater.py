"""
OMOP CDM 동의어 사전 업데이트
"""

from typing import List, Dict, Any, Optional
import time

from .elasticsearch_client import ElasticsearchClient


class SynonymUpdater:
    """OMOP CDM 동의어 사전 업데이트"""
    
    def __init__(self, es_client: Optional[ElasticsearchClient] = None):
        """
        동의어 업데이터 초기화
        
        Args:
            es_client: Elasticsearch 클라이언트
        """
        self.es_client = es_client or ElasticsearchClient.create_default()
        
        print(f"✅ SynonymUpdater 초기화 완료")
    
    def update_synonym_dictionary(
        self,
        new_synonyms: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        동의어 사전 업데이트
        
        Args:
            new_synonyms: concept_id를 키로 하는 동의어 리스트
            
        Returns:
            Dict: 업데이트 결과
        """
        start_time = time.time()
        
        try:
            updated_count = 0
            failed_count = 0
            
            for concept_id, synonyms in new_synonyms.items():
                try:
                    # 기존 동의어 조회
                    existing_synonyms = self.es_client.search_synonyms(concept_id)
                    
                    # 새로운 동의어만 필터링
                    new_only_synonyms = [s for s in synonyms if s not in existing_synonyms]
                    
                    if new_only_synonyms:
                        # 동의어 업데이트 (실제 구현 시 Elasticsearch bulk API 사용)
                        self._update_concept_synonyms(concept_id, new_only_synonyms)
                        updated_count += 1
                        
                except Exception as e:
                    print(f"⚠️ 컨셉 {concept_id} 동의어 업데이트 실패: {str(e)}")
                    failed_count += 1
            
            processing_time = time.time() - start_time
            
            result = {
                'updated_concepts': updated_count,
                'failed_concepts': failed_count,
                'total_concepts': len(new_synonyms),
                'processing_time': processing_time,
                'success_rate': updated_count / len(new_synonyms) if new_synonyms else 0.0,
                'update_timestamp': time.time()
            }
            
            print(f"✅ 동의어 사전 업데이트 완료: {updated_count}/{len(new_synonyms)} 성공")
            return result
            
        except Exception as e:
            return {
                'updated_concepts': 0,
                'failed_concepts': len(new_synonyms),
                'total_concepts': len(new_synonyms),
                'processing_time': time.time() - start_time,
                'success_rate': 0.0,
                'error': str(e),
                'update_timestamp': time.time()
            }
    
    def _update_concept_synonyms(
        self,
        concept_id: str,
        new_synonyms: List[str]
    ):
        """개별 컨셉의 동의어 업데이트"""
        # 실제 구현에서는 Elasticsearch bulk API를 사용하여
        # concept_synonym 인덱스에 새로운 동의어 추가
        
        # 현재는 로그만 출력
        print(f"🔄 컨셉 {concept_id}에 {len(new_synonyms)}개 동의어 추가")
        
        # TODO: 실제 Elasticsearch 업데이트 로직 구현
        # 예시:
        # for synonym in new_synonyms:
        #     self.es_client.index_synonym(concept_id, synonym)
        
        pass
    
    def validate_synonyms(
        self,
        synonyms: List[str]
    ) -> List[str]:
        """동의어 유효성 검증"""
        valid_synonyms = []
        
        for synonym in synonyms:
            # 기본 유효성 검사
            if (
                len(synonym.strip()) > 2 and  # 최소 길이
                len(synonym.strip()) < 200 and  # 최대 길이
                not synonym.isdigit() and  # 숫자만으로 구성되지 않음
                any(c.isalpha() for c in synonym)  # 적어도 하나의 알파벳 포함
            ):
                valid_synonyms.append(synonym.strip())
        
        return valid_synonyms
    
    def get_synonym_statistics(self) -> Dict[str, Any]:
        """동의어 사전 통계 조회"""
        try:
            # Elasticsearch 상태 확인
            es_health = self.es_client.health_check()
            
            # 동의어 인덱스 통계 (예시)
            stats = {
                'elasticsearch_status': es_health.get('status', 'unknown'),
                'synonym_index_exists': es_health.get('omop_indices', {}).get('omop_concept_synonym', {}).get('exists', False),
                'total_synonym_entries': es_health.get('omop_indices', {}).get('omop_concept_synonym', {}).get('doc_count', 0)
            }
            
            return stats
            
        except Exception as e:
            return {
                'elasticsearch_status': 'error',
                'error': str(e)
            }
    
    @classmethod
    def create_default(cls) -> 'SynonymUpdater':
        """기본 설정으로 동의어 업데이터 생성"""
        return cls() 