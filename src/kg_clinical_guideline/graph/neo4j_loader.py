"""
Neo4j 지식그래프 로더
"""

from typing import List, Dict, Any, Optional
import time
from dataclasses import dataclass

# Optional import for Neo4j support
try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False
    # Dummy class for when neo4j is not available
    class GraphDatabase:
        @staticmethod
        def driver(*args, **kwargs):
            return None

from .triple_generator import Triple, TripleType
from ..config import config


@dataclass
class LoadResult:
    """로딩 결과 데이터 클래스"""
    nodes_created: int
    relationships_created: int
    properties_set: int
    labels_added: int
    processing_time: float
    success: bool
    error_message: Optional[str] = None


class Neo4jLoader:
    """Neo4j 지식그래프 로더"""
    
    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None
    ):
        """
        Neo4j 로더 초기화
        
        Args:
            uri: Neo4j 서버 URI
            username: 사용자명
            password: 비밀번호
            database: 데이터베이스명
        """
        # 환경변수에서 설정 가져오기 (주석 처리된 설정 활성화)
        self.uri = uri or getattr(config, 'NEO4J_SERVER_URI', 'bolt://localhost:7687')
        self.username = username or getattr(config, 'NEO4J_SERVER_USER', 'neo4j')
        self.password = password or getattr(config, 'NEO4J_SERVER_PASSWORD', 'password')
        self.database = database or getattr(config, 'NEO4J_SERVER_DATABASE', 'neo4j')
        
        # Neo4j 드라이버 초기화
        self.driver = None
        if HAS_NEO4J:
            self._connect()
        
        neo4j_status = "Neo4j 드라이버 사용 가능" if HAS_NEO4J else "Neo4j 드라이버 없음 (기본 기능만)"
        print(f"✅ Neo4jLoader 초기화 완료 - {neo4j_status}")
    
    def _connect(self):
        """Neo4j 연결 설정"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                encrypted=False,  # 로컬 개발용
                trust=False
            )
            
            # 연결 테스트
            with self.driver.session(database=self.database) as session:
                session.run("RETURN 1")
            
            print(f"✅ Neo4j 연결 성공: {self.uri}")
            
        except Exception as e:
            print(f"⚠️ Neo4j 연결 실패: {str(e)}")
            self.driver = None
    
    def load_triples_to_neo4j(
        self,
        triples: List[Triple],
        clear_existing: bool = False,
        batch_size: int = 1000
    ) -> LoadResult:
        """
        트리플을 Neo4j에 로드
        
        Args:
            triples: 로드할 트리플 리스트
            clear_existing: 기존 데이터 삭제 여부
            batch_size: 배치 크기
            
        Returns:
            LoadResult: 로딩 결과
        """
        if not self.driver:
            return LoadResult(
                nodes_created=0,
                relationships_created=0,
                properties_set=0,
                labels_added=0,
                processing_time=0.0,
                success=False,
                error_message="Neo4j driver not initialized"
            )
        
        start_time = time.time()
        
        try:
            with self.driver.session(database=self.database) as session:
                # 기존 데이터 삭제 (옵션)
                if clear_existing:
                    session.run("MATCH (n) DETACH DELETE n")
                    print("🗑️ 기존 Neo4j 데이터 삭제 완료")
                
                # 인덱스 생성
                self._create_indexes(session)
                
                # 트리플을 타입별로 분류
                typed_triples = self._group_triples_by_type(triples)
                
                # 배치별로 처리
                total_stats = {
                    'nodes_created': 0,
                    'relationships_created': 0,
                    'properties_set': 0,
                    'labels_added': 0
                }
                
                # 1. 노드 생성 (주체와 객체)
                node_stats = self._create_nodes_from_triples(session, triples, batch_size)
                total_stats['nodes_created'] += node_stats['nodes_created']
                total_stats['properties_set'] += node_stats['properties_set']
                total_stats['labels_added'] += node_stats['labels_added']
                
                # 2. 관계 생성
                rel_stats = self._create_relationships_from_triples(session, triples, batch_size)
                total_stats['relationships_created'] += rel_stats['relationships_created']
                total_stats['properties_set'] += rel_stats['properties_set']
                
                processing_time = time.time() - start_time
                
                print(f"✅ Neo4j 로딩 완료: {len(triples)}개 트리플")
                print(f"   - 노드: {total_stats['nodes_created']}개")
                print(f"   - 관계: {total_stats['relationships_created']}개")
                print(f"   - 처리시간: {processing_time:.2f}초")
                
                return LoadResult(
                    nodes_created=total_stats['nodes_created'],
                    relationships_created=total_stats['relationships_created'],
                    properties_set=total_stats['properties_set'],
                    labels_added=total_stats['labels_added'],
                    processing_time=processing_time,
                    success=True
                )
                
        except Exception as e:
            return LoadResult(
                nodes_created=0,
                relationships_created=0,
                properties_set=0,
                labels_added=0,
                processing_time=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
    
    def _create_indexes(self, session):
        """Neo4j 인덱스 생성"""
        indexes = [
            "CREATE INDEX entity_id_index IF NOT EXISTS FOR (e:Entity) ON (e.id)",
            "CREATE INDEX concept_id_index IF NOT EXISTS FOR (c:Concept) ON (c.concept_id)",
            "CREATE INDEX dp_id_index IF NOT EXISTS FOR (d:DigitalPhenotype) ON (d.dp_id)",
            "CREATE INDEX entity_text_index IF NOT EXISTS FOR (e:Entity) ON (e.text)",
            "CREATE INDEX concept_name_index IF NOT EXISTS FOR (c:Concept) ON (c.name)"
        ]
        
        for index_query in indexes:
            try:
                session.run(index_query)
            except Exception as e:
                print(f"⚠️ 인덱스 생성 실패: {str(e)}")
    
    def _group_triples_by_type(self, triples: List[Triple]) -> Dict[TripleType, List[Triple]]:
        """트리플을 타입별로 그룹화"""
        grouped = {}
        
        for triple in triples:
            if triple.triple_type not in grouped:
                grouped[triple.triple_type] = []
            grouped[triple.triple_type].append(triple)
        
        return grouped
    
    def _create_nodes_from_triples(
        self,
        session,
        triples: List[Triple],
        batch_size: int
    ) -> Dict[str, int]:
        """트리플에서 노드 생성"""
        stats = {'nodes_created': 0, 'properties_set': 0, 'labels_added': 0}
        
        # 모든 주체와 객체 수집
        all_nodes = set()
        node_info = {}
        
        for triple in triples:
            # 주체 노드
            subject_uri = triple.subject
            all_nodes.add(subject_uri)
            if subject_uri not in node_info:
                node_info[subject_uri] = self._extract_node_info(subject_uri, triple, 'subject')
            
            # 객체 노드 (리터럴이 아닌 경우)
            object_uri = triple.object
            if self._is_uri(object_uri):
                all_nodes.add(object_uri)
                if object_uri not in node_info:
                    node_info[object_uri] = self._extract_node_info(object_uri, triple, 'object')
        
        # 배치별로 노드 생성
        node_list = list(all_nodes)
        for i in range(0, len(node_list), batch_size):
            batch = node_list[i:i+batch_size]
            batch_data = []
            
            for node_uri in batch:
                info = node_info[node_uri]
                batch_data.append({
                    'uri': node_uri,
                    'id': info['id'],
                    'label': info['label'],
                    'type': info['type'],
                    'properties': info['properties']
                })
            
            # Cypher 쿼리 실행
            query = """
            UNWIND $nodes AS node
            CALL {
                WITH node
                CALL apoc.create.node([node.type], 
                    apoc.map.merge(node.properties, {
                        id: node.id,
                        uri: node.uri,
                        label: node.label
                    })
                ) YIELD node AS created_node
                RETURN created_node
            } IN TRANSACTIONS OF 100 ROWS
            RETURN count(*) as nodes_created
            """
            
            try:
                result = session.run(query, nodes=batch_data)
                batch_stats = result.single()
                if batch_stats:
                    stats['nodes_created'] += batch_stats['nodes_created']
            except Exception as e:
                # APOC이 없는 경우 기본 쿼리 사용
                self._create_nodes_without_apoc(session, batch_data, stats)
        
        return stats
    
    def _create_nodes_without_apoc(self, session, batch_data: List[Dict], stats: Dict):
        """APOC 없이 노드 생성"""
        for node_data in batch_data:
            node_type = node_data['type']
            properties = node_data['properties']
            properties.update({
                'id': node_data['id'],
                'uri': node_data['uri'],
                'label': node_data['label']
            })
            
            # 동적 라벨을 가진 노드 생성 쿼리
            query = f"""
            MERGE (n:{node_type} {{id: $id}})
            SET n += $properties
            RETURN n
            """
            
            try:
                session.run(query, id=node_data['id'], properties=properties)
                stats['nodes_created'] += 1
                stats['properties_set'] += len(properties)
                stats['labels_added'] += 1
            except Exception as e:
                print(f"⚠️ 노드 생성 실패: {str(e)}")
    
    def _create_relationships_from_triples(
        self,
        session,
        triples: List[Triple],
        batch_size: int
    ) -> Dict[str, int]:
        """트리플에서 관계 생성"""
        stats = {'relationships_created': 0, 'properties_set': 0}
        
        # 관계만 필터링 (객체가 URI인 경우)
        relationship_triples = [t for t in triples if self._is_uri(t.object)]
        
        # 배치별로 관계 생성
        for i in range(0, len(relationship_triples), batch_size):
            batch = relationship_triples[i:i+batch_size]
            batch_data = []
            
            for triple in batch:
                relationship_type = self._extract_relationship_type(triple.predicate)
                subject_id = self._extract_id_from_uri(triple.subject)
                object_id = self._extract_id_from_uri(triple.object)
                
                batch_data.append({
                    'subject_id': subject_id,
                    'object_id': object_id,
                    'relationship_type': relationship_type,
                    'properties': {
                        'confidence': triple.confidence,
                        'triple_type': triple.triple_type.value,
                        'metadata': str(triple.metadata) if triple.metadata else ""
                    }
                })
            
            # 관계 생성 쿼리
            query = """
            UNWIND $relationships AS rel
            MATCH (subject {id: rel.subject_id})
            MATCH (object {id: rel.object_id})
            CALL apoc.create.relationship(subject, rel.relationship_type, rel.properties, object)
            YIELD rel AS created_rel
            RETURN count(*) as relationships_created
            """
            
            try:
                result = session.run(query, relationships=batch_data)
                batch_stats = result.single()
                if batch_stats:
                    stats['relationships_created'] += batch_stats['relationships_created']
            except Exception as e:
                # APOC이 없는 경우 기본 쿼리 사용
                self._create_relationships_without_apoc(session, batch_data, stats)
        
        return stats
    
    def _create_relationships_without_apoc(self, session, batch_data: List[Dict], stats: Dict):
        """APOC 없이 관계 생성"""
        for rel_data in batch_data:
            # 동적 관계 타입은 APOC 없이는 어려우므로 일반적인 관계 사용
            query = """
            MATCH (subject {id: $subject_id})
            MATCH (object {id: $object_id})
            MERGE (subject)-[r:RELATED_TO]->(object)
            SET r += $properties
            SET r.relationship_type = $relationship_type
            RETURN r
            """
            
            try:
                session.run(query,
                    subject_id=rel_data['subject_id'],
                    object_id=rel_data['object_id'],
                    relationship_type=rel_data['relationship_type'],
                    properties=rel_data['properties']
                )
                stats['relationships_created'] += 1
                stats['properties_set'] += len(rel_data['properties'])
            except Exception as e:
                print(f"⚠️ 관계 생성 실패: {str(e)}")
    
    def _extract_node_info(self, uri: str, triple: Triple, role: str) -> Dict[str, Any]:
        """URI에서 노드 정보 추출"""
        # URI에서 타입과 ID 추출
        if '/dp/' in uri:
            node_type = 'DigitalPhenotype'
            node_id = self._extract_id_from_uri(uri)
            properties = {'dp_id': node_id}
        elif '/entity/' in uri:
            node_type = 'Entity'
            node_id = self._extract_id_from_uri(uri)
            properties = {'entity_type': triple.metadata.get('entity_type', 'unknown')}
        elif '/omop/' in uri:
            node_type = 'Concept'
            node_id = self._extract_id_from_uri(uri)
            properties = {
                'concept_id': triple.metadata.get('concept_id', ''),
                'domain_id': triple.metadata.get('domain_id', ''),
                'vocabulary_id': triple.metadata.get('vocabulary_id', '')
            }
        elif '/section/' in uri:
            node_type = 'Section'
            node_id = self._extract_id_from_uri(uri)
            properties = {}
        else:
            node_type = 'Resource'
            node_id = self._extract_id_from_uri(uri)
            properties = {}
        
        return {
            'id': node_id,
            'label': node_id,
            'type': node_type,
            'properties': properties
        }
    
    def _extract_id_from_uri(self, uri: str) -> str:
        """URI에서 ID 추출"""
        # URI의 마지막 부분을 ID로 사용
        return uri.split('/')[-1] if '/' in uri else uri
    
    def _extract_relationship_type(self, predicate: str) -> str:
        """술어에서 관계 타입 추출"""
        if '/' in predicate:
            return predicate.split('/')[-1].upper()
        elif '#' in predicate:
            return predicate.split('#')[-1].upper()
        else:
            return predicate.upper()
    
    def _is_uri(self, value: str) -> bool:
        """값이 URI인지 확인"""
        return value.startswith('http://') or value.startswith('https://') or '/' in value
    
    def query_knowledge_graph(self, cypher_query: str, parameters: Dict = None) -> List[Dict]:
        """지식그래프 쿼리 실행"""
        if not self.driver:
            return []
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(cypher_query, parameters or {})
                return [record.data() for record in result]
        except Exception as e:
            print(f"❌ 쿼리 실행 실패: {str(e)}")
            return []
    
    def get_graph_statistics(self) -> Dict[str, Any]:
        """그래프 통계 조회"""
        if not self.driver:
            return {}
        
        try:
            with self.driver.session(database=self.database) as session:
                # 노드 수
                node_result = session.run("MATCH (n) RETURN count(n) as node_count")
                node_count = node_result.single()['node_count']
                
                # 관계 수
                rel_result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
                rel_count = rel_result.single()['rel_count']
                
                # 라벨별 노드 수
                label_result = session.run("""
                    CALL db.labels() YIELD label
                    CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) as count', {})
                    YIELD value
                    RETURN label, value.count as count
                """)
                labels = {record['label']: record['count'] for record in label_result}
                
                # 관계 타입별 수
                type_result = session.run("""
                    CALL db.relationshipTypes() YIELD relationshipType
                    CALL apoc.cypher.run('MATCH ()-[r:' + relationshipType + ']->() RETURN count(r) as count', {})
                    YIELD value
                    RETURN relationshipType, value.count as count
                """)
                relationship_types = {record['relationshipType']: record['count'] for record in type_result}
                
                return {
                    'total_nodes': node_count,
                    'total_relationships': rel_count,
                    'nodes_by_label': labels,
                    'relationships_by_type': relationship_types
                }
                
        except Exception as e:
            print(f"⚠️ 통계 조회 중 APOC 사용 실패, 기본 통계 사용: {str(e)}")
            # APOC 없이 기본 통계
            try:
                with self.driver.session(database=self.database) as session:
                    node_result = session.run("MATCH (n) RETURN count(n) as node_count")
                    node_count = node_result.single()['node_count']
                    
                    rel_result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
                    rel_count = rel_result.single()['rel_count']
                    
                    return {
                        'total_nodes': node_count,
                        'total_relationships': rel_count,
                        'nodes_by_label': {},
                        'relationships_by_type': {}
                    }
            except Exception as e2:
                print(f"❌ 기본 통계 조회 실패: {str(e2)}")
                return {}
    
    def close(self):
        """연결 종료"""
        if self.driver:
            try:
                self.driver.close()
                print("✅ Neo4j 연결 종료")
            except Exception as e:
                print(f"⚠️ Neo4j 연결 종료 중 오류: {str(e)}")
    
    @classmethod
    def create_default(cls) -> 'Neo4jLoader':
        """기본 설정으로 로더 생성"""
        return cls() 