# KG-for-Clinical-Guideline

LangGraph를 활용하여 의료 지침 가이드라인을 지식 그래프로 변환하는 프로젝트입니다.

## 📋 프로젝트 개요

이 프로젝트는 임상 의료 가이드라인 문서를 구조화된 지식 그래프로 변환하여, 의료진이 보다 효율적으로 진료 지침을 검색하고 활용할 수 있도록 돕는 시스템입니다.

### 주요 기능

- 📄 의료 가이드라인 문서 파싱 및 분석
- 🧠 LangGraph를 활용한 4단계 처리 파이프라인
- 🔍 2트랙 검증 시스템을 통한 DP 품질 보장
- 🌐 엔티티 추출 및 OMOP CDM 표준 매핑
- 📊 RDF 트리플 생성 및 지식 그래프 구축
- 💾 Neo4j 그래프 데이터베이스 자동 적재
- 🔎 Elasticsearch 기반 의료 용어 검색

## 🏗️ 아키텍처

```
src/kg_clinical_guideline/
├── data/           # Step 1: 마크다운 변환 워크플로우
├── extraction/     # Step 2: DP 추출 및 프롬프트 관리
├── validation/     # Step 3: 2트랙 검증 시스템
├── graph/          # Step 4: 지식그래프 생성 로직
├── mapping/        # OMOP CDM 매핑 및 Elasticsearch
├── llm/            # LLM 인터페이스 및 팩토리
├── prompt/         # 프롬프트 템플릿 파일들
└── config.py       # 설정 관리
```

### 4단계 처리 파이프라인

1. **Step 1: 마크다운 변환** - 다양한 입력을 표준 마크다운으로 변환
2. **Step 2: DP 추출** - LLM 기반 디지털 표현형 추출
3. **Step 3: 2트랙 검증** - 유사도 + 증거 기반 이중 검증
4. **Step 4: 지식그래프 생성** - 엔티티 추출 → OMOP 매핑 → 트리플 생성 → Neo4j 적재

## 🚀 설치 및 설정

### 1. 의존성 설치

```bash
# Poetry를 사용한 의존성 설치
poetry install

# 개발 의존성 포함 설치
poetry install --with dev
```

### 2. 환경 변수 설정

`.env` 파일을 생성하고 다음 설정을 추가하세요:

```env
# Gemini API 키 (DP 추출 및 검증용)
GEMINI_API_KEY=your_gemini_api_key

# Elasticsearch 설정 (OMOP CDM 매핑용)
ES_SERVER_HOST=localhost
ES_SERVER_PORT=9200
ES_SERVER_USERNAME=elastic
ES_SERVER_PASSWORD=your_password

# Neo4j 데이터베이스 설정 (지식그래프 저장용)
NEO4J_SERVER_URI=bolt://localhost:7687
NEO4J_SERVER_USER=neo4j
NEO4J_SERVER_PASSWORD=your_password
NEO4J_SERVER_DATABASE=neo4j

# AWS S3 설정 (선택사항)
AWS_PROFILE=your_aws_profile
AWS_REGION=ap-northeast-2
AWS_S3_BUCKET=your_bucket_name

# 기타 설정
LOG_LEVEL=INFO
```

### 3. SpaCy 모델 다운로드

```bash
poetry run python -m spacy download en_core_web_sm
poetry run python -m spacy download ko_core_news_sm
```

## 📚 사용법

### CLI를 통한 사용

```bash
# 가이드라인 문서 처리
poetry run kg-clinical process --input data/guidelines.pdf --output output/

# 지식 그래프 시각화
poetry run kg-clinical visualize --graph-id your_graph_id

# 검색 실행
poetry run kg-clinical search --query "고혈압 치료 가이드라인"
```

### Python API 사용

```python
from kg_clinical_guideline.data import DataProcessingWorkflow
from kg_clinical_guideline.extraction import DPExtractor
from kg_clinical_guideline.validation import TwoTrackDPValidator
from kg_clinical_guideline.graph import KnowledgeGraphWorkflow

# Step 1: 마크다운 변환
workflow = DataProcessingWorkflow()
result = workflow.process_sync("의료 가이드라인 텍스트...")

# Step 2: DP 추출
dp_extractor = DPExtractor.create_default()
dp_result = dp_extractor.extract_dps_with_metadata(result['markdown_content'])

# Step 3: 2트랙 검증
validator = TwoTrackDPValidator()
final_dps, validation_results, summary = validator.validate_dps_with_selective_retry(
    dp_result['digital_phenotypes'], 
    result['markdown_content'], 
    dp_extractor
)

# Step 4: 지식그래프 생성
kg_workflow = KnowledgeGraphWorkflow()
kg_result = kg_workflow.process_sync(
    final_dps, 
    result['markdown_content']
)

# 결과 확인
print(f"생성된 엔티티: {len(kg_result['extracted_entities'])}개")
print(f"OMOP 매핑: {len(kg_result['entity_mappings'])}개")  
print(f"RDF 트리플: {len(kg_result['generated_triples'])}개")
```

### Streamlit 데모 실행

```bash
# 웹 기반 데모 실행
poetry run streamlit run examples/streamlit_demo_improved.py
```

## 🧪 테스트

```bash
# 전체 테스트 실행
poetry run pytest

# 커버리지 포함 테스트
poetry run pytest --cov=src/kg_clinical_guideline

# 특정 모듈 테스트
poetry run pytest tests/test_core/
```

## 📊 프로젝트 구조

```
KG-for-Clinical-Guideline/
├── src/
│   └── kg_clinical_guideline/
│       ├── data/              # 데이터 처리 워크플로우
│       ├── extraction/        # DP 추출 및 프롬프트 관리
│       ├── validation/        # 2트랙 검증 시스템
│       ├── graph/             # 지식그래프 생성
│       ├── mapping/           # OMOP CDM 매핑
│       ├── llm/               # LLM 인터페이스
│       └── prompt/            # 프롬프트 템플릿
├── examples/                  # 사용 예제 및 데모
├── tests/                     # 테스트 코드
├── data/                      # 샘플 데이터
├── output/                    # 출력 결과
└── docs/                      # 문서
```

## 🔧 기술 스택

- **LangGraph**: 워크플로우 오케스트레이션
- **Google Gemini**: LLM 기반 텍스트 처리
- **Neo4j**: 그래프 데이터베이스
- **Elasticsearch**: 검색 엔진
- **spaCy**: 자연어 처리
- **Streamlit**: 웹 인터페이스
- **Poetry**: 의존성 관리

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 🙏 감사의 말

- [LangGraph](https://github.com/langchain-ai/langgraph) - 워크플로우 오케스트레이션
- [Neo4j](https://neo4j.com/) - 그래프 데이터베이스
- [spaCy](https://spacy.io/) - 자연어 처리
- [Google Gemini](https://ai.google.dev/) - 대규모 언어 모델