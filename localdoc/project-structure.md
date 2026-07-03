# haness-frame 프로젝트 구조 분석

> 분석 일시: 2026-07-01

---

## 1. 개요

**haness-frame**은 로컬 멀티 모델 코딩 하네스 스캐폴드입니다. 여러 로컬 AI 모델에 역할을 분리하여 할당하고, 구조화된 설계 토론 워크플로우를 통해 프로젝트를 진행할 수 있도록 지원합니다.

---

## 2. 디렉토리 구조

```
haness-frame/
├── README.md                    # 프로젝트 개요 및 사용법
├── config/                      # 설정 파일
│   ├── harness.yaml             # 모델 엔드포인트 및 역할 정책
│   ├── roles.yaml               # 역할 정의 (설계 토론용)
│   └── design_loop.yaml         # 구조화된 연구/토론/의사결정 단계
├── data/
│   └── haness.db                # SQLite 설정 데이터베이스
├── docs/                        # 문서
│   ├── architecture.md          # 하네스 설계 및 루프
│   ├── design-discussion-framework.md  # 설계 토론 워크플로우
│   ├── ko-test-project-manual.md       # 한글 테스트 프로젝트 메뉴얼
│   └── prompts.md               # 역할별 프롬프트 컨트랙트
├── lang/                        # 다국어 지원
│   ├── en.json                  # 영어
│   └── ko.json                  # 한국어
├── projects/                    # 생성된 프로젝트 작업공간
│   ├── english-only-test/
│   ├── internal-business-system/
│   ├── internal-business-system-test/
│   ├── sample-project/
│   └── web-zip-test/
├── runs/                        # 실행 기록
│   └── design-20260701-*.md
├── scripts/                     # PowerShell 스크립트
│   ├── check-services.ps1               # 서비스 상태 확인
│   ├── start-vllm-coder-14b.ps1         # Coder vLLM 시작
│   ├── start-vllm-fallback-qwen3-8b.ps1 # Fallback vLLM 시작
│   ├── start-vllm-model.ps1             # 범용 vLLM 시작
│   └── start-vllm-planner-nemotron.ps1  # Planner vLLM 시작
└── src/                         # 소스 코드
    ├── haness_frame.py          # 메인 CLI/웹 애플리케이션
    └── haness_frame_back.py     # 백업/이전 버전
```

---

## 3. 핵심 설계 원칙

### 3.1 역할 분리 (Role Separation)

여러 로컬 모델에 역할을 엄격히 분리하여 할당합니다:

| 역할 | 모델 | 담당 |
|------|------|------|
| **Planner** | NVIDIA-Nemotron-Nano-9B-v2 | 작업 분해, 파일 선택, 로그 요약, 패치 체크리스트 생성 |
| **Coder** | Qwen2.5-Coder-14B-Instruct-AWQ | 집중 패치 생성, 테스트 실패 수정 |
| **Fallback** | Qwen3-8B-AWQ | 가벼운 편집, 도구 호출, 빠른 확인 |
| **Escalation** | Gemini (클라우드) | 로컬 모델 반복 실패 시 에스컬레이션 |

### 3.2 설계 토론 워크플로우

Project Scout → Researcher → Planner → Designer → Architect → Critic → Decision Maker → Coder

각 역할은 인터넷 검색이 가능하며, 검색 결과는 구조화된 증거로 기록됩니다.

### 3.3 언어 지원

- 영어와 한국어 UI 지원
- 프로젝트 생성 시 영어 작업 설명(English working description) 사용
- 원본 요청(original request)은 원본 언어로 별도 파일에 저장

---

## 4. 설정 파일 구조

### 4.1 config/harness.yaml
- **models**: planner, alternate_planner, coder, fallback, escalation 모델 정의
- **policy**: 재시도 횟수, 테스트 요구사항, 패치 정책
- **loop**: 실행 루프 단계 정의

### 4.2 config/roles.yaml
- 9개 역할 정의: project_scout, researcher, planner, designer, architect, critic, debugger, coder, decision_maker
- 각 역할별 must_do / must_not_do 규칙
- 공통 인터넷 검색 정책

### 4.3 config/design_loop.yaml
- 11단계 설계 루프 정의
- 검색 결과 스키마 및 검색 정책
- 단계별 담당 역할 및 출력물 정의

---

## 5. 데이터 저장소

### 5.1 SQLite 데이터베이스 (data/haness.db)
- **ai_services** 테이블: AI 서비스 설정 (이름, 회사, 제공자, URL, 모델, 역할, 활성화 등)
- **app_settings** 테이블: 애플리케이션 설정 (키-값)

### 5.2 프로젝트 파일 시스템 (projects/)
각 프로젝트는 다음 구조를 가집니다:
```
projects/<project-slug>/
├── README.md
├── context/
│   ├── original-request.md
│   ├── business-context.md
│   └── source-materials.md
├── research/
│   └── search-backlog.md
├── docs/
│   ├── 01-project-discovery.md
│   ├── 02-role-discussion.md
│   └── 03-decision-record.md
├── prompts/
│   └── role-briefs.md
└── implementation/
    └── README.md
```

---

## 6. 의존성

- **표준 라이브러리만 사용** (Python stdlib)
- 외부 패키지 의존성 없음
- vLLM/Ollama 서버는 외부 프로세스로 실행