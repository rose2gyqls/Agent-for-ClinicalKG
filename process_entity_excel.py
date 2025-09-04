#!/usr/bin/env python3
"""
엑셀 파일에서 엔티티를 읽어와서 매핑 결과를 저장하는 스크립트
"""

import pandas as pd
import sys
import os
from typing import List, Dict, Any
import time

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from kg_clinical_guideline.mapping.entity_mapping_api import EntityMappingAPI, EntityInput, EntityTypeAPI
    print("✅ 모듈 import 성공")
except ImportError as e:
    print(f"❌ 모듈 import 실패: {e}")
    print("entity_mapping_api.py를 직접 import 시도...")
    
    # 직접 경로로 import 시도
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "entity_mapping_api", 
        "src/kg_clinical_guideline/mapping/entity_mapping_api.py"
    )
    entity_mapping_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entity_mapping_module)
    
    EntityMappingAPI = entity_mapping_module.EntityMappingAPI
    EntityInput = entity_mapping_module.EntityInput
    EntityTypeAPI = entity_mapping_module.EntityTypeAPI
    print("✅ 직접 import 성공")


def map_domain_to_entity_type(domain: str) -> EntityTypeAPI:
    """도메인을 EntityTypeAPI로 매핑"""
    domain_mapping = {
        "condition": EntityTypeAPI.CONDITION,
        "diagnostic": EntityTypeAPI.DIAGNOSTIC,
        "drug": EntityTypeAPI.DRUG,
        "test": EntityTypeAPI.TEST,
        "measurement": EntityTypeAPI.MEASUREMENT,
        "surgery": EntityTypeAPI.SURGERY,
        "procedure": EntityTypeAPI.PROCEDURE,
        "observation": EntityTypeAPI.OBSERVATION,
        "provider": EntityTypeAPI.PROVIDER,
        # 추가 매핑
        "diagnosis": EntityTypeAPI.DIAGNOSTIC,
        "medication": EntityTypeAPI.DRUG,
        "lab": EntityTypeAPI.TEST,
        "laboratory": EntityTypeAPI.TEST,
    }
    
    domain_lower = domain.lower().strip()
    return domain_mapping.get(domain_lower, EntityTypeAPI.CONDITION)


def process_entities_from_excel(file_path: str, sheet_names: List[str]) -> None:
    """엑셀 파일에서 엔티티를 처리하고 매핑 결과를 저장"""
    
    print(f"📊 엑셀 파일 처리 시작: {file_path}")
    
    # API 초기화
    try:
        api = EntityMappingAPI()
        print("✅ EntityMappingAPI 초기화 성공")
    except Exception as e:
        print(f"❌ API 초기화 실패: {e}")
        return
    
    # 각 시트별로 처리
    for sheet_name in sheet_names:
        print(f"\n{'='*60}")
        print(f"📋 시트 처리 중: {sheet_name}")
        print(f"{'='*60}")
        
        try:
            # 엑셀 파일 읽기
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            print(f"📊 시트 크기: {len(df)} 행, {len(df.columns)} 열")
            print(f"📊 컬럼: {list(df.columns)}")
            
            # 필요한 컬럼 확인
            if 'entity_plain_name' not in df.columns:
                print(f"❌ 'entity_plain_name' 컬럼이 없습니다.")
                continue
            
            if 'entity_domain' not in df.columns:
                print(f"❌ 'entity_domain' 컬럼이 없습니다.")
                continue
            
            # 매핑 결과 저장을 위한 새로운 컬럼 추가
            if 'mapped_concept_id' not in df.columns:
                df['mapped_concept_id'] = ''
            if 'mapped_concept_name' not in df.columns:
                df['mapped_concept_name'] = ''
            if 'mapping_score' not in df.columns:
                df['mapping_score'] = 0.0
            if 'mapping_confidence' not in df.columns:
                df['mapping_confidence'] = ''
            if 'mapping_method' not in df.columns:
                df['mapping_method'] = ''
            
            # 각 엔티티별로 매핑 수행
            successful_mappings = 0
            failed_mappings = 0
            
            for index, row in df.iterrows():
                entity_name = str(row['entity_plain_name']).strip()
                entity_domain = str(row['entity_domain']).strip()
                
                # 빈 값 체크
                if pd.isna(row['entity_plain_name']) or entity_name == '' or entity_name == 'nan':
                    print(f"  {index+1:3d}. ⏭️  빈 엔티티명 건너뛰기")
                    continue
                
                if pd.isna(row['entity_domain']) or entity_domain == '' or entity_domain == 'nan':
                    print(f"  {index+1:3d}. ⏭️  빈 도메인 건너뛰기: {entity_name}")
                    continue
                
                print(f"  {index+1:3d}. 🔍 매핑 중: {entity_name} ({entity_domain})")
                
                try:
                    # 도메인을 EntityTypeAPI로 변환
                    entity_type = map_domain_to_entity_type(entity_domain)
                    
                    # EntityInput 생성
                    entity_input = EntityInput(
                        entity_name=entity_name,
                        entity_type=entity_type,
                        confidence=1.0
                    )
                    
                    # 매핑 수행
                    mapping_result = api.map_entity(entity_input)
                    
                    if mapping_result:
                        # 매핑 성공
                        df.at[index, 'mapped_concept_id'] = mapping_result.mapped_concept_id
                        df.at[index, 'mapped_concept_name'] = mapping_result.mapped_concept_name
                        df.at[index, 'mapping_score'] = mapping_result.mapping_score
                        df.at[index, 'mapping_confidence'] = mapping_result.mapping_confidence
                        df.at[index, 'mapping_method'] = mapping_result.mapping_method
                        
                        successful_mappings += 1
                        print(f"       ✅ 성공: {mapping_result.mapped_concept_name} (점수: {mapping_result.mapping_score:.3f})")
                    else:
                        # 매핑 실패
                        df.at[index, 'mapped_concept_id'] = 'FAILED'
                        df.at[index, 'mapped_concept_name'] = 'NO_MAPPING_FOUND'
                        df.at[index, 'mapping_score'] = 0.0
                        df.at[index, 'mapping_confidence'] = 'failed'
                        df.at[index, 'mapping_method'] = 'failed'
                        
                        failed_mappings += 1
                        print(f"       ❌ 실패: 매핑 결과 없음")
                
                except Exception as e:
                    # 매핑 오류
                    df.at[index, 'mapped_concept_id'] = 'ERROR'
                    df.at[index, 'mapped_concept_name'] = f'ERROR: {str(e)}'
                    df.at[index, 'mapping_score'] = 0.0
                    df.at[index, 'mapping_confidence'] = 'error'
                    df.at[index, 'mapping_method'] = 'error'
                    
                    failed_mappings += 1
                    print(f"       ⚠️ 오류: {str(e)}")
                
                # API 호출 간격 조절 (서버 부하 방지)
                time.sleep(0.1)
            
            # 결과 통계
            total_entities = successful_mappings + failed_mappings
            success_rate = (successful_mappings / total_entities * 100) if total_entities > 0 else 0
            
            print(f"\n📊 {sheet_name} 매핑 결과:")
            print(f"   총 엔티티: {total_entities}")
            print(f"   성공: {successful_mappings}")
            print(f"   실패: {failed_mappings}")
            print(f"   성공률: {success_rate:.1f}%")
            
            # 결과를 새로운 엑셀 파일로 저장
            output_file = file_path.replace('.xlsx', f'_mapped_{sheet_name}.xlsx')
            df.to_excel(output_file, sheet_name=sheet_name, index=False)
            print(f"💾 결과 저장: {output_file}")
            
        except Exception as e:
            print(f"❌ 시트 {sheet_name} 처리 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print(f"\n🎉 모든 시트 처리 완료!")


def main():
    """메인 함수"""
    file_path = "/Users/rose/Desktop/KG-for-Clinical-Guideline/data/entity_sample_9.xlsx"
    sheet_names = ["9", "10"]  # 9번, 10번 시트
    
    print("🚀 엔티티 매핑 처리 시작")
    print(f"📁 파일: {file_path}")
    print(f"📋 시트: {sheet_names}")
    
    # 파일 존재 확인
    if not os.path.exists(file_path):
        print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
        return
    
    # 엔티티 처리
    process_entities_from_excel(file_path, sheet_names)


if __name__ == "__main__":
    main()
