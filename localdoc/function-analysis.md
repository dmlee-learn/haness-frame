# haness-frame 기능 분석

> 분석 일시: 2026-07-01

---

## 1. 개요

**haness-frame**은 순수 Python 표준 라이브러리만으로 구현된 CLI/웹 애플리케이션입니다. 주요 기능은 크게 CLI 명령어, 웹 서버, 데이터베이스 관리, 프로젝트 생성, AI 서비스 관리, 템플릿 생성, 다국어 지원으로 나뉩니다.

---

## 2. 주요 기능 모듈

### 2.1 CLI 명령어 기능

argparse를 기반으로 9개의 서브커맨드를 지원합니다.

| 명령어 | 함수 | 설명 |
|--------|------|------|
| `check` | `cmd_check` | 로컬 모델 엔드포인트(vLLM, Ollama) 연결 상태 확인 |
| `show-config` | `cmd_show_config` | harness.yaml 설정 파일 출력 |
| `roles` | `cmd_roles` | roles.yaml 역할 정의 출력 |
| `design-loop` | `cmd_design_loop` | design_loop.yaml 설계 루프 설정 출력 |
| `prompts` | `cmd_planner_contract` | docs/prompts.md 프롬프트 컨트랙트 출력 |
| `ollama-tags` | `cmd_ollama_tags` | Ollama에 설치된 모델 목록 출력 |
| `init-db` | `cmd_init_db` | SQLite 데이터베이스 초기화 |
| `services` | `cmd_services` | 등록된 AI 서비스 목록 출력 |
| `create-project` | `cmd_create_project` | 프로젝트 하네스 워크스페이스 생성 |
| `serve` | `cmd_serve` | 로컬 웹 서버 시작 (포트 8765) |
| `design-template` | `cmd_design_template` | 설계 토론 템플릿 생성/출력 |
| `discuss` | `cmd_discuss` | 역할 토론 스켈레톤 생성/출력 |

### 2.2 웹 서버 기능 (ProjectServer)

`http.server`를 기반으로 한 로컬 웹 서버를 제공합니다. 포트 8765에서 실행됩니다.

#### 주요 엔드포인트

| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/` | GET/POST | 프로젝트 생성 폼 및 처리 |
| `/projects` | GET | 프로젝트 목록 조회 |
| `/project?name=` | GET | 특정 프로젝트 상세 정보 |
| `/download?name=` | GET | 프로젝트 ZIP 파일 다운로드 |
| `/settings` | GET/POST | AI 서비스 설정 관리 (CRUD) |
| `/preferences` | GET/POST | 언어 설정 관리 |

#### 웹 서버 특징
- **UTF-8** 인코딩 지원 (한글 등 비ASCII 문자 처리)
- 쿠키 기반 사용자 언어 설정
- SQLite 기반 서버 기본 언어 설정
- HTML/CSS 내장 (별도 템플릿 엔진 없음)

### 2.3 데이터베이스 관리 기능

SQLite를 사용하여 설정 데이터를 저장합니다.

#### 테이블 구조

**ai_services 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 ID |
| name | TEXT UNIQUE | 서비스 이름 |
| company | TEXT | 회사명 (openai, anthropic, local 등) |
| provider_type | TEXT | 제공자 유형 (openai_compatible, vllm, ollama, codex, anthropic 등) |
| base_url | TEXT | API 엔드포인트 URL |
| model | TEXT | 모델명 |
| role | TEXT | 주 역할 |
| roles | TEXT | 담당 역할 목록 (쉼표 구분) |
| enabled | INTEGER | 활성화 여부 (0/1) |
| api_key_env | TEXT | API 키 환경변수명 |
| notes | TEXT | 메모 |
| created_at/updated_at | TEXT | 생성/수정 시간 |

**app_settings 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| key | TEXT PK | 설정 키 |
| value | TEXT | 설정 값 |
| updated_at | TEXT | 수정 시간 |

#### 주요 함수
- `init_db()`: 데이터베이스 및 테이블 초기화
- `db_connect()`: SQLite 연결 (row_factory=sqlite3.Row)
- `ensure_column()`: 컬럼 존재 확인 및 추가 (마이그레이션)
- `get_setting()` / `set_setting()`: 설정 값 조회/저장

### 2.4 AI 서비스 관리 기능

AI 서비스에 대한 완전한 CRUD(Create, Read, Update, Delete)를 지원합니다.

#### 기본 제공 서비스 (DEFAULT_AI_SERVICES)

| 서비스명 | 제공자 | 모델 | 역할 |
|----------|--------|------|------|
| local-vllm | local | Qwen3-8B-AWQ | fallback |
| local-vllm-coder | local | Qwen2.5-Coder-14B-Instruct-AWQ | coder |
| ollama | local (Ollama) | qwen3.5:35b | planner,reviewer |
| codex | openai | codex | escalation,coder,reviewer |
| claude | anthropic | claude-sonnet | escalation,planner,reviewer |

#### 지원 역할 옵션 (DEFAULT_ROLE_OPTIONS)
```
project_scout, context_curator, researcher, planner, designer, architect,
critic, debugger, decision_maker, coder, reviewer, escalation
```

#### 주요 함수
- `list_ai_services()`: 전체 서비스 목록 조회
- `get_ai_service(name)`: 특정 서비스 조회
- `upsert_ai_service(data)`: 서비스 등록/수정
- `delete_ai_service(name)`: 서비스 삭제

### 2.5 프로젝트 생성 기능

**create_project_files()** 함수가 프로젝트 워크스페이스를 생성합니다.

#### 생성되는 파일 구조
```
projects/<project-slug>/
├── README.md                          # 프로젝트 개요 및 워크플로우
├── context/
│   ├── original-request.md            # 원본 요청 (원본 언어)
│   ├── business-context.md            # 비즈니스 컨텍스트 템플릿
│   └── source-materials.md            # 소스 자료 목록
├── research/
│   └── search-backlog.md              # 검색 백로그 템플릿
├── docs/
│   ├── 01-project-discovery.md        # 프로젝트 발견 보고서 템플릿
│   ├── 02-role-discussion.md          # 역할 토론 문서 템플릿
│   └── 03-decision-record.md          # 의사결정 기록 템플릿
├── prompts/
│   └── role-briefs.md                 # 역할별 브리프
└── implementation/
    └── README.md                      # 구현 노트 템플릿
```

#### 주요 함수
- `build_project_readme()`: 프로젝트 README 생성
- `build_original_request()`: 원본 요청 파일 생성
- `build_business_context()`: 비즈니스 컨텍스트 템플릿 생성
- `build_search_backlog()`: 검색 백로그 템플릿 생성
- `build_discovery_doc()`: 발견 보고서 템플릿 생성
- `build_role_discussion_doc()`: 역할 토론 템플릿 생성
- `build_decision_record()`: 의사결정 기록 템플릿 생성
- `build_role_briefs()`: 역할 브리프 생성
- `build_implementation_readme()`: 구현 노트 생성

#### 유틸리티 함수
- `project_dir()`: 프로젝트 디렉토리 경로 반환
- `slugify()`: 문자열을 URL 친화적 slug로 변환 (최대 48자)
- `write_project_file()`: 파일 쓰기 (덮어쓰기 제어)
- `list_projects()`: 전체 프로젝트 목록 조회
- `project_file_rows()`: 프로젝트 파일 목록 조회
- `project_zip_bytes()`: 프로젝트 ZIP 아카이브 생성
- `safe_project_path()`: 안전한 프로젝트 경로 검증 (Path traversal 방지)

### 2.6 템플릿 생성 기능

#### 설계 토론 템플릿 (design-template)
10단계의 구조화된 설계 토론 템플릿을 제공합니다:
1. Project Discovery - Project Scout
2. Intake - Planner
3. Research Questions - Researcher
4. Internet Evidence - Researcher
5. Proposal - Planner
6. Experience Design - Designer
7. Architecture Review - Architect
8. Adversarial Review - Critic
9. Debate Round
10. Decision - Decision Maker

#### 역할 토론 스켈레톤 (discuss)
8개 역할별 토론 섹션을 포함한 간결한 템플릿:
- Project Scout, Researcher, Planner, Designer, Architect, Critic, Decision Maker

### 2.7 다국어 지원 기능

영어(en)와 한국어(ko)를 지원합니다.

#### 주요 함수
- `load_language(code)`: 언어 파일 로드 (fallback: 영어)
- `tr(lang, key)`: 번역된 문자열 조회
- `normalize_language(code)`: 지원 언어 확인 및 정규화
- `language_options(selected)`: HTML select 옵션 생성

#### 언어 설정 방식
- **사용자 언어**: 브라우저 쿠키(haness_lang)에 저장
- **서버 기본 언어**: SQLite app_settings 테이블에 저장

### 2.8 설정/환경설정 기능

#### Preferences 웹 페이지
- 사용자 UI 언어 설정 (쿠키 저장)
- 서버 기본 언어 설정 (SQLite 저장)

#### Settings 웹 페이지
- AI 서비스 추가/수정/삭제
- 제공자 유형 선택 (openai_compatible, vllm, ollama, codex, anthropic, openai, gemini, other)
- 역할 체크박스 선택
- 활성화/비활성화 토글

---

## 3. 핵심 데이터 흐름

### 3.1 프로젝트 생성 흐름
```
사용자 입력 (웹 폼 또는 CLI)
    → task_text() 로 작업 텍스트 추출
    → create_project_files() 로 파일 생성
        → build_*() 템플릿 함수들 호출
        → write_project_file() 로 파일 저장
    → 프로젝트 경로 및 생성 결과 출력
```

### 3.2 AI 서비스 관리 흐름
```
웹 폼 입력 (settings 페이지)
    → POST /settings
        → action=save: upsert_ai_service()
        → action=delete: delete_ai_service()
    → 설정 페이지 리다이렉트
```

### 3.3 웹 서버 요청 처리 흐름
```
HTTP 요청
    → do_GET() 또는 do_POST()
    → 쿠키에서 언어 설정 추출 (current_language())
    → 경로별 라우팅
    → HTML 응답 생성 (send_html())
```

---

## 4. 보안 관련 구현

### 4.1 경로 탐색 방지 (Path Traversal)
- `safe_project_path()` 함수에서 slugify 후 경로 검증
- 프로젝트 루트 디렉토리 내에 있는지 `relative_to()`로 확인

### 4.2 XSS 방지
- `html.escape()`를 사용한 HTML 출력 이스케이프
- URL 인코딩 (`urllib.parse.quote`)

### 4.3 API 키 보안
- API 키를 데이터베이스에 직접 저장하지 않고 환경변수 이름만 저장
- 실제 키는 시스템 환경변수에서 참조

---

## 5. 확장 포인트

1. **언어 추가**: `lang/` 디렉토리에 새 JSON 파일 추가 및 `SUPPORTED_LANGUAGES` 업데이트
2. **역할 추가**: `DEFAULT_ROLE_OPTIONS` 및 `roles.yaml` 업데이트
3. **AI 서비스 추가**: 웹 UI를 통해 동적으로 추가 가능
4. **프로젝트 템플릿 커스터마이즈**: `build_*()` 함수 수정
5. **제공자 유형 추가**: `provider_options()` 함수 및 관련 처리 로직 확장