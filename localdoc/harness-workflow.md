# haness-frame 하네스 적용 워크플로우

> 분석 일시: 2026-07-01

---

## 1. 개요

`create-project` 명령으로 프로젝트 템플릿을 생성한 후, 역할 기반 설계 토론 워크플로우를 통해 프로젝트를 진행합니다. 이 문서는 프로젝트 생성 후 하네스를 적용하는 전체 과정을 설명합니다.

---

## 2. 전체 워크플로우 다이어그램

```
[1] 프로젝트 생성 (create-project)
         ↓
[2] 비즈니스 컨텍스트 작성 (business-context.md)
         ↓
[3] Project Scout: 선검색 수행 (search-backlog.md → 01-project-discovery.md)
         ↓
[4] Planner: 목표/제약/대안 정리 (02-role-discussion.md)
         ↓
[5] Designer: 사용자 경험 설계 (02-role-discussion.md)
         ↓
[6] Architect: 시스템 구조 검토 (02-role-discussion.md)
         ↓
[7] Critic: 위험 요소 검토 (02-role-discussion.md)
         ↓
[8] Decision Maker: 최종 결정 (03-decision-record.md)
         ↓
[9] Coder: 구현 브리프 기반 코딩
```

---

## 3. 단계별 상세 설명

### 3.1 프로젝트 생성 (create-project)

**CLI로 생성:**
```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" --english-description "Build an internal business system for approvals" "사내업무시스템을 만들고 싶어요"
```

**웹 UI로 생성:**
```powershell
python .\src\haness_frame.py serve
# http://127.0.0.1:8765/ 열기
```

**생성 결과물:**
```
projects/internal-business-system/
├── README.md                          ← 시작 가이드 (여기서부터 읽기)
├── context/
│   ├── original-request.md            ← 원본 요청 (원본 언어 보존)
│   ├── business-context.md            ← 비즈니스 맥락 템플릿
│   └── source-materials.md            ← 참고 자료 목록
├── research/
│   └── search-backlog.md              ← 검색 백로그 템플릿
├── docs/
│   ├── 01-project-discovery.md        ← 프로젝트 발견 보고서
│   ├── 02-role-discussion.md          ← 역할 토론 문서
│   └── 03-decision-record.md          ← 의사결정 기록
├── prompts/
│   └── role-briefs.md                 ← 역할별 브리프
└── implementation/
    └── README.md                      ← 구현 노트
```

### 3.2 비즈니스 컨텍스트 작성

`context/business-context.md` 파일을 열어 다음 항목을 채웁니다.

| 항목 | 예시 |
|------|------|
| **Business Goal** | 사내 업무 요청, 결재, 문서, 보고를 한 곳에서 관리 |
| **Users** | 임직원, 팀장, 관리자, 경영진 |
| **Current Workflow** | 현재는 메신저, 엑셀, 이메일, 구두 보고가 섞여 있음 |
| **Pain Points** | 요청 누락, 결재 지연, 문서 버전 혼란, 보고 자료 재작성 |
| **Required Capabilities** | 전자결재, 업무 요청, 담당자 지정, 상태 추적, 문서 첨부, 보고서 |
| **Excluded Scope** | 급여, 회계, 인사평가 같은 ERP 전체 기능 |
| **Constraints** | 예산, 일정, 보안, 규정, 기존 시스템 |

### 3.3 Project Scout: 선검색 수행

`research/search-backlog.md`에 자동 생성된 검색어를 Google에서 검색합니다.

**기본 검색어:**
```
internal-business-system existing projects
internal-business-system open source github
internal-business-system alternatives
internal-business-system architecture
internal-business-system common problems
internal-business-system workflow examples
internal-business-system database schema examples
internal-business-system security considerations
```

**검색 결과 기록 형식:**
```text
query: internal-business-system open source github
provider: google
url: https://github.com/example/project
title: Example Internal Business System
excerpt: Open source business management system with approval workflows
retrieved_at: 2026-07-01
confidence: medium
why_it_matters: Reference architecture for approval routing
recommended_use: Study the approval workflow design
```

**발견 결과 → `docs/01-project-discovery.md`에 정리:**
```text
Related Projects:      유사 시스템, 그룹웨어, 전자결재 제품
Existing Products:     Google Workspace, MS 365, Notion, Jira 등
Open Source References: 참고 가능한 오픈소스 시스템
Reusable Ideas:        요청함, 승인 단계, 상태 추적, 권한 관리, 알림
Risks To Avoid:        권한 설계 실패, 결재 흐름 과복잡화
```

### 3.4 Planner: 문제 정의

`docs/02-role-discussion.md`의 Planner 섹션을 채웁니다.

```text
Goals:
- 전자결재 처리 (기안, 승인, 반려, 회수)
- 업무 요청 및 담당자 지정
- 문서 첨부 및 버전 관리
- 보고서 생성

Non-goals:
- 급여/회계 처리
- 인사 평가
- 실시간 채팅

Constraints:
- 웹 기반
- 모바일 대응
- 기존 SSO 연동 필요
- 3개월 내 MVP 출시
```

### 3.5 Designer: 사용자 경험 설계

```text
User workflow:
1. 사용자가 요청서 작성 → 담당자 지정
2. 담당자가 접수 → 처리 → 완료
3. 결재선 따라 승인 진행
4. 보고서 자동 생성

Information structure:
- 대시보드 (내 요청, 내 할 일, 알림)
- 요청 상세 (정보, 첨부파일, 결재 현황)
- 관리자 화면 (결재선 설정, 권한 관리)

UX risks:
- 결재선 설정이 너무 복잡하면 사용자가 포기
- 알림이 너무 많으면 무시됨
```

### 3.6 Architect: 시스템 구조 검토

```text
System boundaries:
- Frontend: React or Vue.js (SPA)
- Backend: REST API
- Database: PostgreSQL
- Auth: SSO + JWT

Data model:
- User, Department, ApprovalLine
- Request, ApprovalStep, Attachment
- Report

Integration risks:
- SSO 연동 실패 시 전체 로그인 마비
- 결재선 순서 변경 시 데이터 일관성 문제
```

### 3.7 Critic: 위험 요소 검토

```text
Blocking risks:
- 결재선 병렬/직렬 처리 로직이 복잡하여 오류 가능성 높음
- 문서 버전 충돌 시 데이터 손실 위험

Weak assumptions:
- "사용자가 결재선을 직접 설정할 수 있다"는 가정이 UX 복잡도를 높임
- 모바일 대응을 MVP에서 하기엔 범위가 큼

Required tests:
- 결재선 5단계 이상에서의 성능 테스트
- 동시 접속 100명 부하 테스트
- 첨부파일 100MB 업로드 테스트
```

### 3.8 Decision Maker: 최종 결정

`docs/03-decision-record.md`에 최종 결정을 기록합니다.

```text
Accepted Decision:
- 우선 웹 기반 (모바일은 MVP 후)
- Vue.js + FastAPI + PostgreSQL
- 결재선은 직렬 3단계로 제한 (MVP)

Rejected Options:
- React: 팀에 Vue 경험자가 더 많아서 제외
- 모바일 우선: 범위가 너무 커져서 제외
- 실시간 알림: WebSocket 도입은 MVP 후로 연기

Implementation Brief For Coder:
1. 사용자 인증 (SSO 연동)
2. 요청 CRUD API
3. 결재선 처리 엔진
4. 기본 UI (대시보드, 요청 폼, 결재 화면)

Verification Commands:
- pytest 로 API 테스트
- cypress 로 E2E 테스트
- k6 로 부하 테스트

Rollback Plan:
- 결재선 기능은 feature flag 로 제어
- DB 마이그레이션은 버전 관리
```

### 3.9 Coder: 구현

Decision Maker의 구현 브리프(Implementation Brief)가 준비된 후에만 Coder가 구현을 시작합니다.

**Coder 원칙:**
- 설계 중에 새로운 기능을 발명하지 않음
- 결정된 범위 내에서만 패치 생성
- 기존 코드를 보존하고 변경 범위를 최소화

---

## 4. 실제 모델 적용 시나리오 (확장 계획)

현재 하네스는 템플릿 생성까지만 지원하며, 자동 모델 호출은 아직 구현되지 않았습니다.
향후 확장 계획:

```
[현재]  사용자 → 수동으로 각 문서 작성 → Coder가 수동 구현
[목표]  사용자 → 하네스가 각 역할별 모델 호출 → 검증 → 자동 구현
```

- `config/harness.yaml`의 loop 섹션에 정의된 자동 루프
- `config/roles.yaml`의 각 역할 정의를 모델에 전달
- `config/design_loop.yaml`의 11단계를 순차 실행

---

## 5. 핵심 규칙

| 규칙 | 설명 |
|------|------|
| **원본 요청 보존** | 사용자의 원본 요청은 `context/original-request.md`에 원본 언어로 저장 |
| **영어 작업 설명** | 모든 생성 파일은 영어 작업 설명(English working description) 사용 |
| **결정 후 구현** | `03-decision-record.md`가 채워진 후에만 Coder가 구현 시작 |
| **역할 분리** | Planner는 설계만, Coder는 구현만 담당 |
| **증거 기반** | 모든 검색 결과는 구조화된 형식으로 기록 |
| **작은 패치** | Coder는 작은 범위의 패치를 생성 (전체 파일 재작성 금지) |

---

## 6. 프로젝트 ZIP 다운로드

웹 UI를 통해 생성된 프로젝트를 ZIP 파일로 다운로드할 수 있습니다.

```text
http://127.0.0.1:8765/download?name=internal-business-system
```

ZIP 파일은 프로젝트 폴더 전체를 압축하여 제공합니다.