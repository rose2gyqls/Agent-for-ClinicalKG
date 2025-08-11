#!/usr/bin/env python3
"""
간단한 Elasticsearch 검색 테스트
"""

import requests
import json

def test_simple_elasticsearch():
    """간단한 Elasticsearch 검색 테스트"""
    print("🔍 간단한 Elasticsearch 검색 테스트 시작...")
    print("=" * 60)
    
    # 기본 설정
    base_url = "http://3.35.110.161:9200"
    auth = ("elastic", "snomed")
    
    try:
        # 1. 클러스터 정보 확인
        print("📊 클러스터 정보:")
        response = requests.get(f"{base_url}/", auth=auth)
        response.raise_for_status()
        cluster_info = response.json()
        print(f"   - 클러스터명: {cluster_info.get('cluster_name')}")
        print(f"   - 버전: {cluster_info.get('version', {}).get('number')}")
        
        # 2. 인덱스 정보 확인
        print("\n📊 인덱스 정보:")
        response = requests.get(f"{base_url}/concept-drug", auth=auth)
        if response.status_code == 200:
            index_info = response.json()
            print(f"   - 인덱스 존재: True")
            mappings = index_info.get('concept-drug', {}).get('mappings', {})
            print(f"   - 매핑 필드 수: {len(mappings.get('properties', {}))}")
            
            # 필드 목록 출력
            properties = mappings.get('properties', {})
            print(f"   - 주요 필드:")
            for field in list(properties.keys())[:10]:  # 처음 10개만
                print(f"     * {field}")
        else:
            print(f"   - 인덱스 존재: False (상태코드: {response.status_code})")
        
        # 3. 간단한 검색 테스트
        print("\n🔍 검색 테스트:")
        test_queries = ["aspirin", "diabetes", "hypertension", "metformin", "insulin"]
        
        for query in test_queries:
            print(f"\n   쿼리: '{query}'")
            
            # 간단한 match 쿼리
            search_body = {
                "size": 5,
                "query": {
                    "match": {
                        "concept_name": query
                    }
                }
            }
            
            response = requests.post(
                f"{base_url}/concept-drug/_search",
                json=search_body,
                auth=auth
            )
            
            if response.status_code == 200:
                result = response.json()
                hits = result.get("hits", {}).get("hits", [])
                print(f"   ✅ 검색 성공: {len(hits)}개 결과")
                
                for i, hit in enumerate(hits[:3], 1):  # 상위 3개만 출력
                    source = hit.get("_source", {})
                    score = hit.get("_score", 0)
                    print(f"   {i}. {source.get('concept_name', 'N/A')} (점수: {score:.2f})")
            else:
                print(f"   ❌ 검색 실패: {response.status_code}")
        
        # 4. 전체 문서 수 확인
        print("\n📊 전체 문서 수:")
        response = requests.get(f"{base_url}/concept-drug/_count", auth=auth)
        if response.status_code == 200:
            count_info = response.json()
            total_docs = count_info.get("count", 0)
            print(f"   - 전체 문서 수: {total_docs:,}개")
        else:
            print(f"   - 문서 수 조회 실패: {response.status_code}")
        
        print("\n" + "=" * 60)
        print("✅ 간단한 Elasticsearch 검색 테스트 완료")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_elasticsearch() 