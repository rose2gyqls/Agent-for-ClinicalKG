"""
엔티티 매핑 API 테스트 - 100개 의료 용어 매핑 및 CSV 출력
"""

import sys
import os
import csv
import time
from typing import List, Dict, Any
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from kg_clinical_guideline.mapping.entity_mapping_api import (
    EntityMappingAPI,
    EntityInput, 
    EntityTypeAPI,
    map_single_entity,
    map_entities_from_analysis
)

def test_single_entity_mapping():
    """단일 엔티티 매핑 테스트"""
    print("=== 단일 엔티티 매핑 테스트 ===")
    
    # 진단 엔티티 테스트
    result = map_single_entity(
        entity_name="diabetes mellitus",
        entity_type="diagnostic"
    )
    
    if result:
        print(f"✅ 매핑 성공:")
        print(f"  - 원본: {result.source_entity.entity_name}")
        print(f"  - 매핑: {result.mapped_concept_name}")
        print(f"  - 도메인: {result.domain_id}")
        print(f"  - 어휘체계: {result.vocabulary_id}")
        print(f"  - 점수: {result.mapping_score:.3f} (0.0~1.0 정규화)")
        print(f"  - 신뢰도: {result.mapping_confidence}")
    else:
        print("❌ 매핑 실패")
    
    print()

def test_batch_entity_mapping():
    """일괄 엔티티 매핑 테스트"""
    print("=== 일괄 엔티티 매핑 테스트 ===")
    
    api = EntityMappingAPI()
    
    # 4개 분류별 테스트 엔티티
    entity_inputs = [
        EntityInput(
            entity_name="diabetes mellitus",
            entity_type=EntityTypeAPI.DIAGNOSTIC
        ),
        EntityInput(
            entity_name="metformin",
            entity_type=EntityTypeAPI.DRUG
        ),
        EntityInput(
            entity_name="hemoglobin A1c",
            entity_type=EntityTypeAPI.TEST
        ),
        EntityInput(
            entity_name="coronary angioplasty",
            entity_type=EntityTypeAPI.SURGERY
        )
    ]
    
    result = api.map_entities_batch(entity_inputs)
    
    print(f"총 엔티티: {result['statistics']['total_entities']}")
    print(f"성공 매핑: {result['statistics']['successful_mappings']}")
    print(f"실패 매핑: {result['statistics']['failed_mappings']}")
    print(f"성공률: {result['statistics']['success_rate']:.1%}")
    print()
    
    # 성공한 매핑 출력
    for mapping in result['successful_mappings']:
        source = mapping['source_entity']
        mapped = mapping['mapped_concept']
        print(f"✅ {source['entity_name']} ({source['entity_type']}) -> {mapped['concept_name']}")
    
    # 실패한 매핑 출력
    for failure in result['failed_mappings']:
        print(f"❌ {failure['entity_name']} ({failure['entity_type']}) - {failure['reason']}")
    
    print()

def test_llm_analysis_mapping():
    """LLM 분석 결과 매핑 테스트"""
    print("=== LLM 분석 결과 매핑 테스트 ===")
    
    # 가상의 LLM 분석 결과
    analysis = {
        "diagnostic": {
            "concept_name": "diabetes mellitus",
            "domain_id": "Condition",
            "vocabulary_id": "SNOMED",
            "confidence": 0.95
        },
        "drug": {
            "concept_name": "metformin",
            "domain_id": "Drug", 
            "vocabulary_id": "RxNorm",
            "confidence": 0.92
        },
        "test": {
            "concept_name": "hemoglobin A1c measurement",
            "domain_id": "Measurement",
            "vocabulary_id": "LOINC",
            "confidence": 0.88
        }
    }
    
    result = map_entities_from_analysis(analysis)
    
    print(f"분석 결과 매핑:")
    print(f"  - 총 엔티티: {result['statistics']['total_entities']}")
    print(f"  - 성공 매핑: {result['statistics']['successful_mappings']}")
    print(f"  - 성공률: {result['statistics']['success_rate']:.1%}")
    
    for mapping in result['successful_mappings']:
        source = mapping['source_entity']
        mapped = mapping['mapped_concept']
        print(f"  ✅ {source['entity_name']} -> {mapped['concept_name']}")
    
    print()

def get_medical_terms() -> List[str]:
    """심장질환 관련 의료 용어 리스트"""
    return [
        # Diagnostic (진단)
        "Acute Coronary Syndromes (ACS)",
        "Myocardial Infarction (MI)",
        "ST-segment elevation myocardial infarction (STEMI)",
        "Non–ST-segment elevation myocardial infarction (NSTEMI)",
        "Unstable Angina",
        "Myocardial Ischemia",
        "Heart Failure (HF)",
        "Arrhythmias",
        "Cardiac Arrest",
        "Chest Pain",
        "Coronary Artery Thrombosis",
        "Atherosclerotic Plaque",
        "Plaque Rupture",
        "Multivessel Disease (MVD)",
        "Chronic Coronary Disease (CCD)",
        "Coronary Artery Spasm",
        "Spontaneous Coronary Artery Dissection",
        "MINOCA (MI with nonobstructive coronary artery disease)",
        "Myonecrosis",
        "Embolism",
        "Left Ventricular Hypertrophy",
        "Acute Pericarditis",
        "Brugada Syndrome",
        "Takotsubo Syndrome",
        "Left Bundle Branch Block (LBBB)",
        "ST-segment Elevation",
        "ST-segment Depression",
        "T-wave Inversion",
        
        # Drug (약물)
        "Unfractionated Heparin (UFH)",
        "Proton Pump Inhibitor (PPI)",
        "SGLT-2 (sodium-glucose cotransporter-2) inhibitors",
        "GLP-1 (glucagon-like peptide-1) agonists",
        "Fibrinolytic Treatment",
        
        # Test (검사)
        "12-lead ECG (electrocardiogram)",
        "Cardiac Troponin (cTn)",
        "High-sensitivity Cardiac Troponin (hs-cTn)",
        "Intravascular Ultrasound (IVUS)",
        "Optical Coherence Tomography (OCT)",
        "Physical Examination",
        "Vital Signs Assessment",
        
        # Surgery (수술/시술)
        "Percutaneous Coronary Intervention (PCI)",
        "Primary Percutaneous Coronary Intervention (PPCI)",
        "Cardiac Catheterization",
        "Implantable Cardioverter-Defibrillator (ICD)",
        "Intra-aortic Balloon Pump (IABP)",
        "Mechanical Circulatory Support (MCS)",
        "Venoarterial Extracorporeal Membrane Oxygenation (VA-ECMO)",
        "Reperfusion",
        "Defibrillation",
        "Right Ventricular Pacing"
    ]


def classify_medical_term(term: str) -> str:
    """의료 용어를 4개 분류로 자동 분류"""
    term_lower = term.lower()
    
    # 진단/질환 관련
    diagnostic_keywords = [
        'syndrome', 'infarction', 'angina', 'ischemia', 'failure', 'arrhythmia',
        'arrest', 'pain', 'thrombosis', 'plaque', 'rupture', 'disease',
        'spasm', 'dissection', 'necrosis', 'embolism', 'hypertrophy',
        'pericarditis', 'block', 'elevation', 'depression', 'inversion'
    ]
    
    # 약물 관련
    drug_keywords = [
        'heparin', 'inhibitor', 'sglt-2', 'glp-1', 'agonist', 'fibrinolytic',
        'treatment', 'ufh', 'ppi'
    ]
    
    # 검사/측정 관련
    test_keywords = [
        'ecg', 'electrocardiogram', 'troponin', 'ultrasound', 'tomography',
        'examination', 'assessment', 'signs', 'ivus', 'oct'
    ]
    
    # 수술/시술 관련
    surgery_keywords = [
        'intervention', 'catheterization', 'implantable', 'defibrillator',
        'balloon', 'pump', 'support', 'ecmo', 'reperfusion', 'defibrillation',
        'pacing', 'pci', 'ppci', 'icd', 'iabp', 'mcs', 'va-ecmo'
    ]
    
    # 키워드 매칭으로 분류
    if any(keyword in term_lower for keyword in diagnostic_keywords):
        return "diagnostic"
    elif any(keyword in term_lower for keyword in drug_keywords):
        return "drug"
    elif any(keyword in term_lower for keyword in test_keywords):
        return "test"
    elif any(keyword in term_lower for keyword in surgery_keywords):
        return "surgery"
    else:
        # 기본값은 진단으로 분류
        return "diagnostic"


def test_cardiac_medical_terms_mapping():
    """심장질환 관련 의료 용어 매핑 테스트 및 CSV 출력"""
    print("=== 심장질환 관련 의료 용어 매핑 테스트 ===")
    
    # 의료 용어 리스트 가져오기
    medical_terms = get_medical_terms()
    print(f"총 {len(medical_terms)}개의 심장질환 관련 의료 용어를 매핑합니다...")
    
    # API 초기화
    api = EntityMappingAPI()
    
    # 결과 저장용 리스트
    mapping_results = []
    
    # 각 용어별로 매핑 수행
    for i, term in enumerate(medical_terms, 1):
        print(f"진행률: {i}/{len(medical_terms)} - {term}")
        
        # 용어 분류
        entity_type = classify_medical_term(term)
        
        # 엔티티 입력 생성
        entity_input = EntityInput(
            entity_name=term,
            entity_type=EntityTypeAPI(entity_type)
        )
        
        # 매핑 수행
        mapping_result = api.map_entity(entity_input)
        
        # 결과 저장
        if mapping_result:
            result_row = {
                'original_term': term,
                'entity_type': entity_type,
                'concept_id': mapping_result.mapped_concept_id,
                'concept_name': mapping_result.mapped_concept_name,
                'mapping_score': mapping_result.mapping_score,
                'domain_id': mapping_result.domain_id,
                'vocabulary_id': mapping_result.vocabulary_id,
                'mapping_confidence': mapping_result.mapping_confidence,
                'mapping_method': mapping_result.mapping_method
            }
        else:
            result_row = {
                'original_term': term,
                'entity_type': entity_type,
                'concept_id': 'N/A',
                'concept_name': 'N/A',
                'mapping_score': 0.0,
                'domain_id': 'N/A',
                'vocabulary_id': 'N/A',
                'mapping_confidence': 'failed',
                'mapping_method': 'failed'
            }
        
        mapping_results.append(result_row)
        
        # API 호출 간격 조절 (서버 부하 방지)
        time.sleep(0.1)
    
    # CSV 파일로 결과 저장
    csv_filename = f"cardiac_medical_terms_mapping_results_{int(time.time())}.csv"
    
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'original_term', 'entity_type', 'concept_id', 'concept_name', 
            'mapping_score', 'domain_id', 'vocabulary_id', 'mapping_confidence', 'mapping_method'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in mapping_results:
            writer.writerow(result)
    
    # 통계 계산
    successful_mappings = [r for r in mapping_results if r['concept_id'] != 'N/A']
    failed_mappings = [r for r in mapping_results if r['concept_id'] == 'N/A']
    
    print(f"\n=== 매핑 결과 통계 ===")
    print(f"총 용어 수: {len(medical_terms)}")
    print(f"성공 매핑: {len(successful_mappings)}")
    print(f"실패 매핑: {len(failed_mappings)}")
    print(f"성공률: {len(successful_mappings)/len(medical_terms)*100:.1f}%")
    print(f"결과 파일: {csv_filename}")
    
    # 분류별 통계
    type_stats = {}
    for result in mapping_results:
        entity_type = result['entity_type']
        if entity_type not in type_stats:
            type_stats[entity_type] = {'total': 0, 'success': 0}
        type_stats[entity_type]['total'] += 1
        if result['concept_id'] != 'N/A':
            type_stats[entity_type]['success'] += 1
    
    print(f"\n=== 분류별 통계 ===")
    for entity_type, stats in type_stats.items():
        success_rate = stats['success'] / stats['total'] * 100
        print(f"{entity_type}: {stats['success']}/{stats['total']} ({success_rate:.1f}%)")
    
    # 상위 매핑 점수 결과
    high_score_results = [r for r in successful_mappings if r['mapping_score'] > 0.8]
    print(f"\n=== 고점수 매핑 (점수 > 0.8, 0.0~1.0 정규화) ===")
    print(f"고점수 매핑 수: {len(high_score_results)}")
    
    for result in sorted(high_score_results, key=lambda x: x['mapping_score'], reverse=True)[:10]:
        print(f"  {result['original_term']} -> {result['concept_name']} (점수: {result['mapping_score']:.3f})")
    
    return mapping_results, csv_filename


def test_api_health_check():
    """API 상태 확인 테스트"""
    print("=== API 상태 확인 ===")
    
    api = EntityMappingAPI()
    health = api.health_check()
    
    print(f"API 상태: {health['api_status']}")
    print(f"지원 엔티티 타입: {health['supported_entity_types']}")
    print(f"신뢰도 임계치: {health['confidence_threshold']}")
    
    print()


if __name__ == "__main__":
    print("🔍 심장질환 관련 의료 용어 엔티티 매핑 API 테스트 시작")
    print()
    
    try:
        # API 상태 확인
        test_api_health_check()
        
        # 심장질환 관련 의료 용어 매핑 테스트
        results, csv_file = test_cardiac_medical_terms_mapping()
        
        print(f"\n✅ 테스트 완료! 결과가 {csv_file} 파일에 저장되었습니다.")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()
