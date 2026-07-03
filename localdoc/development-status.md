# haness-frame 개발 현황 분석

> 분석 일시: 2026-07-02

---

## 1. 전체 구조

haness-frame은 크게 **두 계층**으로 구성되어 있습니다:

| 계층 | 위치 | 설명 |
|------|------|------|
| **하네스 프레임워크** | `src/haness_frame.py` + `src/haness_frame_app/` | 프로젝트 생성, 웹 UI, DB 관리 |
| **생성된 프로젝트** | `projects/<project>/` | 실제 실행 가능한 하네스 엔진 포함 |

---

## 2. 개발 완료된 기능

### 2.1 하네스 프레임워크 (src/)

| 기능 | 파일 | 상태 |
|------|------|------|
| CLI 명령어 12개 | `cli.py` | ✅ 완료 |
| 웹 UI 서버 (포트 8765) | `web.py` | ✅ 완료 |
| SQLite DB 관리 (ai_services, app_settings) | `db.py` | ✅ 완료 |
| AI 서비스 CRUD | `db.py` | ✅ 완료 |
| 다국어 지원 (ko/en) | `i18n.py` | ✅ 완료 |
| 프로젝트 템플릿 생성 (30개 파일) | `project_docs.py` | ✅ 완료 |
| 역할-서비스 자동 매핑 | `db.py` | ✅ 완료 |
| 프로젝트 설정 저장/로드 | `db.py` | ✅ 완료 |
| 경로 관리 및 보안 | `paths.py` | ✅ 완료 |

### 2.2 생성된 프로젝트 내 실행 엔진 (projects/<name>/src/harness_app/)

| 기능 | 파일 | 상태 |
|------|------|------|
| 워크스페이스 초기화 (`init`) | `engine.py` | ✅ 완료 |
| 상태 관리 (`state.json`) | `storage.py` | ✅ 완료 |
| 역할 패킷 생성 (`pack`, `render`) | `engine.py` | ✅ 완료 |
| **AI 모델 호출** (`invoke`) | `client.py` | ✅ 완료 |
| OpenAI-compatible API 호출 | `client.py` | ✅ 완료 |
| Ollama API 호출 | `client.py` | ✅ 완료 |
| Fallback 서비스 자동 전환 | `client.py` | ✅ 완료 |
| API 키 환경변수 처리 | `client.py` | ✅ 완료 |
| 프롬프트 메시지 조립 | `prompting.py` | ✅ 완료 |
| 역할 정의 및 순서 | `roles.py` | ✅ 완료 |
| CLI (init/status/roles/pack/render/invoke) | `cli.py` | ✅ 완료 |
| 서비스 설정 로드 | `services.py` | ✅ 완료 |
| 문서 누락 검사 | `engine.py` | ✅ 완료 |
| 다음 액션 추천 | `engine.py` | ✅ 완료 |

---

## 3. 아직 개발되지 않은 기능

### 3.1 오케스트레이션 (역할 순차 실행)

`config/design_loop.yaml`에 정의된 11단계 설계 루프를 자동으로 실행하는 오케스트레이터가 없습니다.

```yaml
stages:
  - project_discovery    # project_scout
  - intake               # planner
  - research_questions   # all_roles
  - internet_research    # all_roles
  - proposal             # planner
  - experience_design    # designer
  - architecture_review  # architect
  - adversarial_review   # critic
  - debate_round         # planner
  - decision             # decision_maker
  - implementation_brief # coder
```

각 단계의 출력을 다음 단계의 입력으로 자동 전달하는 로직이 없습니다.

### 3.2 외부 검색 연동

- Google 검색 자동 실행 ❌
- 검색 결과 수집 및 구조화 ❌
- 검색 증거 파일 자동 생성 ❌

### 3.3 테스트 체계

- Smoke test ❌
- Role routing test ❌
- Service snapshot test ❌

### 3.4 로그/감사/디버깅

- 실행 로그 저장 ❌
- 역할별 API 호출 기록 ❌
- 응답 시간/성공률 추적 ❌

### 3.5 실패 복구

- 타임아웃 정책 ❌ (client.py에 하드코딩된 60초만 있음)
- 재시도 정책 ❌
- 에러 분류 ❌

### 3.6 운영 UI 고도화

- 프로젝트 상태 대시보드 ❌
- 서비스 설정 변경 UI ❌
- 역할별 서비스 추천 ❌

---

## 4. 생성된 프로젝트의 실행 가능 수준

`projects/internal-business-system/`을 예로 들면:

### 실행 가능한 명령어
```powershell
cd projects/internal-business-system
python app.py init          # 워크스페이스 초기화 ✅
python app.py status        # 상태 보고 ✅
python app.py roles         # 역할 목록 ✅
python app.py pack --role planner  # 역할 패킷 출력 ✅
python app.py render        # 모든 역할 패킷 생성 ✅
python app.py invoke --role planner --prompt "..."  # AI 호출 ✅
```

### AI 호출 예시
```powershell
python app.py invoke --role planner --prompt "Summarize the project state"
```
이 명령은 `workspace/services.json`에서 planner 역할에 매핑된 서비스를 찾아 API를 호출합니다.  
vLLM이나 Ollama가 실행 중이면 실제 응답을 받을 수 있습니다.

### 자동화되지 않은 부분
- 문서를 채우는 것 (`business-context.md` 등) → 사람이 수동 작성
- 역할 순차 실행 → 사람이 수동으로 `invoke` 호출
- 검색 → 사람이 직접 Google 검색
- 코드 생성 → `invoke --role coder`로 호출 가능하지만, 자동 파일 편집은 없음

---

## 5. Phase별 개발 우선순위 (docs/Ko-roadmap.md 기준)

| Phase | 내용 | 상태 |
|-------|------|------|
| **Phase 1: 실행 가능화** | 역할별 AI 호출, 서비스 매핑, fallback | ✅ **완료** |
| **Phase 2: 하네스 흐름** | 역할 순차 실행, 산출물 파일화, decision gate | ❌ 미구현 |
| **Phase 3: 안정성** | timeout, retry, error, scorecard, test | ❌ 미구현 |
| **Phase 4: 검색/토론 통합** | Google 검색, 증거 문서화, 자동 토론 | ❌ 미구현 |
| **Phase 5: 운영성** | 대시보드, 설정 UI, ZIP 백업 | ❌ 미구현 |
| **Phase 6: 확장** | tool call, 멀티 모델, 다국어 확장 | ❌ 미구현 |

---

## 6. 요약

| 구분 | 상태 |
|------|------|
| 프로젝트 템플릿 생성 | ✅ 완료 |
| 웹 UI (생성/관리/설정) | ✅ 완료 |
| AI 서비스 DB 관리 | ✅ 완료 |
| 생성된 프로젝트 내 AI 호출 엔진 | ✅ 완료 (client.py) |
| 역할-서비스 자동 매핑 | ✅ 완료 |
| Fallback 처리 | ✅ 완료 |
| 역할 순차 자동 실행 (오케스트레이션) | ❌ 미구현 |
| 외부 검색 연동 | ❌ 미구현 |
| 테스트/로그/감사 | ❌ 미구현 |
| 운영 UI 고도화 | ❌ 미구현 |

**결론**: Phase 1(실행 가능화)은 완료되었습니다. 생성된 프로젝트를 다른 곳에 복사하면 `python app.py invoke --role planner --prompt "..."` 형태로 AI 모델을 직접 호출할 수 있습니다. 하지만 역할을 순차적으로 자동 실행하거나, 문서를 자동으로 채우거나, 코드를 자동 생성하는 오케스트레이션은 아직 구현되지 않았습니다.