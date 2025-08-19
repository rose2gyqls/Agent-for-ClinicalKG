#!/usr/bin/env python3
"""
Elasticsearch 매핑 모듈 테스트 스크립트
100개의 테스트 데이터로 매핑 결과를 생성하고 저장
"""

import sys
import os
import json
import time
from typing import List, Dict, Any
from dataclasses import asdict

# 프로젝트 루트 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from kg_clinical_guideline.mapping.elasticsearch_client import ElasticsearchClient
from kg_clinical_guideline.mapping.omop_mapper import OMOPMapper
from kg_clinical_guideline.graph.entity_extractor import ClinicalEntity, EntityType


def generate_test_entities() -> List[ClinicalEntity]:
    """테스트용 임상 엔티티 100개 생성"""
    
    # 심장 관련 조건들
    cardiac_conditions = [
        "acute coronary syndrome", "ST-elevation myocardial infarction", "non-ST elevation ACS",
        "unstable angina", "stable angina", "myocardial infarction", "heart failure",
        "atrial fibrillation", "ventricular tachycardia", "bradycardia", "hypertension",
        "dyslipidemia", "coronary artery disease", "cardiomyopathy", "pericarditis",
        "endocarditis", "myocarditis", "valvular heart disease", "aortic stenosis",
        "mitral regurgitation", "tricuspid regurgitation", "pulmonary hypertension"
    ]
    
    # 약물들
    medications = [
        "aspirin", "clopidogrel", "ticagrelor", "prasugrel", "heparin", "warfarin",
        "dabigatran", "rivaroxaban", "apixaban", "edoxaban", "metoprolol", "atenolol",
        "carvedilol", "bisoprolol", "lisinopril", "enalapril", "ramipril", "losartan",
        "valsartan", "candesartan", "amlodipine", "nifedipine", "diltiazem", "verapamil",
        "nitroglycerin", "isosorbide mononitrate", "digoxin", "amiodarone", "propafenone",
        "sotalol", "flecainide", "dofetilide", "ivabradine", "sacubitril", "valsartan"
    ]
    
    # 검사/측정들
    measurements = [
        "troponin I", "troponin T", "creatine kinase", "creatine kinase-MB", "BNP",
        "NT-proBNP", "C-reactive protein", "erythrocyte sedimentation rate", "D-dimer",
        "fibrinogen", "prothrombin time", "activated partial thromboplastin time",
        "international normalized ratio", "platelet count", "white blood cell count",
        "hemoglobin", "hematocrit", "sodium", "potassium", "chloride", "bicarbonate",
        "blood urea nitrogen", "creatinine", "glucose", "glycated hemoglobin",
        "total cholesterol", "high-density lipoprotein", "low-density lipoprotein",
        "triglycerides", "alanine aminotransferase", "aspartate aminotransferase"
    ]
    
    # 증상들
    symptoms = [
        "chest pain", "shortness of breath", "dyspnea", "fatigue", "weakness",
        "dizziness", "syncope", "palpitations", "irregular heartbeat", "rapid heartbeat",
        "slow heartbeat", "swelling", "edema", "cough", "wheezing", "nausea",
        "vomiting", "abdominal pain", "back pain", "arm pain", "jaw pain",
        "neck pain", "headache", "confusion", "anxiety", "depression", "insomnia"
    ]
    
    # 시술들
    procedures = [
        "coronary angiography", "percutaneous coronary intervention", "coronary artery bypass grafting",
        "cardiac catheterization", "echocardiography", "transesophageal echocardiography",
        "stress test", "nuclear stress test", "cardiac MRI", "cardiac CT", "electrocardiography",
        "Holter monitoring", "event recorder", "implantable loop recorder", "pacemaker implantation",
        "implantable cardioverter defibrillator", "cardiac resynchronization therapy",
        "catheter ablation", "cardioversion", "defibrillation", "thrombolysis", "thrombectomy"
    ]
    
    # 해부학적 구조들
    anatomy = [
        "heart", "left ventricle", "right ventricle", "left atrium", "right atrium",
        "coronary artery", "left anterior descending artery", "left circumflex artery",
        "right coronary artery", "aorta", "pulmonary artery", "pulmonary vein",
        "mitral valve", "tricuspid valve", "aortic valve", "pulmonary valve",
        "septum", "pericardium", "myocardium", "endocardium", "epicardium"
    ]
    
    # 모든 카테고리 결합
    all_terms = (cardiac_conditions + medications + measurements + symptoms + procedures + anatomy)
    
    # 100개로 제한하고 중복 제거
    unique_terms = list(set(all_terms))[:100]
    
    # 엔티티 타입 결정 함수
    def determine_entity_type(term: str) -> EntityType:
        if term in cardiac_conditions:
            return EntityType.CONDITION
        elif term in medications:
            return EntityType.MEDICATION
        elif term in measurements:
            return EntityType.MEASUREMENT
        elif term in symptoms:
            return EntityType.SYMPTOM
        elif term in procedures:
            return EntityType.PROCEDURE
        elif term in anatomy:
            return EntityType.ANATOMY
        else:
            return EntityType.CONDITION  # 기본값
    
    # ClinicalEntity 객체들 생성
    entities = []
    for i, term in enumerate(unique_terms):
        entity_type = determine_entity_type(term)
        entity = ClinicalEntity(
            text=term,
            entity_type=entity_type,
            normalized_text=term.lower(),
            confidence=0.9,
            start_pos=i,
            end_pos=i + len(term)
        )
        entities.append(entity)
    
    print(f"✅ {len(entities)}개의 테스트 엔티티 생성 완료")
    return entities


def test_mapping_module(entities: List[ClinicalEntity]) -> Dict[str, Any]:
    """매핑 모듈 테스트 실행"""
    
    print("🔍 Elasticsearch 클라이언트 초기화 중...")
    es_client = ElasticsearchClient.create_default()
    
    print("🔍 OMOP 매퍼 초기화 중...")
    mapper = OMOPMapper(es_client=es_client)
    
    # 헬스 체크
    print("🔍 시스템 상태 확인 중...")
    es_health = es_client.health_check()
    mapper_health = mapper.health_check()
    
    print(f"Elasticsearch 상태: {es_health['status']}")
    print(f"매퍼 상태: {mapper_health['omop_mapper_status']}")
    
    # 매핑 실행
    print("🔍 엔티티 매핑 시작...")
    start_time = time.time()
    
    mapping_results = mapper.map_entities_to_omop(entities)
    
    processing_time = time.time() - start_time
    
    print(f"✅ 매핑 완료: {processing_time:.2f}초 소요")
    print(f"성공: {len(mapping_results['successful_mappings'])}개")
    print(f"실패: {len(mapping_results['failed_mappings'])}개")
    
    # 클라이언트 정리
    es_client.close()
    
    return mapping_results


def save_results(results: Dict[str, Any], output_dir: str):
    """결과를 파일로 저장"""
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 간단한 요약 결과 생성 (input, concept_id, concept_name, mapping_score)
    summary_data = []
    
    for mapping in results['successful_mappings']:
        summary_data.append({
            'input': mapping['source_entity']['text'],
            'concept_id': mapping['omop_concept']['concept_id'],
            'concept_name': mapping['omop_concept']['concept_name'],
            'mapping_score': round(mapping['mapping_score'], 3)
        })
    
    # 실패한 매핑도 포함
    for failure in results['failed_mappings']:
        summary_data.append({
            'input': failure['entity_text'],
            'concept_id': 'N/A',
            'concept_name': 'N/A',
            'mapping_score': 0.0
        })
    
    # 요약 결과 저장
    summary_path = os.path.join(output_dir, "mapping_summary.csv")
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("input,concept_id,concept_name,mapping_score\n")
        for item in summary_data:
            f.write(f'"{item["input"]}","{item["concept_id"]}","{item["concept_name"]}",{item["mapping_score"]}\n')
    
    print(f"✅ 요약 결과 저장: {summary_path}")


def main():
    """메인 실행 함수"""
    
    print("🚀 Elasticsearch 매핑 모듈 테스트 시작")
    print("=" * 50)
    
    try:
        # 1. 테스트 엔티티 생성
        print("1️⃣ 테스트 엔티티 생성 중...")
        entities = generate_test_entities()
        
        # 2. 매핑 모듈 테스트
        print("2️⃣ 매핑 모듈 테스트 실행 중...")
        results = test_mapping_module(entities)
        
        # 3. 결과 저장
        print("3️⃣ 결과 저장 중...")
        output_dir = "/Users/rose/Desktop/KG-for-Clinical-Guideline/data"
        saved_files = save_results(results, output_dir)
        
        # 4. 결과 요약 출력
        print("\n" + "=" * 50)
        print("📊 테스트 결과 요약")
        print("=" * 50)
        
        metadata = results['mapping_metadata']
        print(f"총 엔티티 수: {metadata['total_entities']}")
        print(f"성공한 매핑: {metadata['successful_mappings']}")
        print(f"실패한 매핑: {metadata['failed_mappings']}")
        print(f"성공률: {metadata['success_rate']:.1%}")
        print(f"처리 시간: {metadata['processing_time']:.2f}초")
        
        if 'mapping_statistics' in results:
            stats = results['mapping_statistics']
            if stats:
                print(f"\n📈 매핑 통계:")
                print(f"  - 평균 매핑 점수: {stats.get('avg_mapping_score', 0):.3f}")
                print(f"  - 신뢰도별 분포: {stats.get('by_confidence', {})}")
                print(f"  - 방법별 분포: {stats.get('by_method', {})}")
        
        print(f"\n💾 저장된 파일들:")
        for file_type, file_path in saved_files.items():
            print(f"  - {file_type}: {file_path}")
        
        print("\n✅ 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 테스트 실행 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
