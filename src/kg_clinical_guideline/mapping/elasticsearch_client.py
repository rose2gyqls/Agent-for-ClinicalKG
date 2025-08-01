"""
Elasticsearch 클라이언트 for OMOP CDM 매핑
"""

from typing import List, Dict, Any, Optional
import os
import time
from dataclasses import dataclass

# Optional import for Elasticsearch support
try:
    from elasticsearch import Elasticsearch
    HAS_ELASTICSEARCH = True
except ImportError:
    HAS_ELASTICSEARCH = False
    # Dummy class for when elasticsearch is not available
    class Elasticsearch:
        def __init__(self, *args, **kwargs): pass
        def ping(self): return False
        def search(self, *args, **kwargs): return {'hits': {'hits': []}}
        def close(self): pass

from ..config import config


@dataclass 
class SearchResult:
    """검색 결과 데이터 클래스"""
    concept_id: str
    concept_name: str
    domain_id: str
    vocabulary_id: str
    concept_class_id: str
    standard_concept: str
    concept_code: str
    score: float
    synonyms: List[str] = None
    
    def __post_init__(self):
        if self.synonyms is None:
            self.synonyms = []


class ElasticsearchClient:
    """Elasticsearch 클라이언트"""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = False,
        timeout: int = 30
    ):
        """
        Elasticsearch 클라이언트 초기화
        
        Args:
            host: ES 서버 호스트
            port: ES 서버 포트
            username: 사용자명
            password: 비밀번호
            use_ssl: SSL 사용 여부
            timeout: 타임아웃 (초)
        """
        # 환경변수에서 설정 가져오기
        self.host = host or config.ES_SERVER_HOST or 'localhost'
        self.port = port or (int(config.ES_SERVER_PORT) if config.ES_SERVER_PORT else 9200)
        self.username = username or config.ES_SERVER_USERNAME
        self.password = password or config.ES_SERVER_PASSWORD
        self.use_ssl = use_ssl
        self.timeout = timeout
        
        # Elasticsearch 클라이언트 초기화
        self.client = self._create_client() if HAS_ELASTICSEARCH else None
        
        # OMOP CDM 인덱스 이름들
        self.concept_index = "omop_concept"
        self.concept_synonym_index = "omop_concept_synonym"
        self.concept_relationship_index = "omop_concept_relationship"
        
        es_status = f"Elasticsearch 사용 가능 ({self.host}:{self.port})" if HAS_ELASTICSEARCH else "Elasticsearch 없음 (기본 기능만)"
        print(f"✅ ElasticsearchClient 초기화 완료 - {es_status}")
    
    def _create_client(self) -> Elasticsearch:
        """Elasticsearch 클라이언트 생성"""
        try:
            # 연결 설정
            es_config = {
                'hosts': [{'host': self.host, 'port': self.port}],
                'request_timeout': self.timeout,
                'max_retries': 3,
                'retry_on_timeout': True
            }
            
            # 인증 설정
            if self.username and self.password:
                es_config['basic_auth'] = (self.username, self.password)
            
            # SSL 설정
            if self.use_ssl:
                es_config['use_ssl'] = True
                es_config['verify_certs'] = False
                es_config['ssl_show_warn'] = False
            
            client = Elasticsearch(**es_config)
            
            # 연결 테스트
            if client.ping():
                print(f"✅ Elasticsearch 연결 성공")
            else:
                print(f"⚠️ Elasticsearch 연결 실패")
            
            return client
            
        except Exception as e:
            print(f"❌ Elasticsearch 클라이언트 생성 실패: {str(e)}")
            # 더미 클라이언트 반환 (로컬 테스트용)
            return None
    
    def search_concepts(
        self,
        query: str,
        domain_ids: Optional[List[str]] = None,
        vocabulary_ids: Optional[List[str]] = None,
        standard_concept_only: bool = True,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        OMOP CDM concept 검색
        
        Args:
            query: 검색 쿼리
            domain_ids: 도메인 ID 필터 (예: ['Condition', 'Drug'])
            vocabulary_ids: 어휘체계 ID 필터 (예: ['SNOMED', 'RxNorm'])
            standard_concept_only: 표준 컨셉만 검색 여부
            limit: 결과 제한 수
            
        Returns:
            List[SearchResult]: 검색 결과 리스트
        """
        if not self.client:
            print("⚠️ Elasticsearch 클라이언트가 초기화되지 않음")
            return []
        
        try:
            # 검색 쿼리 구성
            search_body = self._build_concept_search_query(
                query, domain_ids, vocabulary_ids, standard_concept_only, limit
            )
            
            # 검색 실행
            response = self.client.search(
                index=self.concept_index,
                body=search_body
            )
            
            # 결과 파싱
            results = self._parse_concept_search_results(response)
            
            print(f"🔍 Concept 검색 완료: '{query}' → {len(results)}개 결과")
            return results
            
        except Exception as e:
            print(f"❌ Concept 검색 실패: {str(e)}")
            return []
    
    def search_synonyms(
        self,
        concept_id: str
    ) -> List[str]:
        """
        특정 concept의 동의어 검색
        
        Args:
            concept_id: OMOP concept ID
            
        Returns:
            List[str]: 동의어 리스트
        """
        if not self.client:
            return []
        
        try:
            search_body = {
                "query": {
                    "term": {
                        "concept_id": concept_id
                    }
                },
                "size": 100
            }
            
            response = self.client.search(
                index=self.concept_synonym_index,
                body=search_body
            )
            
            synonyms = []
            for hit in response['hits']['hits']:
                synonym_name = hit['_source'].get('concept_synonym_name', '')
                if synonym_name and synonym_name not in synonyms:
                    synonyms.append(synonym_name)
            
            return synonyms
            
        except Exception as e:
            print(f"❌ 동의어 검색 실패: {str(e)}")
            return []
    
    def _build_concept_search_query(
        self,
        query: str,
        domain_ids: Optional[List[str]],
        vocabulary_ids: Optional[List[str]],
        standard_concept_only: bool,
        limit: int
    ) -> Dict[str, Any]:
        """concept 검색 쿼리 구성"""
        
        # 메인 검색 쿼리 (multi-match with boosting)
        must_queries = [
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "concept_name^3",  # concept name에 가장 높은 가중치
                        "concept_name.ngram^2",
                        "concept_synonym_name^2",
                        "concept_code^1"
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            }
        ]
        
        # 필터 조건들
        filter_queries = []
        
        # 도메인 필터
        if domain_ids:
            filter_queries.append({
                "terms": {
                    "domain_id": domain_ids
                }
            })
        
        # 어휘체계 필터
        if vocabulary_ids:
            filter_queries.append({
                "terms": {
                    "vocabulary_id": vocabulary_ids
                }
            })
        
        # 표준 컨셉 필터
        if standard_concept_only:
            filter_queries.append({
                "term": {
                    "standard_concept": "S"
                }
            })
        
        # 최종 쿼리 구성
        search_body = {
            "query": {
                "bool": {
                    "must": must_queries,
                    "filter": filter_queries
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}},
                {"concept_name.keyword": {"order": "asc"}}
            ],
            "_source": [
                "concept_id",
                "concept_name", 
                "domain_id",
                "vocabulary_id",
                "concept_class_id",
                "standard_concept",
                "concept_code"
            ]
        }
        
        return search_body
    
    def _parse_concept_search_results(self, response: Dict[str, Any]) -> List[SearchResult]:
        """concept 검색 결과 파싱"""
        results = []
        
        for hit in response['hits']['hits']:
            source = hit['_source']
            
            result = SearchResult(
                concept_id=source.get('concept_id', ''),
                concept_name=source.get('concept_name', ''),
                domain_id=source.get('domain_id', ''),
                vocabulary_id=source.get('vocabulary_id', ''),
                concept_class_id=source.get('concept_class_id', ''),
                standard_concept=source.get('standard_concept', ''),
                concept_code=source.get('concept_code', ''),
                score=hit['_score']
            )
            
            # 동의어 정보 추가 (별도 검색)
            result.synonyms = self.search_synonyms(result.concept_id)
            
            results.append(result)
        
        return results
    
    def search_fuzzy_concepts(
        self,
        query: str,
        fuzziness: str = "AUTO",
        limit: int = 5
    ) -> List[SearchResult]:
        """
        퍼지 매칭을 사용한 concept 검색
        
        Args:
            query: 검색 쿼리
            fuzziness: 퍼지 정도 ("AUTO", 0, 1, 2)
            limit: 결과 제한 수
            
        Returns:
            List[SearchResult]: 검색 결과
        """
        if not self.client:
            return []
        
        try:
            search_body = {
                "query": {
                    "fuzzy": {
                        "concept_name": {
                            "value": query,
                            "fuzziness": fuzziness,
                            "max_expansions": 50
                        }
                    }
                },
                "size": limit
            }
            
            response = self.client.search(
                index=self.concept_index,
                body=search_body
            )
            
            return self._parse_concept_search_results(response)
            
        except Exception as e:
            print(f"❌ 퍼지 검색 실패: {str(e)}")
            return []
    
    def health_check(self) -> Dict[str, Any]:
        """Elasticsearch 클러스터 상태 확인"""
        if not self.client:
            return {"status": "disconnected", "error": "Client not initialized"}
        
        try:
            cluster_health = self.client.cluster.health()
            indices_stats = self.client.cat.indices(format='json')
            
            # OMOP 인덱스 상태 확인
            omop_indices = {}
            for index_name in [self.concept_index, self.concept_synonym_index]:
                try:
                    index_info = self.client.indices.stats(index=index_name)
                    omop_indices[index_name] = {
                        "exists": True,
                        "doc_count": index_info['_all']['total']['docs']['count']
                    }
                except:
                    omop_indices[index_name] = {
                        "exists": False,
                        "doc_count": 0
                    }
            
            return {
                "status": "connected",
                "cluster_health": cluster_health['status'],
                "cluster_name": cluster_health['cluster_name'],
                "node_count": cluster_health['number_of_nodes'],
                "omop_indices": omop_indices
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def close(self):
        """연결 종료"""
        if self.client:
            try:
                self.client.close()
                print("✅ Elasticsearch 연결 종료")
            except Exception as e:
                print(f"⚠️ Elasticsearch 연결 종료 중 오류: {str(e)}")
    
    @classmethod
    def create_default(cls) -> 'ElasticsearchClient':
        """기본 설정으로 클라이언트 생성"""
        return cls() 